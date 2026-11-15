"""Query execution against the configured backend.

* duckdb (default): an in-process DuckDB database whose KAGGLE_DB.GOLD / BRONZE views
  point at the Parquet snapshot in data/snapshot/. No server, no credentials.
* snowflake: live Gold tables. Credentials come from Streamlit secrets - never code -
  using key-pair authentication, matching the dbt project's profile.

Both backends receive the same SQL (portable ANSI + COUNT_IF) and return identical
Python types (datetime.date, Decimal -> numeric), so nothing upstream changes.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pandas as pd
import streamlit as st

from dashboard.config import (REPORTING_TIMEZONE, SNAPSHOT_DIR, _secrets_section, data_backend,
                              snapshot_manifest)

_PYFORMAT_PARAM = re.compile(r"%\((\w+)\)s")


# --- Snowflake ---------------------------------------------------------------------------

def _load_private_key(settings) -> bytes:
    """Return the private key as DER bytes, from inline PEM or a file path."""
    from cryptography.hazmat.primitives import serialization

    passphrase = settings.get("private_key_passphrase") or None
    if settings.get("private_key"):
        pem = settings["private_key"].encode()
    elif settings.get("private_key_file"):
        with open(settings["private_key_file"], "rb") as key_file:
            pem = key_file.read()
    else:
        raise KeyError("Set `private_key` or `private_key_file` under [snowflake] in secrets.")
    key = serialization.load_pem_private_key(
        pem, password=passphrase.encode() if passphrase else None
    )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@st.cache_resource(show_spinner=False)
def get_snowflake_connection():
    """One shared Snowflake connection per app process."""
    import snowflake.connector

    settings = _secrets_section("snowflake")
    if not settings:
        raise KeyError("data_backend is 'snowflake' but [snowflake] is missing from secrets.")
    return snowflake.connector.connect(
        account=settings["account"],
        user=settings["user"],
        private_key=_load_private_key(settings),
        role=settings.get("role"),
        warehouse=settings.get("warehouse"),
        database=settings.get("database"),
        schema=settings.get("schema"),
        client_session_keep_alive=True,
        session_parameters={
            # Gold dates are already Mountain Time; this keeps any session-level
            # date functions consistent with the reporting timezone.
            "TIMEZONE": REPORTING_TIMEZONE,
            "QUERY_TAG": "streamlit_analytics_dashboard",
        },
    )


def _execute_snowflake(sql: str, params: dict) -> tuple[list, list]:
    from snowflake.connector.errors import DatabaseError

    for attempt in range(2):  # Reconnect once if the cached session has expired.
        try:
            with get_snowflake_connection().cursor() as cursor:
                cursor.execute(sql, params)
                return [col[0] for col in cursor.description], cursor.fetchall()
        except DatabaseError:
            if attempt:
                raise
            get_snowflake_connection.clear()
    raise RuntimeError("unreachable")


# --- DuckDB snapshot -----------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_duckdb_connection():
    """In-memory DuckDB exposing the snapshot under the original Snowflake names."""
    import duckdb

    manifest = snapshot_manifest()
    if not manifest.get("tables"):
        raise FileNotFoundError(
            f"No snapshot found in {SNAPSHOT_DIR}. Run scripts/export_snapshot.py while "
            "Snowflake is available, or set data_backend = 'snowflake'."
        )
    connection = duckdb.connect(database=":memory:")
    connection.execute(f"SET TimeZone = '{REPORTING_TIMEZONE}'")
    database = manifest["database"]
    connection.execute(f"ATTACH ':memory:' AS {database}")
    for schema in {t["schema"] for t in manifest["tables"]}:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {database}.{schema}")
    for table in manifest["tables"]:
        path = (SNAPSHOT_DIR / table["file"]).as_posix().replace("'", "''")
        connection.execute(
            f"CREATE VIEW {database}.{table['schema']}.{table['name']} AS "
            f"SELECT * FROM read_parquet('{path}')"
        )
    return connection


def to_duckdb_sql(sql: str) -> str:
    """Translate %(name)s bind placeholders (Snowflake pyformat) to DuckDB's $name."""
    return _PYFORMAT_PARAM.sub(r"$\1", sql)


def _execute_duckdb(sql: str, params: dict) -> tuple[list, list]:
    # A cursor is a separate handle onto the same database: safe across Streamlit threads.
    cursor = get_duckdb_connection().cursor()
    try:
        used = set(_PYFORMAT_PARAM.findall(sql))
        cursor.execute(to_duckdb_sql(sql), {k: v for k, v in params.items() if k in used})
        return [col[0] for col in cursor.description], cursor.fetchall()
    finally:
        cursor.close()


# --- Public API --------------------------------------------------------------------------------

def execute(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a read-only query; return a DataFrame with lower-case column names."""
    runner = _execute_duckdb if data_backend() == "duckdb" else _execute_snowflake
    columns, rows = runner(sql, params or {})
    frame = pd.DataFrame(rows, columns=[c.lower() for c in columns])
    # NUMBER/DECIMAL columns arrive as Decimal; convert for pandas & Plotly.
    for column in frame.columns:
        sample = frame[column].dropna()
        if not sample.empty and isinstance(sample.iloc[0], Decimal):
            frame[column] = pd.to_numeric(frame[column])
    return frame


def clear_connections() -> None:
    get_snowflake_connection.clear()
    get_duckdb_connection.clear()
