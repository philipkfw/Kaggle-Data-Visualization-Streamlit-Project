"""GPV Analysis: Gross Payment Volume trends, segmentation and detail."""

import streamlit as st

from dashboard.config import TOP_N_CATEGORIES
from dashboard.data import repository
from dashboard.domain import metrics as m
from dashboard.ui import charts, layout, tables
from dashboard.ui.filters import (current_coverage, current_filters, dimension_control,
                                  granularity_control)
from dashboard.ui.kpi_cards import KpiSpec, kpi_row
from dashboard.utils import formatting as fmt

filters = current_filters()
coverage = current_coverage()
comparison = filters.comparison

layout.page_header("Payments", "GPV Analysis", filters)

totals = repository.financial_totals(filters)
cur, prev = totals.current, totals.previous
offline_share = cur["gpv_offline_usd"] / cur["gpv_usd"] if cur["gpv_usd"] else None
kpi_row([
    KpiSpec(m.GPV, cur["gpv_usd"], prev["gpv_usd"] if prev else None, comparison),
    KpiSpec(m.GPV_ELECTRONIC, cur["gpv_electronic_usd"],
            prev["gpv_electronic_usd"] if prev else None, comparison),
    KpiSpec(m.GPV_OFFLINE, cur["gpv_offline_usd"],
            prev["gpv_offline_usd"] if prev else None, comparison,
            tooltip=f"{m.GPV_OFFLINE.definition} {fmt.percent(offline_share)} of GPV in this period."),
    KpiSpec(m.PAYMENT_COUNT, cur["payment_count"],
            prev["payment_count"] if prev else None, comparison),
])
layout.financial_coverage_note(filters, coverage.financial)

st.space("small")
with layout.card("GPV over time",
                 "Payment date (MT) · USD" + (" · grey line = previous period" if comparison else ""),
                 key="gpv_trend", controls=lambda: granularity_control("gpv")) as granularity:
    trend = repository.financial_trend(filters.period, filters.segments, granularity)
    previous = (repository.financial_trend(comparison, filters.segments, granularity)
                if comparison else None)
    charts.show(charts.trend_line(trend, m.GPV, granularity, previous, height=320),
                key="gpv_trend_chart")

st.space("small")
with layout.card("GPV by segment", "Ranked by GPV in the selected period"
                 + (" · grey = previous period" if comparison else ""),
                 key="gpv_segments", controls=lambda: dimension_control("gpv")) as dimension:
    label = next(d.label for d in m.DIMENSIONS if d.key == dimension)
    by_segment = repository.financial_by_dimension(filters, dimension)
    charts.show(charts.ranked_bars(by_segment, m.GPV, label, TOP_N_CATEGORIES,
                                   previous_column="prior_gpv_usd" if comparison else None),
                key="gpv_segment_chart")

st.space("small")
with layout.card("GPV by geography and platform",
                 "One row per country × region × city × sign-up platform with activity",
                 key="gpv_detail"):
    detail = repository.financial_detail(filters)
    detail = detail[detail["payment_count"] > 0].copy()
    total_gpv = detail["gpv_usd"].sum()
    detail["gpv_share"] = detail["gpv_usd"] / total_gpv if total_gpv else 0.0
    tables.detail_table(detail, {
        **tables.DIMENSION_COLUMNS,
        "gpv_usd": tables.usd_column("GPV", m.GPV.definition),
        "gpv_electronic_usd": tables.usd_column("Electronic GPV", m.GPV_ELECTRONIC.definition),
        "gpv_offline_usd": tables.usd_column("Offline GPV", m.GPV_OFFLINE.definition),
        "payment_count": tables.count_column("Payments"),
        "gpv_share": tables.share_column("Share of GPV"),
    }, file_name="gpv_by_segment.csv", key="gpv_detail")

layout.footer(coverage.window.end)
