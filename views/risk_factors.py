"""Risk Factors page."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from charts.plotly_charts import plot_chart, SEVERITY_COLORS
from styles.dataframe import render_dataframe
from styles.theme import COLORS
from transforms import ensure_label_columns as _ensure_label_columns, safe_ratio as _safe_ratio, series_or_default as _series_or_default
from views.constants import (
    DATA_MISSING_LABEL,
    EXPOSURE_CAVEAT,
    SPECIFIED_ROAD_CAVEAT,
    SPEED_LIMIT_NOTE,
    TRUNK_ROAD_NOTE,
    UNKNOWN_SPEED_LABEL,
)

VOLUME_COLOR = COLORS["accent"]
RATE_COLOR = SEVERITY_COLORS["Serious"]

EXCLUDE_UNKNOWN = {
    "Unknown",
    DATA_MISSING_LABEL,
    "unknown (self reported)",
}


def _agg_by_dimension(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    grouped = (
        df.groupby(dimension, dropna=False)
        .agg(
            collisions=("collision_index", "count"),
            serious=("serious_casualties", "sum"),
            ksi=("fatal_or_serious_collision", "sum"),
        )
        .reset_index()
    )
    grouped["ksi_rate_pct"] = _safe_ratio(grouped["ksi"], grouped["collisions"]) * 100
    grouped["serious_rate_pct"] = _safe_ratio(grouped["serious"], grouped["collisions"]) * 100
    return grouped


def _filter_labels(grouped: pd.DataFrame, label_col: str) -> pd.DataFrame:
    labels = grouped[label_col].astype(str).str.strip()
    return grouped[~labels.isin(EXCLUDE_UNKNOWN) & (labels != DATA_MISSING_LABEL)].copy()


def _plot_horizontal_bar(
    data: pd.DataFrame,
    label_col: str,
    value_col: str,
    title: str,
    color: str,
    value_label: str,
    *,
    top_n: int = 10,
) -> None:
    plot_df = data.sort_values(value_col, ascending=True).tail(top_n)
    fig = px.bar(
        plot_df,
        x=value_col,
        y=label_col,
        orientation="h",
        title=title,
        labels={label_col: "", value_col: value_label},
    )
    fig.update_traces(
        marker_color=color,
        hovertemplate=f"%{{y}}<br>{value_label} = %{{x:,.1f}}<extra></extra>",
    )
    fig.update_layout(
        margin=dict(l=10, r=20, t=40, b=20),
        yaxis=dict(categoryorder="total ascending"),
        showlegend=False,
    )
    plot_chart(fig, use_container_width=True)


def _build_insights(
    collision_view: pd.DataFrame,
    speed: pd.DataFrame,
    road_class: pd.DataFrame,
    road_class_col: str,
    hazard_view: pd.DataFrame,
    trunk_split: pd.DataFrame,
) -> list[str]:
    insights: list[str] = []

    speed_valid = speed[speed["speed_limit"] > 0].copy()
    if not speed_valid.empty:
        peak = speed_valid.loc[speed_valid["serious_rate_pct"].idxmax()]
        insights.append(
            f"Serious casualty rate rises with speed limit, peaking on **{int(peak['speed_limit'])} mph** roads "
            f"({peak['serious_rate_pct']:.1f}%)."
        )

    if not road_class.empty:
        road_class_display_map = {
            "A": "A Road",
            "B": "B Road",
            "C": "C Road",
            "A(M)": "A(M) Road",
            "Motorway": "Motorway",
            "Unclassified": "Unclassified Road",
        }
        rc = road_class.copy()
        rc["road_class_display"] = rc[road_class_col].astype("string").replace(road_class_display_map)
        top_rc = rc.sort_values("ksi_rate_pct", ascending=False).iloc[0]
        insights.append(
            f"**{top_rc['road_class_display']}** shows the highest KSI rate by road class ({top_rc['ksi_rate_pct']:.1f}%)."
        )

    weather = _filter_labels(_agg_by_dimension(collision_view, "weather_conditions_label"), "weather_conditions_label")
    light = _filter_labels(_agg_by_dimension(collision_view, "light_conditions_label"), "light_conditions_label")
    if not weather.empty and not light.empty:
        top_weather = weather.sort_values("serious", ascending=False).iloc[0]["weather_conditions_label"]
        top_light = light.sort_values("serious", ascending=False).iloc[0]["light_conditions_label"]
        insights.append(
            f"Most serious casualties occur in **{top_light}** and **{top_weather}** — the most common driving conditions."
        )

    hazard_n = int(hazard_view["hazard_flag"].sum())
    hazard_share = hazard_view["hazard_flag"].mean() * 100
    hazard_ksi = (
        100
        * hazard_view.loc[hazard_view["hazard_flag"] == 1, "fatal_or_serious_collision"].sum()
        / max(1, hazard_n)
    )
    if hazard_n > 0:
        insights.append(
            f"Hazard-present collisions account for **{hazard_share:.1f}%** of records, with a **{hazard_ksi:.1f}%** KSI rate."
        )

    trunk_rows = trunk_split[trunk_split["road_ownership_display"].str.contains("Trunk", na=False)]
    if not trunk_rows.empty:
        trunk_share = trunk_rows["collisions"].sum() / max(1, trunk_split["collisions"].sum()) * 100
        insights.append(
            f"Trunk-road collisions are **{trunk_share:.1f}%** of records — review separately from local-road risks."
        )

    return insights[:5]


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
    junction_control_col = (
        "junction_control_label" if "junction_control_label" in collision_view.columns else "junction_control"
    )
    hazard_col = "carriageway_hazards_label" if "carriageway_hazards_label" in collision_view.columns else "carriageway_hazards"
    special_col = (
        "special_conditions_at_site_label"
        if "special_conditions_at_site_label" in collision_view.columns
        else "special_conditions_at_site"
    )
    trunk_col = "trunk_road_flag_label" if "trunk_road_flag_label" in collision_view.columns else "trunk_road_flag"

    hazard_view = collision_view.copy()
    hazard_view["hazard_flag"] = (
        (_series_or_default(hazard_view, "carriageway_hazards", 0) > 0)
        | (_series_or_default(hazard_view, "special_conditions_at_site", 0) > 0)
    ).astype(int)

    speed = (
        collision_view.groupby("speed_limit", dropna=False)
        .agg(
            collisions=("collision_index", "count"),
            serious=("serious_casualties", "sum"),
            ksi=("fatal_or_serious_collision", "sum"),
        )
        .reset_index()
    )
    speed["serious_rate_pct"] = _safe_ratio(speed["serious"], speed["collisions"]) * 100
    speed_unknown_n = int(speed.loc[speed["speed_limit"] == 0, "collisions"].sum()) if (speed["speed_limit"] == 0).any() else 0

    road_class = _filter_labels(_agg_by_dimension(collision_view, road_class_col), road_class_col)

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
        "-1": DATA_MISSING_LABEL,
        "1": "Trunk (National Highways)",
        "2": "Non-trunk",
    }
    trunk_split["road_ownership_display"] = trunk_split[trunk_col].astype("string").replace(trunk_label_map)

    insights = _build_insights(collision_view, speed, road_class, road_class_col, hazard_view, trunk_split)
    st.markdown("#### Key risk factor insights")
    for line in insights:
        st.markdown(f"- {line}")

    with st.expander("Environmental conditions", expanded=True):
        st.markdown("**Where serious casualties occur most often**")
        st.caption(EXPOSURE_CAVEAT)
        fac1, fac2 = st.columns(2)
        weather = _filter_labels(_agg_by_dimension(collision_view, "weather_conditions_label"), "weather_conditions_label")
        light = _filter_labels(_agg_by_dimension(collision_view, "light_conditions_label"), "light_conditions_label")

        with fac1:
            _plot_horizontal_bar(
                weather,
                "weather_conditions_label",
                "serious",
                "Serious casualties by weather",
                VOLUME_COLOR,
                "Serious casualties",
            )
        with fac2:
            _plot_horizontal_bar(
                light,
                "light_conditions_label",
                "serious",
                "Serious casualties by light",
                VOLUME_COLOR,
                "Serious casualties",
            )

        st.markdown("**Where collisions are more likely to result in KSI**")
        fac3, fac4 = st.columns(2)
        with fac3:
            _plot_horizontal_bar(
                weather,
                "weather_conditions_label",
                "ksi_rate_pct",
                "KSI rate by weather (%)",
                RATE_COLOR,
                "KSI rate (%)",
            )
        with fac4:
            _plot_horizontal_bar(
                light,
                "light_conditions_label",
                "ksi_rate_pct",
                "KSI rate by light (%)",
                RATE_COLOR,
                "KSI rate (%)",
            )

    with st.expander("Speed and road class", expanded=True):
        st.markdown("**Where collisions are more likely to result in KSI**")
        speed_chart = speed[speed["speed_limit"] > 0].copy()
        if not speed_chart.empty:
            speed_fig = px.line(
                speed_chart.sort_values("speed_limit"),
                x="speed_limit",
                y="serious_rate_pct",
                markers=True,
                title="Serious casualty rate by speed limit (%)",
                labels={"speed_limit": "Speed limit (mph)", "serious_rate_pct": "Serious rate (%)"},
            )
            speed_fig.update_traces(
                line_color=RATE_COLOR,
                marker_color=RATE_COLOR,
                hovertemplate="Speed limit = %{x} mph<br>Serious rate = %{y:.1f}%<extra></extra>",
            )
            plot_chart(speed_fig, use_container_width=True)
        st.caption(SPEED_LIMIT_NOTE)
        if speed_unknown_n:
            st.caption(f"*{UNKNOWN_SPEED_LABEL}* speed limits: **{speed_unknown_n:,}** collision records excluded from the chart.")

        if not road_class.empty:
            road_class_display_map = {
                "A": "A Road",
                "B": "B Road",
                "C": "C Road",
                "A(M)": "A(M) Road",
                "Motorway": "Motorway",
                "Unclassified": "Unclassified Road",
            }
            road_class = road_class.copy()
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
                    "ksi": "Fatal/serious collisions",
                },
            )
            road_class_fig.update_traces(
                marker_color=RATE_COLOR,
                hovertemplate=(
                    "Road class = %{x}<br>"
                    "KSI rate = %{y:.1f}%<br>"
                    "Collisions = %{customdata[0]}<br>"
                    "Fatal/serious = %{customdata[1]}<extra></extra>"
                ),
            )
            plot_chart(road_class_fig, use_container_width=True)

        st.markdown("**Specified road corridors**")
        st.caption(SPECIFIED_ROAD_CAVEAT)
        corridors = (
            collision_view[collision_view["first_road_number"] > 0]
            .groupby(["first_road_class", "first_road_number"], dropna=False)
            .agg(
                collisions=("collision_index", "count"),
                ksi=("fatal_or_serious_collision", "sum"),
                serious=("serious_casualties", "sum"),
                slight=("slight_casualties", "sum"),
            )
            .reset_index()
        )
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
        corridors["ksi_rate_pct"] = _safe_ratio(corridors["ksi"], corridors["collisions"]) * 100
        for c in ["collisions", "ksi", "serious", "slight", "harm_index"]:
            corridors[c] = np.rint(corridors[c]).astype("int64")
        if not corridors.empty:
            st.caption("Roads ranked by Harm Index across the current filter selection.")
            render_dataframe(
                corridors.sort_values("harm_index", ascending=False)
                .head(15)
                .rename(
                    columns={
                        "road_ref": "Road",
                        "collisions": "Collision records",
                        "ksi": "Fatal/serious collisions",
                        "serious": "Serious casualties",
                        "slight": "Slight casualties",
                        "ksi_rate_pct": "KSI rate (%)",
                        "harm_index": "Harm Index",
                    }
                )[
                    [
                        "Road",
                        "Collision records",
                        "Fatal/serious collisions",
                        "Serious casualties",
                        "KSI rate (%)",
                        "Harm Index",
                    ]
                ],
                use_container_width=True,
            )

            watchlist_numbers = [4540, 4040, 1000, 666, 406, 259, 124, 41, 38, 35, 34, 27, 13, 6, 1]
            watch = corridors[corridors["first_road_number"].isin(watchlist_numbers)].copy()
            st.subheader("Specified Road Number Watchlist")
            if watch.empty:
                st.info("None of the specified road numbers meet current filters/thresholds.")
            else:
                render_dataframe(
                    watch.sort_values("harm_index", ascending=False).rename(
                        columns={
                            "road_ref": "Road",
                            "collisions": "Collision records",
                            "ksi": "Fatal/serious collisions",
                            "serious": "Serious casualties",
                            "ksi_rate_pct": "KSI rate (%)",
                            "harm_index": "Harm Index",
                        }
                    )[
                        [
                            "Road",
                            "Collision records",
                            "Fatal/serious collisions",
                            "KSI rate (%)",
                            "Harm Index",
                        ]
                    ],
                    use_container_width=True,
                )

    with st.expander("Junction intelligence", expanded=True):
        st.markdown("**Where serious casualties occur most often**")
        junction = (
            _filter_labels(_agg_by_dimension(collision_view, j_detail_col), j_detail_col)
            .sort_values("serious", ascending=False)
            .head(15)
        )
        _plot_horizontal_bar(
            junction,
            j_detail_col,
            "serious",
            "Serious casualties by junction detail",
            VOLUME_COLOR,
            "Serious casualties",
            top_n=15,
        )
        st.caption(EXPOSURE_CAVEAT)

        st.markdown("**Junction detail — volume and KSI rate**")
        junction_table = junction.copy()
        junction_table = junction_table.rename(
            columns={
                j_detail_col: "Junction detail",
                "collisions": "Collision records",
                "serious": "Serious casualties",
                "ksi_rate_pct": "KSI rate (%)",
            }
        )
        render_dataframe(
            junction_table[["Junction detail", "Collision records", "Serious casualties", "KSI rate (%)"]],
            use_container_width=True,
        )

        st.markdown("**Where collisions are more likely to result in KSI**")
        junction_mix = (
            collision_view.groupby([junction_control_col, j_detail_col], dropna=False)
            .agg(collisions=("collision_index", "count"), ksi=("fatal_or_serious_collision", "sum"))
            .reset_index()
        )
        junction_mix = _filter_labels(junction_mix, junction_control_col)
        junction_mix = _filter_labels(junction_mix, j_detail_col)
        if junction_mix.empty:
            st.info("No junction control/detail combinations available for the current filters.")
        else:
            junction_mix["ksi_rate_pct"] = _safe_ratio(junction_mix["ksi"], junction_mix["collisions"]) * 100
            pivot_rate = junction_mix.pivot(
                index=j_detail_col,
                columns=junction_control_col,
                values="ksi_rate_pct",
            )
            pivot_count = junction_mix.pivot(
                index=j_detail_col,
                columns=junction_control_col,
                values="collisions",
            )

            hovertext = pivot_rate.copy().astype(object)
            for r in pivot_rate.index:
                for c in pivot_rate.columns:
                    count = pivot_count.loc[r, c] if r in pivot_count.index and c in pivot_count.columns else np.nan
                    rate = pivot_rate.loc[r, c] if r in pivot_rate.index and c in pivot_rate.columns else np.nan
                    if pd.isna(count) or pd.isna(rate):
                        hovertext.loc[r, c] = "No data"
                    else:
                        hovertext.loc[r, c] = f"Collisions = {int(count)}<br>KSI rate = {rate:.1f}%"

            jheat = go.Figure(
                data=go.Heatmap(
                    z=pivot_rate.astype(float).values,
                    x=list(pivot_rate.columns),
                    y=list(pivot_rate.index),
                    colorscale="Reds",
                    hovertext=hovertext.values,
                    hovertemplate="%{hovertext}<extra></extra>",
                    colorbar=dict(title="KSI rate (%)"),
                )
            )
            jheat.update_layout(
                title="KSI rate by junction control and detail (%)",
                xaxis_title="Junction control",
                yaxis_title="Junction detail",
                margin=dict(t=50, b=40, l=120, r=20),
            )
            plot_chart(jheat, use_container_width=True)

    with st.expander("Hazards and roadworks", expanded=True):
        hazard_n = int(hazard_view["hazard_flag"].sum())
        hazard_share = hazard_view["hazard_flag"].mean() * 100
        hazard_ksi_rate = (
            100
            * hazard_view.loc[hazard_view["hazard_flag"] == 1, "fatal_or_serious_collision"].sum()
            / max(1, hazard_n)
        )
        no_hazard_n = int((hazard_view["hazard_flag"] == 0).sum())
        no_hazard_ksi_rate = (
            100
            * hazard_view.loc[hazard_view["hazard_flag"] == 0, "fatal_or_serious_collision"].sum()
            / max(1, no_hazard_n)
        )

        hz1, hz2, hz3 = st.columns(3)
        hz1.metric("Hazard/special-condition collisions", f"{hazard_n:,}")
        hz2.metric("Hazard collision share", f"{hazard_share:.1f}%")
        hz3.metric(
            "KSI rate when hazard present",
            f"{hazard_ksi_rate:.1f}%",
            help=f"Compared with {no_hazard_ksi_rate:.1f}% when no hazard or special condition is recorded.",
        )
        st.caption(f"KSI rate without hazard recorded: **{no_hazard_ksi_rate:.1f}%**.")

        st.markdown("**Where collisions are more likely to result in KSI**")
        hazard_by_type = _filter_labels(_agg_by_dimension(hazard_view, hazard_col), hazard_col)
        if hazard_by_type.empty:
            st.info("No hazard categories available for the current filters.")
        else:
            _plot_horizontal_bar(
                hazard_by_type,
                hazard_col,
                "ksi_rate_pct",
                "KSI rate by carriageway hazard type (%)",
                RATE_COLOR,
                "KSI rate (%)",
            )

        special_by_type = _filter_labels(_agg_by_dimension(hazard_view, special_col), special_col)
        if special_by_type.empty:
            st.info("No special-condition categories available for the current filters.")
        else:
            _plot_horizontal_bar(
                special_by_type,
                special_col,
                "ksi_rate_pct",
                "KSI rate by special conditions at site (%)",
                RATE_COLOR,
                "KSI rate (%)",
            )

    with st.expander("Governance — trunk road split", expanded=True):
        st.caption(TRUNK_ROAD_NOTE)
        trunk_display = trunk_split.copy()
        for c in ["collisions", "ksi", "serious", "slight"]:
            trunk_display[c] = np.rint(trunk_display[c]).astype("int64")
        trunk_display["ksi_rate_pct"] = _safe_ratio(trunk_display["ksi"], trunk_display["collisions"]) * 100

        governance = trunk_display[
            trunk_display["road_ownership_display"].isin(["Trunk (National Highways)", "Non-trunk"])
        ].copy()
        data_quality = trunk_display[
            trunk_display["road_ownership_display"] == DATA_MISSING_LABEL
        ].copy()

        if not governance.empty:
            st.markdown("**Road ownership comparison**")
            render_dataframe(
                governance.rename(
                    columns={
                        "road_ownership_display": "Road ownership",
                        "collisions": "Collision records",
                        "ksi": "Fatal/serious collisions",
                        "serious": "Serious casualties",
                        "slight": "Slight casualties",
                        "ksi_rate_pct": "KSI rate (%)",
                    }
                )[
                    [
                        "Road ownership",
                        "Collision records",
                        "Fatal/serious collisions",
                        "KSI rate (%)",
                    ]
                ],
                use_container_width=True,
            )

        if not data_quality.empty:
            st.markdown("**Data quality — missing or out-of-range trunk flag**")
            render_dataframe(
                data_quality.rename(
                    columns={
                        "road_ownership_display": "Category",
                        "collisions": "Collision records",
                        "ksi": "Fatal/serious collisions",
                        "ksi_rate_pct": "KSI rate (%)",
                    }
                )[["Category", "Collision records", "Fatal/serious collisions", "KSI rate (%)"]],
                use_container_width=True,
            )

        trunk_district = (
            collision_view[_series_or_default(collision_view, "trunk_road_flag", -1) == 1]
            .groupby("district_display", dropna=False)
            .agg(collisions=("collision_index", "count"), ksi=("fatal_or_serious_collision", "sum"))
            .reset_index()
        )
        if not trunk_district.empty:
            st.markdown("**Top trunk-road districts**")
            st.caption("Districts ranked by fatal/serious trunk-road collisions in the current filter selection.")
            trunk_district["collisions"] = np.rint(trunk_district["collisions"]).astype("int64")
            trunk_district["ksi"] = np.rint(trunk_district["ksi"]).astype("int64")
            trunk_district["ksi_rate_pct"] = _safe_ratio(trunk_district["ksi"], trunk_district["collisions"]) * 100
            render_dataframe(
                trunk_district.sort_values("ksi", ascending=False).head(12).rename(
                    columns={
                        "district_display": "District",
                        "collisions": "Trunk collision records",
                        "ksi": "Fatal/serious collisions",
                        "ksi_rate_pct": "KSI rate (%)",
                    }
                ),
                use_container_width=True,
            )
