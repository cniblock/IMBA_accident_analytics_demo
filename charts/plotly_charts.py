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


def _is_map_figure(fig) -> bool:
    """True when the figure uses Mapbox/Geo traces (basemap must stay visible)."""
    for trace in fig.data:
        trace_type = getattr(trace, "type", "") or ""
        if trace_type in {
            "scattermapbox",
            "choroplethmapbox",
            "densitymapbox",
            "scattermap",
            "choroplethmap",
            "densitymap",
            "scattergeo",
            "choroplethgeo",
        }:
            return True
    return False


def _merge_legend(fig, default_legend: dict) -> dict:
    """Preserve per-chart legend placement while applying theme styling."""
    merged = default_legend.copy()
    existing = fig.layout.legend
    if not existing:
        return merged
    for key in (
        "orientation",
        "x",
        "y",
        "xanchor",
        "yanchor",
        "title",
        "tracegroupgap",
        "itemsizing",
        "itemwidth",
        "valign",
    ):
        val = getattr(existing, key, None)
        if val is not None:
            merged[key] = val
    return merged


def apply_chart_theme(fig):
    """Apply IMBA surface and axis styling to a Plotly figure."""
    is_map = _is_map_figure(fig)
    default_legend = {
        "font": {"color": COLORS["text"]},
        "bgcolor": "rgba(26, 34, 48, 0.85)",
        "bordercolor": COLORS["card_border"],
    }
    layout_kwargs = {
        "paper_bgcolor": COLORS["card_grad_start"],
        "font": {"family": "Inter, sans-serif", "color": COLORS["text"], "size": 13},
        "title": {"font": {"size": 15, "color": COLORS["text"]}},
        "legend": _merge_legend(fig, default_legend),
        "hoverlabel": {
            "bgcolor": COLORS["card"],
            "bordercolor": COLORS["card_border"],
            "font": {"color": COLORS["text"], "family": "Inter, sans-serif", "size": 12},
        },
    }
    if is_map:
        # Opaque plot_bgcolor covers Mapbox/OSM tiles — keep the map surface clear.
        layout_kwargs["plot_bgcolor"] = "rgba(0,0,0,0)"
        layout_kwargs["margin"] = {"l": 0, "r": 0, "t": 40, "b": 0}
        # Overlay legend on the map (avoids a right-hand gutter and widens the map).
        layout_kwargs["legend"] = {
            "title": {"text": "Severity", "font": {"size": 12, "color": COLORS["text_muted"]}},
            "font": {"color": COLORS["text"], "size": 12},
            "bgcolor": "rgba(26, 34, 48, 0.88)",
            "bordercolor": COLORS["card_border"],
            "borderwidth": 1,
            "x": 0.012,
            "y": 0.99,
            "xanchor": "left",
            "yanchor": "top",
            "orientation": "v",
            "tracegroupgap": 8,
            "itemsizing": "constant",
            "itemwidth": 56,
        }
    else:
        layout_kwargs["plot_bgcolor"] = COLORS["card_grad_end"]

    fig.update_layout(**layout_kwargs)
    if not is_map:
        fig.update_xaxes(**AXIS_STYLE)
        fig.update_yaxes(**AXIS_STYLE)
    return fig


def plot_chart(fig, **kwargs) -> None:
    """Render a themed Plotly chart in Streamlit."""
    apply_chart_theme(fig)
    if _is_map_figure(fig):
        user_config = kwargs.pop("config", None) or {}
        kwargs["config"] = {"scrollZoom": True, **user_config}
    st.plotly_chart(fig, **kwargs)
