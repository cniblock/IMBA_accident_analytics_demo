"""Scoped CSS containers for Snowflake Streamlit compatibility.

Snowflake Streamlit applies stronger default styles to native widgets. Global CSS
targeting data-testid selectors is often overridden; scoping rules to a container
(as in Snowflake's Custom UI pattern) makes sidebar nav and filter radios reliable.
"""

from __future__ import annotations

import streamlit as st

# Sidebar intelligence-module navigation
NAV_RADIO_CSS = """
div[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 0.35rem;
  flex-direction: column !important;
  flex-wrap: nowrap !important;
  width: 100%;
}
div[data-testid="stRadio"] div[role="radiogroup"] > label {
  width: 100%;
  justify-content: flex-start;
  font-size: 0.9rem !important;
  font-weight: 500 !important;
  background: rgba(0, 170, 255, 0.06) !important;
  border: 1px solid transparent !important;
  border-radius: 10px !important;
  padding: 0.45rem 0.9rem !important;
  margin: 0 !important;
  transition: all 0.15s ease;
}
div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {
  background: rgba(0, 170, 255, 0.1) !important;
  border-color: rgba(0, 170, 255, 0.25) !important;
}
div[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {
  background: rgba(0, 170, 255, 0.18) !important;
  border-color: rgba(0, 170, 255, 0.45) !important;
  box-shadow: 0 0 20px rgba(0, 170, 255, 0.2) !important;
}
"""

# Sidebar / expander filter radios (vehicle type, etc.)
FILTER_RADIO_CSS = """
div[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 0.35rem;
  flex-wrap: wrap;
}
div[data-testid="stRadio"] div[role="radiogroup"] > label {
  background: rgba(0, 170, 255, 0.06) !important;
  border: 1px solid transparent !important;
  border-radius: 10px !important;
  padding: 0.45rem 0.9rem !important;
  margin: 0 !important;
  transition: all 0.15s ease;
}
div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {
  background: rgba(0, 170, 255, 0.1) !important;
  border-color: rgba(0, 170, 255, 0.25) !important;
}
div[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {
  background: rgba(0, 170, 255, 0.18) !important;
  border-color: rgba(0, 170, 255, 0.45) !important;
  box-shadow: 0 0 20px rgba(0, 170, 255, 0.2) !important;
}
"""


def stylable_container(
    key: str,
    css_styles: str | list[str],
    *,
    parent: st.delta_generator.DeltaGenerator | None = None,
    wrapper_style: str = "",
) -> st.delta_generator.DeltaGenerator:
    """Insert a container whose descendants can be styled with scoped CSS.

    Adapted from Snowflake-Labs/snowflake-demo-streamlit (Custom UI pattern).
    Returns a Streamlit container so ``with stylable_container(...)`` routes widgets correctly.
    """
    host = parent if parent is not None else st
    if isinstance(css_styles, str):
        styles = [css_styles]
    else:
        styles = list(css_styles)

    styles.append(
        """
> div:first-child {
  display: none;
}
"""
    )

    style_text = "<style>\n"
    if wrapper_style:
        style_text += f"""
div[data-testid="stVerticalBlockBorderWrapper"]:has(
  > div
  > div[data-testid="stVerticalBlock"]
  > div.element-container
  > div.stMarkdown
  > div[data-testid="stMarkdownContainer"]
  > p
  > span.{key}
) {{
  {wrapper_style}
}}
"""

    for style in styles:
        style_text += f"""
div[data-testid="stVerticalBlock"]:has(
  > div.element-container
  > div.stMarkdown
  > div[data-testid="stMarkdownContainer"]
  > p
  > span.{key}
) {style}
"""

    style_text += f"""
</style>
<span class="{key}"></span>
"""

    container = host.container()
    container.markdown(style_text, unsafe_allow_html=True)
    return container
