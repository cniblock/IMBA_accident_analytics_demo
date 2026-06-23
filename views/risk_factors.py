"""Risk Factors page."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from transforms import ensure_label_columns as _ensure_label_columns, safe_ratio as _safe_ratio, series_or_default as _series_or_default
from charts.plotly_charts import plot_chart

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
        plot_chart(weather_fig, use_container_width=True)
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
        plot_chart(light_fig, use_container_width=True)

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
    plot_chart(speed_fig, use_container_width=True)

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
    plot_chart(junction_fig, use_container_width=True)

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
        plot_chart(road_class_fig, use_container_width=True)

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
        plot_chart(jheat, use_container_width=True)

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
        plot_chart(hazard_fig, use_container_width=True)

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
        plot_chart(special_fig, use_container_width=True)

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
