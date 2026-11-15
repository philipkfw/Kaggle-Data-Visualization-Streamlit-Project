"""Export the dbt Gold tables from Snowflake to a Parquet snapshot in data/snapshot/.

The snapshot lets the dashboard run with no Snowflake account (DuckDB backend). It
holds every Gold table plus the two Bronze columns sets the validation script uses
to re-check the timezone conversion.

Each table is verified after writing: row count and, for every numeric/date column,
SUM / MIN / MAX computed in Snowflake are compared with the same aggregates computed
by DuckDB over the written Parquet file. The snapshot only replaces the previous
one if every table verifies.

Usage (needs working [snowflake] secrets):
    .venv/bin/python scripts/export_snapshot.py
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.getLogger("streamlit").setLevel(logging.ERROR)

import duckdb  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.config import SNAPSHOT_DIR  # noqa: E402
from dashboard.data.connection import get_snowflake_connection  # noqa: E402
from dashboard.utils.date_utils import mountain_now  # noqa: E402

GOLD_TABLES = (
    "MART_FINANCIAL_PERFORMANCE", "MART_ACCOUNT_LIFECYCLE", "MART_ACCOUNT_PERFORMANCE",
    "DIM_ACCOUNTS", "DIM_DATE", "DIM_FX_RATES",
    "FCT_PAYMENT_TRANSACTIONS", "FCT_INVOICES", "FCT_ACCOUNT_LIFECYCLE", "FCT_ACCOUNT_DAILY_STATUS",
)
# Bronze: only what scripts/validate_metrics.py needs for the timezone re-check.
BRONZE_TABLES = {
    "PAYMENT_TRANSACTIONS": "TRANSACTION_ID, TRANSACTION_TIME",
    "INVOICES": "INVOICE_ID, INVOICE_CREATED_TIME",
}
_CHECK_TYPES = ("NUMBER", "DECIMAL", "INT", "FLOAT", "DOUBLE", "DATE", "TIMESTAMP")


def _equal(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float, Decimal)) and isinstance(b, (int, float, Decimal)):
        return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-6)
    return str(a)[:19] == str(b)[:19]  # dates/timestamps: compare to the second


def export_table(cursor, database: str, schema: str, table: str, columns: str, out_dir: Path
                 ) -> dict:
    fqn = f"{database}.{schema}.{table}"
    cursor.execute(f"SELECT {columns} FROM {fqn}")
    arrow = cursor.fetch_arrow_all(force_return_table=True)
    file_name = f"{schema.lower()}__{table.lower()}.parquet"
    pq.write_table(arrow, out_dir / file_name, compression="zstd")

    # Verify: Snowflake aggregates vs DuckDB aggregates over the written file.
    cursor.execute(f"DESCRIBE TABLE {fqn}")
    sf_types = {row[0]: row[1] for row in cursor.fetchall()}
    checked = [c for c in arrow.column_names
               if any(t in sf_types.get(c, "") for t in _CHECK_TYPES)]
    aggregates = ["COUNT(*)"]
    for column in checked:
        numeric = not any(t in sf_types[column] for t in ("DATE", "TIMESTAMP"))
        aggregates += [f"MIN({column})", f"MAX({column})"]
        if numeric:
            aggregates.append(f"SUM({column})")
    select = ", ".join(aggregates)
    expected = cursor.execute(f"SELECT {select} FROM {fqn}").fetchone()
    path = (out_dir / file_name).as_posix().replace("'", "''")
    actual = duckdb.sql(f"SELECT {select} FROM read_parquet('{path}')").fetchone()
    mismatches = [agg for agg, e, a in zip(aggregates, expected, actual) if not _equal(e, a)]
    if mismatches:
        raise ValueError(f"{fqn}: snapshot differs from Snowflake on {mismatches}")
    print(f"  {schema}.{table}: {arrow.num_rows:,} rows · {len(aggregates)} checksums verified")
    return {"schema": schema, "name": table, "file": file_name, "rows": arrow.num_rows,
            "columns": arrow.num_columns, "checksums_verified": len(aggregates)}


def main() -> int:
    settings = st.secrets["snowflake"]
    database = settings.get("database", "KAGGLE_DB").upper()
    gold = settings.get("schema", "GOLD").upper()
    cursor = get_snowflake_connection().cursor()
    SNAPSHOT_DIR.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="snapshot_", dir=SNAPSHOT_DIR.parent))
    try:
        print(f"Exporting {database}.{gold} (+ BRONZE timestamps) to {SNAPSHOT_DIR}")
        tables = [export_table(cursor, database, gold, t, "*", staging) for t in GOLD_TABLES]
        tables += [export_table(cursor, database, "BRONZE", t, cols, staging)
                   for t, cols in BRONZE_TABLES.items()]
        manifest = {
            "description": "Parquet snapshot of the dbt Gold tables for the DuckDB backend.",
            "database": database,
            "gold_schema": gold,
            "exported_at_mt": mountain_now().isoformat(timespec="seconds"),
            "tables": tables,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if SNAPSHOT_DIR.exists():
            shutil.rmtree(SNAPSHOT_DIR)
        staging.rename(SNAPSHOT_DIR)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    size = sum(f.stat().st_size for f in SNAPSHOT_DIR.iterdir()) / 1024
    print(f"Done: {len(tables)} tables, {size:,.0f} KB. Previous snapshot replaced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
