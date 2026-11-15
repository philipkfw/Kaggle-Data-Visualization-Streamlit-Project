from datetime import date

import pytest

from dashboard.data import queries
from dashboard.domain.filters import SegmentFilters

SCHEMA = "KAGGLE_DB.GOLD"


def test_segment_filters_use_bind_parameters():
    segments = SegmentFilters(country=("UK", "Canada"), sign_up_platform=("web-browser",))
    sql, params = segments.to_sql("f")
    assert "f.country IN (%(f_country_0)s, %(f_country_1)s)" in sql
    assert "f.sign_up_platform IN (%(f_sign_up_platform_0)s)" in sql
    assert params == {"f_country_0": "UK", "f_country_1": "Canada",
                      "f_sign_up_platform_0": "web-browser"}
    assert "UK" not in sql  # Values never interpolated.


def test_empty_filters_add_no_predicate():
    assert SegmentFilters().to_sql() == ("", {})


def test_trend_filters_live_in_join_condition():
    sql, _ = queries.financial_trend(SCHEMA, date(2024, 1, 1), date(2024, 3, 31),
                                     SegmentFilters(city=("Leeds",)), "Weekly")
    join_part = sql.split("LEFT JOIN")[1].split("WHERE")[0]
    assert "f.city IN" in join_part  # Keeps zero-activity days in the spine.
    assert "d.week_start_date" in sql


def test_lifecycle_stocks_never_summed_across_dates():
    sql, _ = queries.lifecycle_trend(SCHEMA, date(2024, 1, 1), date(2024, 12, 31),
                                     SegmentFilters(), "Monthly")
    assert "l.reporting_date = b.period_end" in sql
    sql, params = queries.lifecycle_by_dimension(SCHEMA, date(2025, 8, 12), SegmentFilters(),
                                                 "region")
    assert "reporting_date = %(as_of)s" in sql and params["as_of"] == date(2025, 8, 12)


def test_comparison_columns_only_when_requested():
    sql, params = queries.financial_totals(SCHEMA, date(2024, 7, 1), date(2024, 12, 31),
                                           SegmentFilters())
    assert "prior_" not in sql and "prior_start" not in params
    sql, params = queries.financial_totals(SCHEMA, date(2024, 7, 1), date(2024, 12, 31),
                                           SegmentFilters(), date(2024, 1, 1), date(2024, 6, 30))
    assert "AS prior_gpv_usd" in sql and params["prior_start"] == date(2024, 1, 1)


@pytest.mark.parametrize("bad", ["country; DROP TABLE x", "amount_usd"])
def test_dimension_allow_list(bad):
    with pytest.raises(ValueError):
        queries.financial_by_dimension(SCHEMA, date(2024, 1, 1), date(2024, 1, 2),
                                       SegmentFilters(), bad)


def test_granularity_allow_list():
    with pytest.raises(ValueError):
        queries.financial_trend(SCHEMA, date(2024, 1, 1), date(2024, 1, 2), SegmentFilters(),
                                "Hourly")
