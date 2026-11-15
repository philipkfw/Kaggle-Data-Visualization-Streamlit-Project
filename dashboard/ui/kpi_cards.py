"""KPI cards - identical structure and dimensions everywhere."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date

import streamlit as st

from dashboard.domain.metrics import Metric
from dashboard.utils import formatting as fmt
from dashboard.utils.date_utils import Period, format_date


@dataclass(frozen=True)
class KpiSpec:
    metric: Metric
    current: float
    previous: float | None  # None = no valid comparison period.
    comparison: Period | None
    higher_is_better: bool = True
    label: str | None = None  # Overrides metric.label.
    tooltip: str | None = None
    # Stock metrics (account counts) are point-in-time: name the snapshot dates.
    as_of: date | None = None


def _delta_html(spec: KpiSpec) -> str:
    if spec.previous is None or spec.comparison is None:
        if spec.as_of:
            return f"<span>As of {format_date(spec.as_of)} · no comparison</span>"
        return "<span>No comparable previous period</span>"
    previous_text = fmt.format_value(spec.previous, spec.metric.kind)
    reference = (f"vs {previous_text} on {format_date(spec.comparison.end)}" if spec.as_of
                 else f"vs {previous_text} previous period")
    change = fmt.pct_change(spec.current, spec.previous)
    if change is None:  # Zero base: show the prior value, never a fake %.
        return f'<span class="delta flat">n/a</span><span>{reference}</span>'
    if abs(change) < 0.0005:
        tone, arrow = "flat", "■"
    else:
        improving = (change > 0) == spec.higher_is_better
        tone, arrow = ("good" if improving else "bad"), ("▲" if change > 0 else "▼")
    return (f'<span class="delta {tone}">{arrow} {fmt.signed_percent(change).lstrip("+-")}</span>'
            f'<span>{reference}</span>')


def _card_html(spec: KpiSpec) -> str:
    metric = spec.metric
    label = spec.label or metric.label
    tooltip = spec.tooltip or metric.definition
    full_value = fmt.format_value(spec.current, metric.kind, compact=False)
    title = f"{full_value} — {tooltip}"
    if spec.comparison is not None:
        title += f" Previous period: {spec.comparison.label()}."
    return f"""
<div class="kpi" title="{html.escape(title)}">
  <div class="kpi-label"><span class="kpi-dot" style="background:{metric.color}"></span>
    {html.escape(label)}</div>
  <div class="kpi-value">{fmt.format_value(spec.current, metric.kind)}</div>
  <div class="kpi-foot">{_delta_html(spec)}</div>
</div>"""


def kpi_row(specs: list[KpiSpec]) -> None:
    columns = st.columns(len(specs), gap="small")
    for column, spec in zip(columns, specs):
        with column:
            st.html(_card_html(spec))
