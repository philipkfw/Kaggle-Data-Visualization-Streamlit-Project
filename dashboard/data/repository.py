"""Data access API used by the views.

Each function builds SQL (queries.py), runs it through one cached executor and
returns a tidy DataFrame / dict. Identical queries across pages and widgets hit the
cache, so Snowflake sees each distinct (sql, params) once per TTL.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from dashboard.config import QUERY_CACHE_TTL_SECONDS, data_backend, gold_schema_fqn
from dashboard.data import queries
from dashboard.data.connection import execute
from dashboard.domain.filters import DashboardFilters, SegmentFilters
from dashboard.domain.metrics import STAGE_COLUMNS
from dashboard.utils.date_utils import Period


@st.cache_data(ttl=QUERY_CACHE_TTL_SECONDS, show_spinner=False)
def _run_cached(backend: str, sql: str, params: tuple) -> pd.DataFrame:
    # `backend` is part of the cache key so snapshot and live results never mix.
    return execute(sql, dict(params))


def run(query: tuple[str, dict]) -> pd.DataFrame:
    sql, params = query
    return _run_cached(data_backend(), sql, tuple(sorted(params.items())))


def clear_cache() -> None:
    _run_cached.clear()


# --- Reference data ----------------------------------------------------------------

@dataclass(frozen=True)
class DataCoverage:
    window: Period  # Reporting window (dim_date spine) - lifecycle data spans all of it.
    financial: Period  # First/last date with any payment or invoice.


def data_coverage() -> DataCoverage:
    row = run(queries.data_window(gold_schema_fqn())).iloc[0]
    return DataCoverage(
        window=Period(row.window_start, row.window_end),
        financial=Period(row.financial_start, row.financial_end),
    )


def segment_options() -> pd.DataFrame:
    return run(queries.segment_options(gold_schema_fqn()))


# --- Financial -------------------------------------------------------------------------

@dataclass(frozen=True)
class Totals:
    current: dict
    previous: dict | None  # None when no valid comparison period exists.


def financial_totals(filters: DashboardFilters) -> Totals:
    prior = filters.comparison
    frame = run(queries.financial_totals(
        gold_schema_fqn(), filters.period.start, filters.period.end, filters.segments,
        prior.start if prior else None, prior.end if prior else None,
    ))
    row = frame.iloc[0].to_dict()
    current = {m: float(row[m]) for m in queries.FINANCIAL_MEASURES}
    previous = ({m: float(row[f"prior_{m}"]) for m in queries.FINANCIAL_MEASURES}
                if prior else None)
    return Totals(current, previous)


def financial_trend(period: Period, segments: SegmentFilters, granularity: str) -> pd.DataFrame:
    return run(queries.financial_trend(gold_schema_fqn(), period.start, period.end,
                                       segments, granularity))


def financial_by_dimension(filters: DashboardFilters, dimension: str) -> pd.DataFrame:
    prior = filters.comparison
    return run(queries.financial_by_dimension(
        gold_schema_fqn(), filters.period.start, filters.period.end, filters.segments,
        dimension, prior.start if prior else None, prior.end if prior else None,
    ))


def financial_detail(filters: DashboardFilters) -> pd.DataFrame:
    return run(queries.financial_detail(gold_schema_fqn(), filters.period.start,
                                        filters.period.end, filters.segments))


# --- Lifecycle ---------------------------------------------------------------------------

def _empty_snapshot() -> dict:
    return {c: 0 for c in (*STAGE_COLUMNS, "total_accounts")}


def lifecycle_totals(filters: DashboardFilters) -> Totals:
    """Stage counts at the end of the period and of the comparison period."""
    prior = filters.comparison
    dates = (filters.period.end,) + ((prior.end,) if prior else ())
    frame = run(queries.lifecycle_snapshots(gold_schema_fqn(), dates, filters.segments))
    by_date = {row.reporting_date: row._asdict() for row in frame.itertuples(index=False)}

    def snapshot(day) -> dict:
        values = by_date.get(day)
        if values is None:  # No accounts in this segment yet on that date.
            return _empty_snapshot()
        return {c: int(values[c]) for c in (*STAGE_COLUMNS, "total_accounts")}

    return Totals(snapshot(filters.period.end), snapshot(prior.end) if prior else None)


def lifecycle_trend(filters: DashboardFilters, granularity: str) -> pd.DataFrame:
    return run(queries.lifecycle_trend(gold_schema_fqn(), filters.period.start,
                                       filters.period.end, filters.segments, granularity))


def lifecycle_flows(filters: DashboardFilters, granularity: str) -> pd.DataFrame:
    return run(queries.lifecycle_flows(gold_schema_fqn(), filters.period.start,
                                       filters.period.end, filters.segments, granularity))


def lifecycle_by_dimension(filters: DashboardFilters, dimension: str) -> pd.DataFrame:
    return run(queries.lifecycle_by_dimension(gold_schema_fqn(), filters.period.end,
                                              filters.segments, dimension))


def stale_trials(segments: SegmentFilters) -> dict:
    row = run(queries.stale_trials(gold_schema_fqn(), segments)).iloc[0]
    return {"trial_accounts": int(row.trial_accounts),
            "stale_trial_accounts": int(row.stale_trial_accounts)}


def lifecycle_detail(filters: DashboardFilters) -> pd.DataFrame:
    return run(queries.lifecycle_detail(gold_schema_fqn(), filters.period.end,
                                        filters.segments))
