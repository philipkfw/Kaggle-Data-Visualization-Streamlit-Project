"""Validate dashboard numbers against independent SQL on the Gold fact tables.

Runs the exact repository functions the app uses (mart-based) and compares them with
queries written independently against fct_payment_transactions, fct_invoices,
fct_account_daily_status and dim_accounts - plus internal consistency checks
(trend buckets, segments and detail rows must all sum to the KPI totals) and a
timezone check against the raw Bronze timestamps.

Usage (from the repo root):
    .venv/bin/python scripts/validate_metrics.py                                # snapshot (default)
    DASHBOARD_DATA_BACKEND=snowflake .venv/bin/python scripts/validate_metrics.py   # live
Exit code 1 if any check fails.
"""

from __future__ import annotations

import logging
import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.getLogger("streamlit").setLevel(logging.ERROR)

from dashboard.config import data_backend, gold_schema_fqn  # noqa: E402
from dashboard.data import repository as repo  # noqa: E402
from dashboard.data.connection import execute  # noqa: E402
from dashboard.domain.filters import DashboardFilters, SegmentFilters  # noqa: E402
from dashboard.domain.metrics import DIMENSIONS, STAGE_COLUMNS  # noqa: E402
from dashboard.utils.date_utils import GRANULARITIES, Period, presets  # noqa: E402

TOLERANCE = 0.01  # USD
results: list[tuple[bool, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))


def close(a: float, b: float) -> bool:
    return math.isclose(float(a), float(b), abs_tol=TOLERANCE)


def account_filter(segments: SegmentFilters) -> tuple[str, dict]:
    return segments.to_sql("a")


def independent_financials(period: Period, segments: SegmentFilters) -> dict:
    s = gold_schema_fqn()
    seg, params = account_filter(segments)
    params.update(start=period.start, end=period.end)
    pay = execute(f"""
        SELECT COALESCE(SUM(p.amount_usd), 0) AS gpv_usd,
               COALESCE(SUM(CASE WHEN p.payment_channel = 'electronic' THEN p.amount_usd ELSE 0 END), 0) AS gpv_electronic_usd,
               COALESCE(SUM(CASE WHEN p.payment_channel = 'offline' THEN p.amount_usd ELSE 0 END), 0) AS gpv_offline_usd,
               COUNT(DISTINCT p.transaction_id) AS payment_count,
               COUNT(*) AS payment_rows
        FROM {s}.FCT_PAYMENT_TRANSACTIONS p
        JOIN {s}.DIM_ACCOUNTS a ON a.account_id = p.account_id
        WHERE p.transaction_date_mt BETWEEN %(start)s AND %(end)s{seg}""", params).iloc[0]
    inv = execute(f"""
        SELECT COUNT(DISTINCT i.invoice_id) AS invoice_count,
               COALESCE(SUM(i.invoice_amount_usd), 0) AS invoice_amount_usd,
               COUNT(*) AS invoice_rows
        FROM {s}.FCT_INVOICES i
        JOIN {s}.DIM_ACCOUNTS a ON a.account_id = i.account_id
        WHERE i.invoice_created_date_mt BETWEEN %(start)s AND %(end)s{seg}""", params).iloc[0]
    return {**pay.to_dict(), **inv.to_dict()}


def independent_stages(day: date, segments: SegmentFilters) -> dict:
    s = gold_schema_fqn()
    seg, params = account_filter(segments)
    params["day"] = day
    frame = execute(f"""
        SELECT d.lifecycle_stage, COUNT(DISTINCT d.account_id) AS accounts
        FROM {s}.FCT_ACCOUNT_DAILY_STATUS d
        JOIN {s}.DIM_ACCOUNTS a ON a.account_id = d.account_id
        WHERE d.status_date = %(day)s{seg}
        GROUP BY d.lifecycle_stage""", params)
    counts = dict(zip(frame.lifecycle_stage, frame.accounts))
    out = {f"{k}_accounts": int(counts.get(k, 0)) for k in ("pre_trial", "trial", "subscribed", "churned")}
    out["total_accounts"] = sum(out.values())
    return out


def validate_scenario(name: str, filters: DashboardFilters) -> None:
    print(f"\n== {name}: {filters.period.label()} · {filters.segments.selections() or 'all segments'}")
    totals = repo.financial_totals(filters)
    expected = independent_financials(filters.period, filters.segments)
    for measure in ("gpv_usd", "gpv_electronic_usd", "gpv_offline_usd", "invoice_amount_usd"):
        check(close(totals.current[measure], expected[measure]), f"{measure} matches fact table",
              f"{totals.current[measure]} vs {expected[measure]}")
    for measure in ("payment_count", "invoice_count"):
        check(int(totals.current[measure]) == int(expected[measure]), f"{measure} matches fact table",
              f"{totals.current[measure]} vs {expected[measure]}")
    check(int(expected["payment_rows"]) == int(expected["payment_count"]),
          "no duplicate payments (rows = distinct transaction_id)")
    check(int(expected["invoice_rows"]) == int(expected["invoice_count"]),
          "no duplicate invoices (rows = distinct invoice_id)")
    check(close(totals.current["gpv_electronic_usd"] + totals.current["gpv_offline_usd"],
                totals.current["gpv_usd"]), "electronic + offline = GPV")

    if filters.comparison:
        prior = independent_financials(filters.comparison, filters.segments)
        check(close(totals.previous["gpv_usd"], prior["gpv_usd"]), "previous-period GPV matches")
        check(int(totals.previous["invoice_count"]) == int(prior["invoice_count"]),
              "previous-period invoice count matches")

    for granularity in GRANULARITIES:
        trend = repo.financial_trend(filters.period, filters.segments, granularity)
        check(close(trend.gpv_usd.sum(), totals.current["gpv_usd"])
              and int(trend.invoice_count.sum()) == int(totals.current["invoice_count"]),
              f"{granularity.lower()} trend sums to totals")
        check(int(trend.days_in_bucket.sum()) == filters.period.days,
              f"{granularity.lower()} buckets cover every day exactly once")

    for dimension in DIMENSIONS:
        by_dim = repo.financial_by_dimension(filters, dimension.key)
        check(close(by_dim.gpv_usd.sum(), totals.current["gpv_usd"])
              and int(by_dim.invoice_count.sum()) == int(totals.current["invoice_count"]),
              f"GPV & invoices by {dimension.key} sum to totals")
    detail = repo.financial_detail(filters)
    check(close(detail.gpv_usd.sum(), totals.current["gpv_usd"]), "GPV detail table sums to total")

    accounts = repo.lifecycle_totals(filters)
    expected_stages = independent_stages(filters.period.end, filters.segments)
    check(accounts.current == expected_stages, "stage counts match daily status fact",
          f"{accounts.current} vs {expected_stages}")
    check(sum(accounts.current[c] for c in STAGE_COLUMNS) == accounts.current["total_accounts"],
          "stages sum to total accounts")
    if filters.comparison:
        check(accounts.previous == independent_stages(filters.comparison.end, filters.segments),
              "previous-period stage counts match")
    for dimension in DIMENSIONS:
        by_dim = repo.lifecycle_by_dimension(filters, dimension.key)
        check(int(by_dim.total_accounts.sum()) == accounts.current["total_accounts"],
              f"accounts by {dimension.key} sum to total")
    for granularity in GRANULARITIES:
        trend = repo.lifecycle_trend(filters, granularity)
        last = trend.iloc[-1]
        check(last.period_end == filters.period.end
              and int(last.total_accounts) == accounts.current["total_accounts"],
              f"{granularity.lower()} stage trend ends at the period-end snapshot")


def validate_reference() -> None:
    s = gold_schema_fqn()
    print("\n== Reference checks")
    nulls = execute(f"""
        SELECT COUNT_IF(country IS NULL OR country = 'Unknown' OR region IS NULL OR region = 'Unknown'
                        OR city IS NULL OR city = 'Unknown' OR sign_up_platform IS NULL
                        OR sign_up_platform = 'Unknown') AS bad
        FROM {s}.MART_FINANCIAL_PERFORMANCE""").iloc[0].bad
    check(int(nulls) == 0, "no NULL/Unknown segments in the financial mart")
    nulls = execute(f"""
        SELECT COUNT_IF(country = 'Unknown' OR region = 'Unknown' OR city = 'Unknown'
                        OR sign_up_platform = 'Unknown') AS bad
        FROM {s}.MART_ACCOUNT_LIFECYCLE""").iloc[0].bad
    check(int(nulls) == 0, "no Unknown segments in the lifecycle mart")
    accounts = execute(f"SELECT COUNT(*) AS n, COUNT(DISTINCT account_id) AS d FROM {s}.DIM_ACCOUNTS").iloc[0]
    check(int(accounts.n) == int(accounts.d), "dim_accounts has one row per account_id")

    # Timezone: re-derive Mountain Time dates from raw Bronze UTC timestamps, using each
    # engine's own IANA-aware conversion (independent of the dbt macro).
    database = s.split(".")[0]
    if data_backend() == "duckdb":
        def mt_date(col: str) -> str:
            return f"CAST(timezone('America/Denver', {col} AT TIME ZONE 'UTC') AS DATE)"
    else:
        def mt_date(col: str) -> str:
            return f"TO_DATE(CONVERT_TIMEZONE('UTC', 'America/Denver', {col}))"
    try:
        mismatches = execute(f"""
            SELECT
              (SELECT COUNT(*) FROM {database}.BRONZE.PAYMENT_TRANSACTIONS b
                 JOIN {s}.FCT_PAYMENT_TRANSACTIONS f ON f.transaction_id = b.transaction_id
                WHERE {mt_date('b.transaction_time')} <> f.transaction_date_mt) AS payments,
              (SELECT COUNT(*) FROM {database}.BRONZE.INVOICES b
                 JOIN {s}.FCT_INVOICES f ON f.invoice_id = b.invoice_id
                WHERE {mt_date('b.invoice_created_time')} <> f.invoice_created_date_mt) AS invoices,
              (SELECT COUNT(*) FROM {database}.BRONZE.PAYMENT_TRANSACTIONS b
                WHERE {mt_date('b.transaction_time')} <> CAST(b.transaction_time AS DATE))
                AS payments_shifted
        """).iloc[0]
        check(int(mismatches.payments) == 0, "payment dates = Bronze UTC → America/Denver (DST-aware)")
        check(int(mismatches.invoices) == 0, "invoice dates = Bronze UTC → America/Denver (DST-aware)")
        print(f"         ({int(mismatches.payments_shifted)} payments fall on a different date in MT "
              "than in UTC - the conversion is material)")
    except Exception as error:  # noqa: BLE001 - Bronze may be unavailable to a reporting role.
        print(f"  [SKIP] timezone check against Bronze: {error}")


def main() -> int:
    print(f"Backend: {data_backend()} · schema {gold_schema_fqn()}")
    coverage = repo.data_coverage()
    window = coverage.window
    named = presets(window)
    scenarios = [
        ("All data", DashboardFilters(window, window)),
        ("H2 2024 vs H1 2024, UK + Canada",
         DashboardFilters(Period(date(2024, 7, 1), date(2024, 12, 31)), window,
                          SegmentFilters(country=("UK", "Canada")))),
        ("Last 6 months, iOS + iPad", DashboardFilters(named["Last 6 months"], window,
                                                       SegmentFilters(sign_up_platform=("mobile-ios", "mobile-ipad")))),
        ("Single DST-transition week, one region",
         DashboardFilters(Period(date(2024, 11, 1), date(2024, 11, 7)), window,
                          SegmentFilters(region=("England-Central",)))),
        ("Calendar 2025, two cities, web",
         DashboardFilters(named["Calendar 2025"], window,
                          SegmentFilters(city=("Toronto", "Houston"), sign_up_platform=("web-browser",)))),
    ]
    for name, filters in scenarios:
        validate_scenario(name, filters)
    validate_reference()
    failed = [name for ok, name in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
