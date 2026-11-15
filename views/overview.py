"""Executive Overview: headline KPIs and the three core trends."""

import streamlit as st

from dashboard.data import repository
from dashboard.domain import metrics as m
from dashboard.ui import charts, layout
from dashboard.ui.filters import current_coverage, current_filters, granularity_control
from dashboard.ui.kpi_cards import KpiSpec, kpi_row
from dashboard.utils import formatting as fmt
from dashboard.utils.date_utils import format_date

filters = current_filters()
coverage = current_coverage()
comparison = filters.comparison

layout.page_header("Overview", "Executive Overview", filters)
layout.mock_data_banner()

financial = repository.financial_totals(filters)
accounts = repository.lifecycle_totals(filters)
prev_fin, prev_acc = financial.previous, accounts.previous

kpi_row([
    KpiSpec(m.GPV, financial.current["gpv_usd"],
            prev_fin["gpv_usd"] if prev_fin else None, comparison),
    KpiSpec(m.INVOICE_COUNT, financial.current["invoice_count"],
            prev_fin["invoice_count"] if prev_fin else None, comparison),
    KpiSpec(m.TOTAL_ACCOUNTS, accounts.current["total_accounts"],
            prev_acc["total_accounts"] if prev_acc else None, comparison,
            as_of=filters.period.end),
    KpiSpec(m.SUBSCRIBED_ACCOUNTS, accounts.current["subscribed_accounts"],
            prev_acc["subscribed_accounts"] if prev_acc else None, comparison,
            as_of=filters.period.end),
])

if comparison is not None:
    layout.financial_coverage_note(filters, coverage.financial)

st.space("small")
left, right = st.columns(2, gap="medium")
with left:
    with layout.card("Gross Payment Volume", "Payment date · USD", key="ov_gpv",
                     controls=lambda: granularity_control("overview")) as granularity:
        trend = repository.financial_trend(filters.period, filters.segments, granularity)
        previous = (repository.financial_trend(comparison, filters.segments, granularity)
                    if comparison else None)
        charts.show(charts.trend_line(trend, m.GPV, granularity, previous), key="ov_gpv_chart")
with right:
    with layout.card("Invoice Volume", "Distinct invoices · invoice created date",
                     key="ov_invoices"):
        charts.show(charts.trend_line(trend, m.INVOICE_COUNT, granularity, previous),
                    key="ov_invoice_chart")

st.space("small")
with layout.card(
    "Accounts by lifecycle stage",
    f"End-of-day snapshot on {format_date(filters.period.end)} · "
    f"{fmt.count_full(accounts.current['total_accounts'])} accounts",
    key="ov_stages",
):
    charts.show(charts.stage_distribution(accounts.current), key="ov_stage_chart")

layout.footer(coverage.window.end)
