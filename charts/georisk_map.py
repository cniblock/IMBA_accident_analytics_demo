"""GeoRisk map rendering — Plotly locally, Pydeck on Snowflake (CSP-safe basemaps)."""

from __future__ import annotations

import html
import inspect

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
# SiS warehouse runtimes enforce a 32 MB browser message limit.
SNOWFLAKE_PYDECK_POINT_CAP = 12_000


def _hex_to_rgba(hex_color: str, alpha: int) -> list[int]:
    value = hex_color.lstrip("#")
    return [int(value[i : i + 2], 16) for i in (0, 2, 4)] + [alpha]


def _severity_labels(map_geo: pd.DataFrame, sev_col: str) -> pd.Series:
    if sev_col == "collision_severity":
        return map_geo[sev_col].map(_SEVERITY_CODE_LABELS).fillna("Unknown")
    return map_geo[sev_col].astype("string").fillna("Unknown")


def _sample_points_stratified(points: pd.DataFrame, max_points: int) -> pd.DataFrame:
    """Downsample while preserving severity mix (for SiS 32 MB message limit)."""
    if len(points) <= max_points:
        return points

    sample_prob = max_points / len(points)
    sampled = points.groupby("severity_label", observed=True, group_keys=False).apply(
        lambda group: group.sample(
            n=max(1, min(len(group), int(round(len(group) * sample_prob)))),
            random_state=42,
        ),
        include_groups=False,
    )
    if len(sampled) > max_points:
        sampled = sampled.sample(n=max_points, random_state=42)
    return sampled.reset_index(drop=True)


def _prepare_pydeck_points(
    map_geo: pd.DataFrame,
    *,
    sev_col: str,
    marker_opacity: float,
) -> tuple[pd.DataFrame, bool]:
    """Build a minimal pydeck payload — never send the full collision_view to the browser."""
    alpha = max(1, min(255, int(marker_opacity * 255)))
    labels = _severity_labels(map_geo, sev_col)
    slim = pd.DataFrame(
        {
            "longitude": pd.to_numeric(map_geo["longitude"], errors="coerce"),
            "latitude": pd.to_numeric(map_geo["latitude"], errors="coerce"),
            "severity_label": labels.astype(str),
        }
    )
    if "collision_index" in map_geo.columns:
        slim["collision_index"] = map_geo["collision_index"].astype("string")
    if "date" in map_geo.columns:
        slim["date"] = pd.to_datetime(map_geo["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    slim = slim.dropna(subset=["longitude", "latitude"]).reset_index(drop=True)
    slim["color"] = slim["severity_label"].map(
        lambda label: _hex_to_rgba(SEVERITY_COLORS.get(str(label), COLORS["accent"]), alpha)
    )

    sampled = False
    if is_snowflake_streamlit() and len(slim) > SNOWFLAKE_PYDECK_POINT_CAP:
        slim = _sample_points_stratified(slim, SNOWFLAKE_PYDECK_POINT_CAP)
        sampled = True

    slim["longitude"] = slim["longitude"].astype("float32")
    slim["latitude"] = slim["latitude"].astype("float32")
    return slim, sampled


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

    points, sampled = _prepare_pydeck_points(
        map_geo,
        sev_col=sev_col,
        marker_opacity=marker_opacity,
    )
    if points.empty:
        st.warning("No geocoded collisions available to plot on the map.")
        return

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
    if sampled:
        st.caption(
            f"Showing **{len(points):,}** of **{point_count:,}** map points on Snowflake "
            f"(32 MB browser limit). District table below uses all **{point_count:,}** points."
        )
    _render_georisk_legend()
    _render_pydeck_chart(deck)


def _render_pydeck_chart(deck) -> None:
    """Render pydeck with height when supported (SiS warehouse runtimes use older Streamlit)."""
    kwargs: dict = {"use_container_width": True}
    if "height" in inspect.signature(st.pydeck_chart).parameters:
        kwargs["height"] = MAP_HEIGHT
    else:
        st.markdown(
            f"""
<style>
.stApp [data-testid="stPydeckChart"],
.stApp [data-testid="stPydeckChart"] > div,
.stApp [data-testid="stPydeckChart"] iframe {{
  height: {MAP_HEIGHT}px !important;
  min-height: {MAP_HEIGHT}px !important;
}}
</style>
""",
            unsafe_allow_html=True,
        )
    st.pydeck_chart(deck, **kwargs)


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
