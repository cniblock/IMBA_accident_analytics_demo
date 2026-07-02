"""Themed dataframe rendering for IMBA dashboard (Snowflake Streamlit compatible)."""

from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler


def _format_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Format numeric columns for readable dashboard tables."""
    out = df.reset_index(drop=True).copy()
    for col in out.columns:
        if not pd.api.types.is_numeric_dtype(out[col]):
            continue
        series = out[col]
        if pd.api.types.is_integer_dtype(series):
            out[col] = series.map(lambda x: f"{x:,}" if pd.notna(x) else "–")
        elif pd.api.types.is_float_dtype(series):
            non_null = series.dropna()
            if len(non_null) and (non_null % 1 == 0).all():
                out[col] = series.map(lambda x: f"{int(x):,}" if pd.notna(x) else "–")
            else:
                out[col] = series.map(lambda x: f"{x:,.2f}" if pd.notna(x) else "–")
    return out


def _styler_to_html(styler: Styler) -> str:
    table_html = styler.to_html()
    if 'class="' in table_html:
        return table_html.replace('class="', 'class="imba-table ', 1)
    return table_html.replace("<table", '<table class="imba-table"', 1)


def _df_to_html(df: pd.DataFrame) -> str:
    display = _format_display_df(df)
    escaped = display.copy()
    for col in escaped.columns:
        escaped[col] = escaped[col].map(
            lambda v: html.escape(str(v)) if pd.notna(v) and str(v) != "nan" else "–"
        )

    header = "".join(f"<th>{html.escape(str(col))}</th>" for col in escaped.columns)
    rows = []
    for _, row in escaped.iterrows():
        cells = "".join(f"<td>{val}</td>" for val in row)
        rows.append(f"<tr>{cells}</tr>")

    return (
        f'<table class="imba-table"><thead><tr>{header}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_dataframe(
    data: Any,
    use_container_width: bool = True,
    title: str | None = None,
    **kwargs: Any,
) -> None:
    """
    Render a pandas DataFrame or Styler with IMBA dark-theme styling.

    Uses HTML tables so styling is consistent on Snowflake Streamlit (older builds
    ignore theme CSS on st.dataframe). Unsupported kwargs (e.g. hide_index) are ignored.
    """
    _ = use_container_width, kwargs

    if title:
        st.caption(title)

    if isinstance(data, Styler):
        table_html = _styler_to_html(data)
    elif isinstance(data, pd.DataFrame):
        table_html = _df_to_html(data)
    else:
        st.dataframe(data, use_container_width=use_container_width)
        return

    st.markdown(
        f'<div class="imba-table-block"><div class="imba-table-container">{table_html}</div></div>',
        unsafe_allow_html=True,
    )
