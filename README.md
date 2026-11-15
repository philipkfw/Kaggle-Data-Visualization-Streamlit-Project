# Field Service Analytics Dashboard

An interactive Streamlit + Plotly dashboard for **Gross Payment Volume (GPV)**, **Invoice Volume** and **Accounts by lifecycle stage**. It reads the Gold reporting marts built in Snowflake by the companion dbt project, [Kaggle-Data-Modelling-Project](../Kaggle-Data-Modelling-Project).

The dbt project is the source of truth for every metric definition, the timezone conversion and the USD conversion. This app adds no business logic of its own: it filters the Gold marts, aggregates them in SQL, and presents the results.

**The dashboard runs with no Snowflake account.** A verified Parquet snapshot of the Gold tables ships in [`data/snapshot/`](data/snapshot/), and the app queries it with DuckDB by default. Live Snowflake is optional (see [Data backends](#data-backends)).

| Page | What it answers |
|---|---|
| **Executive Overview** | Headline KPIs vs the previous period; GPV and invoice trends; lifecycle stage distribution |
| **GPV Analysis** | GPV, electronic vs offline GPV and payments; trends; ranking by country, region, city or platform; detail table |
| **Invoice Analysis** | Invoice count vs invoice dollar volume; average invoice value; trends; segment ranking; detail table |
| **Account Lifecycle** | Stage counts and mix; stage history; lifecycle flows; stage mix by segment; detail table |
| **Definitions & Data Notes** | Metric definitions, calculation rules and known data limitations |

Every page shares the same sidebar filters: reporting period (presets or a custom range), country, region, city and sign-up platform. Every KPI, chart and table respects them.

---

## Data sources and metric mapping

The app reads only the `KAGGLE_DB.GOLD` tables, either from the bundled snapshot or live from Snowflake.

| Metric | Gold model · column | dbt definition | Date basis |
|---|---|---|---|
| Gross Payment Volume | `mart_financial_performance.gpv_usd` | `SUM(amount_usd)`, all payment methods | Payment date (MT) |
| Electronic / Offline GPV | `gpv_electronic_usd` / `gpv_offline_usd` | Card, ACH, Paypal / Cash, Cheque | Payment date (MT) |
| Invoice Volume | `mart_financial_performance.invoice_count` | `COUNT(DISTINCT invoice_id)`, paid or unpaid | Invoice created date (MT) |
| Invoice Dollar Volume | `invoice_amount_usd` | `SUM(invoice_amount_usd)` | Invoice created date (MT) |
| Accounts by stage | `mart_account_lifecycle.*_accounts` | End-of-day stage: pre-trial, trial, subscribed, churned | Snapshot date (MT) |
| Filter options | `dim_accounts` | Distinct country × region × city × platform | — |
| Calendar | `dim_date` | Day, ISO week (Monday start), month | — |

**Aggregation rules:**
- **Payments and invoices are fully additive.** They are summed across dates and segments. The two are aggregated separately in dbt, so they can never inflate each other.
- **Account counts are point-in-time balances.** They are summed across segments for a single date, and never across dates. A period shows its last day's balance; weekly and monthly trends show each bucket's closing balance.
- **Trend charts include empty periods.** They are driven from `dim_date`, so days with no activity show as zero instead of disappearing.
- **"Subscribed Accounts" is the active-accounts KPI.** It is an existing dbt stage; no new "active" definition was created.
- **Average invoice value is the only derived figure:** Invoice Dollar Volume ÷ Invoice Volume.

### Mountain Time and USD
- **Timezone:** dbt converts source timestamps to `America/Denver` once, using IANA rules, so daylight saving time is handled. The app reads those Mountain Time dates directly and never converts again. Both backends' session timezone is also set to `America/Denver`.
- **Date presets** count back from the last date in the data (Aug 12, 2025), not from today, because the data is a static snapshot.
- **USD:** amounts are converted in dbt at Federal Reserve H.10 rates. The app reads the `_usd` columns, with no conversion.
- **Formatting:** compact values (`$1.97M`, `$450K`) on cards, axes and labels; full values (`$1,968,622.53`) in tooltips and tables. All formatting is in [dashboard/utils/formatting.py](dashboard/utils/formatting.py).

### Period comparisons
- **Whole calendar months** compare with the same number of preceding months: Q3 → Q2, H2 → H1, a year → the prior year.
- **Any other range** compares with the equal-length window immediately before it.
- **If the comparison window starts before the data** (Jan 1, 2024), no comparison is shown, so the default "All data" view has none.
- **If the previous value is zero,** the change shows "n/a" instead of a misleading percentage.

---

## Getting started

### 1. Install
Requires Python 3.10+.
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt    # app + pytest (requirements.txt = app only)
```

### 2. Run
```bash
streamlit run app.py
```
Open http://localhost:8501. No configuration or credentials are needed: the app reads the bundled snapshot.

### 3. Test
```bash
pytest                                   # 33 tests, fully offline (incl. snapshot totals)
python scripts/validate_metrics.py       # 162 metric checks (snapshot by default)
```

---

## Data backends

| Backend | When | Needs |
|---|---|---|
| `duckdb` *(default)* | Always works: local, Streamlit Cloud, after the Snowflake account is gone | Nothing; the data is in `data/snapshot/` |
| `snowflake` | Live queries while a Snowflake account exists | `[snowflake]` credentials in secrets |

To choose a backend, set `data_backend` under `[app]` in `.streamlit/secrets.toml`, or the `DASHBOARD_DATA_BACKEND` environment variable.
- Both backends receive the **same SQL**: portable ANSI SQL plus `COUNT_IF`, with bind parameters.
- The DuckDB backend recreates the original `KAGGLE_DB.GOLD` names as views over the Parquet files, so queries are identical on both.

### The snapshot
- **Contents:** [`data/snapshot/`](data/snapshot/) holds all 10 Gold tables (the marts, dimensions and facts) plus the Bronze timestamp columns the validation script uses. That's 12 Parquet files, about 2 MB.
- **[`manifest.json`](data/snapshot/manifest.json)** records the export time, row counts and how many checksums were verified for each table. It holds no account or user identifiers.
- **Verification at export:** each table's row count and its SUM, MIN and MAX on every numeric and date column were compared between Snowflake and the written Parquet file. All 251 checksums matched.
- **Proven equivalent:** [`scripts/compare_backends.py`](scripts/compare_backends.py) ran every data function the dashboard uses, through both backends, across 4 filter scenarios and all granularities and dimensions. **All 90 result sets were identical.** The only differences were float rounding under $0.000001.
- **Protected by tests:** offline tests (`tests/test_snapshot.py`) check the snapshot's known totals ($1,968,622.53 GPV, 609 invoices, 61 / 51 / 88 accounts by stage), so any accidental change to the files is caught.

### Re-exporting the snapshot (only while Snowflake is available)
After rebuilding the dbt project:
```bash
python scripts/export_snapshot.py        # exports + verifies; replaces data/snapshot/ only if all checks pass
python scripts/compare_backends.py       # proves snapshot == live, result set by result set
python scripts/validate_metrics.py       # 162 checks against the snapshot
DASHBOARD_DATA_BACKEND=snowflake python scripts/validate_metrics.py   # ... and against live
```
Then commit `data/snapshot/`.

### Live Snowflake configuration (optional)
Credentials live in `.streamlit/secrets.toml`, which is **gitignored and never committed**. Copy [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example) and fill it in:
```toml
[app]
data_backend = "snowflake"

[snowflake]
account = "ORGNAME-ACCOUNTNAME"
user = "YOUR_USER"
role = "SYSADMIN"                 # or a read-only role (below)
warehouse = "COMPUTE_WH"
database = "KAGGLE_DB"
schema = "GOLD"                   # "DEV_GOLD" for the dbt dev target
private_key_file = "/Users/you/.snowflake/keys/rsa_key.p8"
```
- **Authentication** is key-pair. It reuses the same key and user as the dbt profile, so there's no password or MFA prompt.
- **On Streamlit Community Cloud,** use `private_key = """-----BEGIN PRIVATE KEY----- ..."""` instead of `private_key_file`.
- **For production,** use a read-only role with `SELECT` on Gold only. The dbt project's `docs/bi_connection.md` has the grants for a `REPORTER` role.

---

## Validation
[scripts/validate_metrics.py](scripts/validate_metrics.py) runs the app's own data functions and checks them against **independent SQL on the Gold fact tables** (`fct_payment_transactions`, `fct_invoices`, `fct_account_daily_status`). It works on either backend, runs 5 filter and date scenarios including a daylight-saving-transition week, and checks that:
- Totals and previous-period values match the fact tables.
- Electronic + offline GPV equals total GPV.
- There are no duplicate payments or invoices.
- Daily, weekly and monthly trends each sum to the totals and cover every day exactly once.
- Every segment breakdown and detail table sums to the totals.
- Stage counts match the daily status snapshot.
- No segment is NULL or 'Unknown'.
- Mountain Time dates match a fresh DST-aware conversion of the raw Bronze UTC timestamps, done with each engine's own timezone functions.

All 162 checks pass on both backends.

---

## Deploying to Streamlit Community Cloud
1. Push this repository to GitHub, including `data/snapshot/`. `secrets.toml` is excluded by `.gitignore`.
2. At [share.streamlit.io](https://share.streamlit.io), create an app from the repo, with main file `app.py`.
3. Deploy. **No secrets are needed**; the app uses the bundled snapshot. `requirements.txt` pins every dependency.
   - Only to query live Snowflake: under **Advanced settings → Secrets**, paste `[app] data_backend = "snowflake"` and the `[snowflake]` block, using `private_key` with the key contents.

---

## Project structure
```
app.py                        # Entry: page config, theme, shared sidebar, navigation
views/                        # One file per page
  overview.py  gpv.py  invoices.py  lifecycle.py  methodology.py
dashboard/
  config.py                   # App settings; data backend selection; Gold schema
  data/
    connection.py             # Query execution: DuckDB snapshot or Snowflake (key-pair)
    queries.py                # All SQL (portable): aggregation in SQL, bind parameters, allow-lists
    repository.py             # Cached data functions used by the views
  domain/
    metrics.py                # Metric / lifecycle stage / dimension registry (labels, colours)
    filters.py                # Filter state → SQL predicates
  ui/
    palette.py                # The only place colours are defined
    theme.py                  # Plotly template + stylesheet (the design system)
    layout.py                 # Page header, cards, notes, footer
    kpi_cards.py  charts.py  tables.py  filters.py
  utils/
    formatting.py             # Currency, count and percent formatting
    date_utils.py             # Periods, comparisons, presets, labels
data/snapshot/                # Verified Parquet snapshot of the Gold tables + manifest.json
scripts/
  export_snapshot.py          # Snowflake → Parquet, with per-table checksum verification
  compare_backends.py         # Proves the snapshot reproduces live Snowflake exactly
  validate_metrics.py         # 162 checks against independent Gold SQL (either backend)
tests/                        # pytest: unit tests + offline snapshot tests
.streamlit/config.toml        # Base theme
```

**Extending:**
- **A new metric:** add its SQL column in `queries.py`, register it in `domain/metrics.py` (label, format, colour), then use the existing chart and KPI components in a view.
- **A new page:** add a file to `views/` and register it in `app.py`.

## Design system
- **Look:** light surfaces, navy/charcoal ink, Inter, white cards with hairline borders.
- **Fixed colour identities:** GPV blue `#2A78D6`, invoices teal `#0F9488`, total accounts violet `#6250D6`, subscribed green `#008300`. Previous periods are always muted grey `#B8C0CC`.
- **Lifecycle stages** keep the same colours on every chart: pre-trial slate `#A3AEBF`, trial amber `#EDA100`, subscribed green `#008300`, churned rose `#D9506A`.
  - Colours follow the entity, never its rank, so filtering never repaints a series.
  - The stage palette was checked for colour-blind separation (OKLab ΔE, Machado CVD simulation; worst pair 11.3, target ≥ 8).
- **Charts:** line charts for trends; ranked horizontal bars for segments; stacked bars or areas for stage history; 100% stacked bars for stage mix; tables for detail. **No pie or donut charts, no 3D, no animation.**

## Data notes and limitations
- **Coverage differs by metric.** Payments and invoices run from Feb 21, 2024 to Jun 12, 2025; lifecycle data runs to Aug 12, 2025. Financial activity drops sharply after Feb 2025. The dashboard shows a note whenever a period or its comparison falls outside financial coverage.
- **Every current Trial account is stale** (61 of 61): no further event after more than 90 days. The source has no trial-expiry event, so they are counted as recorded and the Lifecycle page says so.
- **GPV includes offline payments** (cash and cheques, about 38% of GPV), per the dbt definition; they are shown separately.
- **Invoice Volume includes unpaid invoices,** since there is no invoice status.
- **Segments use current account attributes.** Region isn't hierarchical (cities span regions), so the filters narrow each other instead of drilling down.
- **Source timestamps are assumed to be UTC** (dbt `source_timezone`).
