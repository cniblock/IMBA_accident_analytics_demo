"""IMBA Dynamics color theme and Streamlit CSS injection."""

from __future__ import annotations

import streamlit as st

COLORS: dict[str, str] = {
    "bg": "#121722",
    "card": "#1a2230",
    "card_border": "#2a3548",
    "card_grad_start": "#222d3f",
    "card_grad_end": "#161e2c",
    "accent": "#00aaff",
    "accent_glow": "#00d4ff",
    "text": "#e8edf5",
    "text_muted": "#94a3b8",
    "positive": "#22c55e",
    "negative": "#ef4444",
    "warning": "#f59e0b",
    "at_risk": "#fbbf24",
    "on_track": "#00aaff",
    "delayed": "#f97316",
    "accent_deep": "#0066aa",
    "kpi_bar_end": "#4db8ff",
    "sidebar_start": "#151b28",
    "sidebar_end": "#111722",
    "sidebar_border": "#1e2636",
    "page_glow": "#1a2840",
    "page_deep": "#0d121c",
    "dataframe_header": "#1e2838",
    "purple": "#7c6df0",
}

CSS_VARIABLES = "\n".join(
    f"  --imba-{key.replace('_', '-')}: {value};" for key, value in COLORS.items()
)


def _css() -> str:
    c = COLORS
    return f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {{
{CSS_VARIABLES}
}}

html, body, [class*="css"] {{
  font-family: 'Inter', sans-serif !important;
}}

[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main {{
  background: radial-gradient(
    ellipse at 20% 0%,
    {c["page_glow"]} 0%,
    {c["bg"]} 45%,
    {c["page_deep"]} 100%
  ) !important;
  color: {c["text"]};
}}

[data-testid="stHeader"] {{
  background: transparent !important;
}}

[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child {{
  background: linear-gradient(180deg, {c["sidebar_start"]} 0%, {c["sidebar_end"]} 100%) !important;
  border-right: 1px solid {c["card_border"]} !important;
}}

[data-testid="stSidebar"] * {{
  color: {c["text"]} !important;
}}

[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p {{
  color: {c["text"]} !important;
}}

[data-testid="stAppViewContainer"] > .main .block-container {{
  padding-top: 0.75rem !important;
  padding-bottom: 2rem;
}}

[data-testid="stMainBlockContainer"] {{
  padding-top: 0.5rem !important;
}}

h1, [data-testid="stHeadingWithActionElements"] h1 {{
  font-size: 1.5rem !important;
  font-weight: 700 !important;
  color: {c["text"]} !important;
  letter-spacing: -0.02em;
  margin-top: 0.25rem !important;
  margin-bottom: 0.75rem !important;
}}

h1.imba-page-title,
.imba-page-title {{
  font-size: 2.15rem !important;
  font-weight: 700 !important;
  color: {c["text"]} !important;
  letter-spacing: -0.025em;
  line-height: 1.15;
  margin-top: 0 !important;
  margin-bottom: 0.65rem !important;
  padding-top: 0 !important;
}}

h2, h3, [data-testid="stHeadingWithActionElements"] h2,
[data-testid="stHeadingWithActionElements"] h3 {{
  font-size: 1.1rem !important;
  font-weight: 700 !important;
  color: {c["text"]} !important;
}}

.stCaption, small, [data-testid="stCaptionContainer"] {{
  color: {c["text_muted"]} !important;
  font-size: 0.82rem !important;
}}

[data-testid="stMetric"] {{
  background: linear-gradient(160deg, {c["card_grad_start"]} 0%, {c["card_grad_end"]} 100%);
  border: 1px solid {c["card_border"]};
  border-radius: 14px;
  padding: 1rem 1.25rem 1.1rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35),
              inset 0 1px 0 rgba(255, 255, 255, 0.04);
  position: relative;
  overflow: hidden;
}}

[data-testid="stMetric"]::before {{
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, {c["accent_glow"]} 0%, {c["accent"]} 55%, {c["kpi_bar_end"]} 100%);
  box-shadow: 0 0 16px rgba(0, 212, 255, 0.45);
}}

[data-testid="stMetricLabel"] {{
  font-size: 0.9rem !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: {c["text_muted"]} !important;
}}

[data-testid="stMetricValue"] {{
  font-size: 2.5rem !important;
  font-weight: 700 !important;
  color: {c["text"]} !important;
}}

[data-testid="stPlotlyChart"] {{
  background: linear-gradient(145deg, {c["card_grad_start"]} 0%, {c["card_grad_end"]} 100%);
  border: 1px solid {c["card_border"]};
  border-radius: 14px;
  padding: 0.35rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35),
              inset 0 1px 0 rgba(255, 255, 255, 0.04);
  overflow: hidden;
}}

[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {{
  background: {c["card"]};
  border: 1px solid {c["card_border"]};
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 6px 28px rgba(0, 0, 0, 0.35),
              inset 0 1px 0 rgba(255, 255, 255, 0.04);
}}

.imba-table-container {{
  width: 100%;
  background: linear-gradient(160deg, {c["card_grad_start"]} 0%, {c["card_grad_end"]} 100%);
  border: 1px solid {c["card_border"]};
  border-radius: 14px;
  overflow-x: auto;
  overflow-y: auto;
  max-height: 520px;
  box-shadow: 0 6px 28px rgba(0, 0, 0, 0.35),
              inset 0 1px 0 rgba(255, 255, 255, 0.04);
}}

table.imba-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
  font-family: 'Inter', sans-serif;
}}

table.imba-table thead th {{
  position: sticky;
  top: 0;
  z-index: 1;
  background: {c["dataframe_header"]};
  color: {c["text_muted"]};
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.7rem 1rem;
  text-align: left;
  border-bottom: 2px solid {c["card_border"]};
  white-space: nowrap;
}}

table.imba-table tbody td {{
  padding: 0.6rem 1rem;
  color: {c["text"]};
  border-bottom: 1px solid rgba(42, 53, 72, 0.55);
  vertical-align: middle;
}}

table.imba-table tbody tr:nth-child(even) td {{
  background: rgba(255, 255, 255, 0.025);
}}

table.imba-table tbody tr:hover td {{
  background: rgba(0, 170, 255, 0.08);
}}

table.imba-table tbody tr:last-child td {{
  border-bottom: none;
}}

.imba-table-container table {{
  background: transparent !important;
}}

.imba-table-container table th,
.imba-table-container table td {{
  background: transparent !important;
  color: {c["text"]} !important;
  border-color: rgba(42, 53, 72, 0.55) !important;
}}

.imba-table-container table thead th {{
  background: {c["dataframe_header"]} !important;
  color: {c["text_muted"]} !important;
}}

div[data-testid="stExpander"] {{
  background: linear-gradient(145deg, {c["card_grad_start"]} 0%, {c["card_grad_end"]} 100%);
  border: 1px solid {c["card_border"]};
  border-radius: 14px;
  box-shadow: 0 6px 28px rgba(0, 0, 0, 0.3);
}}

div[data-testid="stExpander"]:hover {{
  border-color: rgba(0, 170, 255, 0.28);
}}

[data-testid="stAlert"] {{
  border-radius: 12px !important;
  border: 1px solid {c["card_border"]} !important;
}}

[data-testid="stAlert"][data-baseweb="notification"] {{
  background: linear-gradient(145deg, {c["card_grad_start"]} 0%, {c["card_grad_end"]} 100%) !important;
}}

div[data-testid="stNotificationContentInfo"] {{
  background: rgba(0, 170, 255, 0.08) !important;
  border-left: 3px solid {c["accent"]} !important;
}}

div[data-testid="stNotificationContentWarning"] {{
  background: rgba(245, 158, 11, 0.15) !important;
  border-left: 3px solid {c["warning"]} !important;
}}

div[data-testid="stNotificationContentError"] {{
  background: rgba(239, 68, 68, 0.15) !important;
  border-left: 3px solid {c["negative"]} !important;
}}

div[data-testid="stNotificationContentSuccess"] {{
  background: rgba(34, 197, 94, 0.12) !important;
  border-left: 3px solid {c["positive"]} !important;
}}

div[data-testid="stRadio"] div[role="radiogroup"] {{
  gap: 0.35rem;
  flex-wrap: wrap;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {{
  flex-direction: column !important;
  flex-wrap: nowrap !important;
  width: 100%;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label {{
  width: 100%;
  justify-content: flex-start;
  font-size: 0.9rem !important;
  font-weight: 500 !important;
}}

div[data-testid="stRadio"] div[role="radiogroup"] > label {{
  background: rgba(0, 170, 255, 0.06) !important;
  border: 1px solid transparent !important;
  border-radius: 10px !important;
  padding: 0.45rem 0.9rem !important;
  margin: 0 !important;
  transition: all 0.15s ease;
}}

div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {{
  background: rgba(0, 170, 255, 0.1) !important;
  border-color: rgba(0, 170, 255, 0.25) !important;
}}

div[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {{
  background: rgba(0, 170, 255, 0.18) !important;
  border-color: rgba(0, 170, 255, 0.45) !important;
  box-shadow: 0 0 20px rgba(0, 170, 255, 0.2) !important;
}}

.stDownloadButton button,
[data-testid="stButton"] button {{
  background: rgba(0, 170, 255, 0.12) !important;
  border: 1px solid rgba(0, 170, 255, 0.35) !important;
  color: {c["accent_glow"]} !important;
  border-radius: 10px !important;
  font-weight: 600 !important;
}}

.stDownloadButton button:hover,
[data-testid="stButton"] button:hover {{
  background: rgba(0, 170, 255, 0.22) !important;
  border-color: rgba(0, 212, 255, 0.5) !important;
  box-shadow: 0 0 16px rgba(0, 170, 255, 0.25) !important;
}}

[data-testid="stMultiSelect"],
[data-testid="stSelectbox"],
[data-testid="stDateInput"] {{
  background: {c["card"]};
  border-radius: 10px;
}}
"""


def inject_theme() -> None:
    """Inject IMBA Dynamics CSS on each Streamlit run."""
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)
