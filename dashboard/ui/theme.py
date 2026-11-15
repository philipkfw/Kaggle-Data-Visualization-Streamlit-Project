"""Design system: one Plotly template and one stylesheet for the whole app.

Charts never set fonts, grid colours or margins themselves - they inherit the
"saas" template registered here, so every visual reads as one product.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from dashboard.ui import palette as p

FONT_FAMILY = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
TEMPLATE_NAME = "saas"


def register_plotly_template() -> None:
    axis_common = dict(
        tickfont=dict(size=11, color=p.TEXT_MUTED),
        title=dict(font=dict(size=12, color=p.TEXT_MUTED), standoff=12),
        zeroline=False,
        automargin=True,
    )
    pio.templates[TEMPLATE_NAME] = go.layout.Template(
        layout=dict(
            font=dict(family=FONT_FAMILY, size=12, color=p.TEXT_SECONDARY),
            paper_bgcolor=p.SURFACE,
            plot_bgcolor=p.SURFACE,
            colorway=[p.GPV, p.INVOICE, p.TOTAL_ACCOUNTS, p.SUBSCRIBED],
            margin=dict(l=4, r=12, t=8, b=4),
            xaxis=dict(**axis_common, showgrid=False, showline=True, linecolor=p.AXIS,
                       linewidth=1, ticks="outside", tickcolor=p.AXIS, ticklen=4),
            yaxis=dict(**axis_common, showgrid=True, gridcolor=p.GRID, gridwidth=1,
                       showline=False, ticks=""),
            hoverlabel=dict(bgcolor=p.SURFACE, bordercolor=p.BORDER, align="left",
                            font=dict(family=FONT_FAMILY, size=12, color=p.TEXT_PRIMARY)),
            legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                        bgcolor="rgba(0,0,0,0)", font=dict(size=12, color=p.TEXT_SECONDARY),
                        itemclick=False, itemdoubleclick=False, title=dict(text="")),
            bargap=0.3,
            barcornerradius=4,
            hovermode="closest",
            separators=".,",
        )
    )
    pio.templates.default = TEMPLATE_NAME


_CSS = f"""
<style>
:root {{
  --bg: {p.BACKGROUND}; --surface: {p.SURFACE}; --border: {p.BORDER};
  --text: {p.TEXT_PRIMARY}; --text-2: {p.TEXT_SECONDARY}; --muted: {p.TEXT_MUTED};
  --up: {p.DELTA_UP}; --down: {p.DELTA_DOWN}; --accent: {p.GPV};
}}
.stApp {{ background: var(--bg); }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{ max-width: 1360px; padding: 2rem 2rem 3rem; }}
@media (max-width: 640px) {{
  [data-testid="stMainBlockContainer"] {{ padding: 3.25rem 1rem 2rem; }}
}}
[data-testid="stSidebar"] {{ border-right: 1px solid var(--border); }}
[data-testid="stSidebarUserContent"] {{ padding-top: 0.5rem; }}

/* Page header */
.page-header {{ margin: 0 0 1.25rem; }}
.page-eyebrow {{ font-size: 12px; font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }}
.page-title {{ font-size: 26px; font-weight: 650; color: var(--text); line-height: 1.2;
  letter-spacing: -0.01em; }}
.page-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
.chip {{ display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
  color: var(--text-2); background: var(--surface); border: 1px solid var(--border);
  border-radius: 999px; padding: 3px 10px; white-space: nowrap; }}
.chip b {{ color: var(--text); font-weight: 600; }}
a.chip-link {{ color: var(--accent); text-decoration: none; border-color: rgba(42,120,214,.35);
  background: rgba(42,120,214,.06); }}
a.chip-link:hover {{ background: rgba(42,120,214,.12); }}
.note a, .footer a, .sidebar-caption a {{ color: var(--accent); text-decoration: none; }}
.note a:hover, .footer a:hover, .sidebar-caption a:hover {{ text-decoration: underline; }}

/* Cards: any container keyed "card_*" */
[class*="st-key-card_"] {{ background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 20px 12px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
.card-title {{ font-size: 15px; font-weight: 600; color: var(--text); line-height: 1.3; }}
.card-subtitle {{ font-size: 12.5px; color: var(--muted); margin-top: 2px; }}

/* KPI cards */
.kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px 18px; min-height: 128px; display: flex; flex-direction: column;
  justify-content: space-between; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
.kpi-label {{ display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500;
  color: var(--text-2); }}
.kpi-dot {{ width: 8px; height: 8px; border-radius: 2px; flex: none; }}
.kpi-value {{ font-size: 28px; font-weight: 650; color: var(--text); letter-spacing: -0.02em;
  line-height: 1.15; margin: 8px 0 6px; }}
.kpi-foot {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 12px;
  color: var(--muted); }}
.delta {{ display: inline-flex; align-items: center; gap: 3px; font-weight: 600;
  border-radius: 6px; padding: 1px 6px; font-size: 12px; }}
.delta.good {{ color: var(--up); background: rgba(6,118,71,.08); }}
.delta.bad {{ color: var(--down); background: rgba(180,35,24,.08); }}
.delta.flat {{ color: var(--muted); background: rgba(102,112,133,.10); }}

/* Notes */
.note {{ font-size: 12.5px; color: var(--text-2); background: var(--surface);
  border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 8px;
  padding: 10px 14px; margin: 4px 0 12px; }}
.note.demo {{ border-left-color: var(--text-2); background: #F2F4F7; color: var(--text); }}
.footer {{ font-size: 12px; color: var(--muted); border-top: 1px solid var(--border);
  margin-top: 2rem; padding-top: 12px; }}
.sidebar-label {{ font-size: 11px; font-weight: 600; letter-spacing: .05em;
  text-transform: uppercase; color: var(--muted); margin: 14px 0 4px; }}
.sidebar-caption {{ font-size: 12px; color: var(--text-2); line-height: 1.5; }}
</style>
"""


def inject_css() -> None:
    st.html(_CSS)


def apply() -> None:
    register_plotly_template()
    inject_css()
