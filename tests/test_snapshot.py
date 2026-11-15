"""Offline tests: the bundled DuckDB snapshot reproduces the known Gold totals.

These need no credentials or network, so they guard the preserved dashboard data
indefinitely (e.g. after the Snowflake account is gone).
"""

import os
from datetime import date

import pytest

from dashboard.config import SNAPSHOT_DIR, snapshot_manifest
from dashboard.data import repository as repo
from dashboard.data.connection import to_duckdb_sql
from dashboard.domain.filters import DashboardFilters, SegmentFilters
from dashboard.utils.date_utils import Period


@pytest.fixture(autouse=True)
def snapshot_backend(monkeypatch):
    monkeypatch.setenv("DASHBOARD_DATA_BACKEND", "duckdb")


def test_param_translation():
    assert to_duckdb_sql("a = %(start)s AND b IN (%(f_city_0)s)") == "a = $start AND b IN ($f_city_0)"


def test_manifest_lists_every_file():
    manifest = snapshot_manifest()
    assert manifest["database"] == "KAGGLE_DB" and manifest["gold_schema"] == "GOLD"
    for table in manifest["tables"]:
        assert (SNAPSHOT_DIR / table["file"]).exists(), table["file"]


def test_known_totals():
    coverage = repo.data_coverage()
    assert coverage.window == Period(date(2024, 1, 1), date(2025, 8, 12))
    filters = DashboardFilters(coverage.window, coverage.window)
    financial = repo.financial_totals(filters).current
    assert financial["gpv_usd"] == pytest.approx(1_968_622.532738, abs=0.01)
    assert financial["invoice_count"] == 609
    assert financial["payment_count"] == 435
    assert financial["invoice_amount_usd"] == pytest.approx(2_743_557.226247, abs=0.01)
    accounts = repo.lifecycle_totals(filters).current
    assert accounts == {"pre_trial_accounts": 0, "trial_accounts": 61, "subscribed_accounts": 51,
                        "churned_accounts": 88, "total_accounts": 200}


def test_filtered_query_runs():
    coverage = repo.data_coverage()
    filters = DashboardFilters(coverage.window, coverage.window,
                               SegmentFilters(country=("UK",), sign_up_platform=("mobile-ios",)))
    by_city = repo.financial_by_dimension(filters, "city")
    assert by_city.gpv_usd.sum() == pytest.approx(repo.financial_totals(filters).current["gpv_usd"])
    assert os.environ["DASHBOARD_DATA_BACKEND"] == "duckdb"
