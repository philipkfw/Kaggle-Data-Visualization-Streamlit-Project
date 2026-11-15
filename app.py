"""Entry point: `streamlit run app.py`.

Sets up the page, theme and shared sidebar filters, then hands off to the selected
page via st.navigation.
"""

import streamlit as st

from dashboard.config import APP_TITLE, data_backend
from dashboard.ui import theme
from dashboard.ui.filters import render_sidebar

st.set_page_config(page_title=APP_TITLE, page_icon=":material/insights:", layout="wide",
                   initial_sidebar_state="auto")
theme.apply()

pages = st.navigation(
    {
        "Dashboards": [
            st.Page("views/overview.py", title="Executive Overview", icon=":material/dashboard:",
                    default=True),
            st.Page("views/gpv.py", title="GPV Analysis", icon=":material/payments:"),
            st.Page("views/invoices.py", title="Invoice Analysis", icon=":material/receipt_long:"),
            st.Page("views/lifecycle.py", title="Account Lifecycle", icon=":material/group:"),
        ],
        "Reference": [
            st.Page("views/methodology.py", title="Definitions & Data Notes",
                    icon=":material/menu_book:"),
        ],
    },
    position="sidebar",
)

try:
    render_sidebar()
except Exception as error:  # noqa: BLE001 - surface data-source problems clearly.
    if data_backend() == "snowflake":
        message = ("Could not load data from Snowflake. Check the `[snowflake]` settings in "
                   "`.streamlit/secrets.toml`, or switch to the bundled snapshot with "
                   '`data_backend = "duckdb"` under `[app]` (see README).')
    else:
        message = ("Could not load the data snapshot in `data/snapshot/`. Restore it from git, "
                   "or re-export it with `scripts/export_snapshot.py` (see README).")
    st.error(message, icon=":material/cloud_off:")
    with st.expander("Error details"):
        st.exception(error)
    st.stop()

pages.run()
