"""Custom metric cards — HTML-based for consistent styling on Snowflake Streamlit."""

from __future__ import annotations

import html
import re

import streamlit as st


def _delta_classes(delta: str, delta_color: str) -> tuple[str, str]:
    """Map a delta string to good/bad tone classes (mirrors st.metric delta_color)."""
    cleaned = delta.replace("↑", "").replace("↓", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if not match:
        return "imba-metric-delta imba-metric-delta-neutral", ""
    numeric = float(match.group())
    if numeric > 0:
        direction = "up"
    elif numeric < 0:
        direction = "down"
    else:
        return "imba-metric-delta imba-metric-delta-neutral", ""

    inverse = delta_color == "inverse"
    good = (numeric < 0) if inverse else (numeric > 0)
    tone = "good" if good else "bad"
    arrow = "↑" if direction == "up" else "↓"
    return f"imba-metric-delta imba-metric-delta-{direction} imba-metric-delta-{tone}", arrow


def render_metric(
    label: str,
    value: str | int | float,
    *,
    delta: str | None = None,
    delta_color: str = "normal",
    help_text: str | None = None,
) -> None:
    """Render a KPI card styled like st.metric, using HTML (Snowflake-safe)."""
    safe_label = html.escape(label)
    safe_value = html.escape(str(value))
    help_attr = f' title="{html.escape(help_text)}"' if help_text else ""

    delta_html = ""
    if delta:
        classes, arrow = _delta_classes(delta, delta_color)
        safe_delta = html.escape(delta)
        if arrow not in safe_delta:
            safe_delta = f"{arrow} {safe_delta}"
        delta_html = f'<div class="{classes}">{safe_delta}</div>'

    st.markdown(
        f"""
<div class="imba-metric-slot">
  <div class="imba-metric"{help_attr}>
    <div class="imba-metric-label">{safe_label}</div>
    <div class="imba-metric-body">
      <div class="imba-metric-value">{safe_value}</div>
    </div>
    {delta_html}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_text_metric(
    label: str,
    value: str,
    *,
    help_text: str | None = None,
    title: str | None = None,
) -> None:
    """Render a KPI card with wrapping text values (e.g. district names)."""
    safe_label = html.escape(label)
    safe_value = html.escape(value)
    safe_title = html.escape(title or value)
    help_attr = f' title="{html.escape(help_text)}"' if help_text else ""
    st.markdown(
        f"""
<div class="imba-metric-slot imba-metric-slot-text">
  <div class="imba-metric imba-metric-text"{help_attr}>
    <div class="imba-metric-label">{safe_label}</div>
    <div class="imba-metric-body">
      <div class="imba-metric-value imba-metric-value-text" title="{safe_title}">{safe_value}</div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
