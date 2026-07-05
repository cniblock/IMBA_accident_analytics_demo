"""GeoRisk map rendering — Plotly locally, Pydeck on Snowflake (CSP-safe basemaps)."""

from __future__ import annotations

import html

import pandas as pd
import plotly.express as px
import streamlit as st

from charts.plotly_charts import SEVERITY_COLORS, plot_chart
from runtime_env import is_snowflake_streamlit
from styles.theme import COLORS

MAP_HEIGHT = 780
MAP_CENTER = {"lat": 52.8, "lon": -2.0}
MAP_ZOOM = 5.2
PYDECK_MAP_STYLE = "mapbox://styles/mapbox/dark-v11"

_SEVERITY_CODE_LABELS = {1: "Fatal", 2: "Serious", 3: "Slight"}


def _hex_to_rgba(hex_color: str, alpha: int) -> list[int]:
    value = hex_color.lstrip("#")
    return [int(value[i : i + 2], 16) for i in (0, 2, 4)] + [alpha]


def _severity_labels(map_geo: pd.DataFrame, sev_col: str) -> pd.Series:
    if sev_col == "collision_severity":
        return map_geo[sev_col].map(_SEVERITY_CODE_LABELS).fillna("Unknown")
    return map_geo[sev_col].astype("string").fillna("Unknown")


def _render_georisk_legend() -> None:
    items = "".join(
        f'<span class="georisk-legend-item">'
        f'<span class="georisk-legend-dot" style="background:{color};"></span>'
        f"{html.escape(label)}</span>"
        for label, color in SEVERITY_COLORS.items()
    )
    st.markdown(f'<div class="georisk-legend">{items}</div>', unsafe_allow_html=True)


def _render_plotly_map(
    map_geo: pd.DataFrame,
    *,
    sev_col: str,
    point_count: int,
    point_visibility: str,
    marker_size: int,
    marker_opacity: float,
    hover_cols: list[str],
) -> None:
    map_fig = px.scatter_map(
        map_geo,
        lat="latitude",
        lon="longitude",
        color=sev_col,
        color_discrete_map=SEVERITY_COLORS,
        zoom=MAP_ZOOM,
        center=MAP_CENTER,
        map_style="open-street-map",
        height=MAP_HEIGHT,
        hover_data=hover_cols if hover_cols else None,
        title=f"Collision hotspots — last 12 months ({point_count:,} points)",
        labels={
            sev_col: "Severity",
            "latitude": "Latitude",
            "longitude": "Longitude",
            "collision_index": "Collision Index",
            "date": "Date",
            "speed_limit": "Speed Limit (mph)",
            "light_conditions_label": "Light Conditions",
            "weather_conditions_label": "Weather Conditions",
        },
    )
    map_fig.update_layout(
        map=dict(zoom=MAP_ZOOM, center=MAP_CENTER, style="open-street-map"),
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        uirevision="georisk-map",
        dragmode="pan",
        hoverlabel=dict(
            namelength=-1,
            bgcolor="#1a2230",
            font_size=12,
            font_color="#e8edf5",
        ),
    )
    if len(hover_cols) >= 5:
        map_fig.update_traces(
            hovertemplate=(
                "<b>Collision Severity</b> = %{fullData.name}<br>"
                "Latitude = %{lat}<br>"
                "Longitude = %{lon}<br>"
                "Collision Index = %{customdata[0]}<br>"
                "Date = %{customdata[1]}<br>"
                "Speed Limit (mph) = %{customdata[2]}<br>"
                "Light Conditions = %{customdata[3]}<br>"
                "Weather Conditions = %{customdata[4]}<extra></extra>"
            )
        )
    map_fig.update_traces(marker=dict(size=marker_size, opacity=marker_opacity))
    plot_chart(map_fig, use_container_width=True)


def _render_pydeck_map(
    map_geo: pd.DataFrame,
    *,
    sev_col: str,
    point_count: int,
    marker_size: int,
    marker_opacity: float,
) -> None:
    import pydeck as pdk

    alpha = max(1, min(255, int(marker_opacity * 255)))
    labels = _severity_labels(map_geo, sev_col)
    points = map_geo.assign(severity_label=labels)
    if "date" in points.columns:
        points["date"] = pd.to_datetime(points["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    points["color"] = points["severity_label"].map(
        lambda label: _hex_to_rgba(SEVERITY_COLORS.get(str(label), COLORS["accent"]), alpha)
    )

    tooltip_lines = ["<b>{severity_label}</b>"]
    if "collision_index" in points.columns:
        tooltip_lines.append("Collision index: {collision_index}")
    if "date" in points.columns:
        tooltip_lines.append("Date: {date}")
    tooltip_lines.extend(["Lat: {latitude}", "Lon: {longitude}"])

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=points,
        get_position=["longitude", "latitude"],
        get_fill_color="color",
        get_radius=1,
        radius_min_pixels=marker_size,
        radius_max_pixels=marker_size,
        pickable=True,
        auto_highlight=True,
    )
    view_state = pdk.ViewState(
        latitude=MAP_CENTER["lat"],
        longitude=MAP_CENTER["lon"],
        zoom=MAP_ZOOM,
        pitch=0,
        bearing=0,
    )
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style=PYDECK_MAP_STYLE,
        tooltip={
            "html": "<br/>".join(tooltip_lines),
            "style": {
                "backgroundColor": COLORS["card"],
                "color": COLORS["text"],
                "fontSize": "12px",
            },
        },
    )
    st.subheader(f"Collision hotspots — last 12 months ({point_count:,} points)")
    _render_georisk_legend()
    st.pydeck_chart(deck, use_container_width=True, height=MAP_HEIGHT)


def render_georisk_map(
    map_geo: pd.DataFrame,
    *,
    sev_col: str,
    point_visibility: str,
    marker_size: int,
    marker_opacity: float,
    hover_cols: list[str],
) -> None:
    """Render the GeoRisk collision map using a runtime-appropriate backend."""
    point_count = len(map_geo)
    if is_snowflake_streamlit():
        try:
            _render_pydeck_map(
                map_geo,
                sev_col=sev_col,
                point_count=point_count,
                marker_size=marker_size,
                marker_opacity=marker_opacity,
            )
        except ImportError:
            st.error(
                "Pydeck is required for maps on Streamlit in Snowflake. "
                "Add `pydeck` to the app packages and acknowledge the Mapbox External Offerings Terms."
            )
        return

    _render_plotly_map(
        map_geo,
        sev_col=sev_col,
        point_count=point_count,
        point_visibility=point_visibility,
        marker_size=marker_size,
        marker_opacity=marker_opacity,
        hover_cols=hover_cols,
    )
