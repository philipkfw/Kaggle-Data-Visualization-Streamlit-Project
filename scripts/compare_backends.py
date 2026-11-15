"""Prove the DuckDB snapshot reproduces live Snowflake exactly.

Runs every repository function the dashboard uses, across several filter/date
scenarios and all granularities and dimensions, once per backend, and compares the
results value by value. Run it after scripts/export_snapshot.py while Snowflake is
still reachable.

Usage:  .venv/bin/python scripts/compare_backends.py
"""

from __future__ import annotations

import logging
import math
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.getLogger("streamlit").setLevel(logging.ERROR)

import pandas as pd  # noqa: E402

from dashboard.data import repository as repo  # noqa: E402
from dashboard.domain.filters import DashboardFilters, SegmentFilters  # noqa: E402
from dashboard.domain.metrics import DIMENSIONS  # noqa: E402
from dashboard.utils.date_utils import GRANULARITIES, Period, presets  # noqa: E402


def collect(backend: str) -> dict[str, object]:
    os.environ["DASHBOARD_DATA_BACKEND"] = backend
    coverage = repo.data_coverage()
    window = coverage.window
    named = presets(window)
    scenarios = {
        "all": DashboardFilters(window, window),
        "h2_2024_uk_ca": DashboardFilters(Period(date(2024, 7, 1), date(2024, 12, 31)), window,
                                          SegmentFilters(country=("UK", "Canada"))),
        "last_6m_ios": DashboardFilters(named["Last 6 months"], window,
                                        SegmentFilters(sign_up_platform=("mobile-ios",))),
        "q1_2025_cities": DashboardFilters(Period(date(2025, 1, 1), date(2025, 3, 31)), window,
                                           SegmentFilters(city=("Toronto", "Leeds", "Houston"))),
    }
    out: dict[str, object] = {"coverage": coverage, "segment_options": repo.segment_options()}
    for name, f in scenarios.items():
        out[f"{name}/financial_totals"] = repo.financial_totals(f)
        out[f"{name}/lifecycle_totals"] = repo.lifecycle_totals(f)
        out[f"{name}/financial_detail"] = repo.financial_detail(f)
        out[f"{name}/lifecycle_detail"] = repo.lifecycle_detail(f)
        out[f"{name}/stale_trials"] = repo.stale_trials(f.segments)
        for g in GRANULARITIES:
            out[f"{name}/financial_trend/{g}"] = repo.financial_trend(f.period, f.segments, g)
            out[f"{name}/lifecycle_trend/{g}"] = repo.lifecycle_trend(f, g)
            out[f"{name}/lifecycle_flows/{g}"] = repo.lifecycle_flows(f, g)
        for d in DIMENSIONS:
            out[f"{name}/financial_by/{d.key}"] = repo.financial_by_dimension(f, d.key)
            out[f"{name}/lifecycle_by/{d.key}"] = repo.lifecycle_by_dimension(f, d.key)
    return out


def normalise(frame: pd.DataFrame) -> pd.DataFrame:
    """Order-independent comparison: sort by all non-float columns, reset index."""
    keys = [c for c in frame.columns if frame[c].dtype == object or "int" in str(frame[c].dtype)]
    frame = frame.sort_values(keys or list(frame.columns)).reset_index(drop=True)
    return frame.apply(lambda s: s.astype(float) if s.dtype.kind in "iuf" else s.astype(str))


def same(a, b) -> bool:
    """Equal values; floats within 1e-6 (engines differ at ~1e-10 in decimal sums)."""
    if isinstance(a, repo.Totals):
        return same(a.current, b.current) and same(a.previous, b.previous)
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-6)
    if isinstance(a, pd.DataFrame):
        if list(a.columns) != list(b.columns) or len(a) != len(b):
            return False
        try:
            pd.testing.assert_frame_equal(normalise(a), normalise(b), check_dtype=False,
                                          rtol=1e-9, atol=1e-6)
            return True
        except AssertionError:
            return False
    return a == b


def main() -> int:
    live, snapshot = collect("snowflake"), collect("duckdb")
    failed = [key for key in live if not same(live[key], snapshot[key])]
    for key in failed:
        print(f"  [DIFF] {key}")
    print(f"{len(live) - len(failed)} of {len(live)} result sets identical "
          "(Snowflake vs DuckDB snapshot)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
