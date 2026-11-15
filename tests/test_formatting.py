import math

import pytest

from dashboard.utils import formatting as fmt


@pytest.mark.parametrize("value, expected", [
    (1_968_622.53, "$1.97M"),
    (450_000, "$450K"),
    (45_210, "$45.2K"),
    (999_999, "$1M"),
    (950, "$950"),
    (0, "$0"),
    (-12_500, "-$12.5K"),
    (2_500_000_000, "$2.5B"),
])
def test_usd_compact(value, expected):
    assert fmt.usd_compact(value) == expected


def test_usd_full_and_missing():
    assert fmt.usd_full(1968622.532738) == "$1,968,622.53"
    assert fmt.usd_full(None) == "—"
    assert fmt.usd_compact(float("nan")) == "—"


def test_counts():
    assert fmt.count_full(1234) == "1,234"
    assert fmt.count_compact(9_999) == "9,999"
    assert fmt.count_compact(12_345) == "12.3K"


def test_pct_change_never_divides_by_zero():
    assert fmt.pct_change(10, 0) is None
    assert fmt.pct_change(10, None) is None
    assert math.isclose(fmt.pct_change(110, 100), 0.10)
    assert fmt.signed_percent(None) == "—"
    assert fmt.signed_percent(0.1234) == "+12.3%"
    assert fmt.signed_percent(-0.05) == "-5.0%"


def test_nice_ticks():
    assert fmt.nice_ticks(197_836) == [0, 50_000, 100_000, 150_000, 200_000]
    assert fmt.nice_ticks(0) == [0, 1]
    assert fmt.nice_ticks(61)[-1] >= 61
