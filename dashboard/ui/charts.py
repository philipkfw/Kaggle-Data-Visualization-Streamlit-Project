"""Reusable Plotly charts. No pie or donut charts, no 3D, no animation.

Conventions (from the design system):
* One metric = one colour (metrics.Metric.color); lifecycle stages use their fixed
  colours; previous periods are always muted grey.
* Lines 2px; bars <= 24px thick with 4px rounded data ends; hairline grids.
* A legend only when there are 2+ series; single series are named by the card title.
* Tooltips use full-precision values; axes and labels use compact values.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.domain.metrics import LIFECYCLE_STAGES, Metric
from dashboard.ui import palette as p
from dashboard.ui.theme import TEMPLATE_NAME
from dashboard.utils import formatting as fmt
from dashboard.utils.date_utils import format_bucket

_PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}
_FULL_BUCKET_DAYS = {"Daily": lambda d: 1, "Weekly": lambda d: 7,
                     "Monthly": lambda d: pd.Timestamp(d).days_in_month}


def show(fig: go.Figure, key: str) -> None:
    # Explicit template + backgrounds: Streamlit's frontend substitutes its own theme
    # colours for any background left unset on the figure itself.
    fig.update_layout(template=TEMPLATE_NAME, paper_bgcolor=p.SURFACE, plot_bgcolor=p.SURFACE)
    st.plotly_chart(fig, theme=None, config=_PLOTLY_CONFIG, key=key, width="stretch")


def _value_axis(fig: go.Figure, max_value: float, kind: str, axis: str = "yaxis") -> None:
    """Clean round ticks formatted with the app's own number rules."""
    ticks = fmt.nice_ticks(max_value)
    labels = [fmt.format_value(t, kind) for t in ticks]
    fig.update_layout({axis: dict(tickmode="array", tickvals=ticks, ticktext=labels,
                                  range=[0, ticks[-1] * 1.02])})


def _bucket_labels(frame: pd.DataFrame, granularity: str, start_col: str = "period_start",
                   days_col: str = "days_in_bucket") -> list[str]:
    """Bucket labels, flagging buckets clipped by the selected date range."""
    labels = []
    for start, first_day, days in zip(frame[start_col], frame["first_day"], frame[days_col]):
        label = format_bucket(start, granularity)
        full = _FULL_BUCKET_DAYS[granularity](start)
        if days < full:
            label += f" (partial: {days} of {full} days from {first_day:%b} {first_day.day})"
        labels.append(label)
    return labels


def _empty(fig_height: int, message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(color=p.TEXT_MUTED, size=13),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_layout(height=fig_height, xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


# --- Time series ------------------------------------------------------------------------

def trend_line(frame: pd.DataFrame, metric: Metric, granularity: str,
               previous: pd.DataFrame | None = None, height: int = 300) -> go.Figure:
    """Single-metric line over time, optionally with the previous period overlaid.

    The previous period is aligned bucket-by-bucket (1st bucket over 1st bucket) so
    shapes compare directly; its tooltip names its real dates.
    """
    if frame.empty:
        return _empty(height, "No data for the selected period")
    x = pd.to_datetime(frame["period_start"])
    labels = _bucket_labels(frame, granularity)
    values = frame[metric.column].astype(float)
    show_markers = len(frame) <= 31
    fig = go.Figure()
    max_value = values.max()

    if previous is not None and not previous.empty:
        prior = previous.iloc[: len(frame)]
        prior_values = prior[metric.column].astype(float)
        max_value = max(max_value, prior_values.max())
        prior_labels = _bucket_labels(prior, granularity)
        fig.add_trace(go.Scatter(
            x=x[: len(prior)], y=prior_values, name="Previous period", mode="lines",
            line=dict(color=p.PREVIOUS_PERIOD, width=2),
            customdata=list(zip(prior_labels, [fmt.format_value(v, metric.kind, False)
                                               for v in prior_values])),
            hovertemplate="Previous · %{customdata[0]}: <b>%{customdata[1]}</b><extra></extra>",
        ))

    fig.add_trace(go.Scatter(
        x=x, y=values, name="Selected period",
        mode="lines+markers" if show_markers else "lines",
        line=dict(color=metric.color, width=2, shape="linear"),
        marker=dict(size=8, color=metric.color, line=dict(color=p.SURFACE, width=2)),
        fill="tozeroy", fillcolor=p.with_alpha(metric.color, 0.08),
        customdata=list(zip(labels, [fmt.format_value(v, metric.kind, False) for v in values])),
        hovertemplate=f"{metric.label} · %{{customdata[0]}}: <b>%{{customdata[1]}}</b><extra></extra>",
    ))
    _value_axis(fig, max_value, metric.kind)
    fig.update_layout(
        height=height, hovermode="x unified" if previous is not None else "closest",
        showlegend=previous is not None and not previous.empty,
        xaxis=dict(hoverformat=" ", showspikes=True, spikemode="across", spikethickness=1,
                   spikecolor=p.AXIS, spikedash="solid"),
    )
    if fig.layout.showlegend:
        fig.update_layout(margin=dict(t=36))
    return fig


def stage_trend(frame: pd.DataFrame, granularity: str, as_share: bool = False,
                height: int = 340) -> go.Figure:
    """Accounts by lifecycle stage over time (end-of-bucket balances).

    Stacked columns for weekly/monthly; a stacked area for daily (too many columns).
    """
    if frame.empty:
        return _empty(height, "No data for the selected period")
    x = pd.to_datetime(frame["period_start"])
    totals = frame["total_accounts"].replace(0, pd.NA)
    labels = [format_bucket(s, granularity) + f" (as of {e:%b} {e.day}, {e.year})"
              for s, e in zip(frame["period_start"], frame["period_end"])]
    fig = go.Figure()
    for stage in LIFECYCLE_STAGES:
        counts = frame[stage.column].astype(int)
        shares = (counts / totals).astype(float).fillna(0.0)
        y = shares if as_share else counts
        custom = list(zip(labels, [fmt.count_full(c) for c in counts],
                          [fmt.percent(s) for s in shares]))
        hover = (f"{stage.label}: <b>%{{customdata[1]}}</b> (%{{customdata[2]}})<extra></extra>")
        if granularity == "Daily":
            fig.add_trace(go.Scatter(
                x=x, y=y, name=stage.label, stackgroup="stages", mode="lines",
                line=dict(width=0.5, color=p.SURFACE), fillcolor=p.with_alpha(stage.color, 0.85),
                customdata=custom, hovertemplate=hover,
            ))
        else:
            fig.add_trace(go.Bar(
                x=x, y=y, name=stage.label, marker=dict(color=stage.color,
                                                        line=dict(color=p.SURFACE, width=1)),
                customdata=custom, hovertemplate=hover,
            ))
    fig.update_layout(
        height=height, barmode="stack", bargap=0.45, barcornerradius=0, hovermode="x unified",
        showlegend=True, margin=dict(t=36), legend=dict(traceorder="normal"),
        xaxis=dict(hoverformat=" "),
    )
    if as_share:
        fig.update_yaxes(tickformat=".0%", range=[0, 1], tickvals=[0, .25, .5, .75, 1])
    else:
        _value_axis(fig, frame["total_accounts"].max(), "count")
    # Unified-hover header: the bucket label of the first trace.
    fig.data[0].hovertemplate = ("<b>%{customdata[0]}</b><br>" + fig.data[0].hovertemplate)
    return fig


def multi_line(frame: pd.DataFrame, series: Sequence[tuple[str, str, str]], granularity: str,
               height: int = 300) -> go.Figure:
    """Several count series over time. `series` = (column, label, colour)."""
    if frame.empty:
        return _empty(height, "No data for the selected period")
    x = pd.to_datetime(frame["period_start"])
    labels = _bucket_labels(frame, granularity, days_col="days_in_bucket")
    fig = go.Figure()
    max_value = 0
    for i, (column, label, color) in enumerate(series):
        values = frame[column].astype(int)
        max_value = max(max_value, values.max())
        header = "<b>%{customdata[0]}</b><br>" if i == 0 else ""
        fig.add_trace(go.Scatter(
            x=x, y=values, name=label, mode="lines+markers" if len(frame) <= 31 else "lines",
            line=dict(color=color, width=2),
            marker=dict(size=8, color=color, line=dict(color=p.SURFACE, width=2)),
            customdata=list(zip(labels, [fmt.count_full(v) for v in values])),
            hovertemplate=header + f"{label}: <b>%{{customdata[1]}}</b><extra></extra>",
        ))
    _value_axis(fig, max_value, "count")
    fig.update_layout(height=height, hovermode="x unified", showlegend=True,
                      margin=dict(t=36), xaxis=dict(hoverformat=" "))
    return fig


# --- Categorical comparisons --------------------------------------------------------------

def ranked_bars(frame: pd.DataFrame, metric: Metric, category_label: str,
                top_n: int, previous_column: str | None = None) -> go.Figure:
    """Ranked horizontal bars (descending), optionally grouped with the previous period."""
    column = metric.column
    data = frame[frame[column] > 0] if previous_column is None else \
        frame[(frame[column] > 0) | (frame[previous_column] > 0)]
    data = data.sort_values(column, ascending=False)
    total = float(frame[column].sum())
    hidden = max(len(data) - top_n, 0)
    data = data.head(top_n).iloc[::-1]  # Largest at the top.
    if data.empty:
        return _empty(220, "No activity for the selected filters")

    grouped = previous_column is not None
    row_px = 46 if grouped else 34
    height = max(len(data) * row_px + (70 if grouped else 40), 180)
    values = data[column].astype(float)
    shares = values / total if total else values * 0
    fig = go.Figure()
    if grouped:
        prior = data[previous_column].astype(float)
        changes = [fmt.signed_percent(fmt.pct_change(c, b)) for c, b in zip(values, prior)]
        fig.add_trace(go.Bar(
            y=data["segment"], x=prior, orientation="h", name="Previous period",
            marker=dict(color=p.PREVIOUS_PERIOD),
            text=[fmt.format_value(v, metric.kind) for v in prior], textposition="outside",
            customdata=[fmt.format_value(v, metric.kind, False) for v in prior],
            hovertemplate="<b>%{y}</b><br>Previous period: %{customdata}<extra></extra>",
        ))
    fig.add_trace(go.Bar(
        y=data["segment"], x=values, orientation="h",
        name="Selected period" if grouped else metric.label,
        marker=dict(color=metric.color),
        text=[fmt.format_value(v, metric.kind) for v in values], textposition="outside",
        customdata=list(zip([fmt.format_value(v, metric.kind, False) for v in values],
                            [fmt.percent(s) for s in shares],
                            changes if grouped else [""] * len(values))),
        hovertemplate=("<b>%{y}</b><br>" + metric.label + ": %{customdata[0]}"
                       "<br>Share of total: %{customdata[1]}"
                       + ("<br>Change vs previous: %{customdata[2]}" if grouped else "")
                       + "<extra></extra>"),
    ))
    max_value = max(values.max(), data[previous_column].max() if grouped else 0)
    fig.update_traces(textfont=dict(size=11, color=p.TEXT_SECONDARY), cliponaxis=False)
    fig.update_layout(
        height=height, barmode="group", bargap=0.34 if not grouped else 0.22,
        bargroupgap=0.08, showlegend=grouped, margin=dict(t=36 if grouped else 8, r=56),
        xaxis=dict(visible=False, range=[0, max_value * 1.18 if max_value else 1]),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color=p.TEXT_SECONDARY),
                   title=dict(text="")),
    )
    if hidden:
        fig.add_annotation(text=f"+ {hidden} more {category_label.lower()} in the table below",
                           xref="paper", yref="paper", x=1, y=-0.02, xanchor="right",
                           yanchor="top", showarrow=False,
                           font=dict(size=11, color=p.TEXT_MUTED))
        fig.update_layout(margin=dict(b=28))
    return fig


def stage_distribution(snapshot: dict, height: int | None = None) -> go.Figure:
    """Accounts per lifecycle stage on one date, as horizontal bars in lifecycle order."""
    total = snapshot.get("total_accounts", 0)
    stages = list(LIFECYCLE_STAGES)[::-1]  # Plotly draws bottom-up; keep lifecycle order top-down.
    counts = [snapshot.get(s.column, 0) for s in stages]
    shares = [c / total if total else 0 for c in counts]
    fig = go.Figure(go.Bar(
        y=[s.label for s in stages], x=counts, orientation="h",
        marker=dict(color=[s.color for s in stages]),
        text=[f"{fmt.count_full(c)} · {fmt.percent(sh)}" for c, sh in zip(counts, shares)],
        textposition="outside", textfont=dict(size=12, color=p.TEXT_SECONDARY), cliponaxis=False,
        customdata=list(zip([fmt.count_full(c) for c in counts], [fmt.percent(s) for s in shares],
                            [s.description for s in stages])),
        hovertemplate="<b>%{y}</b>: %{customdata[0]} accounts (%{customdata[1]})"
                      "<br><span style='color:#667085'>%{customdata[2]}</span><extra></extra>",
    ))
    max_count = max(counts) if counts else 0
    fig.update_layout(
        height=height or len(stages) * 44 + 24, showlegend=False, bargap=0.38,
        margin=dict(r=90),
        xaxis=dict(visible=False, range=[0, max_count * 1.3 if max_count else 1]),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color=p.TEXT_SECONDARY)),
    )
    return fig


def stage_mix_by_segment(frame: pd.DataFrame, top_n: int, category_label: str) -> go.Figure:
    """100% stacked horizontal bars: lifecycle mix within each segment value."""
    data = frame[frame["total_accounts"] > 0].sort_values("total_accounts", ascending=False)
    hidden = max(len(data) - top_n, 0)
    data = data.head(top_n).iloc[::-1]
    if data.empty:
        return _empty(220, "No accounts for the selected filters")
    height = max(len(data) * 34 + 60, 200)
    labels = [f"{seg}  ·  {fmt.count_full(t)}" for seg, t in zip(data["segment"], data["total_accounts"])]
    fig = go.Figure()
    for stage in LIFECYCLE_STAGES:
        counts = data[stage.column].astype(int)
        shares = counts / data["total_accounts"]
        # In-segment labels only where they fit; the tooltip and table carry the rest.
        text = [fmt.percent(s, 0) if s >= 0.12 else "" for s in shares]
        dark_text = stage.key in ("trial", "pre_trial")
        fig.add_trace(go.Bar(
            y=labels, x=shares, orientation="h", name=stage.label,
            marker=dict(color=stage.color, line=dict(color=p.SURFACE, width=1.5)),
            text=text, textposition="inside", insidetextanchor="middle",
            textfont=dict(size=11, color=p.TEXT_PRIMARY if dark_text else "#FFFFFF"),
            customdata=list(zip(data["segment"], [fmt.count_full(c) for c in counts],
                                [fmt.percent(s) for s in shares])),
            hovertemplate=("<b>%{customdata[0]}</b><br>" + stage.label
                           + ": %{customdata[1]} (%{customdata[2]})<extra></extra>"),
        ))
    fig.update_layout(
        height=height, barmode="stack", bargap=0.3, barcornerradius=0, showlegend=True,
        margin=dict(t=36, r=20), legend=dict(traceorder="normal"),
        xaxis=dict(range=[0, 1], tickformat=".0%", tickvals=[0, .25, .5, .75, 1], showgrid=True,
                   gridcolor=p.GRID, showline=False, ticks=""),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color=p.TEXT_SECONDARY)),
        uniformtext=dict(minsize=10, mode="hide"),
    )
    if hidden:
        fig.add_annotation(text=f"+ {hidden} more {category_label.lower()} in the table below",
                           xref="paper", yref="paper", x=1, y=-0.12, xanchor="right",
                           showarrow=False, font=dict(size=11, color=p.TEXT_MUTED))
        fig.update_layout(margin=dict(b=40))
    return fig
