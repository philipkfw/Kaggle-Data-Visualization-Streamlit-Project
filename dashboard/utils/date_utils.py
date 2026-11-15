"""Reporting periods, presets and date labels.

All dates handled here are Mountain Time calendar dates: the Gold models already
convert source timestamps to America/Denver (dbt macro `to_mountain_time`), so the
app never converts again. The data is a static snapshot, so presets are anchored to
the last date in the data, not to today.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from dashboard.config import REPORTING_TIMEZONE

GRANULARITIES = ("Daily", "Weekly", "Monthly")


@dataclass(frozen=True)
class Period:
    """An inclusive date range."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"Period start {self.start} is after end {self.end}")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def is_whole_months(self) -> bool:
        last_day = calendar.monthrange(self.end.year, self.end.month)[1]
        return self.start.day == 1 and self.end.day == last_day

    def previous(self) -> "Period":
        """The previous equivalent period.

        Whole calendar months compare with the same number of preceding months
        (Q3 -> Q2, H2 -> H1, a year -> the prior year); any other range compares
        with the equal-length window immediately before it.
        """
        prior_end = self.start - timedelta(days=1)
        if self.is_whole_months:
            months = (self.end.year - self.start.year) * 12 + self.end.month - self.start.month + 1
            return Period(_add_months(self.start, -months), prior_end)
        return Period(prior_end - timedelta(days=self.days - 1), prior_end)

    def within(self, window: "Period") -> bool:
        return window.start <= self.start and self.end <= window.end

    def clamp(self, window: "Period") -> "Period":
        start = min(max(self.start, window.start), window.end)
        end = max(min(self.end, window.end), start)
        return Period(start, end)

    def label(self) -> str:
        return f"{format_date(self.start)} – {format_date(self.end)}"


def comparison_period(period: Period, data_window: Period) -> Period | None:
    """The previous equivalent period, or None if any of it predates the data.

    A comparison that falls partly before the reporting window would compare
    against missing data, so no comparison is shown rather than a misleading one.
    """
    prior = period.previous()
    return prior if prior.within(data_window) else None


def presets(data_window: Period) -> dict[str, Period]:
    """Named reporting periods, anchored to the last date in the data."""
    end = data_window.end
    candidates = {
        "All data": data_window,
        "Last 30 days": Period(end - timedelta(days=29), end),
        "Last 90 days": Period(end - timedelta(days=89), end),
        "Last 6 months": Period(_add_months(end, -6) + timedelta(days=1), end),
        "Last 12 months": Period(_add_months(end, -12) + timedelta(days=1), end),
        "Year to date": Period(date(end.year, 1, 1), end),
    }
    for year in range(data_window.start.year, end.year + 1):
        candidates[f"Calendar {year}"] = Period(date(year, 1, 1), date(year, 12, 31))
    return {name: p.clamp(data_window) for name, p in candidates.items()}


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    # Clamp to the last valid day of the target month (e.g. Mar 31 -> Feb 28).
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def mountain_now() -> datetime:
    """Current wall-clock time in Mountain Time (DST-aware via IANA rules)."""
    return datetime.now(ZoneInfo(REPORTING_TIMEZONE))


def format_date(day: date) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def format_bucket(day: date, granularity: str) -> str:
    """Human label for a time bucket's start date."""
    if granularity == "Monthly":
        return f"{day:%b %Y}"
    if granularity == "Weekly":
        return f"Week of {format_date(day)}"
    return f"{day:%a}, {format_date(day)}"
