"""Plotly chart theming for IMBA Dynamics."""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from styles.theme import COLORS

CHART_LAYOUT = {
    "paper_bgcolor": COLORS["card_grad_start"],
    "plot_bgcolor": COLORS["card_grad_end"],
    "font": {"family": "Inter, sans-serif", "color": COLORS["text"], "size": 13},
    "margin": {"l": 8, "r": 8, "t": 40, "b": 8},
    "title": {"font": {"size": 15, "color": COLORS["text"], "family": "Inter, sans-serif"}},
    "legend": {
        "font": {"color": COLORS["text"], "size": 12},
        "bgcolor": "rgba(26, 34, 48, 0.85)",
        "bordercolor": COLORS["card_border"],
    },
    "colorway": [
        COLORS["accent_glow"],
        "#3b82f6",
        COLORS["purple"],
        COLORS["warning"],
        COLORS["positive"],
        COLORS["negative"],
        COLORS["at_risk"],
    ],
}

AXIS_STYLE = {
    "showgrid": True,
    "gridcolor": "rgba(30, 38, 54, 0.6)",
    "zeroline": False,
    "tickfont": {"size": 12, "color": COLORS["text"]},
    "linecolor": "rgba(30, 38, 54, 0.8)",
    "title": {"font": {"color": COLORS["text_muted"], "size": 12}},
}

SEVERITY_COLORS = {
    "Fatal": COLORS["negative"],
    "Serious": COLORS["warning"],
    "Slight": COLORS["positive"],
}

GEO_LEGEND_COLORS = {
    "accident_led": COLORS["accent_glow"],
    "elevated": COLORS["warning"],
    "critical": COLORS["negative"],
    "emerging": COLORS["purple"],
}

_plotly_theme_ready = False


def init_plotly_theme() -> None:
    """Register and activate the IMBA Plotly template."""
    global _plotly_theme_ready
    if _plotly_theme_ready:
        return
    template = go.layout.Template(
        layout=go.Layout(
            **CHART_LAYOUT,
            xaxis=go.layout.XAxis(**AXIS_STYLE),
            yaxis=go.layout.YAxis(**AXIS_STYLE),
        )
    )
    pio.templates["imba"] = template
    pio.templates.default = "imba"
    _plotly_theme_ready = True


def apply_chart_theme(fig):
    """Apply IMBA surface and axis styling to a Plotly figure."""
    fig.update_layout(
        paper_bgcolor=COLORS["card_grad_start"],
        plot_bgcolor=COLORS["card_grad_end"],
        font={"family": "Inter, sans-serif", "color": COLORS["text"], "size": 13},
        title={"font": {"size": 15, "color": COLORS["text"]}},
        legend={
            "font": {"color": COLORS["text"]},
            "bgcolor": "rgba(26, 34, 48, 0.85)",
            "bordercolor": COLORS["card_border"],
        },
        hoverlabel={
            "bgcolor": COLORS["card"],
            "bordercolor": COLORS["card_border"],
            "font": {"color": COLORS["text"], "family": "Inter, sans-serif", "size": 12},
        },
    )
    fig.update_xaxes(**AXIS_STYLE)
    fig.update_yaxes(**AXIS_STYLE)
    return fig


def plot_chart(fig, **kwargs) -> None:
    """Render a themed Plotly chart in Streamlit."""
    apply_chart_theme(fig)
    st.plotly_chart(fig, **kwargs)
