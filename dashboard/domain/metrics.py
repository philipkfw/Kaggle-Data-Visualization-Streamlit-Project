"""Metric and lifecycle-stage registry.

Each entry maps a dashboard metric to the Gold mart column that already implements
the dbt definition (see the dbt project's docs/metrics.md). Nothing is redefined
here - this is labels, formats and the fixed colour identity of each metric.
"""

from __future__ import annotations

from dataclasses import dataclass

from dashboard.ui import palette


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    column: str  # Column in the Gold mart.
    kind: str  # "currency" | "count"
    color: str
    definition: str
    date_basis: str


GPV = Metric(
    "gpv", "Gross Payment Volume", "gpv_usd", "currency", palette.GPV,
    "SUM(amount_usd) of all payment transactions, all payment methods, converted to USD "
    "at transaction-date FX rates.",
    "Payment date (MT)",
)
GPV_ELECTRONIC = Metric(
    "gpv_electronic", "Electronic GPV", "gpv_electronic_usd", "currency", palette.GPV,
    "GPV from Credit Card, ACH and Paypal.", "Payment date (MT)",
)
GPV_OFFLINE = Metric(
    "gpv_offline", "Offline GPV", "gpv_offline_usd", "currency", palette.GPV_SECONDARY,
    "GPV from Cash and Cheque (recorded manually).", "Payment date (MT)",
)
PAYMENT_COUNT = Metric(
    "payment_count", "Payments", "payment_count", "count", palette.GPV,
    "COUNT(transaction_id).", "Payment date (MT)",
)
INVOICE_COUNT = Metric(
    "invoice_count", "Invoice Volume", "invoice_count", "count", palette.INVOICE,
    "COUNT(DISTINCT invoice_id) - every invoice, paid or unpaid.",
    "Invoice created date (MT)",
)
INVOICE_AMOUNT = Metric(
    "invoice_amount", "Invoice Dollar Volume", "invoice_amount_usd", "currency", palette.INVOICE,
    "SUM(invoice_amount_usd), converted at invoice-created-date FX rates.",
    "Invoice created date (MT)",
)
TOTAL_ACCOUNTS = Metric(
    "total_accounts", "Total Accounts", "total_accounts", "count", palette.TOTAL_ACCOUNTS,
    "All accounts signed up by end of day (sum of all lifecycle stages).",
    "Snapshot date (end of day, MT)",
)
SUBSCRIBED_ACCOUNTS = Metric(
    "subscribed_accounts", "Subscribed Accounts", "subscribed_accounts", "count",
    palette.SUBSCRIBED,
    "Accounts whose end-of-day lifecycle stage is subscribed.",
    "Snapshot date (end of day, MT)",
)


@dataclass(frozen=True)
class LifecycleStage:
    key: str  # Value of lifecycle_stage in the dbt models.
    label: str
    column: str  # Stock column in mart_account_lifecycle.
    color: str
    description: str


# Order = natural lifecycle progression; also the stacking order in charts.
LIFECYCLE_STAGES: tuple[LifecycleStage, ...] = (
    LifecycleStage("pre_trial", "Pre-trial", "pre_trial_accounts", palette.STAGE_PRE_TRIAL,
                   "Signed up, no trial event yet (derived stage)."),
    LifecycleStage("trial", "Trial", "trial_accounts", palette.STAGE_TRIAL,
                   "Most recent lifecycle event is a trial start."),
    LifecycleStage("subscribed", "Subscribed", "subscribed_accounts", palette.STAGE_SUBSCRIBED,
                   "Most recent lifecycle event is a subscription."),
    LifecycleStage("churned", "Churned", "churned_accounts", palette.STAGE_CHURNED,
                   "Account has churned (terminal stage)."),
)
STAGE_COLUMNS = tuple(stage.column for stage in LIFECYCLE_STAGES)


@dataclass(frozen=True)
class Dimension:
    key: str  # Column name in the marts and dim_accounts.
    label: str
    plural: str
    short: str  # Compact label for toggles.


DIMENSIONS: tuple[Dimension, ...] = (
    Dimension("country", "Country", "Countries", "Country"),
    Dimension("region", "Region", "Regions", "Region"),
    Dimension("city", "City", "Cities", "City"),
    Dimension("sign_up_platform", "Sign-up platform", "Platforms", "Platform"),
)
DIMENSION_KEYS = frozenset(d.key for d in DIMENSIONS)
DIMENSIONS_BY_LABEL = {d.label: d for d in DIMENSIONS}
