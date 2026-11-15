from datetime import date

import pytest

from dashboard.utils.date_utils import Period, comparison_period, format_bucket, presets

WINDOW = Period(date(2024, 1, 1), date(2025, 8, 12))


def test_previous_equal_length_window():
    period = Period(date(2025, 5, 15), date(2025, 8, 12))  # 90 days
    prior = period.previous()
    assert prior == Period(date(2025, 2, 14), date(2025, 5, 14))
    assert prior.days == period.days


@pytest.mark.parametrize("period, expected", [
    (Period(date(2024, 7, 1), date(2024, 12, 31)), Period(date(2024, 1, 1), date(2024, 6, 30))),
    (Period(date(2025, 3, 1), date(2025, 3, 31)), Period(date(2025, 2, 1), date(2025, 2, 28))),
    (Period(date(2025, 1, 1), date(2025, 12, 31)), Period(date(2024, 1, 1), date(2024, 12, 31))),
    (Period(date(2024, 4, 1), date(2024, 6, 30)), Period(date(2024, 1, 1), date(2024, 3, 31))),
])
def test_previous_whole_months(period, expected):
    assert period.previous() == expected


def test_comparison_none_when_prior_predates_data():
    assert comparison_period(WINDOW, WINDOW) is None
    assert comparison_period(Period(date(2024, 1, 1), date(2024, 1, 31)), WINDOW) is None
    assert comparison_period(Period(date(2024, 2, 1), date(2024, 2, 29)), WINDOW) == \
        Period(date(2024, 1, 1), date(2024, 1, 31))


def test_presets_anchor_to_data_end_and_clamp():
    named = presets(WINDOW)
    assert named["All data"] == WINDOW
    assert named["Last 30 days"] == Period(date(2025, 7, 14), date(2025, 8, 12))
    assert named["Year to date"] == Period(date(2025, 1, 1), date(2025, 8, 12))
    assert named["Calendar 2025"].end == date(2025, 8, 12)  # Clamped to the data.
    assert named["Last 12 months"] == Period(date(2024, 8, 13), date(2025, 8, 12))
    assert all(p.within(WINDOW) for p in named.values())


def test_period_rejects_inverted_range():
    with pytest.raises(ValueError):
        Period(date(2025, 1, 2), date(2025, 1, 1))


def test_bucket_labels():
    assert format_bucket(date(2025, 3, 1), "Monthly") == "Mar 2025"
    assert format_bucket(date(2025, 3, 3), "Weekly") == "Week of Mar 3, 2025"
