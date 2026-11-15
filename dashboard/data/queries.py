"""SQL builders for the Gold reporting marts.

Every function returns (sql, params). Rules applied throughout:

* Aggregation happens in Snowflake; only aggregated rows reach pandas.
* Financial measures (mart_financial_performance) are fully additive -> SUM over
  dates and segments. GPV is dated by payment date, invoices by invoice created
  date; both are already resolved into `reporting_date` by dbt.
* Lifecycle stocks (mart_account_lifecycle) are semi-additive -> SUM across
  segments on a SINGLE date, never across dates. Trends take each bucket's last date.
* User values are bind parameters; identifiers come from allow-lists only.
"""

from __future__ import annotations

from datetime import date

from dashboard.domain.filters import SegmentFilters
from dashboard.domain.metrics import DIMENSION_KEYS, STAGE_COLUMNS

FINANCIAL_MART = "MART_FINANCIAL_PERFORMANCE"
LIFECYCLE_MART = "MART_ACCOUNT_LIFECYCLE"
DIM_DATE = "DIM_DATE"
DIM_ACCOUNTS = "DIM_ACCOUNTS"

FINANCIAL_MEASURES = (
    "gpv_usd", "gpv_electronic_usd", "gpv_offline_usd",
    "payment_count", "invoice_count", "invoice_amount_usd",
)

_SEP = ",\n    "

# dim_date columns used as time buckets (ISO weeks start on Monday).
_BUCKETS = {"Daily": "date_day", "Weekly": "week_start_date", "Monthly": "month_start_date"}


def _bucket_column(granularity: str) -> str:
    if granularity not in _BUCKETS:
        raise ValueError(f"Unknown granularity {granularity!r}")
    return _BUCKETS[granularity]


def _dimension(dimension: str) -> str:
    if dimension not in DIMENSION_KEYS:
        raise ValueError(f"Unknown dimension {dimension!r}")
    return dimension


def _sum_measures(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return ",\n    ".join(f"COALESCE(SUM({prefix}{m}), 0) AS {m}" for m in FINANCIAL_MEASURES)


def _sum_stages(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    columns = (*STAGE_COLUMNS, "total_accounts")
    return ",\n    ".join(f"COALESCE(SUM({prefix}{c}), 0) AS {c}" for c in columns)


# --- Reference data ----------------------------------------------------------------

def data_window(schema: str) -> tuple[str, dict]:
    """Reporting window (dim_date spine) and financial activity coverage."""
    sql = f"""
SELECT
    (SELECT MIN(date_day) FROM {schema}.{DIM_DATE}) AS window_start,
    (SELECT MAX(date_day) FROM {schema}.{DIM_DATE}) AS window_end,
    (SELECT MIN(reporting_date) FROM {schema}.{FINANCIAL_MART}) AS financial_start,
    (SELECT MAX(reporting_date) FROM {schema}.{FINANCIAL_MART}) AS financial_end
"""
    return sql, {}


def segment_options(schema: str) -> tuple[str, dict]:
    """Distinct segment combinations, used to build (cascading) filter options."""
    sql = f"""
SELECT DISTINCT country, region, city, sign_up_platform
FROM {schema}.{DIM_ACCOUNTS}
ORDER BY country, region, city, sign_up_platform
"""
    return sql, {}


# --- Financial (GPV & invoices) -----------------------------------------------------

def _period_measures(params: dict, start: date, end: date, prior_start: date | None,
                     prior_end: date | None) -> tuple[str, str]:
    """Measure columns for the period and optional comparison, from a single scan.

    Returns (select-list, scan start placeholder). Uses portable CASE WHEN so the
    same SQL runs on Snowflake and on the DuckDB snapshot.
    """
    params.update(start=start, end=end)
    columns = [f"COALESCE(SUM(CASE WHEN reporting_date BETWEEN %(start)s AND %(end)s "
               f"THEN {m} ELSE 0 END), 0) AS {m}" for m in FINANCIAL_MEASURES]
    scan_start = "%(start)s"
    if prior_start and prior_end:
        params.update(prior_start=prior_start, prior_end=prior_end)
        columns += [f"COALESCE(SUM(CASE WHEN reporting_date BETWEEN %(prior_start)s AND "
                    f"%(prior_end)s THEN {m} ELSE 0 END), 0) AS prior_{m}"
                    for m in FINANCIAL_MEASURES]
        scan_start = "%(prior_start)s"
    return _SEP.join(columns), scan_start


def financial_totals(schema: str, start: date, end: date, segments: SegmentFilters,
                     prior_start: date | None = None, prior_end: date | None = None
                     ) -> tuple[str, dict]:
    """Totals for the period and (optionally) the comparison period in one scan."""
    seg_sql, params = segments.to_sql()
    columns, scan_start = _period_measures(params, start, end, prior_start, prior_end)
    sql = f"""
SELECT
    {columns}
FROM {schema}.{FINANCIAL_MART}
WHERE reporting_date BETWEEN {scan_start} AND %(end)s{seg_sql}
"""
    return sql, params


def financial_trend(schema: str, start: date, end: date, segments: SegmentFilters,
                    granularity: str) -> tuple[str, dict]:
    """Financial measures per time bucket, with empty buckets filled as zero.

    The mart is sparse (only days with activity), so the calendar drives the query.
    Segment filters sit in the JOIN condition so they don't remove empty days.
    """
    bucket = _bucket_column(granularity)
    seg_sql, params = segments.to_sql("f")
    params.update(start=start, end=end)
    sql = f"""
SELECT
    d.{bucket} AS period_start,
    MIN(d.date_day) AS first_day,
    MAX(d.date_day) AS last_day,
    COUNT(DISTINCT d.date_day) AS days_in_bucket,
    {_sum_measures("f")}
FROM {schema}.{DIM_DATE} AS d
LEFT JOIN {schema}.{FINANCIAL_MART} AS f
    ON f.reporting_date = d.date_day{seg_sql}
WHERE d.date_day BETWEEN %(start)s AND %(end)s
GROUP BY d.{bucket}
ORDER BY period_start
"""
    return sql, params


def financial_by_dimension(schema: str, start: date, end: date, segments: SegmentFilters,
                           dimension: str, prior_start: date | None = None,
                           prior_end: date | None = None) -> tuple[str, dict]:
    """Financial measures per segment value, with optional comparison columns."""
    dim = _dimension(dimension)
    seg_sql, params = segments.to_sql()
    columns, scan_start = _period_measures(params, start, end, prior_start, prior_end)
    sql = f"""
SELECT
    {dim} AS segment,
    {columns}
FROM {schema}.{FINANCIAL_MART}
WHERE reporting_date BETWEEN {scan_start} AND %(end)s{seg_sql}
GROUP BY {dim}
"""
    return sql, params


def financial_detail(schema: str, start: date, end: date, segments: SegmentFilters
                     ) -> tuple[str, dict]:
    """Period totals at full segment grain (country x region x city x platform)."""
    seg_sql, params = segments.to_sql()
    params.update(start=start, end=end)
    sql = f"""
SELECT
    country, region, city, sign_up_platform,
    {_sum_measures()}
FROM {schema}.{FINANCIAL_MART}
WHERE reporting_date BETWEEN %(start)s AND %(end)s{seg_sql}
GROUP BY country, region, city, sign_up_platform
ORDER BY gpv_usd DESC
"""
    return sql, params


# --- Account lifecycle ---------------------------------------------------------------

def lifecycle_snapshots(schema: str, dates: tuple[date, ...], segments: SegmentFilters
                        ) -> tuple[str, dict]:
    """Stage counts on specific dates (stocks: one date at a time, summed over segments)."""
    seg_sql, params = segments.to_sql()
    names = []
    for i, day in enumerate(dates):
        params[f"d_{i}"] = day
        names.append(f"%(d_{i})s")
    sql = f"""
SELECT
    reporting_date,
    {_sum_stages()}
FROM {schema}.{LIFECYCLE_MART}
WHERE reporting_date IN ({", ".join(names)}){seg_sql}
GROUP BY reporting_date
"""
    return sql, params


def lifecycle_trend(schema: str, start: date, end: date, segments: SegmentFilters,
                    granularity: str) -> tuple[str, dict]:
    """Stage counts at the END of each bucket (a partial last bucket uses `end`)."""
    bucket = _bucket_column(granularity)
    seg_sql, params = segments.to_sql("l")
    params.update(start=start, end=end)
    sql = f"""
WITH buckets AS (
    SELECT
        {bucket} AS period_start,
        MIN(date_day) AS first_day,
        MAX(date_day) AS period_end,
        COUNT(*) AS days_in_bucket
    FROM {schema}.{DIM_DATE}
    WHERE date_day BETWEEN %(start)s AND %(end)s
    GROUP BY {bucket}
)
SELECT
    b.period_start,
    b.first_day,
    b.period_end,
    b.days_in_bucket,
    {_sum_stages("l")}
FROM buckets AS b
LEFT JOIN {schema}.{LIFECYCLE_MART} AS l
    ON l.reporting_date = b.period_end{seg_sql}
GROUP BY b.period_start, b.first_day, b.period_end, b.days_in_bucket
ORDER BY b.period_start
"""
    return sql, params


def lifecycle_flows(schema: str, start: date, end: date, segments: SegmentFilters,
                    granularity: str) -> tuple[str, dict]:
    """Lifecycle flows (sign-ups, new trials/subscriptions/churns) per bucket."""
    bucket = _bucket_column(granularity)
    seg_sql, params = segments.to_sql("l")
    params.update(start=start, end=end)
    flows = ("new_sign_ups", "new_trials", "new_subscriptions", "new_churns")
    measures = ",\n    ".join(f"COALESCE(SUM(l.{c}), 0) AS {c}" for c in flows)
    sql = f"""
SELECT
    d.{bucket} AS period_start,
    MIN(d.date_day) AS first_day,
    MAX(d.date_day) AS last_day,
    COUNT(DISTINCT d.date_day) AS days_in_bucket,
    {measures}
FROM {schema}.{DIM_DATE} AS d
LEFT JOIN {schema}.{LIFECYCLE_MART} AS l
    ON l.reporting_date = d.date_day{seg_sql}
WHERE d.date_day BETWEEN %(start)s AND %(end)s
GROUP BY d.{bucket}
ORDER BY period_start
"""
    return sql, params


def lifecycle_by_dimension(schema: str, as_of: date, segments: SegmentFilters,
                           dimension: str) -> tuple[str, dict]:
    """Stage counts per segment value on a single snapshot date."""
    dim = _dimension(dimension)
    seg_sql, params = segments.to_sql()
    params["as_of"] = as_of
    sql = f"""
SELECT
    {dim} AS segment,
    {_sum_stages()}
FROM {schema}.{LIFECYCLE_MART}
WHERE reporting_date = %(as_of)s{seg_sql}
GROUP BY {dim}
"""
    return sql, params


def stale_trials(schema: str, segments: SegmentFilters) -> tuple[str, dict]:
    """Current trial accounts and those dbt flags as stale (dim_accounts.is_stale_trial).

    Current state only (as of the reporting end date) - the flag has no history.
    """
    seg_sql, params = segments.to_sql()
    sql = f"""
SELECT
    COUNT_IF(current_lifecycle_stage = 'trial') AS trial_accounts,
    COUNT_IF(is_stale_trial) AS stale_trial_accounts
FROM {schema}.{DIM_ACCOUNTS}
WHERE TRUE{seg_sql}
"""
    return sql, params


def lifecycle_detail(schema: str, as_of: date, segments: SegmentFilters) -> tuple[str, dict]:
    """Stage counts at full segment grain on a single snapshot date."""
    seg_sql, params = segments.to_sql()
    params["as_of"] = as_of
    sql = f"""
SELECT
    country, region, city, sign_up_platform,
    {_sum_stages()}
FROM {schema}.{LIFECYCLE_MART}
WHERE reporting_date = %(as_of)s{seg_sql}
GROUP BY country, region, city, sign_up_platform
ORDER BY total_accounts DESC
"""
    return sql, params
