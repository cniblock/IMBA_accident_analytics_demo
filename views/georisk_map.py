"""GeoRisk Map page."""

import numpy as np
import pandas as pd
import streamlit as st

from charts.georisk_map import render_georisk_map
from styles.dataframe import render_dataframe
from transforms import ensure_label_columns as _ensure_label_columns, series_or_default as _series_or_default
from views.constants import HARM_INDEX_CAPTION

POINT_VISIBILITY_OPTIONS = ["Overview", "Standard", "Zoomed in", "High visibility"]


def _marker_style(point_visibility: str, n_points: int) -> tuple[int, float]:
    if point_visibility == "Overview":
        marker_size = 4 if n_points <= 10_000 else 3 if n_points <= 100_000 else 2
        marker_opacity = 0.55 if n_points <= 100_000 else 0.35
    elif point_visibility == "Standard":
        marker_size = 7 if n_points <= 10_000 else 5 if n_points <= 100_000 else 4
        marker_opacity = 0.70 if n_points <= 100_000 else 0.45
    elif point_visibility == "Zoomed in":
        marker_size = 11 if n_points <= 10_000 else 8 if n_points <= 100_000 else 6
        marker_opacity = 0.85 if n_points <= 100_000 else 0.60
    else:
        marker_size = 15 if n_points <= 10_000 else 11 if n_points <= 100_000 else 8
        marker_opacity = 0.95 if n_points <= 100_000 else 0.70
    return marker_size, marker_opacity


def page_georisk_map(collision_view: pd.DataFrame) -> None:
    st.title("GeoRisk Map")
    collision_view = _ensure_label_columns(
        collision_view,
        ["collision_severity", "light_conditions", "weather_conditions"],
    )
    if "latitude" not in collision_view.columns or "longitude" not in collision_view.columns:
        st.warning("Geocoding (latitude/longitude) is not available for this dataset.")
        return
    geo = collision_view.dropna(subset=["latitude", "longitude"]).copy()
    sev_col = "collision_severity_label" if "collision_severity_label" in geo.columns else "collision_severity"

    if geo.empty:
        st.warning("No geocoded collisions available for current filters.")
        return

    map_geo = geo
    map_period_label = "all available dates"
    if "date" in geo.columns:
        collision_dates = pd.to_datetime(geo["date"], errors="coerce")
        max_date = collision_dates.max()
        if pd.notna(max_date):
            cutoff = max_date - pd.DateOffset(months=12)
            map_geo = geo[collision_dates >= cutoff].copy()
            map_period_label = (
                f"{cutoff.strftime('%d %b %Y')} – {max_date.strftime('%d %b %Y')}"
            )

    if map_geo.empty:
        st.warning("No geocoded collisions in the last 12 months for current filters.")
        return

    st.caption(
        f"Map shows geocoded collisions in the last 12 months ({map_period_label}). "
        "Click a severity in the map legend to show or hide that group. "
        "Scroll the mouse wheel over the map to zoom in and out."
    )
    point_count = len(map_geo)
    point_visibility = st.radio(
        "Point visibility",
        POINT_VISIBILITY_OPTIONS,
        horizontal=True,
        index=1,
        help=(
            "Marker size is fixed in pixels — switch to Zoomed in or High visibility "
            "after panning to street level. Overview keeps the UK-wide view less dense."
        ),
    )
    hover_cols = [
        c
        for c in [
            "collision_index",
            "date",
            "speed_limit",
            "light_conditions_label",
            "weather_conditions_label",
        ]
        if c in map_geo.columns
    ]
    marker_size, marker_opacity = _marker_style(point_visibility, point_count)
    render_georisk_map(
        map_geo,
        sev_col=sev_col,
        point_visibility=point_visibility,
        marker_size=marker_size,
        marker_opacity=marker_opacity,
        hover_cols=hover_cols,
    )

    st.subheader("Top 10 Risk Districts")
    st.caption(HARM_INDEX_CAPTION)
    st.caption(f"District ranking uses the same 12-month map window ({map_period_label}).")
    fatal_collision = _series_or_default(map_geo, "collision_severity", 3) == 1
    top_districts = (
        map_geo.assign(fatal_collision=fatal_collision.astype(int))
        .groupby("district_display", dropna=False)
        .agg(
            Collisions=("collision_index", "count"),
            Fatal=("fatal_collision", "sum"),
            Serious=("serious_casualties", "sum"),
            Slight=("slight_casualties", "sum"),
        )
        .reset_index()
    )
    top_districts["Harm Index"] = (
        top_districts["Fatal"] * 5 + top_districts["Serious"] * 2 + top_districts["Slight"]
    )
    top_districts = (
        top_districts.sort_values("Harm Index", ascending=False)
        .head(10)
        .rename(columns={"district_display": "District"})
    )
    for c in ["Collisions", "Fatal", "Serious", "Slight", "Harm Index"]:
        top_districts[c] = np.rint(top_districts[c]).astype("int64")
    render_dataframe(top_districts, use_container_width=True)
