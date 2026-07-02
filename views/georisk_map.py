"""GeoRisk Map page."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from charts.plotly_charts import plot_chart, SEVERITY_COLORS
from styles.dataframe import render_dataframe
from transforms import ensure_label_columns as _ensure_label_columns, series_or_default as _series_or_default
from views.constants import HARM_INDEX_CAPTION

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
    severity_opts = sorted(geo[sev_col].dropna().astype(str).unique().tolist())
    severity_filter = st.multiselect(
        "Severity",
        options=severity_opts,
        default=severity_opts,
    )
    if severity_filter:
        geo = geo[geo[sev_col].astype(str).isin(severity_filter)]

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

    st.caption(f"Map shows geocoded collisions in the last 12 months ({map_period_label}).")
    point_count = len(map_geo)
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
    map_fig = px.scatter_mapbox(
        map_geo,
        lat="latitude",
        lon="longitude",
        color=sev_col,
        color_discrete_map=SEVERITY_COLORS,
        zoom=5,
        height=620,
        hover_data=hover_cols if hover_cols else None,
        title=f"Collision hotspots — last 12 months ({point_count:,} points)",
        labels={
            sev_col: "Collision Severity",
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
        mapbox_style="open-street-map",
        mapbox=dict(zoom=5, center={"lat": 54.5, "lon": -2.5}),
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
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
    marker_size = 5 if point_count <= 10_000 else 3 if point_count <= 100_000 else 2
    marker_opacity = 0.85 if point_count <= 10_000 else 0.55 if point_count <= 100_000 else 0.35
    map_fig.update_traces(marker=dict(size=marker_size, opacity=marker_opacity))
    plot_chart(map_fig, use_container_width=True)

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
