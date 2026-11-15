"""Application-level settings.

Business rules (metric definitions, timezone conversion, FX conversion) live in the
dbt project. This module only holds what the *application* needs to know: where the
Gold models are and how to present them.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import streamlit as st

APP_TITLE = "Field Service Analytics"
REPORTING_TIMEZONE = "America/Denver"  # Matches dbt var `reporting_timezone`.
REPORTING_TIMEZONE_LABEL = "Mountain Time"
CURRENCY = "USD"

# Ranked bar charts show at most this many categories; the full list is in tables.
TOP_N_CATEGORIES = 12

QUERY_CACHE_TTL_SECONDS = 6 * 60 * 60  # Gold data is a static snapshot.

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def _identifier(value: str, name: str) -> str:
    """Validate a Snowflake identifier read from secrets (never user input)."""
    if not _IDENTIFIER.match(value):
        raise ValueError(f"Invalid Snowflake identifier for {name!r}: {value!r}")
    return value.upper()


# --- Data backend ------------------------------------------------------------------------
# "duckdb"    (default) - local Parquet snapshot of the Gold tables in data/snapshot/.
#                         Needs no credentials, so the dashboard keeps working forever.
# "snowflake"           - live queries against the Gold schema (credentials in secrets).
# Choose with env var DASHBOARD_DATA_BACKEND or [app] data_backend in secrets.toml.
BACKENDS = ("duckdb", "snowflake")
SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "data" / "snapshot"
SNAPSHOT_MANIFEST = SNAPSHOT_DIR / "manifest.json"


def _secrets_section(name: str) -> dict:
    """A secrets section, or {} when there is no secrets file (e.g. snapshot-only deploys)."""
    try:
        return dict(st.secrets.get(name, {}))
    except Exception:  # noqa: BLE001 - Streamlit raises when no secrets file exists.
        return {}


def data_backend() -> str:
    backend = (os.environ.get("DASHBOARD_DATA_BACKEND")
               or _secrets_section("app").get("data_backend")
               or "duckdb").lower()
    if backend not in BACKENDS:
        raise ValueError(f"data_backend must be one of {BACKENDS}, got {backend!r}")
    return backend


def snapshot_manifest() -> dict:
    """Export metadata written by scripts/export_snapshot.py ({} if missing)."""
    try:
        return json.loads(SNAPSHOT_MANIFEST.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def gold_schema_fqn() -> str:
    """Fully-qualified Gold schema, e.g. KAGGLE_DB.GOLD.

    The DuckDB backend recreates the same database/schema names over the snapshot,
    so every query is identical on both backends.
    """
    if data_backend() == "duckdb":
        manifest = snapshot_manifest()
        database = manifest.get("database", "KAGGLE_DB")
        schema = manifest.get("gold_schema", "GOLD")
    else:
        settings = _secrets_section("snowflake")
        database = settings.get("database", "KAGGLE_DB")
        schema = settings.get("schema", "GOLD")
    return f"{_identifier(database, 'database')}.{_identifier(schema, 'schema')}"


def data_source_label() -> str:
    if data_backend() == "duckdb":
        exported = snapshot_manifest().get("exported_at_mt", "")[:10]
        return ("Snapshot of the dbt Gold tables"
                + (f" exported from Snowflake on {exported}" if exported else ""))
    return "Live dbt Gold tables in Snowflake"
