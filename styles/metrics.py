"""Custom metric cards for text values that need to wrap (e.g. district names)."""

from __future__ import annotations

import html

import streamlit as st


def render_text_metric(
    label: str,
    value: str,
    *,
    help_text: str | None = None,
    title: str | None = None,
) -> None:
    """Render a KPI card styled like st.metric, with wrapping text values."""
    safe_label = html.escape(label)
    safe_value = html.escape(value)
    safe_title = html.escape(title or value)
    help_attr = f' title="{html.escape(help_text)}"' if help_text else ""
    st.markdown(
        f"""
<div class="imba-text-metric-slot">
  <div class="imba-text-metric"{help_attr}>
    <div class="imba-text-metric-label">{safe_label}</div>
    <div class="imba-text-metric-body">
      <div class="imba-text-metric-value" title="{safe_title}">{safe_value}</div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
