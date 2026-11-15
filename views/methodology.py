"""Definitions & Data Notes: what each number means and its known limitations."""

import pandas as pd
import streamlit as st

from dashboard.config import DASHBOARD_OWNER, DATA_SOURCE_URL, data_source_label
from dashboard.domain import metrics as m
from dashboard.ui import layout
from dashboard.ui.filters import current_coverage
from dashboard.utils.date_utils import format_date

coverage = current_coverage()

st.html(f"""
<div class="page-header">
  <div class="page-eyebrow">Reference</div>
  <div class="page-title">Definitions & Data Notes</div>
  {layout.owner_byline()}
</div>""")

with layout.card("About this data", "Mock data for a portfolio project", key="about"):
    st.markdown(f"""
Dashboard owner: **{DASHBOARD_OWNER}**. Designed and built as a portfolio project.

This dashboard uses **mock (synthetic) data** from a public Kaggle dataset describing a
field-service SaaS business: [view the dataset on Kaggle ↗]({DATA_SOURCE_URL}).
The figures are illustrative and do not represent any real company's performance.

- **Raw data:** six CSV extracts. 200 accounts with sign-up platform and geography,
  427 lifecycle events (trial, subscribed, churned), 609 invoices with 1,848 line items,
  and 435 payments.
- **Pipeline:** the CSVs were loaded into Snowflake and modelled with dbt from Bronze to
  Silver to Gold. That includes timezone conversion to Mountain Time, conversion to USD at
  Federal Reserve H.10 rates, and daily lifecycle snapshots, with 176 data tests.
- **This app** reads only the Gold reporting tables. It runs from a verified snapshot of
  them, so it works without a live warehouse connection.
""")

st.space("small")
with layout.card("Metric definitions",
                 "All definitions come from the dbt project; the dashboard does not redefine them",
                 key="defs"):
    rows = [(x.label, x.definition, x.date_basis, "USD" if x.kind == "currency" else "Count")
            for x in (m.GPV, m.GPV_ELECTRONIC, m.GPV_OFFLINE, m.PAYMENT_COUNT, m.INVOICE_COUNT,
                      m.INVOICE_AMOUNT, m.TOTAL_ACCOUNTS)]
    rows += [(f"{s.label} accounts", s.description, "Snapshot date (end of day, MT)", "Count")
             for s in m.LIFECYCLE_STAGES]
    st.dataframe(pd.DataFrame(rows, columns=["Metric", "Definition", "Date basis", "Unit"]),
                 hide_index=True, width="stretch")

st.space("small")
with layout.card("How the numbers are calculated", key="calc"):
    st.markdown(f"""
- **Source.** Every figure is aggregated in SQL from the dbt Gold reporting marts:
  `mart_financial_performance` (GPV and invoices) and `mart_account_lifecycle` (accounts).
  These marts are reconciled to the source data by dbt tests on every build. Current
  source: {data_source_label()}.
- **Mountain Time.** Source timestamps are converted to `America/Denver` once, in dbt, using
  IANA timezone rules (daylight saving time is handled automatically). Daily, weekly
  (Monday-start) and monthly buckets use those Mountain Time dates. The app performs no
  further timezone conversion.
- **USD.** Payments and invoices are converted to USD in dbt using Federal Reserve H.10 rates
  for the transaction date (payments) or invoice created date (invoices). The app reads the
  USD columns directly.
- **Account counts are point-in-time.** They are end-of-day balances and are never summed
  across dates. A period's value is the balance on its last day; trends show each week's or
  month's closing balance.
- **Previous period.** Whole calendar months compare with the same number of preceding
  months; other ranges compare with the equal-length window immediately before. When that
  window starts before the data ({format_date(coverage.window.start)}), no comparison is
  shown. When the previous value is zero, the change shows "n/a".
- **Segments** use each account's current country, region, city and sign-up platform.
""")

st.space("small")
with layout.card("Known data limitations", key="limits"):
    st.markdown(f"""
- **Coverage differs by metric.** Payments and invoices run from
  {format_date(coverage.financial.start)} to {format_date(coverage.financial.end)}; lifecycle
  data runs to {format_date(coverage.window.end)}. Financial activity also declines sharply
  after February 2025.
- **GPV includes all payment methods**, including manually recorded cash and cheques
  (shown separately as *Offline GPV*). There is no refund, failure or reversal status, so no
  transactions are excluded.
- **Invoice Volume counts every invoice**, paid or unpaid; the source has no invoice status.
- **Stale trials.** Some accounts have stayed in Trial for more than 90 days with no further
  event; the source has no trial-expiry event, so they remain counted as Trial.
- **Post-churn activity.** A small number of invoices and payments are dated after the
  account churned; they are included in all metrics, as in dbt.
- **Region is not hierarchical.** The same city can appear under two regions, so the region,
  city and country filters work independently and narrow each other's options.
- **Source timezone assumption.** The source timestamps are assumed to be UTC (dbt
  `source_timezone`).
""")

layout.footer(coverage.window.end)
