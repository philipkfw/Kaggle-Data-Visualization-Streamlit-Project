"""Invoice Analysis: invoice volume (count) and invoice dollar volume."""

import streamlit as st

from dashboard.config import TOP_N_CATEGORIES
from dashboard.data import repository
from dashboard.domain import metrics as m
from dashboard.domain.metrics import Metric
from dashboard.ui import charts, layout, tables
from dashboard.ui.filters import (current_coverage, current_filters, dimension_control,
                                  granularity_control)
from dashboard.ui.kpi_cards import KpiSpec, kpi_row

filters = current_filters()
coverage = current_coverage()
comparison = filters.comparison

layout.page_header("Invoicing", "Invoice Analysis", filters)


def average_invoice(values: dict | None) -> float | None:
    """Derived ratio of two dbt metrics; None when there are no invoices."""
    if not values or not values["invoice_count"]:
        return None
    return values["invoice_amount_usd"] / values["invoice_count"]


AVERAGE_INVOICE = Metric(
    "avg_invoice", "Average Invoice Value", "avg_invoice_usd", "currency", m.INVOICE_COUNT.color,
    "Invoice Dollar Volume ÷ Invoice Volume (derived from the two dbt metrics).",
    m.INVOICE_COUNT.date_basis,
)

totals = repository.financial_totals(filters)
cur, prev = totals.current, totals.previous
avg_cur, avg_prev = average_invoice(cur), average_invoice(prev)
kpi_row([
    KpiSpec(m.INVOICE_COUNT, cur["invoice_count"], prev["invoice_count"] if prev else None,
            comparison),
    KpiSpec(m.INVOICE_AMOUNT, cur["invoice_amount_usd"],
            prev["invoice_amount_usd"] if prev else None, comparison),
    KpiSpec(AVERAGE_INVOICE, avg_cur if avg_cur is not None else float("nan"),
            avg_prev if prev else None, comparison),
])
layout.financial_coverage_note(filters, coverage.financial)

st.space("small")
MEASURES = {"Invoice count": m.INVOICE_COUNT, "Invoice dollar volume": m.INVOICE_AMOUNT}
measure_label = st.segmented_control("Measure", list(MEASURES), default="Invoice count",
                                     key="invoice_measure") or "Invoice count"
metric = MEASURES[measure_label]

with layout.card(f"{metric.label} over time",
                 "Invoice created date (MT)" + (" · USD" if metric.kind == "currency" else "")
                 + (" · grey line = previous period" if comparison else ""),
                 key="inv_trend", controls=lambda: granularity_control("invoices")) as granularity:
    trend = repository.financial_trend(filters.period, filters.segments, granularity)
    previous = (repository.financial_trend(comparison, filters.segments, granularity)
                if comparison else None)
    charts.show(charts.trend_line(trend, metric, granularity, previous, height=320),
                key="inv_trend_chart")

st.space("small")
with layout.card(f"{metric.label} by segment",
                 f"Ranked by {metric.label.lower()} in the selected period"
                 + (" · grey = previous period" if comparison else ""),
                 key="inv_segments", controls=lambda: dimension_control("invoices")) as dimension:
    label = next(d.label for d in m.DIMENSIONS if d.key == dimension)
    by_segment = repository.financial_by_dimension(filters, dimension)
    charts.show(charts.ranked_bars(by_segment, metric, label, TOP_N_CATEGORIES,
                                   previous_column=f"prior_{metric.column}" if comparison else None),
                key="inv_segment_chart")

st.space("small")
with layout.card("Invoices by geography and platform",
                 "One row per country × region × city × sign-up platform with invoices",
                 key="inv_detail"):
    detail = repository.financial_detail(filters)
    detail = detail[detail["invoice_count"] > 0].copy()
    detail["avg_invoice_usd"] = detail["invoice_amount_usd"] / detail["invoice_count"]
    total = detail["invoice_count"].sum()
    detail["invoice_share"] = detail["invoice_count"] / total if total else 0.0
    detail = detail.sort_values("invoice_count", ascending=False)
    tables.detail_table(detail, {
        **tables.DIMENSION_COLUMNS,
        "invoice_count": tables.count_column("Invoices", m.INVOICE_COUNT.definition),
        "invoice_amount_usd": tables.usd_column("Invoice $ volume", m.INVOICE_AMOUNT.definition),
        "avg_invoice_usd": tables.usd_column("Avg invoice value", AVERAGE_INVOICE.definition),
        "invoice_share": tables.share_column("Share of invoices"),
    }, file_name="invoices_by_segment.csv", key="inv_detail")

layout.footer(coverage.window.end)
