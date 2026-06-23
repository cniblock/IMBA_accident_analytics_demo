import base64
import io
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import CODE_MAPS
from data_loading import (
    add_district_labels as _add_district_labels,
    data_cache_fingerprint as _data_cache_fingerprint,
    load_raw_tables,
    resolve_district_display as _resolve_district_display,
)
from transforms import (
    REQUIRED_CASUALTY_VIEW_COLUMNS,
    REQUIRED_COLLISION_VIEW_COLUMNS,
    add_vehicle_intelligence_features as _add_vehicle_intelligence_features,
    apply_code_labels as _apply_code_labels,
    as_int_if_possible as _as_int_if_possible,
    build_casualty_views,
    build_collision_view,
    build_vehicle_view,
    casualty_priority_reason,
    casualty_priority_score,
    collision_level_serious_fatal_stats as _collision_level_serious_fatal_stats,
    effective_code_maps as _effective_code_maps,
    ensure_label_columns as _ensure_label_columns,
    safe_ratio as _safe_ratio,
    series_or_default as _series_or_default,
    validate_schema as _validate_schema,
)


st.set_page_config(
    page_title="STATS19 Intelligence Platform",
    page_icon="🚦",
    layout="wide",
)

def apply_sidebar_filters(collision_view: pd.DataFrame) -> pd.DataFrame:
    logo_path = Path(__file__).parent / "imba_logo.png"
    if logo_path.exists():
        logo_bytes = logo_path.read_bytes()
        logo_b64 = base64.b64encode(logo_bytes).decode()
        st.sidebar.markdown(
            f'<img src="data:image/png;base64,{logo_b64}" style="width:100%; border-radius:12px; object-fit:contain;" alt="IMBA logo" />',
            unsafe_allow_html=True,
        )
    st.sidebar.header("Global Filters")
    collision_view = collision_view.copy()
    collision_view["has_car"] = collision_view.get("has_car", 0).fillna(0)
    collision_view["has_motorbike"] = collision_view.get("has_motorbike", 0).fillna(0)
    collision_view["district_filter_display"] = _resolve_district_display(
        collision_view["local_authority_ons_district"]
    )

    with st.sidebar.expander("Vehicle Type", expanded=True):
        vehicle_type_filter = st.radio(
            "Show collisions involving",
            options=["cars", "motorbikes", "both"],
            index=0,
            format_func=lambda x: {"cars": "Cars", "motorbikes": "Motorbikes", "both": "Cars or Motorbikes"}[x],
            key="vehicle_type_filter",
        )

    min_date = collision_view["date"].min()
    max_date = collision_view["date"].max()

    if pd.isna(min_date) or pd.isna(max_date):
        return collision_view

    with st.sidebar.expander("Date Filter", expanded=True):
        date_range = st.date_input(
            "Date range",
            value=(min_date.date(), max_date.date()),
            min_value=min_date.date(),
            max_value=max_date.date(),
        )

    road_types = sorted(collision_view["road_type"].dropna().unique().tolist())
    road_type_map = CODE_MAPS.get("road_type", {})
    road_type_options = [_as_int_if_possible(v) for v in road_types]
    road_type_labels = {
        opt: f"{road_type_map.get(opt, 'Code')} ({opt})" if isinstance(opt, int) else str(opt)
        for opt in road_type_options
    }
    with st.sidebar.expander("Road Type Filter", expanded=False):
        selected_road_types = st.multiselect(
            "Road type",
            options=road_type_options,
            default=road_type_options,
            format_func=lambda x: road_type_labels.get(x, str(x)),
        )

    districts = (
        collision_view["district_filter_display"]
        .dropna()
        .astype("string")
        .sort_values()
        .unique()
        .tolist()
    )

    code_to_display = (
        collision_view[["local_authority_ons_district", "district_filter_display"]]
        .dropna()
        .drop_duplicates(subset=["local_authority_ons_district"])
        .set_index("local_authority_ons_district")["district_filter_display"]
        .to_dict()
    )
    state_key = "district_filter_selection"
    prior_selection = st.session_state.get(state_key, None)
    # None or first run: default to empty = show all regions. User choices persist in session.
    if prior_selection is not None and len(prior_selection) > 0:
        remapped_prior = [
            code_to_display.get(str(item).strip().upper(), item) for item in prior_selection
        ]
        remapped_prior = [item for item in remapped_prior if item in districts]
        default_districts = remapped_prior
    else:
        default_districts = []  # Empty = show all regions by default

    with st.sidebar.expander("District Filter", expanded=True):
        selected_districts = st.multiselect(
            "Local authority district (ONS)",
            options=districts,
            default=default_districts,
            key=state_key,
            help="Leave empty to show all regions. Select districts to filter.",
        )

    start_date, end_date = date_range
    mask = (
        collision_view["date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
        & collision_view["road_type"].isin(selected_road_types)
    )
    if selected_districts:
        mask &= collision_view["district_filter_display"].isin(selected_districts)
    if vehicle_type_filter == "cars":
        mask &= collision_view["has_car"] == 1
    elif vehicle_type_filter == "motorbikes":
        mask &= collision_view["has_motorbike"] == 1
    else:
        # "both" = collisions with at least one car or motorbike
        mask &= (collision_view["has_car"] == 1) | (collision_view["has_motorbike"] == 1)
    return collision_view[mask].copy()


def page_executive_overview(
    collision_view: pd.DataFrame,
    operational_stats: dict | None = None,
) -> None:
    st.title("Executive Overview")
    total_collisions = len(collision_view)
    fatal = int(collision_view["fatal_casualties"].sum()) if "fatal_casualties" in collision_view.columns else 0
    serious = int(collision_view["serious_casualties"].sum())
    slight = int(collision_view["slight_casualties"].sum())
    dark_pct = float(collision_view["is_dark"].mean() * 100) if len(collision_view) else 0.0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total collisions", f"{total_collisions:,}")
    col2.metric("Fatalities", f"{fatal:,}")
    col3.metric("Serious casualties", f"{serious:,}")
    col4.metric("Slight casualties", f"{slight:,}")
    col5.metric("Night-time collisions", f"{dark_pct:.1f}%")

    df = collision_view.dropna(subset=["date"]).copy()
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    months = sorted(df["month"].unique())
    alerts = None
    alerts_full = None
    focus_month = None
    baseline_months = []
    if len(months) >= 7:
        last_3_start = months[-4]
        focus_month = last_3_start
        baseline_months = [m for m in months if m < focus_month][-3:]
        if baseline_months:
            focus_data = (
                df[df["month"] == focus_month]
                .groupby("district_display", dropna=False)
                .size()
                .reset_index(name="focus")
            )
            baseline_data = (
                df[df["month"].isin(baseline_months)]
                .groupby("district_display", dropna=False)
                .size()
                .reset_index(name="baseline_total")
            )
            baseline_data["baseline_avg"] = baseline_data["baseline_total"] / 3
            alerts_full = (
                focus_data.merge(baseline_data[["district_display", "baseline_avg"]], on="district_display", how="outer")
                .fillna(0)
                .assign(change=lambda d: d["focus"] - d["baseline_avg"])
            )
            districts_worsening_count = int((alerts_full["change"] > 0).sum())
            alerts = alerts_full.sort_values("change", ascending=False).head(10)
    weekly = (
        collision_view.dropna(subset=["date"])
        .assign(week=lambda d: d["date"].dt.to_period("W").dt.start_time)
        .groupby("week", dropna=False)
        .size()
        .reset_index(name="collisions")
        .sort_values("week")
    )
    cases_this_week = int(weekly.iloc[-1]["collisions"]) if len(weekly) else 0
    high_priority = fatal + serious

    districts_worsening_count = (
        int((alerts_full["change"] > 0).sum()) if alerts_full is not None else 0
    )

    if operational_stats is not None:
        snap = {
            **operational_stats,
            "cases_this_week": cases_this_week,
            "districts_worsening": districts_worsening_count,
            "high_priority_casualties": high_priority,
        }
        st.subheader("Operations Snapshot")
        os1, os2, os3, os4, os5 = st.columns(5)
        os1.metric("Collisions in latest week", f"{snap.get('cases_this_week', 0):,}")
        os2.metric("Districts with worsening trend", snap.get("districts_worsening", 0))
        os3.metric("Fatal & serious casualties", f"{snap.get('high_priority_casualties', 0):,}")
        os4.metric("Last data refresh", snap.get("max_date_str", "–"))
        os5.metric("Records ingested this cycle", f"{snap.get('total_records', 0):,}")

    monthly_agg = {"collisions": ("collision_index", "count")}
    if "fatal_casualties" in collision_view.columns:
        monthly_agg["fatalities"] = ("fatal_casualties", "sum")
    monthly_agg["serious"] = ("serious_casualties", "sum")
    monthly = (
        collision_view.dropna(subset=["date"])
        .groupby(pd.Grouper(key="date", freq="MS"))
        .agg(**monthly_agg)
        .reset_index()
    )
    if "fatalities" in monthly.columns:
        monthly["fatalities"] = monthly["fatalities"].fillna(0)

    covid_ts = pd.Timestamp("2020-04-01")
    has_covid_period = len(monthly) > 0 and monthly["date"].min() <= covid_ts <= monthly["date"].max()
    covid_x_ms = covid_ts.timestamp() * 1000

    def _add_covid_vline(fig: go.Figure) -> None:
        if has_covid_period:
            fig.add_vline(
                x=covid_x_ms,
                line_dash="dash",
                line_color="gray",
                annotation_text="COVID mobility restrictions – April 2020",
                annotation_position="top",
            )

    tc1, tc2 = st.columns(2)
    harm_fig = None
    with tc1:
        exposure_fig = px.line(monthly, x="date", y="collisions", title="Collisions per month (Exposure)")
        exposure_fig.update_traces(line_color="#1f77b4")
        exposure_fig.update_layout(
            xaxis_title="", yaxis_title="Collisions",
            margin=dict(t=40, b=30, l=50, r=20), showlegend=False,
        )
        exposure_fig.update_traces(hovertemplate="%{x|%b %Y}<br>Collisions = %{y}<extra></extra>")
        _add_covid_vline(exposure_fig)
        st.plotly_chart(exposure_fig, use_container_width=True)

    with tc2:
        harm_cols = [c for c in ["fatalities", "serious"] if c in monthly.columns]
        if harm_cols:
            harm_long = monthly.melt(
                id_vars=["date"],
                value_vars=harm_cols,
                var_name="metric",
                value_name="count",
            )
            harm_long["metric"] = harm_long["metric"].map(
                {"fatalities": "Fatalities", "serious": "Serious injuries"}
            )
            harm_fig = px.line(
                harm_long, x="date", y="count", color="metric",
                title="Fatalities & Serious injuries per month (Harm)",
                color_discrete_map={"Fatalities": "#8B0000", "Serious injuries": "#ff7f0e"},
            )
            harm_fig.update_layout(
                xaxis_title="", yaxis_title="Count",
                margin=dict(t=40, b=30, l=50, r=20),
                legend_title="",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            harm_fig.update_traces(hovertemplate="%{x|%b %Y}<br>%{fullData.name} = %{y}<extra></extra>")
            _add_covid_vline(harm_fig)
            st.plotly_chart(harm_fig, use_container_width=True)
        else:
            st.info("Harm metrics (fatalities, serious injuries) not available in this dataset.")

    fatal_col = "fatal_casualties" if "fatal_casualties" in collision_view.columns else None
    risk_agg = {
        "collisions": ("collision_index", "count"),
        "serious": ("serious_casualties", "sum"),
        "slight": ("slight_casualties", "sum"),
    }
    if fatal_col:
        risk_agg["fatal"] = (fatal_col, "sum")
    risk_by_district = (
        collision_view.groupby("district_display", dropna=False)
        .agg(**risk_agg)
        .reset_index()
    )
    risk_by_district["harm_index"] = (
        risk_by_district["serious"] * 2 + risk_by_district["slight"]
    )
    if "fatal" in risk_by_district.columns:
        risk_by_district["harm_index"] += risk_by_district["fatal"] * 5
    force_col = "police_force_label" if "police_force_label" in collision_view.columns else "police_force"
    district_force = (
        collision_view.groupby("district_display", dropna=False)[force_col]
        .agg(lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else "Unknown")
        .reset_index(name="police_force_display")
    )
    top_risk = risk_by_district.sort_values("harm_index", ascending=False).head(10)
    round_cols = ["serious", "slight", "harm_index"]
    if "fatal" in top_risk.columns:
        round_cols.append("fatal")
    for col in round_cols:
        top_risk[col] = np.rint(top_risk[col]).astype("int64")
    top_risk = top_risk.merge(district_force, on="district_display", how="left")
    rename_map = {
        "district_display": "District",
        "police_force_display": "Police Force",
        "collisions": "Collisions",
        "serious": "Serious Injuries",
        "slight": "Slight Injuries",
        "harm_index": "Harm Index",
    }
    if "fatal" in top_risk.columns:
        rename_map["fatal"] = "Fatalities"
    top_risk = top_risk.rename(columns=rename_map)
    col_order = ["District", "Collisions", "Fatalities", "Serious Injuries", "Slight Injuries", "Harm Index", "Police Force"]
    top_risk = top_risk[[c for c in col_order if c in top_risk.columns]]
    st.subheader("Top Risk Districts")
    st.dataframe(top_risk, use_container_width=True, hide_index=True)

    st.subheader("Report Export")
    with st.expander("Download automated report packs"):
        exec_summary = pd.DataFrame(
            [
                {"Metric": "Total collisions", "Value": total_collisions},
                {"Metric": "Fatalities", "Value": fatal},
                {"Metric": "Serious casualties", "Value": serious},
                {"Metric": "Slight casualties", "Value": slight},
            ]
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                label="Executive summary CSV",
                data=exec_summary.to_csv(index=False),
                file_name="executive_summary.csv",
                mime="text/csv",
            )
        with c2:
            st.download_button(
                label="District MI export",
                data=top_risk.to_csv(index=False),
                file_name="district_MI_export.csv",
                mime="text/csv",
            )
        with c3:
            st.download_button(
                label="Filtered pack download",
                data=collision_view.to_csv(index=False),
                file_name="filtered_collision_pack.csv",
                mime="text/csv",
            )

    st.subheader("Operational Alerts")
    if alerts is not None and len(alerts) > 0:
        alerts_display = alerts.rename(
            columns={
                "district_display": "District",
                "focus": "Collisions (focus mo)",
                "baseline_avg": "Prior 3‑mo avg",
                "change": "Change vs baseline",
            }
        )
        alerts_display[["Collisions (focus mo)", "Prior 3‑mo avg", "Change vs baseline"]] = alerts_display[
            ["Collisions (focus mo)", "Prior 3‑mo avg", "Change vs baseline"]
        ].round(1)
        focus_label = focus_month.strftime("%b %Y")
        st.caption(
            f"Top 10 districts with the largest increase in collisions in {focus_label} "
            f"vs their prior 3‑month average (avoids incomplete recent data)."
        )
        st.dataframe(alerts_display[["District", "Collisions (focus mo)", "Prior 3‑mo avg", "Change vs baseline"]], use_container_width=True, hide_index=True)
    elif len(months) >= 7 and len(baseline_months) == 0:
        st.info("Not enough historical data to compute month-over-baseline comparison.")
    else:
        st.info("Need at least 7 months of data for the month-versus-baseline comparison.")


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

    sample_size = min(5000, len(geo))
    hover_cols = [c for c in ["collision_index", "date", "speed_limit", "light_conditions_label", "weather_conditions_label"] if c in geo.columns]
    map_fig = px.scatter_mapbox(
        geo.sample(n=sample_size, random_state=42),
        lat="latitude",
        lon="longitude",
        color=sev_col,
        zoom=5,
        height=620,
        hover_data=hover_cols if hover_cols else None,
        title="Collision hotspots (sampled for performance)",
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
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        hoverlabel=dict(
            namelength=-1,
            bgcolor="white",
            font_size=12,
        ),
    )
    # Only set custom hovertemplate when we have all 5 hover columns to avoid index errors
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
    st.plotly_chart(map_fig, use_container_width=True)

    st.subheader("Top 10 Risk Districts")
    fatal_collision = _series_or_default(geo, "collision_severity", 3) == 1
    top_districts = (
        geo.assign(fatal_collision=fatal_collision.astype(int))
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
    st.dataframe(top_districts, use_container_width=True, hide_index=True)


def page_risk_factors(collision_view: pd.DataFrame) -> None:
    st.title("Risk Factors")
    collision_view = _ensure_label_columns(
        collision_view,
        [
            "junction_detail",
            "first_road_class",
            "junction_control",
            "carriageway_hazards",
            "special_conditions_at_site",
        ],
    )
    j_detail_col = "junction_detail_label" if "junction_detail_label" in collision_view.columns else "junction_detail"
    road_class_col = "first_road_class_label" if "first_road_class_label" in collision_view.columns else "first_road_class"

    fac1, fac2 = st.columns(2)
    exclude_missing = "Data missing or out of range"
    with fac1:
        weather = (
            collision_view.groupby("weather_conditions_label", dropna=False)
            .agg(collisions=("collision_index", "count"), serious=("serious_casualties", "sum"))
            .reset_index()
            .sort_values("serious", ascending=False)
        )
        weather = weather[weather["weather_conditions_label"] != exclude_missing]
        weather_fig = px.bar(
            weather,
            x="weather_conditions_label",
            y="serious",
            title="Serious casualties by weather",
            labels={"weather_conditions_label": "Weather conditions", "serious": "Serious casualties"},
        )
        weather_fig.update_traces(
            hovertemplate="Weather Conditions = %{x}<br>Serious Casualties = %{y}<extra></extra>"
        )
        st.plotly_chart(weather_fig, use_container_width=True)
    with fac2:
        light = (
            collision_view.groupby("light_conditions_label", dropna=False)
            .agg(collisions=("collision_index", "count"), serious=("serious_casualties", "sum"))
            .reset_index()
            .sort_values("serious", ascending=False)
        )
        light = light[light["light_conditions_label"] != exclude_missing]
        light_fig = px.bar(
            light,
            x="light_conditions_label",
            y="serious",
            title="Serious casualties by light",
            labels={"light_conditions_label": "Light conditions", "serious": "Serious casualties"},
        )
        light_fig.update_traces(
            hovertemplate="Light Conditions = %{x}<br>Serious Casualties = %{y}<extra></extra>"
        )
        st.plotly_chart(light_fig, use_container_width=True)

    speed = (
        collision_view.groupby("speed_limit", dropna=False)
        .agg(
            collisions=("collision_index", "count"),
            serious=("serious_casualties", "sum"),
            slight=("slight_casualties", "sum"),
        )
        .reset_index()
    )
    speed["serious_rate"] = _safe_ratio(speed["serious"], speed["collisions"]) * 100
    speed_fig = px.line(
        speed.sort_values("speed_limit"),
        x="speed_limit",
        y="serious_rate",
        markers=True,
        title="Serious casualty rate by speed limit (%)",
        labels={"speed_limit": "Speed limit (mph)", "serious_rate": "Serious rate (%)"},
    )
    speed_fig.update_traces(
        hovertemplate="Speed Limit (mph) = %{x}<br>Serious Rate (%) = %{y:.1f}<extra></extra>"
    )
    st.plotly_chart(speed_fig, use_container_width=True)

    junction = (
        collision_view.groupby(j_detail_col, dropna=False)
        .agg(collisions=("collision_index", "count"), serious=("serious_casualties", "sum"))
        .reset_index()
        .sort_values("serious", ascending=False)
        .head(15)
    )
    junction_exclude = {"Data missing or out of range", "unknown (self reported)"}
    junction = junction[~junction[j_detail_col].astype(str).str.strip().isin(junction_exclude)]
    junction_fig = px.bar(
        junction,
        x=j_detail_col,
        y="serious",
        title="Junction detail vs serious casualties",
        labels={j_detail_col: "Junction detail", "serious": "Serious casualties"},
    )
    junction_fig.update_traces(
        hovertemplate="Junction Detail = %{x}<br>Serious Casualties = %{y}<extra></extra>"
    )
    st.plotly_chart(junction_fig, use_container_width=True)

    st.markdown("### Road Class & Corridor Intelligence")
    road_class = (
        collision_view.groupby(road_class_col, dropna=False)
        .agg(
            collisions=("collision_index", "count"),
            ksi=("fatal_or_serious_collision", "sum"),
        )
        .reset_index()
    )
    road_class["ksi_rate_pct"] = _safe_ratio(road_class["ksi"], road_class["collisions"]) * 100
    road_class = road_class[road_class["collisions"] >= 50].copy()
    if not road_class.empty:
        road_class_display_map = {
            "A": "A Road",
            "B": "B Road",
            "C": "C Road",
            "A(M)": "A(M) Road",
            "Motorway": "Motorway",
            "Unclassified": "Unclassified Road",
        }
        road_class["road_class_display"] = road_class[road_class_col].astype("string").replace(road_class_display_map)
        road_class_fig = px.bar(
            road_class.sort_values("ksi_rate_pct", ascending=False),
            x="road_class_display",
            y="ksi_rate_pct",
            hover_data=["collisions", "ksi"],
            title="KSI rate by first road class (%)",
            labels={
                "road_class_display": "Road class",
                "ksi_rate_pct": "KSI rate (%)",
                "collisions": "Collisions",
                "ksi": "Fatal/Serious",
            },
        )
        road_class_fig.update_traces(
            hovertemplate=(
                "Road Class = %{x}<br>"
                "KSI Rate (%) = %{y:.1f}<br>"
                "Collisions = %{customdata[0]}<br>"
                "Fatal/Serious = %{customdata[1]}<extra></extra>"
            )
        )
        st.plotly_chart(road_class_fig, use_container_width=True)

    corridors = (
        collision_view[collision_view["first_road_number"] > 0]
        .groupby(["first_road_class", "first_road_number"], dropna=False)
        .agg(
            collisions=("collision_index", "count"),
            fatal_or_serious=("fatal_or_serious_collision", "sum"),
            serious=("serious_casualties", "sum"),
            slight=("slight_casualties", "sum"),
        )
        .reset_index()
    )
    corridors = corridors[corridors["collisions"] >= 30].copy()
    class_to_prefix = {1: "M", 2: "A", 3: "A", 4: "B", 5: "C"}
    corridors["road_ref"] = corridors.apply(
        lambda r: (
            f"{class_to_prefix.get(int(r['first_road_class']), '')}{int(r['first_road_number'])}"
            if int(r["first_road_class"]) in class_to_prefix
            else f"Road {int(r['first_road_number'])}"
        ),
        axis=1,
    )
    corridors["harm_index"] = corridors["serious"] * 2 + corridors["slight"]
    for c in ["collisions", "fatal_or_serious", "serious", "slight", "harm_index"]:
        corridors[c] = np.rint(corridors[c]).astype("int64")
    if not corridors.empty:
        st.dataframe(
            corridors.sort_values("harm_index", ascending=False)
            .head(15)
            .rename(
                columns={
                    "road_ref": "Road",
                    "first_road_number": "Road Number (Numeric)",
                    "collisions": "Collisions",
                    "fatal_or_serious": "Fatal/Serious Collisions",
                    "serious": "Serious",
                    "slight": "Slight",
                    "harm_index": "Harm Index",
                }
            )[
                [
                    "Road",
                    "Collisions",
                    "Fatal/Serious Collisions",
                    "Serious",
                    "Slight",
                    "Harm Index",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        watchlist_numbers = [4540, 4040, 1000, 666, 406, 259, 124, 41, 38, 35, 34, 27, 13, 6, 1]
        watch = corridors[corridors["first_road_number"].isin(watchlist_numbers)].copy()
        st.subheader("Specified Road Number Watchlist")
        if watch.empty:
            st.info("None of the specified road numbers meet current filters/thresholds.")
        else:
            st.dataframe(
                watch.sort_values("harm_index", ascending=False).rename(
                    columns={
                        "road_ref": "Road",
                        "first_road_number": "Road Number (Numeric)",
                        "collisions": "Collisions",
                        "fatal_or_serious": "Fatal/Serious Collisions",
                        "serious": "Serious",
                        "slight": "Slight",
                        "harm_index": "Harm Index",
                    }
                )[
                    [
                        "Road",
                        "Collisions",
                        "Fatal/Serious Collisions",
                        "Serious",
                        "Slight",
                        "Harm Index",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("### Junction & Control Intelligence")
    junction_control_col = "junction_control_label" if "junction_control_label" in collision_view.columns else "junction_control"
    junction_loc_col = j_detail_col
    junction_mix = (
        collision_view.groupby([junction_control_col, junction_loc_col], dropna=False)
        .agg(collisions=("collision_index", "count"), ksi=("fatal_or_serious_collision", "sum"))
        .reset_index()
    )
    j_exclude = {"Data missing or out of range", "unknown (self reported)"}
    junction_mix = junction_mix[
        (junction_mix["collisions"] >= 25)
        & (~junction_mix[junction_control_col].astype(str).str.strip().isin(j_exclude))
        & (~junction_mix[junction_loc_col].astype(str).str.strip().isin(j_exclude))
    ].copy()
    if not junction_mix.empty:
        junction_mix["ksi_rate_pct"] = _safe_ratio(junction_mix["ksi"], junction_mix["collisions"]) * 100
        jheat = px.density_heatmap(
            junction_mix,
            x=junction_control_col,
            y=junction_loc_col,
            z="ksi_rate_pct",
            histfunc="avg",
            title="KSI rate by junction control and detail (%)",
            color_continuous_scale="Reds",
            labels={
                junction_control_col: "Junction control",
                junction_loc_col: "Junction detail",
                "ksi_rate_pct": "KSI rate (%)",
            },
        )
        jheat.update_traces(
            hovertemplate="Junction Control = %{x}<br>Junction Detail = %{y}<br>KSI Rate (%) = %{z:.1f}<extra></extra>"
        )
        st.plotly_chart(jheat, use_container_width=True)

    st.markdown("### Hazards & Roadworks Lens")
    hazard_col = "carriageway_hazards_label" if "carriageway_hazards_label" in collision_view.columns else "carriageway_hazards"
    special_col = "special_conditions_at_site_label" if "special_conditions_at_site_label" in collision_view.columns else "special_conditions_at_site"
    hazard_view = collision_view.copy()
    hazard_view["hazard_flag"] = (
        (_series_or_default(hazard_view, "carriageway_hazards", 0) > 0)
        | (_series_or_default(hazard_view, "special_conditions_at_site", 0) > 0)
    ).astype(int)
    hz1, hz2, hz3 = st.columns(3)
    hz1.metric("Hazard/Special condition collisions", f"{int(hazard_view['hazard_flag'].sum()):,}")
    hz2.metric("Hazard collision share", f"{hazard_view['hazard_flag'].mean()*100:.1f}%")
    hazard_ksi_rate = (
        100
        * hazard_view.loc[hazard_view["hazard_flag"] == 1, "fatal_or_serious_collision"].sum()
        / max(1, (hazard_view["hazard_flag"] == 1).sum())
    )
    hz3.metric("KSI rate when hazard present", f"{hazard_ksi_rate:.1f}%")

    exclude_unknown = {
        "Unknown",
        "Data missing or out of range",
        "unknown (self reported)",
    }
    hazard_by_type = (
        hazard_view.groupby(hazard_col, dropna=False)
        .agg(collisions=("collision_index", "count"), ksi=("fatal_or_serious_collision", "sum"))
        .reset_index()
    )
    hazard_by_type = hazard_by_type[
        (hazard_by_type["collisions"] >= 20)
        & (~hazard_by_type[hazard_col].astype(str).str.strip().isin(exclude_unknown))
    ].copy()
    if not hazard_by_type.empty:
        hazard_by_type["ksi_rate_pct"] = _safe_ratio(hazard_by_type["ksi"], hazard_by_type["collisions"]) * 100
        hazard_fig = px.bar(
            hazard_by_type.sort_values("ksi_rate_pct", ascending=False),
            x=hazard_col,
            y="ksi_rate_pct",
            hover_data=["collisions", "ksi"],
            title="KSI rate by carriageway hazard type (%)",
            labels={
                hazard_col: "Carriageway hazard",
                "ksi_rate_pct": "KSI rate (%)",
                "collisions": "Collisions",
                "ksi": "Fatal/Serious",
            },
        )
        hazard_fig.update_traces(
            hovertemplate=(
                "Carriageway Hazard = %{x}<br>"
                "KSI Rate (%) = %{y:.1f}<br>"
                "Collisions = %{customdata[0]}<br>"
                "Fatal/Serious = %{customdata[1]}<extra></extra>"
            )
        )
        st.plotly_chart(hazard_fig, use_container_width=True)

    special_by_type = (
        hazard_view.groupby(special_col, dropna=False)
        .agg(collisions=("collision_index", "count"), ksi=("fatal_or_serious_collision", "sum"))
        .reset_index()
    )
    special_by_type = special_by_type[
        (special_by_type["collisions"] >= 20)
        & (~special_by_type[special_col].astype(str).str.strip().isin(exclude_unknown))
    ].copy()
    if not special_by_type.empty:
        special_by_type["ksi_rate_pct"] = _safe_ratio(special_by_type["ksi"], special_by_type["collisions"]) * 100
        special_fig = px.bar(
            special_by_type.sort_values("ksi_rate_pct", ascending=False),
            x=special_col,
            y="ksi_rate_pct",
            hover_data=["collisions", "ksi"],
            title="KSI rate by special conditions at site (%)",
            labels={
                special_col: "Special conditions at site",
                "ksi_rate_pct": "KSI rate (%)",
                "collisions": "Collisions",
                "ksi": "Fatal/Serious",
            },
        )
        special_fig.update_traces(
            hovertemplate=(
                "Special Conditions At Site = %{x}<br>"
                "KSI Rate (%) = %{y:.1f}<br>"
                "Collisions = %{customdata[0]}<br>"
                "Fatal/Serious = %{customdata[1]}<extra></extra>"
            )
        )
        st.plotly_chart(special_fig, use_container_width=True)

    st.markdown("### Trunk Road Governance Split")
    trunk_col = "trunk_road_flag_label" if "trunk_road_flag_label" in collision_view.columns else "trunk_road_flag"
    trunk_split = (
        collision_view.groupby(trunk_col, dropna=False)
        .agg(
            collisions=("collision_index", "count"),
            ksi=("fatal_or_serious_collision", "sum"),
            serious=("serious_casualties", "sum"),
            slight=("slight_casualties", "sum"),
        )
        .reset_index()
    )
    trunk_label_map = {
        "-1": "Data missing or out of range",
        "1": "Trunk (Roads managed by Highways England)",
        "2": "Non-trunk",
    }
    trunk_split["road_ownership_display"] = trunk_split[trunk_col].astype("string").replace(trunk_label_map)
    for c in ["collisions", "ksi", "serious", "slight"]:
        trunk_split[c] = np.rint(trunk_split[c]).astype("int64")
    trunk_split["ksi_rate_pct"] = _safe_ratio(trunk_split["ksi"], trunk_split["collisions"]) * 100
    st.dataframe(
        trunk_split.rename(
            columns={
                "road_ownership_display": "Road Ownership",
                "collisions": "Collisions",
                "ksi": "Fatal/Serious Collisions",
                "serious": "Serious Casualties",
                "slight": "Slight Casualties",
                "ksi_rate_pct": "KSI Rate (%)",
            }
        )[
            [
                "Road Ownership",
                "Collisions",
                "Fatal/Serious Collisions",
                "Serious Casualties",
                "Slight Casualties",
                "KSI Rate (%)",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    trunk_district = (
        collision_view[_series_or_default(collision_view, "trunk_road_flag", -1) == 1]
        .groupby("district_display", dropna=False)
        .agg(collisions=("collision_index", "count"), ksi=("fatal_or_serious_collision", "sum"))
        .reset_index()
    )
    if not trunk_district.empty:
        trunk_district["collisions"] = np.rint(trunk_district["collisions"]).astype("int64")
        trunk_district["ksi"] = np.rint(trunk_district["ksi"]).astype("int64")
        trunk_district["ksi_rate_pct"] = _safe_ratio(trunk_district["ksi"], trunk_district["collisions"]) * 100
        st.dataframe(
            trunk_district.sort_values("ksi", ascending=False).head(12).rename(
                columns={
                    "district_display": "District",
                    "collisions": "Trunk Road Collisions",
                    "ksi": "Trunk Road Fatal/Serious Collisions",
                    "ksi_rate_pct": "Trunk Road KSI Rate (%)",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


def page_vehicle_intelligence(vehicle_view: pd.DataFrame) -> None:
    st.title("Vehicle Intelligence")
    if vehicle_view.empty:
        st.warning("No vehicle records available for the selected filters.")
        return

    vehicle_data = vehicle_view.copy()
    vehicle_data["vehicle_type_label"] = vehicle_data["vehicle_type_label"].fillna("Unknown")
    if "incident_signature" not in vehicle_data.columns:
        vehicle_data = _add_vehicle_intelligence_features(vehicle_data)

    total_vehicle_rows = len(vehicle_data)
    total_collisions = vehicle_data["collision_index"].nunique()
    avg_driver_age = vehicle_data["age_of_driver"].mean()
    avg_risk_score = vehicle_data["triage_score"].mean()
    avg_harm_score = vehicle_data["harm_score"].mean()

    st.markdown("### Vehicle Risk Profile")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Vehicle records", f"{total_vehicle_rows:,}")
    k2.metric("Linked collisions", f"{total_collisions:,}")
    k3.metric("Avg driver age", f"{avg_driver_age:.1f}" if pd.notna(avg_driver_age) else "N/A")
    k4.metric("Avg triage score", f"{avg_risk_score:.1f}" if pd.notna(avg_risk_score) else "N/A")
    k5.metric("Avg harm score", f"{avg_harm_score:.1f}" if pd.notna(avg_harm_score) else "N/A")

    vehicle_agg = (
        vehicle_data.groupby("vehicle_type_label", dropna=False)
        .agg(
            vehicles=("vehicle_reference", "count"),
            avg_speed_limit=("speed_limit", "mean"),
            avg_driver_age=("age_of_driver", "mean"),
        )
        .reset_index()
    )
    collision_stats = _collision_level_serious_fatal_stats(vehicle_data, ["vehicle_type_label"])
    by_vehicle = vehicle_agg.merge(collision_stats, on="vehicle_type_label", how="left")
    by_vehicle = by_vehicle.sort_values("serious_fatal_collision_rate_pct", ascending=False)

    top_vehicle = by_vehicle.head(15).copy()
    for col in ["fatal_collisions", "serious_collisions", "serious_or_fatal_collisions"]:
        top_vehicle[col] = np.rint(top_vehicle[col]).astype("int64")
    top_vehicle["avg_speed_limit"] = np.rint(top_vehicle["avg_speed_limit"]).astype("int64")
    top_vehicle["avg_driver_age"] = np.rint(top_vehicle["avg_driver_age"]).astype("int64")
    st.subheader("Vehicle Type Risk Ranking")
    st.dataframe(
        top_vehicle.rename(
            columns={
                "vehicle_type_label": "Vehicle Type",
                "vehicles": "Vehicle Records",
                "collisions": "Collisions",
                "fatal_collisions": "Fatal Collisions",
                "serious_collisions": "Serious Collisions",
                "serious_or_fatal_collisions": "Serious/Fatal Collisions",
                "serious_fatal_collision_rate_pct": "Serious/Fatal Collision Rate (%)",
                "avg_speed_limit": "Avg Speed Limit",
                "avg_driver_age": "Avg Driver Age",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        ratio_fig = px.bar(
            by_vehicle.head(12),
            x="vehicle_type_label",
            y="serious_fatal_collision_rate_pct",
            title="Serious/fatal collision rate by vehicle type (%)",
            labels={
                "vehicle_type_label": "Vehicle type",
                "serious_fatal_collision_rate_pct": "Serious/Fatal collision rate (%)",
            },
        )
        ratio_fig.update_traces(
            hovertemplate="Vehicle Type = %{x}<br>Serious/Fatal Collision Rate (%) = %{y:.1f}<extra></extra>"
        )
        st.plotly_chart(ratio_fig, use_container_width=True)
    with c2:
        speed_fig = px.scatter(
            by_vehicle,
            x="avg_speed_limit",
            y="serious_fatal_collision_rate_pct",
            size="collisions",
            color="vehicle_type_label",
            title="Serious/fatal collision rate vs average speed limit",
            hover_data=["avg_driver_age", "vehicles"],
            labels={
                "avg_speed_limit": "Average speed limit (mph)",
                "serious_fatal_collision_rate_pct": "Serious/Fatal collision rate (%)",
                "vehicle_type_label": "Vehicle type",
                "avg_driver_age": "Average driver age",
                "vehicles": "Vehicles",
            },
        )
        speed_fig.update_traces(
            hovertemplate=(
                "Vehicle Type = %{fullData.name}<br>"
                "Average Speed Limit (mph) = %{x}<br>"
                "Serious/Fatal Collision Rate (%) = %{y:.1f}<br>"
                "Average Driver Age = %{customdata[0]}<br>"
                "Vehicles = %{customdata[1]}<extra></extra>"
            )
        )
        st.plotly_chart(speed_fig, use_container_width=True)

    st.subheader("Vehicle Type and Speed Risk Matrix")
    speed_matrix_stats = _collision_level_serious_fatal_stats(
        vehicle_data, ["vehicle_type_label", "speed_limit"]
    )
    vehicle_type_order = [
        "Car",
        "Taxi/Private hire car",
        "Van/Goods under 3.5t",
        "Goods 3.5t to 7.5t",
        "Goods over 7.5t",
        "Bus/coach",
        "Minibus",
        "Agricultural vehicle",
        "Pedal cycle",
        "Mobility scooter",
        "Motorcycle 50cc and under",
        "Motorcycle 125cc and under",
        "Motorcycle over 125cc and up to 500cc",
        "Motorcycle over 500cc",
        "Electric motorcycle",
        "Other vehicle",
    ]
    speed_matrix = speed_matrix_stats[
        (speed_matrix_stats["collisions"] >= 25)
        & (pd.to_numeric(speed_matrix_stats["speed_limit"], errors="coerce") > 0)
        & (speed_matrix_stats["vehicle_type_label"].astype(str).str.strip() != "Unknown")
    ].copy()
    if speed_matrix.empty:
        st.info("Not enough data for a stable vehicle-speed risk matrix under current filters.")
    else:
        extra_vehicle_types = [
            label
            for label in speed_matrix["vehicle_type_label"].dropna().astype(str).unique().tolist()
            if label not in vehicle_type_order
        ]
        ordered_vehicle_types = vehicle_type_order + sorted(extra_vehicle_types)
        speed_matrix["vehicle_type_label"] = pd.Categorical(
            speed_matrix["vehicle_type_label"],
            categories=ordered_vehicle_types,
            ordered=True,
        )
        speed_matrix = speed_matrix.sort_values(["vehicle_type_label", "speed_limit"])
        speed_order = sorted(pd.to_numeric(speed_matrix["speed_limit"], errors="coerce").dropna().unique().tolist())
        matrix = (
            speed_matrix.assign(speed_limit=pd.to_numeric(speed_matrix["speed_limit"], errors="coerce"))
            .set_index(["vehicle_type_label", "speed_limit"])[
                ["serious_fatal_collision_rate_pct", "collisions", "fatal_collisions", "serious_collisions"]
            ]
            .reindex(
                pd.MultiIndex.from_product(
                    [ordered_vehicle_types, speed_order],
                    names=["vehicle_type_label", "speed_limit"],
                )
            )
            .reset_index()
        )
        matrix["has_data"] = matrix["collisions"].notna()
        matrix["z_value"] = matrix["serious_fatal_collision_rate_pct"].where(matrix["has_data"], -1.0)
        matrix["collisions_display"] = matrix["collisions"].map(
            lambda v: f"{int(round(v)):,}" if pd.notna(v) else ""
        )
        matrix["fatal_collisions_display"] = matrix["fatal_collisions"].map(
            lambda v: f"{int(round(v)):,}" if pd.notna(v) else ""
        )
        matrix["serious_collisions_display"] = matrix["serious_collisions"].map(
            lambda v: f"{int(round(v)):,}" if pd.notna(v) else ""
        )
        matrix["hover_text"] = np.where(
            matrix["has_data"],
            (
                "Speed Limit (mph) = "
                + matrix["speed_limit"].astype(int).astype(str)
                + "<br>Vehicle Type = "
                + matrix["vehicle_type_label"].astype(str)
                + "<br>Serious/Fatal Collision Rate (%) = "
                + matrix["serious_fatal_collision_rate_pct"].round(1).astype(str)
                + "<br>Collisions = "
                + matrix["collisions_display"]
                + "<br>Fatal Collisions = "
                + matrix["fatal_collisions_display"]
                + "<br>Serious Collisions = "
                + matrix["serious_collisions_display"]
            ),
            (
                "Speed Limit (mph) = "
                + matrix["speed_limit"].astype(int).astype(str)
                + "<br>Vehicle Type = "
                + matrix["vehicle_type_label"].astype(str)
                + "<br>No data for this cell"
            ),
        )
        z_matrix = matrix.pivot(index="vehicle_type_label", columns="speed_limit", values="z_value").reindex(ordered_vehicle_types)
        text_matrix = matrix.pivot(index="vehicle_type_label", columns="speed_limit", values="hover_text").reindex(ordered_vehicle_types)
        max_rate = float(speed_matrix["serious_fatal_collision_rate_pct"].max())
        heat = go.Figure(
            data=[
                go.Heatmap(
                    x=speed_order,
                    y=ordered_vehicle_types,
                    z=z_matrix.values,
                    text=text_matrix.values,
                    hovertemplate="%{text}<extra></extra>",
                    zmin=-1,
                    zmax=max_rate,
                    colorbar={"title": "Serious/Fatal collision rate (%)"},
                    colorscale=[
                        [0.0, "#d9d9d9"],
                        [0.015, "#d9d9d9"],
                        [0.0151, "#fff5f0"],
                        [0.35, "#fcbba1"],
                        [0.6, "#fb6a4a"],
                        [0.8, "#ef3b2c"],
                        [1.0, "#99000d"],
                    ],
                )
            ]
        )
        heat.update_layout(
            title="Serious/fatal collision rate by vehicle type and speed limit (%)",
            xaxis_title="Speed limit (mph)",
            yaxis_title="Vehicle type",
        )
        st.plotly_chart(heat, use_container_width=True)

    st.subheader("Average Driver Age by Vehicle Type")
    age_fig = px.bar(
        by_vehicle.sort_values("avg_driver_age", ascending=False).head(15),
        x="vehicle_type_label",
        y="avg_driver_age",
        title="Average driver age for selected vehicle types",
        labels={
            "vehicle_type_label": "Vehicle type",
            "avg_driver_age": "Average driver age",
        },
    )
    age_fig.update_traces(
        hovertemplate="Vehicle Type = %{x}<br>Average Driver Age = %{y:.0f}<extra></extra>"
    )
    st.plotly_chart(age_fig, use_container_width=True)

    st.markdown("### Loss of Control & Departure Intelligence")
    st.caption(
        "Rates below are computed at vehicle-record level (not collision level). "
        "They reflect the proportion of vehicle records with each characteristic."
    )
    severe_rate_loc = (
        100
        * vehicle_data.loc[vehicle_data["loss_of_control_flag"] == 1, "serious_or_fatal_collision"].sum()
        / max(1, (vehicle_data["loss_of_control_flag"] == 1).sum())
    )
    loc1, loc2, loc3, loc4 = st.columns(4)
    loc1.metric(
        "Loss-of-control vehicle-record rate",
        f"{vehicle_data['loss_of_control_flag'].mean() * 100:.1f}%",
    )
    loc2.metric(
        "Roadway-departure vehicle-record rate",
        f"{vehicle_data['roadway_departure_flag'].mean() * 100:.1f}%",
    )
    loc3.metric(
        "Off-carriageway impact vehicle-record rate",
        f"{vehicle_data['impact_off_carriageway_flag'].mean() * 100:.1f}%",
    )
    loc4.metric(
        "Serious/Fatal rate among LOC-tagged vehicle records",
        f"{severe_rate_loc:.1f}%",
    )

    loc_conditions = (
        vehicle_data.groupby("road_surface_conditions_label", dropna=False)
        .agg(
            vehicles=("vehicle_reference", "count"),
            loss_of_control=("loss_of_control_flag", "sum"),
        )
        .reset_index()
    )
    loc_conditions = loc_conditions[
        loc_conditions["road_surface_conditions_label"].astype(str).str.strip() != "Data missing or out of range"
    ].copy()
    loc_conditions["loc_rate_pct"] = _safe_ratio(loc_conditions["loss_of_control"], loc_conditions["vehicles"]) * 100
    loc_fig = px.bar(
        loc_conditions.sort_values("loc_rate_pct", ascending=False),
        x="road_surface_conditions_label",
        y="loc_rate_pct",
        title="Loss-of-control vehicle-record rate by road surface (%)",
        labels={
            "road_surface_conditions_label": "Road surface conditions",
            "loc_rate_pct": "Loss-of-control vehicle-record rate (%)",
        },
    )
    loc_fig.update_traces(
        hovertemplate="Road Surface Conditions = %{x}<br>Loss-Of-Control Rate (%) = %{y:.1f}<extra></extra>"
    )
    st.plotly_chart(loc_fig, use_container_width=True)

    manoeuvre_collision_stats = _collision_level_serious_fatal_stats(
        vehicle_data, ["vehicle_manoeuvre_label"]
    )
    manoeuvre_rank = manoeuvre_collision_stats[
        (manoeuvre_collision_stats["collisions"] >= 30)
        & (
            manoeuvre_collision_stats["vehicle_manoeuvre_label"].astype(str).str.strip()
            != "Data missing or out of range"
        )
    ].copy()
    if not manoeuvre_rank.empty:
        manoeuvre_rank["serious_fatal_rate_pct"] = manoeuvre_rank["serious_fatal_collision_rate_pct"]
        st.dataframe(
            manoeuvre_rank.sort_values("serious_fatal_rate_pct", ascending=False)
            .head(12)
            .rename(
                columns={
                    "vehicle_manoeuvre_label": "Vehicle Manoeuvre",
                    "collisions": "Collisions",
                    "fatal_collisions": "Fatal Collisions",
                    "serious_collisions": "Serious Collisions",
                    "serious_fatal_rate_pct": "Serious/Fatal Rate (%)",
                }
            )[
                ["Vehicle Manoeuvre", "Collisions", "Fatal Collisions", "Serious Collisions", "Serious/Fatal Rate (%)"]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("### Incident Signature Intelligence")
    signature_summary = _collision_level_serious_fatal_stats(vehicle_data, ["incident_signature"])
    signature_summary["serious_fatal_rate_pct"] = signature_summary["serious_fatal_collision_rate_pct"]
    st.dataframe(
        signature_summary.sort_values("serious_fatal_rate_pct", ascending=False).rename(
            columns={
                "incident_signature": "Incident Signature",
                "collisions": "Collisions",
                "fatal_collisions": "Fatal Collisions",
                "serious_collisions": "Serious Collisions",
                "serious_fatal_rate_pct": "Serious/Fatal Rate (%)",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Collision Mechanics Flow")
    sankey_scope = st.selectbox(
        "Sankey scope",
        options=["All vehicle types"] + sorted(vehicle_data["vehicle_type_label"].dropna().astype(str).unique().tolist()),
        key="sankey_scope_vehicle_type",
    )
    sankey_source = (
        vehicle_data
        if sankey_scope == "All vehicle types"
        else vehicle_data[vehicle_data["vehicle_type_label"] == sankey_scope]
    )
    sankey_df = sankey_source[
        ["vehicle_manoeuvre_label", "first_point_of_impact_label", "collision_severity_label"]
    ].dropna()
    if not sankey_df.empty:
        # Keep fewer nodes for readability.
        top_man = sankey_df["vehicle_manoeuvre_label"].value_counts().head(6).index
        top_imp = sankey_df["first_point_of_impact_label"].value_counts().head(5).index
        sankey_df["man_node"] = sankey_df["vehicle_manoeuvre_label"].where(
            sankey_df["vehicle_manoeuvre_label"].isin(top_man), "Other manoeuvre"
        )
        sankey_df["impact_node"] = sankey_df["first_point_of_impact_label"].where(
            sankey_df["first_point_of_impact_label"].isin(top_imp), "Other impact"
        )
        sankey_df["severity_node"] = sankey_df["collision_severity_label"]

        label_short = {
            "Waiting to go ahead (held up)": "Wait to go ahead",
            "Overtaking moving vehicle (offside)": "Overtake moving vehicle",
            "Overtaking stationary vehicle (offside)": "Overtake stationary vehicle",
            "Going ahead left-hand bend": "Ahead left bend",
            "Going ahead right-hand bend": "Ahead right bend",
            "Changing lane to left": "Lane change left",
            "Changing lane to right": "Lane change right",
            "Did not impact": "No direct impact",
        }
        sankey_df["man_node"] = sankey_df["man_node"].replace(label_short)
        sankey_df["impact_node"] = sankey_df["impact_node"].replace(label_short)

        nodes = pd.Index(
            pd.concat(
                [
                    sankey_df["man_node"],
                    sankey_df["impact_node"],
                    sankey_df["severity_node"],
                ],
                ignore_index=True,
            ).unique()
        )
        node_map = {label: i for i, label in enumerate(nodes)}

        links_1 = (
            sankey_df.groupby(["man_node", "impact_node"])
            .size()
            .reset_index(name="value")
            .assign(
                source=lambda d: d["man_node"].map(node_map),
                target=lambda d: d["impact_node"].map(node_map),
                color="rgba(140,140,140,0.25)",
            )
        )
        links_2 = (
            sankey_df.groupby(["impact_node", "severity_node"])
            .size()
            .reset_index(name="value")
            .assign(
                source=lambda d: d["impact_node"].map(node_map),
                target=lambda d: d["severity_node"].map(node_map),
                color=lambda d: d["severity_node"].map(
                    {
                        "Fatal": "rgba(201,42,42,0.65)",
                        "Serious": "rgba(244,162,97,0.65)",
                        "Slight": "rgba(46,196,182,0.65)",
                    }
                ).fillna("rgba(120,120,120,0.35)"),
            )
        )
        links = pd.concat(
            [links_1[["source", "target", "value", "color"]], links_2[["source", "target", "value", "color"]]],
            ignore_index=True,
        )
        sankey_fig = go.Figure(
            data=[
                go.Sankey(
                    node={
                        "label": nodes.tolist(),
                        "pad": 20,
                        "thickness": 16,
                        "color": "rgba(98,114,164,0.55)",
                    },
                    link={
                        "source": links["source"].tolist(),
                        "target": links["target"].tolist(),
                        "value": links["value"].tolist(),
                        "color": links["color"].tolist(),
                    },
                )
            ]
        )
        sankey_fig.update_layout(
            title_text="Collision mechanics flow: Manoeuvre -> Impact -> Severity",
            height=780,
            font={"size": 12},
        )
        st.plotly_chart(sankey_fig, use_container_width=True)

    st.markdown("### Drilldown: Vehicle Type Case Context")
    type_options = sorted(vehicle_data["vehicle_type_label"].dropna().astype(str).unique().tolist())
    if not type_options:
        st.info("No vehicle types available for drilldown under current filters.")
        return
    selected_type = st.selectbox("Select vehicle type for case drilldown", options=type_options)
    drill = vehicle_data[vehicle_data["vehicle_type_label"] == selected_type].copy()
    if drill.empty:
        st.info("No records for this vehicle type under current filters.")
    else:
        st.caption(f"Showing highest triage score cases for {selected_type}")
        st.dataframe(
            drill.sort_values(["triage_score", "harm_score"], ascending=False)[
                [
                    "collision_index",
                    "date",
                    "district_display",
                    "speed_limit",
                    "age_of_driver",
                    "vehicle_manoeuvre_label",
                    "first_point_of_impact_label",
                    "incident_signature",
                    "triage_score",
                    "harm_score",
                ]
            ]
            .head(50)
            .rename(columns={"collision_index": "case_id"}),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("### Manufacturer Intelligence")
    if "generic_make_model" in vehicle_data.columns:
        vehicle_type_filter = st.session_state.get("vehicle_type_filter", "cars")
        vt_numeric = pd.to_numeric(vehicle_data["vehicle_type"], errors="coerce")
        if vehicle_type_filter == "cars":
            manufacturer_data = vehicle_data[vt_numeric.isin([8, 9, 10])].copy()
        elif vehicle_type_filter == "motorbikes":
            manufacturer_data = vehicle_data[vt_numeric.isin([2, 3, 4, 5, 23])].copy()
        else:
            manufacturer_data = vehicle_data[vt_numeric.isin([2, 3, 4, 5, 23, 8, 9, 10])].copy()

        if manufacturer_data.empty:
            st.info("No vehicle records match the selected vehicle type filter for Manufacturer Intelligence.")
        else:
            make_model = (
                manufacturer_data["generic_make_model"]
                .astype("string")
                .fillna("Unknown")
                .str.strip()
                .replace({"": "Unknown", "-1": "Unknown", "UNKNOWN": "Unknown"})
            )
            manufacturer_data["make_model_label"] = make_model

            model_vehicle_agg = (
                manufacturer_data[manufacturer_data["make_model_label"] != "Unknown"]
                .groupby("make_model_label", dropna=False)
                .agg(
                    vehicle_records=("vehicle_reference", "count"),
                    avg_driver_age=("age_of_driver", "mean"),
                    avg_speed_limit=("speed_limit", "mean"),
                )
                .reset_index()
            )
            model_collision_stats = _collision_level_serious_fatal_stats(
                manufacturer_data[manufacturer_data["make_model_label"] != "Unknown"], ["make_model_label"]
            )
            model_summary = model_vehicle_agg.merge(model_collision_stats, on="make_model_label", how="left")
            model_summary = model_summary[model_summary["make_model_label"] != "Unknown"]
            if model_summary.empty:
                st.info("No make/model values available under current filters.")
            else:
                model_summary = model_summary[model_summary["collisions"] >= 20].copy()
                if model_summary.empty:
                    st.info("Not enough make/model records to compute stable risk ratios.")
                else:
                    top_models = model_summary.sort_values(
                        "serious_fatal_collision_rate_pct", ascending=False
                    ).head(20).copy()
                    for c in [
                        "fatal_collisions",
                        "serious_collisions",
                        "serious_or_fatal_collisions",
                        "avg_driver_age",
                        "avg_speed_limit",
                    ]:
                        top_models[c] = np.rint(top_models[c]).astype("int64")
                    st.dataframe(
                        top_models.rename(
                            columns={
                                "make_model_label": "Make/Model",
                                "vehicle_records": "Vehicle Records",
                                "collisions": "Collisions",
                                "fatal_collisions": "Fatal Collisions",
                                "serious_collisions": "Serious Collisions",
                                "serious_or_fatal_collisions": "Serious/Fatal Collisions",
                                "serious_fatal_collision_rate_pct": "Serious/Fatal Collision Rate (%)",
                                "avg_driver_age": "Avg Driver Age",
                                "avg_speed_limit": "Avg Speed Limit",
                            }
                        )[
                            [
                                "Make/Model",
                                "Collisions",
                                "Fatal Collisions",
                                "Serious Collisions",
                                "Avg Driver Age",
                                "Avg Speed Limit",
                                "Serious/Fatal Collision Rate (%)",
                            ]
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

                    model_segment = manufacturer_data[manufacturer_data["make_model_label"] != "Unknown"].copy()
                    vt_seg = pd.to_numeric(model_segment["vehicle_type"], errors="coerce")
                    model_segment["segment"] = np.select(
                        [vt_seg.isin([2, 3, 4, 5, 23]), vt_seg.isin([8, 9, 10])],
                        ["Motorbike", "Car"],
                        default="Other",
                    )
                    segment_summary = _collision_level_serious_fatal_stats(
                        model_segment[model_segment["segment"].isin(["Motorbike", "Car"])],
                        ["segment", "make_model_label"],
                    )
                    segment_summary = segment_summary[segment_summary["collisions"] >= 20].copy()

                    bike_top = (
                        segment_summary[segment_summary["segment"] == "Motorbike"]
                        .sort_values("serious_fatal_collision_rate_pct", ascending=False)
                        .head(10)
                    )
                    car_top = (
                        segment_summary[segment_summary["segment"] == "Car"]
                        .sort_values("serious_fatal_collision_rate_pct", ascending=False)
                        .head(10)
                    )
                    show_bike = vehicle_type_filter in ("motorbikes", "both") and not bike_top.empty
                    show_car = vehicle_type_filter in ("cars", "both") and not car_top.empty
                    if vehicle_type_filter == "motorbikes" and bike_top.empty:
                        st.info("Not enough motorbike model data for top 10 chart.")
                    elif vehicle_type_filter == "cars" and car_top.empty:
                        st.info("Not enough car model data for top 10 chart.")
                    elif show_bike and show_car:
                        chart_left, chart_right = st.columns(2)
                        with chart_left:
                            bike_fig = px.bar(
                                bike_top,
                                x="make_model_label",
                                y="serious_fatal_collision_rate_pct",
                                title="Top 10 motorbike models by serious/fatal collision rate (%)",
                                labels={
                                    "make_model_label": "Motorbike model",
                                    "serious_fatal_collision_rate_pct": "Serious/Fatal collision rate (%)",
                                },
                            )
                            bike_fig.update_traces(
                                hovertemplate="Motorbike Model = %{x}<br>Serious/Fatal Collision Rate (%) = %{y:.1f}<extra></extra>"
                            )
                            st.plotly_chart(bike_fig, use_container_width=True)
                        with chart_right:
                            car_fig = px.bar(
                                car_top,
                                x="make_model_label",
                                y="serious_fatal_collision_rate_pct",
                                title="Top 10 car models by serious/fatal collision rate (%)",
                                labels={
                                    "make_model_label": "Car model",
                                    "serious_fatal_collision_rate_pct": "Serious/Fatal collision rate (%)",
                                },
                            )
                            car_fig.update_traces(
                                hovertemplate="Car Model = %{x}<br>Serious/Fatal Collision Rate (%) = %{y:.1f}<extra></extra>"
                            )
                            st.plotly_chart(car_fig, use_container_width=True)
                    elif show_bike:
                        bike_fig = px.bar(
                            bike_top,
                            x="make_model_label",
                            y="serious_fatal_collision_rate_pct",
                            title="Top 10 motorbike models by serious/fatal collision rate (%)",
                            labels={
                                "make_model_label": "Motorbike model",
                                "serious_fatal_collision_rate_pct": "Serious/Fatal collision rate (%)",
                            },
                        )
                        bike_fig.update_traces(
                            hovertemplate="Motorbike Model = %{x}<br>Serious/Fatal Collision Rate (%) = %{y:.1f}<extra></extra>"
                        )
                        st.plotly_chart(bike_fig, use_container_width=True)
                    elif show_car:
                        car_fig = px.bar(
                            car_top,
                            x="make_model_label",
                            y="serious_fatal_collision_rate_pct",
                            title="Top 10 car models by serious/fatal collision rate (%)",
                            labels={
                                "make_model_label": "Car model",
                                "serious_fatal_collision_rate_pct": "Serious/Fatal collision rate (%)",
                            },
                        )
                        car_fig.update_traces(
                            hovertemplate="Car Model = %{x}<br>Serious/Fatal Collision Rate (%) = %{y:.1f}<extra></extra>"
                        )
                        st.plotly_chart(car_fig, use_container_width=True)


def page_casualty_intelligence(casualty_person_view: pd.DataFrame, casualty_linked_view: pd.DataFrame) -> None:
    st.title("Casualty Intelligence")
    if casualty_person_view.empty:
        st.warning("No casualty records available for the selected filters.")
        return

    missing_casualty = _validate_schema(casualty_person_view, REQUIRED_CASUALTY_VIEW_COLUMNS)
    if missing_casualty:
        st.error(
            f"Casualty schema validation failed: missing required columns **{', '.join(missing_casualty)}**. "
            "These are required for the Casualty Intelligence module. Check that your casualty data "
            "includes casualty_class, casualty_type, casualty_severity, and casualty_reference."
        )
        return

    data = casualty_person_view.copy()
    data = _ensure_label_columns(
        data,
        [
            "casualty_type",
            "casualty_class",
            "age_band_of_casualty",
            "sex_of_casualty",
            "pedestrian_location",
            "pedestrian_movement",
            "casualty_distance_banding",
        ],
    )
    if "district_display" not in data.columns:
        data = _add_district_labels(data)

    data["priority_score"] = casualty_priority_score(data)
    data["priority_reason"] = casualty_priority_reason(data)

    class_options = sorted(data["casualty_class_label"].dropna().astype(str).unique().tolist())
    type_options = sorted(data["casualty_type_label"].dropna().astype(str).unique().tolist())
    type_counts = data["casualty_type_label"].value_counts()
    top_types = type_counts.head(12).index.tolist()
    for preferred in ["Pedestrian", "Cyclist", "Car occupant"]:
        if preferred in type_options and preferred not in top_types:
            top_types.append(preferred)
    default_types = [t for t in top_types if t in type_options]

    with st.expander("Casualty module filters", expanded=True):
        f1, f2, f3 = st.columns(3)
        with f1:
            selected_class = st.multiselect("Casualty class", options=class_options, default=class_options)
        with f2:
            selected_types = st.multiselect("Casualty type", options=type_options, default=default_types)
        with f3:
            ksi_definition = st.selectbox(
                "KSI definition",
                options=["Reported severity", "Adjusted severity estimate"],
                index=0,
            )

    if selected_class:
        data = data[data["casualty_class_label"].isin(selected_class)]
    if selected_types:
        data = data[data["casualty_type_label"].isin(selected_types)]
    if data.empty:
        st.info("No casualty records left after casualty filters.")
        return

    if ksi_definition == "Adjusted severity estimate" and "casualty_adjusted_severity_serious" in data.columns:
        data["fatal_flag"] = (_series_or_default(data, "casualty_severity", 3) == 1).astype(float)
        data["serious_flag"] = _series_or_default(data, "casualty_adjusted_severity_serious", 0).clip(lower=0, upper=1)
        data["slight_flag"] = _series_or_default(data, "casualty_adjusted_severity_slight", 0).clip(lower=0, upper=1)
        data["ksi_flag"] = (data["fatal_flag"] + data["serious_flag"]).clip(upper=1)
        fatal_metric_label = "Fatal"
        serious_metric_label = "Estimated Serious"
        slight_metric_label = "Estimated Slight"
        metric_value_fmt = "{:.1f}"
        rate_caption = "Adjusted mode uses weighted serious/slight estimates from the STATS19 adjusted severity fields."
    else:
        severity = _series_or_default(data, "casualty_severity", 3)
        data["fatal_flag"] = (severity == 1).astype(float)
        data["serious_flag"] = (severity == 2).astype(float)
        data["slight_flag"] = (severity == 3).astype(float)
        data["ksi_flag"] = (data["fatal_flag"] + data["serious_flag"]).clip(upper=1)
        fatal_metric_label = "Fatal"
        serious_metric_label = "Serious"
        slight_metric_label = "Slight"
        metric_value_fmt = "{:,.0f}"
        rate_caption = "Reported mode uses the original STATS19 casualty severity codes."

    st.markdown("### Casualty Demographics & Severity")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Casualties", f"{len(data):,}")
    c2.metric(fatal_metric_label, metric_value_fmt.format(data["fatal_flag"].sum()))
    c3.metric(serious_metric_label, metric_value_fmt.format(data["serious_flag"].sum()))
    c4.metric(slight_metric_label, metric_value_fmt.format(data["slight_flag"].sum()))
    c5.metric("KSI Rate", f"{data['ksi_flag'].mean() * 100:.1f}%")
    st.caption(rate_caption)

    extra1, extra2, extra3, extra4, extra5 = st.columns(5)
    extra1.metric("Pedestrian KSI Rate", f"{(data[data['casualty_class'] == 3]['ksi_flag'].mean() * 100):.1f}%" if (data["casualty_class"] == 3).any() else "N/A")
    extra2.metric("Cyclist KSI Rate", f"{(data[data['casualty_type'] == 1]['ksi_flag'].mean() * 100):.1f}%" if (data["casualty_type"] == 1).any() else "N/A")
    extra3.metric("Under-16 KSI Rate", f"{(data[data['age_of_casualty'] <= 16]['ksi_flag'].mean() * 100):.1f}%" if (data["age_of_casualty"] <= 16).any() else "N/A")
    extra4.metric("75+ KSI Rate", f"{(data[data['age_of_casualty'] >= 75]['ksi_flag'].mean() * 100):.1f}%" if (data["age_of_casualty"] >= 75).any() else "N/A")
    extra5.metric("% Casualties in Darkness", f"{(data['is_dark'].mean() * 100):.1f}%")

    top_type = (
        data.groupby("casualty_type_label")["ksi_flag"].mean().sort_values(ascending=False).head(1)
    )
    peak_hour = (
        data.groupby("hour")["ksi_flag"].mean().sort_values(ascending=False).head(1)
    )
    top_district = (
        data.assign(harm=np.where(data["fatal_flag"] == 1, 5, np.where(data["serious_flag"] == 1, 2, 0)))
        .groupby("district_display")["harm"]
        .sum()
        .sort_values(ascending=False)
        .head(1)
    )
    if not top_type.empty and not peak_hour.empty and not top_district.empty:
        peak_hour_val = int(peak_hour.index[0])
        peak_hour_am_pm = f"{(peak_hour_val % 12) or 12}:00 {'AM' if peak_hour_val < 12 else 'PM'}"
        st.info(
            f"Top insight: highest KSI rate is for `{top_type.index[0]}` ({top_type.iloc[0]*100:.1f}%), "
            f"peak KSI hour is `{peak_hour_am_pm}` ({peak_hour.iloc[0]*100:.1f}%), "
            f"and highest casualty harm district is `{top_district.index[0]}`."
        )

    age_order = ["0-5", "6-10", "11-15", "16-20", "21-25", "26-35", "36-45", "46-55", "56-65", "66-75", "Over 75", "Missing"]
    if "age_band_of_casualty_label" in data.columns:
        data["age_band_of_casualty_label"] = pd.Categorical(
            data["age_band_of_casualty_label"], categories=age_order, ordered=True
        )

    min_den = 30
    age_band = (
        data.groupby("age_band_of_casualty_label", dropna=False)
        .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
        .reset_index()
    )
    age_band = age_band[age_band["casualties"] >= min_den].copy()
    age_band["ksi_rate_pct"] = _safe_ratio(age_band["ksi"], age_band["casualties"]) * 100
    age_band_fig = px.bar(
        age_band,
        x="age_band_of_casualty_label",
        y="ksi_rate_pct",
        hover_data=["casualties", "ksi"],
        title=f"KSI rate by casualty age band (%) (n >= {min_den})",
        labels={
            "age_band_of_casualty_label": "Age band",
            "ksi_rate_pct": "KSI rate (%)",
            "casualties": "Casualties",
            "ksi": "KSI",
        },
    )
    age_band_fig.update_traces(
        hovertemplate=(
            "Age Band = %{x}<br>"
            "KSI Rate (%) = %{y:.1f}<br>"
            "Casualties = %{customdata[0]}<br>"
            "KSI = %{customdata[1]}<extra></extra>"
        )
    )
    st.plotly_chart(age_band_fig, use_container_width=True)

    st.markdown("### Age & Sex Analysis")
    age_sex = (
        data.groupby(["sex_of_casualty_label", "age_band_of_casualty_label"], dropna=False)
        .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
        .reset_index()
    )
    age_sex = age_sex[
        (age_sex["age_band_of_casualty_label"] != "Missing")
        & (age_sex["sex_of_casualty_label"] != "Data missing or out of range")
    ].copy()
    age_sex = age_sex[age_sex["casualties"] >= min_den].copy()
    age_sex["ksi_rate_pct"] = _safe_ratio(age_sex["ksi"], age_sex["casualties"]) * 100
    if not age_sex.empty:
        age_order_clean = [x for x in age_order if x != "Missing"]
        sex_order = ["Male", "Female"]
        age_sex["age_band_of_casualty_label"] = pd.Categorical(
            age_sex["age_band_of_casualty_label"], categories=age_order_clean, ordered=True
        )
        age_sex["sex_of_casualty_label"] = pd.Categorical(
            age_sex["sex_of_casualty_label"], categories=sex_order, ordered=True
        )
        age_sex = age_sex.sort_values(["sex_of_casualty_label", "age_band_of_casualty_label"])
        sex_fig = px.density_heatmap(
            age_sex,
            x="age_band_of_casualty_label",
            y="sex_of_casualty_label",
            z="ksi_rate_pct",
            histfunc="avg",
            category_orders={
                "age_band_of_casualty_label": age_order_clean,
                "sex_of_casualty_label": sex_order,
            },
            title=f"KSI rate by age band and sex (%) (n >= {min_den})",
            color_continuous_scale="Oranges",
            labels={
                "age_band_of_casualty_label": "Age band",
                "sex_of_casualty_label": "Sex",
                "ksi_rate_pct": "KSI rate (%)",
            },
        )
        sex_fig.update_traces(
            hovertemplate="Age Band = %{x}<br>Sex = %{y}<br>KSI Rate (%) = %{z:.1f}<extra></extra>"
        )
        st.plotly_chart(sex_fig, use_container_width=True)
        st.dataframe(
            age_sex.sort_values("ksi_rate_pct", ascending=False).head(12).rename(
                columns={
                    "sex_of_casualty_label": "Sex",
                    "age_band_of_casualty_label": "Age Band",
                    "casualties": "Casualties",
                    "ksi": "KSI",
                    "ksi_rate_pct": "KSI Rate (%)",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    adverse_group = age_sex.sort_values(["ksi_rate_pct", "casualties"], ascending=[False, False]).head(1)
    if not adverse_group.empty:
        row = adverse_group.iloc[0]
        st.info(
            f"Most adverse age/sex group (n >= {min_den}): "
            f"`{row['sex_of_casualty_label']}` + `{row['age_band_of_casualty_label']}` "
            f"with KSI rate `{row['ksi_rate_pct']:.1f}%` ({int(row['ksi'])}/{int(row['casualties'])})."
        )

    if not casualty_linked_view.empty:
        linked_cols = [c for c in ["collision_index", "casualty_reference", "generic_make_model", "link_status"] if c in casualty_linked_view.columns]
        linked_subset = casualty_linked_view[linked_cols].drop_duplicates().copy()
        profile = data[["collision_index", "casualty_reference", "sex_of_casualty_label", "age_band_of_casualty_label", "ksi_flag"]].merge(
            linked_subset,
            on=["collision_index", "casualty_reference"],
            how="left",
        )
        profile["generic_make_model"] = (
            profile["generic_make_model"]
            .astype("string")
            .fillna("Unknown")
            .str.strip()
            .replace({"": "Unknown", "-1": "Unknown", "UNKNOWN": "Unknown"})
        )
        profile = profile[(profile.get("link_status") == "linked") & (profile["generic_make_model"] != "Unknown")].copy()
        if not profile.empty:
            min_den_linked = 15
            adverse_linked = (
                profile.groupby(["sex_of_casualty_label", "age_band_of_casualty_label", "generic_make_model"], dropna=False)
                .agg(casualties=("ksi_flag", "count"), ksi=("ksi_flag", "sum"))
                .reset_index()
            )
            adverse_linked = adverse_linked[adverse_linked["casualties"] >= min_den_linked].copy()
            if not adverse_linked.empty:
                adverse_linked["ksi_rate_pct"] = _safe_ratio(adverse_linked["ksi"], adverse_linked["casualties"]) * 100
                top_linked = adverse_linked.sort_values(["ksi_rate_pct", "casualties"], ascending=[False, False]).head(1).iloc[0]
                st.info(
                    f"Most adverse linked profile (n >= {min_den_linked}): "
                    f"`{top_linked['sex_of_casualty_label']}` + `{top_linked['age_band_of_casualty_label']}` "
                    f"in `{top_linked['generic_make_model']}` with KSI rate `{top_linked['ksi_rate_pct']:.1f}%` "
                    f"({int(top_linked['ksi'])}/{int(top_linked['casualties'])})."
                )

    trends = (
        data.dropna(subset=["date"])
        .assign(month=lambda d: d["date"].dt.to_period("M").dt.to_timestamp())
        .groupby(["month", "casualty_type_label"], dropna=False)
        .size()
        .reset_index(name="casualties")
    )
    top_types_trend = trends.groupby("casualty_type_label")["casualties"].sum().sort_values(ascending=False).head(8).index
    trends = trends[trends["casualty_type_label"].isin(top_types_trend)]
    trends_fig = px.area(
        trends,
        x="month",
        y="casualties",
        color="casualty_type_label",
        title="Casualties over time by type",
        labels={"month": "Month", "casualties": "Casualties", "casualty_type_label": "Casualty Type"},
    )
    trends_fig.update_traces(
        hovertemplate="Casualty Type = %{fullData.name}<br>Month = %{x|%Y-%m-%d}<br>Casualties = %{y}<extra></extra>"
    )
    st.plotly_chart(trends_fig, use_container_width=True)

    st.markdown("### Deprivation & Vulnerable Road Users")
    imd_order = [
        "Most deprived 10%",
        "More deprived 10-20%",
        "More deprived 20-30%",
        "More deprived 30-40%",
        "More deprived 40-50%",
        "Less deprived 40-50%",
        "Less deprived 30-40%",
        "Less deprived 20-30%",
        "Less deprived 10-20%",
        "Least deprived 10%",
        "Data missing or out of range",
    ]
    if "casualty_imd_decile_label" in data.columns:
        data["casualty_imd_decile_label"] = pd.Categorical(
            data["casualty_imd_decile_label"], categories=imd_order, ordered=True
        )

    imd = (
        data.groupby("casualty_imd_decile_label", dropna=False)
        .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
        .reset_index()
    )
    imd = imd[
        (imd["casualties"] >= min_den)
        & (imd["casualty_imd_decile_label"].astype(str).str.strip() != "Data missing or out of range")
    ].copy()
    if not imd.empty:
        imd["ksi_rate_pct"] = _safe_ratio(imd["ksi"], imd["casualties"]) * 100
        imd_fig = px.bar(
            imd,
            x="casualty_imd_decile_label",
            y="ksi_rate_pct",
            hover_data=["casualties", "ksi"],
            title=f"KSI rate by deprivation decile (%) (n >= {min_den})",
            labels={
                "casualty_imd_decile_label": "Deprivation decile",
                "ksi_rate_pct": "KSI rate (%)",
                "casualties": "Casualties",
                "ksi": "KSI",
            },
        )
        imd_fig.update_traces(
            hovertemplate=(
                "Deprivation Decile = %{x}<br>"
                "KSI Rate (%) = %{y:.1f}<br>"
                "Casualties = %{customdata[0]}<br>"
                "KSI = %{customdata[1]}<extra></extra>"
            )
        )
        st.plotly_chart(imd_fig, use_container_width=True)

    st.markdown("### Reporting Mode & Data Quality Lens")
    report_col = (
        "did_police_officer_attend_scene_of_accident_label"
        if "did_police_officer_attend_scene_of_accident_label" in data.columns
        else "did_police_officer_attend_scene_of_accident"
    )
    report_summary = (
        data.groupby(report_col, dropna=False)
        .agg(
            casualties=("casualty_reference", "count"),
            ksi=("ksi_flag", "sum"),
            missing_age=("age_of_casualty", lambda s: s.isna().mean() * 100),
            missing_sex=("sex_of_casualty", lambda s: s.isna().mean() * 100),
            missing_imd=("casualty_imd_decile", lambda s: s.isna().mean() * 100),
        )
        .reset_index()
    )
    report_summary["ksi_rate_pct"] = _safe_ratio(report_summary["ksi"], report_summary["casualties"]) * 100
    report_summary = report_summary[
        report_summary[report_col].astype(str).str.strip() != "Data missing or out of range"
    ].copy()
    st.dataframe(
        report_summary.rename(
            columns={
                report_col: "Reporting Mode",
                "casualties": "Casualties",
                "ksi": "KSI",
                "ksi_rate_pct": "KSI Rate (%)",
                "missing_age": "Missing Age (%)",
                "missing_sex": "Missing Sex (%)",
                "missing_imd": "Missing IMD (%)",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    ped_rank = (
        data[data["casualty_class"] == 3]
        .groupby("district_display", dropna=False)
        .agg(
            pedestrian_casualties=("casualty_reference", "count"),
            pedestrian_ksi=("ksi_flag", "sum"),
        )
        .reset_index()
    )
    if not ped_rank.empty:
        ped_rank["pedestrian_ksi_rate_pct"] = _safe_ratio(ped_rank["pedestrian_ksi"], ped_rank["pedestrian_casualties"]) * 100
        st.dataframe(
            ped_rank.sort_values("pedestrian_ksi", ascending=False).head(12).rename(
                columns={
                    "district_display": "District",
                    "pedestrian_casualties": "Pedestrian Casualties",
                    "pedestrian_ksi": "Pedestrian KSI",
                    "pedestrian_ksi_rate_pct": "Pedestrian KSI Rate (%)",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    district_harm = (
        data.groupby("district_display", dropna=False)
        .agg(
            fatal=("fatal_flag", "sum"),
            serious=("serious_flag", "sum"),
        )
        .reset_index()
    )
    district_harm["harm_index"] = district_harm["serious"] * 2 + district_harm["fatal"] * 5
    st.dataframe(
        district_harm.sort_values("harm_index", ascending=False).head(12).rename(
            columns={
                "district_display": "District",
                "fatal": "Fatal Casualties",
                "serious": "Serious Casualties",
                "harm_index": "Harm Index",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    vrus = data[data["casualty_type_label"].isin(["Pedestrian", "Cyclist"])].copy()
    if not vrus.empty:
        hour_profile = (
            vrus.groupby("hour", dropna=False)
            .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
            .reset_index()
        )
        hour_profile["ksi_rate_pct"] = _safe_ratio(hour_profile["ksi"], hour_profile["casualties"]) * 100
        hour_fig = px.line(
            hour_profile.sort_values("hour"),
            x="hour",
            y="ksi_rate_pct",
            markers=True,
            title="Vulnerable user KSI rate by hour (%)",
            labels={"hour": "Hour of day", "ksi_rate_pct": "KSI rate (%)"},
        )
        hour_fig.update_traces(
            hovertemplate="Hour Of Day = %{x}<br>KSI Rate (%) = %{y:.1f}<extra></extra>"
        )
        st.plotly_chart(hour_fig, use_container_width=True)

    st.markdown("### Pedestrian Infrastructure Lens")
    if "pedestrian_crossing_label" in data.columns:
        ped_infra = data[data["casualty_class"] == 3].copy()
        if not ped_infra.empty:
            cross = (
                ped_infra.groupby("pedestrian_crossing_label", dropna=False)
                .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
                .reset_index()
            )
            cross = cross[cross["casualties"] >= min_den].copy()
            if not cross.empty:
                cross["ksi_rate_pct"] = _safe_ratio(cross["ksi"], cross["casualties"]) * 100
                cross_fig = px.bar(
                    cross.sort_values("ksi_rate_pct", ascending=False),
                    x="pedestrian_crossing_label",
                    y="ksi_rate_pct",
                    hover_data=["casualties", "ksi"],
                    title=f"Pedestrian KSI rate by crossing facility (%) (n >= {min_den})",
                    labels={
                        "pedestrian_crossing_label": "Crossing facility",
                        "ksi_rate_pct": "KSI rate (%)",
                        "casualties": "Casualties",
                        "ksi": "KSI",
                    },
                )
                cross_fig.update_traces(
                    hovertemplate=(
                        "Crossing Facility = %{x}<br>"
                        "KSI Rate (%) = %{y:.1f}<br>"
                        "Casualties = %{customdata[0]}<br>"
                        "KSI = %{customdata[1]}<extra></extra>"
                    )
                )
                st.plotly_chart(cross_fig, use_container_width=True)

            cross_night = (
                ped_infra.groupby(["pedestrian_crossing_label", "is_dark"], dropna=False)
                .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
                .reset_index()
            )
            cross_night = cross_night[cross_night["casualties"] >= min_den].copy()
            if not cross_night.empty:
                cross_night["ksi_rate_pct"] = _safe_ratio(cross_night["ksi"], cross_night["casualties"]) * 100
                cross_night["light_period"] = cross_night["is_dark"].map({0: "Daylight", 1: "Darkness"}).fillna("Unknown")
                infra_fig = px.bar(
                    cross_night,
                    x="pedestrian_crossing_label",
                    y="ksi_rate_pct",
                    color="light_period",
                    barmode="group",
                    title=f"Pedestrian KSI by crossing and light period (%) (n >= {min_den})",
                    labels={
                        "pedestrian_crossing_label": "Crossing facility",
                        "ksi_rate_pct": "KSI rate (%)",
                        "light_period": "Light period",
                    },
                )
                infra_fig.update_traces(
                    hovertemplate=(
                        "Crossing Facility = %{x}<br>"
                        "KSI Rate (%) = %{y:.1f}<br>"
                        "Light Period = %{fullData.name}<extra></extra>"
                    )
                )
                st.plotly_chart(infra_fig, use_container_width=True)

    ped_flow = data.loc[
        data["casualty_class"] == 3,
        ["pedestrian_location_label", "pedestrian_movement_label", "casualty_severity_label"],
    ].dropna().copy()
    if not ped_flow.empty:
        top_loc = ped_flow["pedestrian_location_label"].value_counts().head(6).index
        top_mov = ped_flow["pedestrian_movement_label"].value_counts().head(6).index
        ped_flow["pedestrian_location_label"] = ped_flow["pedestrian_location_label"].where(
            ped_flow["pedestrian_location_label"].isin(top_loc), "Other location"
        )
        ped_flow["pedestrian_movement_label"] = ped_flow["pedestrian_movement_label"].where(
            ped_flow["pedestrian_movement_label"].isin(top_mov), "Other movement"
        )
        p1 = ped_flow.groupby(["pedestrian_location_label", "pedestrian_movement_label"]).size().reset_index(name="value")
        p2 = ped_flow.groupby(["pedestrian_movement_label", "casualty_severity_label"]).size().reset_index(name="value")
        labels = pd.Index(
            pd.concat(
                [p1["pedestrian_location_label"], p1["pedestrian_movement_label"], p2["casualty_severity_label"]],
                ignore_index=True,
            ).unique()
        )
        m = {k: i for i, k in enumerate(labels)}
        links_a = p1.assign(
            source=lambda d: d["pedestrian_location_label"].map(m),
            target=lambda d: d["pedestrian_movement_label"].map(m),
            color="rgba(120,120,120,0.25)",
        )
        links_b = p2.assign(
            source=lambda d: d["pedestrian_movement_label"].map(m),
            target=lambda d: d["casualty_severity_label"].map(m),
            color=lambda d: d["casualty_severity_label"].map(
                {"Fatal": "rgba(201,42,42,0.7)", "Serious": "rgba(244,162,97,0.7)", "Slight": "rgba(46,196,182,0.7)"}
            ).fillna("rgba(140,140,140,0.35)"),
        )
        links = pd.concat(
            [
                links_a[["source", "target", "value", "color"]],
                links_b[["source", "target", "value", "color"]],
            ],
            ignore_index=True,
        )
        ped_fig = go.Figure(
            data=[
                go.Sankey(
                    node={"label": labels.tolist(), "pad": 18, "thickness": 14},
                    link={
                        "source": links["source"].tolist(),
                        "target": links["target"].tolist(),
                        "value": links["value"].tolist(),
                        "color": links["color"].tolist(),
                    },
                )
            ]
        )
        ped_fig.update_layout(title_text="Pedestrian flow: location -> movement -> severity", height=650)
        st.plotly_chart(ped_fig, use_container_width=True)

    st.markdown("### Priority Case Queue")
    queue = data.copy()
    queue["case_id"] = queue["collision_index"].astype(str) + "-" + queue["casualty_reference"].astype(str)
    queue = queue.sort_values("priority_score", ascending=False)
    queue_display = queue[
        [
            "case_id",
            "date",
            "district_display",
            "casualty_severity_label",
            "casualty_class_label",
            "casualty_type_label",
            "age_of_casualty",
            "sex_of_casualty_label",
            "casualty_distance_banding_label",
            "priority_reason",
            "priority_score",
        ]
    ].head(200).rename(
        columns={
            "district_display": "District",
            "casualty_severity_label": "Severity",
            "casualty_class_label": "Class",
            "casualty_type_label": "Type",
            "age_of_casualty": "Age",
            "sex_of_casualty_label": "Sex",
            "casualty_distance_banding_label": "Distance Band",
            "priority_reason": "Priority Reason",
            "priority_score": "Priority Score",
        }
    )
    st.dataframe(queue_display, use_container_width=True, hide_index=True)
    st.download_button(
        label="Download Priority Case Queue (CSV)",
        data=queue_display.to_csv(index=False),
        file_name="priority_case_queue.csv",
        mime="text/csv",
    )

    if not casualty_linked_view.empty and "link_status" in casualty_linked_view.columns:
        linked_work = casualty_linked_view.copy()
        if "linkable_to_vehicle" not in linked_work.columns:
            linked_work["linkable_to_vehicle"] = (linked_work["link_status"] != "not_linkable").astype(int)
        coverage = (
            linked_work.groupby("casualty_class_label", dropna=False)
            .agg(
                casualties=("casualty_reference", "count"),
                linkable=("linkable_to_vehicle", "sum"),
                linked=("link_status", lambda s: (s == "linked").sum()),
            )
            .reset_index()
        )
        coverage["linked_of_linkable_pct"] = _safe_ratio(coverage["linked"], coverage["linkable"]) * 100
        st.dataframe(
            coverage.rename(
                columns={
                    "casualty_class_label": "Casualty Class",
                    "casualties": "Casualties",
                    "linkable": "Linkable to Vehicle",
                    "linked": "Linked to Vehicle",
                    "linked_of_linkable_pct": "Linked of Linkable (%)",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        overall_linked = _safe_ratio(pd.Series([coverage["linked"].sum()]), pd.Series([coverage["linkable"].sum()])).iloc[0] * 100
        st.caption(f"Vehicle-context linkage coverage among linkable casualties: {overall_linked:.1f}%")


def page_pipeline_health(
    collisions: pd.DataFrame,
    vehicles: pd.DataFrame,
    casualties: pd.DataFrame,
    collision_view: pd.DataFrame,
) -> None:
    st.title("Data Quality & Refresh Status")
    st.caption(
        "Reflects the full loaded datasets and is not affected by sidebar analytical filters."
    )
    st.caption(f"Data loaded at: {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    max_date = collision_view["date"].max() if "date" in collision_view.columns and collision_view["date"].notna().any() else None
    max_date_str = max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else "–"
    total_records = len(collisions) + len(vehicles) + len(casualties)
    st.markdown("---")
    st.caption(
        f"**Last refresh:** {max_date_str} (data as of) | "
        f"**Records ingested this cycle:** {total_records:,} | "
        "**Source:** STATS19"
    )
    st.markdown("---")

    row1, row2, row3 = st.columns(3)
    row1.metric("Collisions rows", f"{len(collisions):,}")
    row2.metric("Vehicles rows", f"{len(vehicles):,}")
    row3.metric("Casualties rows", f"{len(casualties):,}")

    collisions_keys = set(collisions["collision_index"].dropna().astype(str))
    vehicles_keys = set(vehicles["collision_index"].dropna().astype(str))
    casualties_keys = set(casualties["collision_index"].dropna().astype(str))

    join_checks = pd.DataFrame(
        [
            {
                "metric": "Vehicles matching collisions",
                "value_pct": 100 * (len(vehicles_keys & collisions_keys) / max(1, len(vehicles_keys))),
            },
            {
                "metric": "Casualties matching collisions",
                "value_pct": 100 * (len(casualties_keys & collisions_keys) / max(1, len(casualties_keys))),
            },
            {
                "metric": "Collisions with geocodes",
                "value_pct": 100 * (collision_view["latitude"].notna().mean()),
            },
            {
                "metric": "Vehicles with missing driver age",
                "value_pct": 100 * (vehicles["age_of_driver"].isna().mean()),
            },
        ]
    )
    st.subheader("Join Integrity / Quality Metrics")
    st.dataframe(join_checks.style.format({"value_pct": "{:.2f}%"}), use_container_width=True, hide_index=True)

    collision_counts = (
        collision_view[["collision_index", "number_of_casualties", "casualties_total"]]
        .assign(
            number_of_casualties=lambda d: d["number_of_casualties"].fillna(0),
            casualties_total=lambda d: d["casualties_total"].fillna(0),
        )
        .assign(casualty_count_diff=lambda d: (d["number_of_casualties"] - d["casualties_total"]).abs())
    )
    mismatch_rate = 100 * (collision_counts["casualty_count_diff"] > 0).mean()
    duplicates_rate = 100 * (
        collisions.duplicated(subset=["collision_index"]).mean()
    )
    st.metric("Collisions casualty-count mismatch", f"{mismatch_rate:.2f}%")
    st.metric("Duplicate collision_index rows", f"{duplicates_rate:.4f}%")

    st.subheader("Code Decoding Dictionary (sample)")
    dict_rows = []
    for col, mapper in CODE_MAPS.items():
        for key, label in mapper.items():
            dict_rows.append({"column": col, "code": key, "label": label})
    st.dataframe(pd.DataFrame(dict_rows), use_container_width=True, hide_index=True)


def main() -> None:
    cache_fingerprint = _data_cache_fingerprint()
    try:
        collision_view = build_collision_view(cache_fingerprint)
    except (ValueError, KeyError) as e:
        st.error(
            f"Data loading failed: {e} "
            "Please check that your casualty and collision CSVs use the expected STATS19 schema "
            "(collision_index, casualty_reference, casualty_severity, casualty_class, casualty_type, age_of_casualty)."
        )
        st.stop()
    except (MemoryError, OSError) as e:
        st.error(
            "Data loading failed (out of memory or system limit). On Streamlit Cloud free tier, try: "
            "1) Add **Build command**: `python scripts/prepare_data.py` in app settings, 2) Redeploy."
        )
        st.stop()
    except Exception as e:
        st.error(f"Data loading failed: {type(e).__name__}: {e}")
        st.stop()

    missing_collision = _validate_schema(collision_view, REQUIRED_COLLISION_VIEW_COLUMNS)
    if missing_collision:
        st.error(
            f"Schema validation failed: missing required columns in collision view: **{', '.join(missing_collision)}**. "
            "These columns are required for Executive Overview, GeoRisk Map, Risk Factors, Vehicle Intelligence, "
            "and sidebar filtering. The app cannot run without them."
        )
        st.stop()

    filtered_collision = apply_sidebar_filters(collision_view)

    st.title("UK Gov Road Safety Open Data (Last 5 Years)")

    collisions_raw, vehicles_raw, casualties_raw = load_raw_tables(cache_fingerprint)  # cached; hit after build_collision_view
    max_date = collision_view["date"].max() if "date" in collision_view.columns and collision_view["date"].notna().any() else None
    operational_stats = {
        "total_records": len(collisions_raw) + len(vehicles_raw) + len(casualties_raw),
        "max_date_str": max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else "–",
    }

    st.markdown("### Intelligence Modules")
    page = st.radio(
        "Select intelligence module",
        options=[
            "Executive Overview",
            "GeoRisk Map",
            "Risk Factors",
            "Vehicle Intelligence",
            "Casualty Intelligence",
            "Data Quality & Refresh Status",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )

    def safe_page(name: str, fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception as e:
            st.error(f"**{name}** could not load: {e}")
            st.exception(e)

    if page == "Executive Overview":
        safe_page("Executive Overview", page_executive_overview, filtered_collision, operational_stats)
    elif page == "GeoRisk Map":
        safe_page("GeoRisk Map", page_georisk_map, filtered_collision)
    elif page == "Risk Factors":
        safe_page("Risk Factors", page_risk_factors, filtered_collision)
    elif page == "Vehicle Intelligence":
        vehicle_view = build_vehicle_view(cache_fingerprint)
        filtered_vehicle = vehicle_view[
            vehicle_view["collision_index"].isin(filtered_collision["collision_index"])
        ]
        safe_page("Vehicle Intelligence", page_vehicle_intelligence, filtered_vehicle)
    elif page == "Casualty Intelligence":
        casualty_view, casualty_person_view = build_casualty_views(cache_fingerprint)
        filtered_casualty_linked = casualty_view[
            casualty_view["collision_index"].isin(filtered_collision["collision_index"])
        ]
        filtered_casualty_person = casualty_person_view[
            casualty_person_view["collision_index"].isin(filtered_collision["collision_index"])
        ]
        safe_page("Casualty Intelligence", page_casualty_intelligence, filtered_casualty_person, filtered_casualty_linked)
    elif page == "Data Quality & Refresh Status":
        safe_page("Data Quality & Refresh Status", page_pipeline_health, collisions_raw, vehicles_raw, casualties_raw, collision_view)


if __name__ == "__main__":
    main()
