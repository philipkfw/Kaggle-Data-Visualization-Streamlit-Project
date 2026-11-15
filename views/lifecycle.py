"""Account Lifecycle: stage distribution, history, flows and segmentation."""

import streamlit as st

from dashboard.config import TOP_N_CATEGORIES
from dashboard.data import repository
from dashboard.domain import metrics as m
from dashboard.domain.metrics import LIFECYCLE_STAGES, Metric
from dashboard.ui import charts, layout, palette, tables
from dashboard.ui.filters import (current_coverage, current_filters, dimension_control,
                                  granularity_control)
from dashboard.ui.kpi_cards import KpiSpec, kpi_row
from dashboard.utils import formatting as fmt
from dashboard.utils.date_utils import format_date

filters = current_filters()
coverage = current_coverage()
comparison = filters.comparison
as_of = filters.period.end

layout.page_header("Accounts", "Account Lifecycle", filters)

totals = repository.lifecycle_totals(filters)
cur, prev = totals.current, totals.previous


def stage_metric(stage) -> Metric:
    return Metric(stage.key, f"{stage.label} Accounts", stage.column, "count", stage.color,
                  stage.description, "Snapshot date (end of day, MT)")


trial, subscribed, churned = (s for s in LIFECYCLE_STAGES if s.key != "pre_trial")
kpi_row([
    KpiSpec(m.TOTAL_ACCOUNTS, cur["total_accounts"], prev["total_accounts"] if prev else None,
            comparison, as_of=as_of),
    KpiSpec(stage_metric(trial), cur[trial.column], prev[trial.column] if prev else None,
            comparison, as_of=as_of),
    KpiSpec(stage_metric(subscribed), cur[subscribed.column],
            prev[subscribed.column] if prev else None, comparison, as_of=as_of),
    KpiSpec(stage_metric(churned), cur[churned.column], prev[churned.column] if prev else None,
            comparison, as_of=as_of, higher_is_better=False),
])

stale = repository.stale_trials(filters.segments)
if stale["stale_trial_accounts"]:
    layout.note(
        f"<b>{stale['stale_trial_accounts']} of {stale['trial_accounts']}</b> accounts currently "
        f"in Trial (as of {format_date(coverage.window.end)}) have been in trial for more than "
        "90 days with no further lifecycle event. The source has no trial-expiry event, so they "
        "are reported as recorded (dbt flag <code>is_stale_trial</code>); the Trial count "
        "likely overstates live trials."
    )

st.space("small")
left, right = st.columns([2, 3], gap="medium")
with left:
    with layout.card("Lifecycle stage distribution",
                     f"Share of {fmt.count_full(cur['total_accounts'])} accounts on "
                     f"{format_date(as_of)}", key="lc_distribution"):
        charts.show(charts.stage_distribution(cur, height=230), key="lc_distribution_chart")
with right:
    with layout.card("Stage mix by segment", f"Share of accounts per stage on {format_date(as_of)}",
                     key="lc_mix", controls=lambda: dimension_control("lifecycle")) as dimension:
        label = next(d.label for d in m.DIMENSIONS if d.key == dimension)
        by_segment = repository.lifecycle_by_dimension(filters, dimension)
        charts.show(charts.stage_mix_by_segment(by_segment, TOP_N_CATEGORIES, label),
                    key="lc_mix_chart")

st.space("small")


def trend_controls():
    granularity = granularity_control("lifecycle")
    share = st.segmented_control("Scale", ["Count", "Share"], default="Count",
                                 key="lc_scale", label_visibility="collapsed") or "Count"
    return granularity, share == "Share"


with layout.card("Accounts by lifecycle stage over time",
                 "Balance at the end of each period (a partial last period uses its last day)",
                 key="lc_trend", controls=trend_controls) as (granularity, as_share):
    trend = repository.lifecycle_trend(filters, granularity)
    charts.show(charts.stage_trend(trend, granularity, as_share=as_share), key="lc_trend_chart")

st.space("small")
PER = {"Daily": "day", "Weekly": "week", "Monthly": "month"}
with layout.card("Lifecycle flows", f"Events per {PER[granularity]} · sign-up date and "
                 "lifecycle event date (MT)", key="lc_flows"):
    flows = repository.lifecycle_flows(filters, granularity)
    charts.show(charts.multi_line(flows, [
        ("new_sign_ups", "New sign-ups", palette.TOTAL_ACCOUNTS),
        ("new_trials", "Trials started", palette.STAGE_TRIAL),
        ("new_subscriptions", "New subscriptions", palette.STAGE_SUBSCRIBED),
        ("new_churns", "Churns", palette.STAGE_CHURNED),
    ], granularity), key="lc_flows_chart")

st.space("small")
with layout.card("Account distribution by geography and platform",
                 f"Accounts per lifecycle stage on {format_date(as_of)}", key="lc_detail"):
    detail = repository.lifecycle_detail(filters)
    detail = detail[detail["total_accounts"] > 0].copy()
    for stage in LIFECYCLE_STAGES:
        detail[f"{stage.key}_share"] = detail[stage.column] / detail["total_accounts"]
    tables.detail_table(detail, {
        **tables.DIMENSION_COLUMNS,
        "total_accounts": tables.count_column("Total accounts"),
        **{stage.column: tables.count_column(stage.label, stage.description)
           for stage in LIFECYCLE_STAGES},
        "subscribed_share": tables.share_column("% subscribed"),
        "churned_share": tables.share_column("% churned"),
    }, file_name="accounts_by_lifecycle_stage.csv", key="lc_detail")

layout.footer(coverage.window.end)
