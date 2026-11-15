"""Detail tables: sortable, formatted, searchable, downloadable."""

from __future__ import annotations

import pandas as pd
import streamlit as st

DIMENSION_COLUMNS = {
    "country": st.column_config.TextColumn("Country"),
    "region": st.column_config.TextColumn("Region"),
    "city": st.column_config.TextColumn("City"),
    "sign_up_platform": st.column_config.TextColumn("Sign-up platform"),
}


def usd_column(label: str, help_text: str | None = None):
    return st.column_config.NumberColumn(label, format="dollar", help=help_text)


def count_column(label: str, help_text: str | None = None):
    return st.column_config.NumberColumn(label, format="localized", help=help_text)


SHARE_FORMAT = "%.1f%%"


def share_column(label: str, help_text: str | None = None):
    """Share columns hold ratios (0-1); detail_table scales them to percent for display."""
    return st.column_config.NumberColumn(label, format=SHARE_FORMAT, help=help_text)


def detail_table(frame: pd.DataFrame, columns: dict, file_name: str, key: str,
                 height: int = 420) -> None:
    """Render a detail table with a search box and CSV export of the filtered rows.

    `columns` maps source column -> st.column_config entry, and fixes column order.
    """
    search_col, download_col = st.columns([3, 1], vertical_alignment="bottom")
    with search_col:
        query = st.text_input("Search", key=f"{key}_search", placeholder="Search rows…",
                              label_visibility="collapsed")
    data = frame[list(columns)].copy()
    for column, config in columns.items():  # One decimal for every share, everywhere.
        if config.get("type_config", {}).get("format") == SHARE_FORMAT:
            data[column] = (data[column] * 100).round(1)
    if query:
        text_cols = data.select_dtypes(include="object").columns
        mask = pd.Series(False, index=data.index)
        for column in text_cols:
            mask |= data[column].astype(str).str.contains(query, case=False, regex=False)
        data = data[mask]
    with download_col:
        export = data.rename(columns={
            c: cfg["label"] + (" (%)" if cfg.get("type_config", {}).get("format") == SHARE_FORMAT
                               else "")
            for c, cfg in columns.items()})
        st.download_button("Download CSV", export.to_csv(index=False).encode(), file_name=file_name,
                           mime="text/csv", key=f"{key}_download", icon=":material/download:",
                           width="stretch")
    st.dataframe(data, column_config=columns, hide_index=True, width="stretch",
                 height=min(height, 38 + 35 * max(len(data), 1)), key=f"{key}_table")
    st.caption(f"{len(data):,} rows · click a column header to sort")
