"""Page-level layout primitives: header, cards, notes, footer."""

from __future__ import annotations

import html
import re
from contextlib import contextmanager

import streamlit as st

from dashboard.config import (CURRENCY, REPORTING_TIMEZONE, REPORTING_TIMEZONE_LABEL,
                              data_source_label)
from dashboard.domain.filters import DashboardFilters
from dashboard.domain.metrics import DIMENSIONS
from dashboard.utils.date_utils import format_date


def page_header(eyebrow: str, title: str, filters: DashboardFilters) -> None:
    comparison = filters.comparison
    compare_text = (f"vs <b>{html.escape(comparison.label())}</b>" if comparison
                    else "No comparison period")
    segments = filters.segments.selections()
    names = {d.key: d for d in DIMENSIONS}
    segment_text = (" · ".join(
        ", ".join(v) if len(v) <= 2 else f"{len(v)} {names[k].plural.lower()}"
        for k, v in segments.items()) if segments else "All segments")
    st.html(f"""
<div class="page-header">
  <div class="page-eyebrow">{html.escape(eyebrow)}</div>
  <div class="page-title">{html.escape(title)}</div>
  <div class="page-meta">
    <span class="chip"><b>{html.escape(filters.period.label())}</b></span>
    <span class="chip">{compare_text}</span>
    <span class="chip">{html.escape(segment_text)}</span>
    <span class="chip">{REPORTING_TIMEZONE_LABEL} · {CURRENCY}</span>
  </div>
</div>""")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


@contextmanager
def card(title: str, subtitle: str | None = None, key: str | None = None, controls=None):
    """A white bordered card with a title row.

    `controls` is an optional callable rendered right-aligned in the title row
    (e.g. a granularity toggle); its return value is yielded.
    """
    with st.container(key=f"card_{key or _slug(title)}"):
        result = None
        if controls:
            left, right = st.columns([1, 1], vertical_alignment="center")
        else:
            left, right = st.container(), None
        with left:
            sub = f'<div class="card-subtitle">{html.escape(subtitle)}</div>' if subtitle else ""
            st.html(f'<div class="card-title">{html.escape(title)}</div>{sub}')
        if right is not None:
            with right, st.container(horizontal=True, horizontal_alignment="right"):
                result = controls()
        yield result


def note(text: str) -> None:
    """Informational callout. `text` may contain trusted inline HTML."""
    st.html(f'<div class="note">{text}</div>')


def financial_coverage_note(filters: DashboardFilters, financial: "Period") -> None:
    """Warn when the period (or its comparison) reaches outside financial activity."""
    spans = [filters.period] + ([filters.comparison] if filters.comparison else [])
    if all(span.within(financial) for span in spans):
        return
    note(
        "Payment and invoice activity runs from "
        f"<b>{format_date(financial.start)}</b> to <b>{format_date(financial.end)}</b> "
        "(lifecycle data continues later). Days outside that range have no financial "
        "activity, so totals and period-over-period changes reflect only the covered days."
    )


def footer(data_end) -> None:
    st.html(
        f'<div class="footer">All dates are {REPORTING_TIMEZONE_LABEL} ({REPORTING_TIMEZONE}); '
        f'all amounts in {CURRENCY}. Data through {format_date(data_end)}. '
        f"Source: {html.escape(data_source_label())}.</div>"
    )
