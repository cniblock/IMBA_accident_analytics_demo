"""IMBA Dynamics color theme and Streamlit CSS injection."""

from __future__ import annotations

import os
import re
from pathlib import Path

import streamlit as st

STYLES_DIR = Path(__file__).resolve().parent
APP_ROOT = STYLES_DIR.parent
THEME_CSS_PATH = STYLES_DIR / "theme.css"

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
:root, .stApp {{
{CSS_VARIABLES}
}}

.stApp, .stApp [class*="css"] {{
  font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif !important;
}}

.stApp [data-testid="stAppViewContainer"],
.stApp [data-testid="stAppViewContainer"] > .main {{
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
  margin-top: 1.5rem !important;
  margin-bottom: 0.75rem !important;
}}

.stCaption, small, [data-testid="stCaptionContainer"] {{
  color: {c["text_muted"]} !important;
  font-size: 0.82rem !important;
  margin-top: 0.35rem !important;
  margin-bottom: 0.65rem !important;
}}

[data-testid="stMetric"] {{
  background: linear-gradient(160deg, {c["card_grad_start"]} 0%, {c["card_grad_end"]} 100%) !important;
  border: 1px solid {c["card_border"]} !important;
  border-radius: 14px !important;
  padding: 1rem 1.25rem 1.1rem !important;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35),
              inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
  position: relative !important;
  overflow: hidden !important;
  min-height: 7.25rem !important;
  box-sizing: border-box !important;
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
  line-height: 1.15 !important;
}}

[data-testid="stMetricValue"] > div {{
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}

[data-testid="stMarkdownContainer"]:has(.imba-text-metric-slot) {{
  margin-bottom: 0 !important;
}}

[data-testid="stMarkdownContainer"]:has(.imba-text-metric-slot) p {{
  margin: 0 !important;
  line-height: 0;
}}

.imba-text-metric-slot {{
  height: 100%;
  min-height: 7.25rem;
}}

.imba-text-metric {{
  background: linear-gradient(160deg, {c["card_grad_start"]} 0%, {c["card_grad_end"]} 100%);
  border: 1px solid {c["card_border"]};
  border-radius: 14px;
  padding: 1rem 1.25rem 1.1rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35),
              inset 0 1px 0 rgba(255, 255, 255, 0.04);
  position: relative;
  overflow: hidden;
  height: 100%;
  min-height: 7.25rem;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  container-type: inline-size;
}}

.imba-text-metric::before {{
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, {c["accent_glow"]} 0%, {c["accent"]} 55%, {c["kpi_bar_end"]} 100%);
  box-shadow: 0 0 16px rgba(0, 212, 255, 0.45);
}}

.imba-text-metric-label {{
  font-size: 0.9rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: {c["text_muted"]};
  margin-bottom: 0.35rem;
  line-height: 1.3;
  flex-shrink: 0;
}}

.imba-text-metric-body {{
  flex: 1;
  display: flex;
  align-items: center;
  min-height: 0;
  overflow: hidden;
}}

.imba-text-metric-value {{
  width: 100%;
  font-size: clamp(0.85rem, 11cqi, 2.5rem);
  font-weight: 700;
  color: {c["text"]};
  line-height: 1.15;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  hyphens: auto;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}}

.stApp [data-testid="stPlotlyChart"] {{
  background: linear-gradient(145deg, {c["card_grad_start"]} 0%, {c["card_grad_end"]} 100%) !important;
  border: 1px solid {c["card_border"]} !important;
  border-radius: 14px !important;
  padding: 0.35rem !important;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35),
              inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
  overflow: hidden !important;
  margin-bottom: 1.25rem !important;
}}

[data-testid="stPlotlyChart"]:has(.mapboxgl-map),
[data-testid="stPlotlyChart"]:has(.maplibregl-map) {{
  overscroll-behavior: contain;
}}

[data-testid="stPlotlyChart"]:has(.mapboxgl-map) .modebar-container,
[data-testid="stPlotlyChart"]:has(.maplibregl-map) .modebar-container {{
  right: 3.25rem !important;
  top: 0.35rem !important;
}}

[data-testid="stPlotlyChart"]:has(.mapboxgl-map) .js-plotly-plot,
[data-testid="stPlotlyChart"]:has(.maplibregl-map) .js-plotly-plot {{
  width: 100% !important;
}}

[data-testid="stPlotlyChart"]:has(.mapboxgl-map) .legend .scatterpts path,
[data-testid="stPlotlyChart"]:has(.maplibregl-map) .legend .scatterpts path {{
  transform: scale(1.45);
  transform-origin: center;
}}

.georisk-legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem 1.1rem;
  margin: 0.35rem 0 0.75rem;
  padding: 0.55rem 0.85rem;
  background: rgba(26, 34, 48, 0.92);
  border: 1px solid {c["card_border"]};
  border-radius: 10px;
  width: fit-content;
  font-size: 0.82rem;
  color: {c["text"]};
}}

.georisk-legend-item {{
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}}

.georisk-legend-dot {{
  width: 11px;
  height: 11px;
  border-radius: 50%;
  flex-shrink: 0;
}}

[data-testid="stPydeckChart"] {{
  background: linear-gradient(145deg, {c["card_grad_start"]} 0%, {c["card_grad_end"]} 100%);
  border: 1px solid {c["card_border"]};
  border-radius: 14px;
  padding: 0.35rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35),
              inset 0 1px 0 rgba(255, 255, 255, 0.04);
  overflow: hidden;
  margin-bottom: 1.25rem;
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

.imba-table-block {{
  margin-bottom: 1.25rem;
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
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.75rem 1rem;
  text-align: left;
  border-bottom: 2px solid {c["card_border"]};
  white-space: nowrap;
}}

table.imba-table tbody td {{
  padding: 0.72rem 1rem;
  color: {c["text"]};
  border-bottom: 1px solid rgba(42, 53, 72, 0.55);
  vertical-align: middle;
  font-size: 0.9rem;
  white-space: normal;
  word-wrap: break-word;
  overflow-wrap: anywhere;
}}

table.imba-table tbody td.imba-num,
table.imba-table thead th.imba-num {{
  text-align: right;
  font-variant-numeric: tabular-nums;
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


def _scope_css_for_hosted_streamlit(css: str) -> str:
    """Raise selector specificity so theme CSS wins on hosted Streamlit (1.42+)."""
    css = re.sub(r"(?<!\.stApp )\[data-testid=", ".stApp [data-testid=", css)
    css = re.sub(r"(?<!\.stApp )div\[data-testid=", ".stApp div[data-testid=", css)
    css = re.sub(r"(?<!\.stApp )\.stCaption", ".stApp .stCaption", css)
    css = re.sub(r"(?<!\.stApp )\.stDownloadButton", ".stApp .stDownloadButton", css)
    css = re.sub(r"(?<!\.stApp )\.imba-", ".stApp .imba-", css)
    css = re.sub(r"(?<!\.stApp )\.georisk-", ".stApp .georisk-", css)
    css = re.sub(r"(?<!\.stApp )table\.imba-table", ".stApp table.imba-table", css)
    css = re.sub(r"^h1,", ".stApp h1,", css, flags=re.MULTILINE)
    css = re.sub(r"^h2, h3,", ".stApp h2, .stApp h3,", css, flags=re.MULTILINE)
    css = re.sub(r"(?<!\.stApp )h1\.imba-page-title", ".stApp h1.imba-page-title", css)
    return css


def _load_theme_css() -> tuple[str, str]:
    """Load CSS from committed theme.css, falling back to in-code template."""
    if THEME_CSS_PATH.is_file():
        return THEME_CSS_PATH.read_text(encoding="utf-8"), "file"
    return _css(), "python"


def _inject_style_block(css: str) -> None:
    """Inject CSS using markdown (Snowflake) and st.html (Streamlit Cloud) for compatibility."""
    style_block = f"<style>{css}</style>"
    st.markdown(style_block, unsafe_allow_html=True)
    if hasattr(st, "html"):
        st.html(style_block, unsafe_allow_javascript=False)


def inject_theme(*, warn_if_missing: bool = True) -> None:
    """Inject IMBA Dynamics CSS immediately after st.set_page_config()."""
    raw_css, source = _load_theme_css()
    css = _scope_css_for_hosted_streamlit(raw_css)
    _inject_style_block(css)

    if warn_if_missing and source == "python":
        st.sidebar.warning(f"Theme CSS file not found: {THEME_CSS_PATH}")


def render_theme_debug() -> None:
    """Sidebar diagnostics for hosted Streamlit/Snowflake theme troubleshooting."""
    raw_css, source = _load_theme_css()
    st.sidebar.markdown("---")
    st.sidebar.caption("Theme debug")
    st.sidebar.caption(f"Streamlit: {st.__version__}")
    st.sidebar.caption(f"CWD: {Path.cwd()}")
    st.sidebar.caption(f"App root: {APP_ROOT}")
    st.sidebar.caption(f"CSS path: {THEME_CSS_PATH}")
    st.sidebar.caption(f"CSS exists: {THEME_CSS_PATH.is_file()}")
    st.sidebar.caption(f"CSS source: {source}")
    if THEME_CSS_PATH.is_file():
        st.sidebar.caption(f"CSS bytes: {THEME_CSS_PATH.stat().st_size:,}")
    st.sidebar.caption(f"Scoped CSS bytes: {len(_scope_css_for_hosted_streamlit(raw_css)):,}")


def theme_debug_enabled() -> bool:
    return os.environ.get("IMBA_THEME_DEBUG", "").strip().lower() in {"1", "true", "yes"}
