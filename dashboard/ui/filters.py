"""Sidebar filters, shared by every page.

Rendered once in app.py (before page navigation runs), so selections persist and
apply identically to every KPI, chart and table on every page.
"""

from __future__ import annotations

import html
from datetime import date

import pandas as pd
import streamlit as st

from dashboard.config import data_source_label
from dashboard.data import repository
from dashboard.ui.layout import source_link
from dashboard.domain.filters import DashboardFilters, SegmentFilters
from dashboard.domain.metrics import DIMENSIONS
from dashboard.utils.date_utils import GRANULARITIES, Period, format_date, presets

CUSTOM = "Custom range"
DEFAULT_PRESET = "All data"
_SEGMENT_KEYS = {d.key: f"filter_{d.key}" for d in DIMENSIONS}
_FILTERS_STATE = "dashboard_filters"


def _reset() -> None:
    for key in (*_SEGMENT_KEYS.values(), "filter_preset", "filter_custom_range"):
        st.session_state.pop(key, None)


def _refresh() -> None:
    repository.clear_cache()


def _cascading_options(options: pd.DataFrame, column: str) -> list[str]:
    """Values of `column` compatible with the selections in the *other* filters.

    Region is not hierarchical in this data (cities span regions), so every filter
    narrows the others rather than following a fixed drill path.
    """
    mask = pd.Series(True, index=options.index)
    for other, key in _SEGMENT_KEYS.items():
        selected = st.session_state.get(key) or []
        if other != column and selected:
            mask &= options[other].isin(selected)
    values = set(options.loc[mask, column])
    values |= set(st.session_state.get(_SEGMENT_KEYS[column]) or [])  # Never drop a selection.
    return sorted(values)


def _period_controls(window: Period) -> Period:
    named = presets(window)
    choice = st.selectbox("Reporting period", [*named, CUSTOM], key="filter_preset",
                          index=list(named).index(DEFAULT_PRESET))
    if choice != CUSTOM:
        return named[choice]
    picked = st.date_input("Custom range", value=(window.start, window.end),
                           min_value=window.start, max_value=window.end,
                           key="filter_custom_range", format="MMM D, YYYY")
    if isinstance(picked, (tuple, list)) and len(picked) == 2:
        return Period(picked[0], picked[1])
    start = picked[0] if isinstance(picked, (tuple, list)) and picked else window.start
    return Period(start, start) if isinstance(start, date) else window


def render_sidebar() -> DashboardFilters:
    coverage = repository.data_coverage()
    options = repository.segment_options()
    with st.sidebar:
        st.html('<div class="sidebar-label">Reporting period</div>')
        period = _period_controls(coverage.window).clamp(coverage.window)
        filters_preview = DashboardFilters(period, coverage.window)
        comparison = filters_preview.comparison
        st.html(
            f'<div class="sidebar-caption">{period.label()} · {period.days:,} days<br>'
            + (f"Compared with {comparison.label()}" if comparison
               else "No comparison: the previous period falls before the data starts")
            + "</div>"
        )

        st.html('<div class="sidebar-label">Segments</div>')
        selections = {}
        for dimension in DIMENSIONS:
            selections[dimension.key] = tuple(st.multiselect(
                dimension.label, _cascading_options(options, dimension.key),
                key=_SEGMENT_KEYS[dimension.key], placeholder=f"All {dimension.plural.lower()}",
            ))
        st.button("Reset filters", on_click=_reset, icon=":material/restart_alt:",
                  width="stretch", type="secondary")

        st.html('<div class="sidebar-label">Data</div>')
        st.html(
            f'<div class="sidebar-caption">Payments & invoices: '
            f'{format_date(coverage.financial.start)} – {format_date(coverage.financial.end)}<br>'
            f'Account lifecycle: {format_date(coverage.window.start)} – '
            f'{format_date(coverage.window.end)}<br>Mountain Time · USD<br>'
            f'{html.escape(data_source_label())}<br>'
            f'Mock data: {source_link("Kaggle dataset ↗")}</div>'
        )
        st.button("Refresh data", on_click=_refresh, icon=":material/refresh:", width="stretch",
                  type="tertiary")

    filters = DashboardFilters(period, coverage.window, SegmentFilters(**selections))
    st.session_state[_FILTERS_STATE] = filters
    st.session_state["data_coverage"] = coverage
    return filters


def current_filters() -> DashboardFilters:
    return st.session_state[_FILTERS_STATE]


def current_coverage() -> repository.DataCoverage:
    return st.session_state["data_coverage"]


def granularity_control(page_key: str, default: str = "Monthly") -> str:
    """Daily / Weekly / Monthly toggle. The choice is shared across pages."""
    shared = st.session_state.setdefault("granularity", default)
    widget_key = f"granularity_{page_key}"

    def _sync() -> None:
        if st.session_state.get(widget_key):
            st.session_state["granularity"] = st.session_state[widget_key]

    value = st.segmented_control("Granularity", GRANULARITIES, default=shared, key=widget_key,
                                 on_change=_sync, label_visibility="collapsed")
    return value or shared


def dimension_control(page_key: str) -> str:
    """Dimension switcher for segmentation charts. Returns the dimension key."""
    labels = [d.short for d in DIMENSIONS]
    shared = st.session_state.setdefault("dimension", labels[0])
    widget_key = f"dimension_{page_key}"

    def _sync() -> None:
        if st.session_state.get(widget_key):
            st.session_state["dimension"] = st.session_state[widget_key]

    value = st.segmented_control("Dimension", labels, default=shared, key=widget_key,
                                 on_change=_sync, label_visibility="collapsed") or shared
    return next(d.key for d in DIMENSIONS if d.short == value)
