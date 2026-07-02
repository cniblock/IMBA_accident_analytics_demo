"""Vehicle Intelligence page."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from charts.plotly_charts import plot_chart, SEVERITY_COLORS
from styles.dataframe import render_dataframe
from styles.theme import COLORS
from transforms import (
    add_vehicle_intelligence_features as _add_vehicle_intelligence_features,
    collision_level_serious_fatal_stats as _collision_level_serious_fatal_stats,
    safe_ratio as _safe_ratio,
)
from views.constants import (
    CASE_DRILLDOWN_NOTE,
    DRIVER_AGE_NOTE,
    INVOLVEMENT_RATE_LABEL,
    MODEL_INVOLVEMENT_CAVEAT,
    SCORE_DEFINITIONS,
    TRIAGE_HARM_CAPTION,
    VEHICLE_EXPOSURE_CAVEAT,
    VEHICLE_RECORD_CONTEXT,
)

VOLUME_COLOR = COLORS["accent"]
RATE_COLOR = SEVERITY_COLORS["Serious"]
DATA_MISSING = "Data missing or out of range"

VEHICLE_TYPE_ORDER = [
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


def _valid_driver_age_series(series: pd.Series) -> pd.Series:
    ages = pd.to_numeric(series, errors="coerce")
    return ages.where(ages.between(1, 120, inclusive="both"))


def _plot_horizontal_bar(
    data: pd.DataFrame,
    label_col: str,
    value_col: str,
    title: str,
    color: str,
    value_label: str,
    *,
    top_n: int = 12,
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
    fig.update_traces(marker_color=color, hovertemplate=f"%{{y}}<br>{value_label} = %{{x:.1f}}<extra></extra>")
    fig.update_layout(
        margin=dict(l=10, r=20, t=40, b=20),
        yaxis=dict(categoryorder="total ascending"),
        showlegend=False,
    )
    plot_chart(fig, use_container_width=True)


def _format_stats_table(df: pd.DataFrame, label_col: str, label_name: str) -> pd.DataFrame:
    out = df.copy()
    for col in ["fatal_collisions", "serious_collisions", "serious_or_fatal_collisions", "collisions", "vehicles", "vehicle_records"]:
        if col in out.columns:
            out[col] = np.rint(out[col]).astype("int64")
    for col in ["avg_speed_limit", "avg_driver_age"]:
        if col in out.columns:
            out[col] = np.rint(out[col]).astype("int64")
    if "serious_fatal_collision_rate_pct" in out.columns:
        out["serious_fatal_collision_rate_pct"] = out["serious_fatal_collision_rate_pct"].round(1)
    rename = {
        label_col: label_name,
        "vehicles": "Vehicle records",
        "vehicle_records": "Vehicle records",
        "collisions": "Collisions",
        "fatal_collisions": "Fatal",
        "serious_collisions": "Serious",
        "serious_or_fatal_collisions": "Serious/fatal",
        "serious_fatal_collision_rate_pct": INVOLVEMENT_RATE_LABEL,
        "avg_speed_limit": "Avg speed (mph)",
        "avg_driver_age": "Avg driver age",
    }
    return out.rename(columns={k: v for k, v in rename.items() if k in out.columns})


def _format_ranking_table(df: pd.DataFrame) -> pd.DataFrame:
    return _format_stats_table(df, "vehicle_type_label", "Vehicle type")


def _build_vehicle_insights(
    by_vehicle: pd.DataFrame,
    vehicle_data: pd.DataFrame,
    speed_matrix: pd.DataFrame | None,
) -> list[str]:
    insights: list[str] = []

    if not by_vehicle.empty:
        top = by_vehicle.iloc[0]
        insights.append(
            f"**{top['vehicle_type_label']}** has the highest serious/fatal involvement rate "
            f"({top['serious_fatal_collision_rate_pct']:.1f}%) among vehicle types."
        )
        motorcycle_mask = by_vehicle["vehicle_type_label"].astype(str).str.contains("Motorcycle|motorcycle", regex=True)
        if motorcycle_mask.any():
            top_bike = by_vehicle[motorcycle_mask].iloc[0]
            insights.append(
                f"Motorcycles show elevated involvement rates — highest: **{top_bike['vehicle_type_label']}** "
                f"({top_bike['serious_fatal_collision_rate_pct']:.1f}%)."
            )

    if speed_matrix is not None and not speed_matrix.empty:
        matrix = speed_matrix.copy()
        matrix["speed_limit"] = pd.to_numeric(matrix["speed_limit"], errors="coerce")
        mid_speed = matrix[matrix["speed_limit"].between(50, 60, inclusive="both")]
        if not mid_speed.empty:
            peak = mid_speed.sort_values("serious_fatal_collision_rate_pct", ascending=False).iloc[0]
            insights.append(
                f"Serious/fatal involvement rises on **50–60 mph** roads for several types — e.g. "
                f"**{peak['vehicle_type_label']}** at {int(peak['speed_limit'])} mph "
                f"({peak['serious_fatal_collision_rate_pct']:.1f}%)."
            )

    loc_rate = vehicle_data["loss_of_control_flag"].mean() * 100
    severe_loc = (
        100
        * vehicle_data.loc[vehicle_data["loss_of_control_flag"] == 1, "serious_or_fatal_collision"].sum()
        / max(1, (vehicle_data["loss_of_control_flag"] == 1).sum())
    )
    insights.append(
        f"Loss of control appears in **{loc_rate:.1f}%** of vehicle records and is associated with "
        f"**{severe_loc:.1f}%** serious/fatal involvement among LOC-tagged records."
    )

    if "incident_signature" in vehicle_data.columns:
        sig_stats = _collision_level_serious_fatal_stats(vehicle_data, ["incident_signature"])
        if not sig_stats.empty:
            top_sig = sig_stats.sort_values("serious_fatal_collision_rate_pct", ascending=False).iloc[0]
            insights.append(
                f"**{top_sig['incident_signature']}** is the highest-rate incident signature "
                f"({top_sig['serious_fatal_collision_rate_pct']:.1f}% involvement)."
            )

    insights.append(
        "Manufacturer/model rankings are **indicative only** — interpret with sample size and usage context."
    )
    return insights[:5]


def page_vehicle_intelligence(vehicle_view: pd.DataFrame) -> None:
    st.title("Vehicle Intelligence")
    if vehicle_view.empty:
        st.warning("No vehicle records available for the selected filters.")
        return

    vehicle_data = vehicle_view.copy()
    vehicle_data["vehicle_type_label"] = vehicle_data["vehicle_type_label"].fillna("Unknown")
    if "incident_signature" not in vehicle_data.columns:
        vehicle_data = _add_vehicle_intelligence_features(vehicle_data)

    st.markdown(VEHICLE_RECORD_CONTEXT)
    st.info(TRIAGE_HARM_CAPTION)

    total_vehicle_rows = len(vehicle_data)
    total_collisions = vehicle_data["collision_index"].nunique()
    valid_ages = _valid_driver_age_series(vehicle_data["age_of_driver"])
    avg_driver_age = valid_ages.mean()
    avg_risk_score = vehicle_data["triage_score"].mean()
    avg_harm_score = vehicle_data["harm_score"].mean()

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Vehicle records", f"{total_vehicle_rows:,}")
    k2.metric("Linked collisions", f"{total_collisions:,}")
    k3.metric("Avg driver age", f"{avg_driver_age:.1f}" if pd.notna(avg_driver_age) else "N/A")
    k4.metric("Avg triage score", f"{avg_risk_score:.1f}" if pd.notna(avg_risk_score) else "N/A")
    k5.metric("Avg harm score", f"{avg_harm_score:.1f}" if pd.notna(avg_harm_score) else "N/A")

    with st.expander("How triage and harm scores are calculated"):
        st.markdown(SCORE_DEFINITIONS)

    vehicle_agg = (
        vehicle_data.groupby("vehicle_type_label", dropna=False)
        .agg(
            vehicles=("vehicle_reference", "count"),
            avg_speed_limit=("speed_limit", "mean"),
            avg_driver_age=("age_of_driver", lambda s: _valid_driver_age_series(s).mean()),
        )
        .reset_index()
    )
    collision_stats = _collision_level_serious_fatal_stats(vehicle_data, ["vehicle_type_label"])
    by_vehicle = vehicle_agg.merge(collision_stats, on="vehicle_type_label", how="left")
    by_vehicle = by_vehicle.sort_values("serious_fatal_collision_rate_pct", ascending=False)

    speed_matrix_stats = _collision_level_serious_fatal_stats(
        vehicle_data, ["vehicle_type_label", "speed_limit"]
    )
    speed_matrix_preview = speed_matrix_stats[
        (pd.to_numeric(speed_matrix_stats["speed_limit"], errors="coerce") > 0)
        & (speed_matrix_stats["vehicle_type_label"].astype(str).str.strip() != "Unknown")
    ].copy()

    st.markdown("#### Key vehicle insights")
    for line in _build_vehicle_insights(by_vehicle, vehicle_data, speed_matrix_preview):
        st.markdown(f"- {line}")

    with st.expander("Vehicle type risk profile", expanded=True):
        st.caption(VEHICLE_EXPOSURE_CAVEAT)
        st.markdown("**Where serious/fatal collisions involve each vehicle type most often**")
        top_vehicle = _format_ranking_table(by_vehicle.head(15))
        render_dataframe(
            top_vehicle[
                [
                    "Vehicle type",
                    "Vehicle records",
                    "Avg speed (mph)",
                    "Avg driver age",
                    "Collisions",
                    "Fatal",
                    "Serious",
                    "Serious/fatal",
                    INVOLVEMENT_RATE_LABEL,
                ]
            ],
            use_container_width=True,
        )

        st.markdown("**Serious/fatal involvement rate by vehicle type**")
        _plot_horizontal_bar(
            by_vehicle,
            "vehicle_type_label",
            "serious_fatal_collision_rate_pct",
            INVOLVEMENT_RATE_LABEL,
            RATE_COLOR,
            INVOLVEMENT_RATE_LABEL,
        )

        speed_fig = px.scatter(
            by_vehicle,
            x="avg_speed_limit",
            y="serious_fatal_collision_rate_pct",
            size="collisions",
            title=f"Serious/fatal involvement rate vs average speed limit (bubble size = collision count)",
            hover_name="vehicle_type_label",
            labels={
                "avg_speed_limit": "Average speed limit (mph)",
                "serious_fatal_collision_rate_pct": INVOLVEMENT_RATE_LABEL,
                "collisions": "Collisions",
            },
        )
        speed_fig.update_traces(
            marker=dict(color=RATE_COLOR, opacity=0.75, sizeref=2.0 * max(by_vehicle["collisions"]) / (40.0**2)),
            customdata=by_vehicle[["collisions", "avg_driver_age"]],
            hovertemplate=(
                "Vehicle type = %{hovertext}<br>"
                "Average speed limit = %{x:.0f} mph<br>"
                f"{INVOLVEMENT_RATE_LABEL} = %{{y:.1f}}<br>"
                "Collisions = %{customdata[0]}<br>"
                "Average driver age = %{customdata[1]:.0f}<extra></extra>"
            ),
        )
        speed_fig.update_layout(showlegend=False, margin=dict(t=40, b=30, l=50, r=20))
        plot_chart(speed_fig, use_container_width=True)

        st.markdown("**Average driver age by vehicle type**")
        st.caption(DRIVER_AGE_NOTE)
        _plot_horizontal_bar(
            by_vehicle.dropna(subset=["avg_driver_age"]),
            "vehicle_type_label",
            "avg_driver_age",
            "Average driver age by vehicle type",
            VOLUME_COLOR,
            "Average driver age",
        )

    with st.expander("Vehicle type × speed matrix", expanded=True):
        st.caption(VEHICLE_EXPOSURE_CAVEAT)
        speed_matrix = speed_matrix_stats[
            (pd.to_numeric(speed_matrix_stats["speed_limit"], errors="coerce") > 0)
            & (speed_matrix_stats["vehicle_type_label"].astype(str).str.strip() != "Unknown")
        ].copy()
        if speed_matrix.empty:
            st.info("No vehicle type × speed limit combinations available for the current filters.")
        else:
            extra_vehicle_types = [
                label
                for label in speed_matrix["vehicle_type_label"].dropna().astype(str).unique().tolist()
                if label not in VEHICLE_TYPE_ORDER
            ]
            ordered_vehicle_types = VEHICLE_TYPE_ORDER + sorted(extra_vehicle_types)
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
            matrix["hover_text"] = np.where(
                matrix["has_data"],
                (
                    "Speed limit = "
                    + matrix["speed_limit"].astype(int).astype(str)
                    + " mph<br>Vehicle type = "
                    + matrix["vehicle_type_label"].astype(str)
                    + f"<br>{INVOLVEMENT_RATE_LABEL} = "
                    + matrix["serious_fatal_collision_rate_pct"].round(1).astype(str)
                    + "<br>Collisions = "
                    + matrix["collisions"].map(lambda v: f"{int(round(v)):,}" if pd.notna(v) else "")
                ),
                (
                    "Speed limit = "
                    + matrix["speed_limit"].astype(int).astype(str)
                    + " mph<br>Vehicle type = "
                    + matrix["vehicle_type_label"].astype(str)
                    + "<br>No data for this cell"
                ),
            )
            z_matrix = matrix.pivot(index="vehicle_type_label", columns="speed_limit", values="z_value").reindex(
                ordered_vehicle_types
            )
            text_matrix = matrix.pivot(index="vehicle_type_label", columns="speed_limit", values="hover_text").reindex(
                ordered_vehicle_types
            )
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
                        colorbar={"title": INVOLVEMENT_RATE_LABEL},
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
                title=f"{INVOLVEMENT_RATE_LABEL} by vehicle type and speed limit",
                xaxis_title="Speed limit (mph)",
                yaxis_title="Vehicle type",
            )
            plot_chart(heat, use_container_width=True)

    with st.expander("Loss of control and incident signatures", expanded=True):
        st.caption("Rates below are at **vehicle-record level** — the proportion of records with each characteristic.")
        severe_rate_loc = (
            100
            * vehicle_data.loc[vehicle_data["loss_of_control_flag"] == 1, "serious_or_fatal_collision"].sum()
            / max(1, (vehicle_data["loss_of_control_flag"] == 1).sum())
        )
        loc1, loc2, loc3, loc4 = st.columns(4)
        loc1.metric("Loss-of-control vehicle-record rate", f"{vehicle_data['loss_of_control_flag'].mean() * 100:.1f}%")
        loc2.metric("Roadway-departure vehicle-record rate", f"{vehicle_data['roadway_departure_flag'].mean() * 100:.1f}%")
        loc3.metric("Off-carriageway impact vehicle-record rate", f"{vehicle_data['impact_off_carriageway_flag'].mean() * 100:.1f}%")
        loc4.metric("Serious/fatal involvement among LOC records", f"{severe_rate_loc:.1f}%")

        loc_conditions = (
            vehicle_data.groupby("road_surface_conditions_label", dropna=False)
            .agg(
                vehicles=("vehicle_reference", "count"),
                loss_of_control=("loss_of_control_flag", "sum"),
            )
            .reset_index()
        )
        unknown_surface = loc_conditions[
            loc_conditions["road_surface_conditions_label"].astype(str).str.strip().isin(["Unknown", DATA_MISSING])
        ]
        loc_plot = loc_conditions[
            ~loc_conditions["road_surface_conditions_label"].astype(str).str.strip().isin(
                ["Unknown", DATA_MISSING, "unknown (self reported)"]
            )
        ].copy()
        loc_plot["loc_rate_pct"] = _safe_ratio(loc_plot["loss_of_control"], loc_plot["vehicles"]) * 100
        if not unknown_surface.empty:
            unknown_n = int(unknown_surface["vehicles"].sum())
            st.caption(
                f"**Unknown** road surface: **{unknown_n:,}** vehicle records excluded from ranked comparison "
                f"(often incomplete coding)."
            )
        if not loc_plot.empty:
            _plot_horizontal_bar(
                loc_plot,
                "road_surface_conditions_label",
                "loc_rate_pct",
                "Loss-of-control vehicle-record rate by road surface (%)",
                RATE_COLOR,
                "LOC rate (%)",
            )

        st.markdown("**Manoeuvre involvement ranking**")
        manoeuvre_collision_stats = _collision_level_serious_fatal_stats(vehicle_data, ["vehicle_manoeuvre_label"])
        manoeuvre_rank = manoeuvre_collision_stats[
            manoeuvre_collision_stats["vehicle_manoeuvre_label"].astype(str).str.strip() != DATA_MISSING
        ].copy()
        if manoeuvre_rank.empty:
            st.info("No manoeuvre data available for the current filters.")
        else:
            render_dataframe(
                _format_stats_table(
                    manoeuvre_rank.sort_values("serious_fatal_collision_rate_pct", ascending=False).head(12),
                    "vehicle_manoeuvre_label",
                    "Vehicle manoeuvre",
                )[
                    [
                        "Vehicle manoeuvre",
                        "Collisions",
                        "Fatal",
                        "Serious",
                        "Serious/fatal",
                        INVOLVEMENT_RATE_LABEL,
                    ]
                ],
                use_container_width=True,
            )

        st.markdown("**Incident signature ranking**")
        signature_summary = _collision_level_serious_fatal_stats(vehicle_data, ["incident_signature"])
        render_dataframe(
            _format_stats_table(
                signature_summary.sort_values("serious_fatal_collision_rate_pct", ascending=False),
                "incident_signature",
                "Incident signature",
            )[
                [
                    "Incident signature",
                    "Collisions",
                    "Fatal",
                    "Serious",
                    "Serious/fatal",
                    INVOLVEMENT_RATE_LABEL,
                ]
            ],
            use_container_width=True,
        )

    with st.expander("Collision mechanics flow", expanded=True):
        sankey_scope = st.selectbox(
            "Sankey scope",
            options=["All vehicle types"] + sorted(vehicle_data["vehicle_type_label"].dropna().astype(str).unique().tolist()),
            key="sankey_scope_vehicle_type",
        )
        min_flow = st.selectbox(
            "Minimum flow (vehicle records)",
            options=[0, 500, 1000, 5000],
            index=0,
            format_func=lambda n: "All flows" if n == 0 else f"{n:,}+ records",
        )
        st.caption("Flow width represents vehicle records. Link colours indicate final collision severity.")

        sankey_source = (
            vehicle_data
            if sankey_scope == "All vehicle types"
            else vehicle_data[vehicle_data["vehicle_type_label"] == sankey_scope]
        )
        sankey_df = sankey_source[
            ["vehicle_manoeuvre_label", "first_point_of_impact_label", "collision_severity_label"]
        ].dropna()
        if sankey_df.empty:
            st.info("Not enough data to build the Sankey flow for the selected scope.")
        else:
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
                    [sankey_df["man_node"], sankey_df["impact_node"], sankey_df["severity_node"]],
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
            if min_flow > 0:
                links = links[links["value"] >= min_flow]
            if links.empty:
                st.info("No flows meet the minimum record threshold for the selected scope.")
            else:
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
                    title_text="Manoeuvre → Impact → Severity",
                    height=780,
                    font={"size": 12},
                )
                plot_chart(sankey_fig, use_container_width=True)

    with st.expander("Case and model drilldown", expanded=True):
        st.markdown("**Vehicle type case context**")
        st.caption(CASE_DRILLDOWN_NOTE)
        type_options = sorted(vehicle_data["vehicle_type_label"].dropna().astype(str).unique().tolist())
        if not type_options:
            st.info("No vehicle types available for drilldown under current filters.")
        else:
            selected_type = st.selectbox("Select vehicle type for case examples", options=type_options)
            drill = vehicle_data[vehicle_data["vehicle_type_label"] == selected_type].copy()
            if drill.empty:
                st.info("No records for this vehicle type under current filters.")
            else:
                st.caption(f"Highest triage-score examples for **{selected_type}** (max 50 rows).")
                drill_display = drill.sort_values(["triage_score", "harm_score"], ascending=False).head(50).copy()
                if "date" in drill_display.columns:
                    drill_display["date"] = pd.to_datetime(drill_display["date"], errors="coerce").dt.strftime("%Y-%m-%d")
                render_dataframe(
                    drill_display[
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
                    ].rename(
                        columns={
                            "collision_index": "Collision reference",
                            "district_display": "District",
                            "speed_limit": "Speed limit (mph)",
                            "age_of_driver": "Driver age",
                            "vehicle_manoeuvre_label": "Manoeuvre",
                            "first_point_of_impact_label": "First impact point",
                            "incident_signature": "Incident signature",
                            "triage_score": "Triage score",
                            "harm_score": "Harm score",
                        }
                    ),
                    use_container_width=True,
                )

        st.markdown("**Model involvement patterns**")
        st.caption(MODEL_INVOLVEMENT_CAVEAT)
        if "generic_make_model" not in vehicle_data.columns:
            st.info("Make/model data is not available in this dataset.")
        else:
            min_model_records = st.selectbox(
                "Minimum records per model",
                options=[20, 50, 100, 500],
                index=2,
                format_func=lambda n: f"{n}+ vehicle records",
                help="Small samples can produce unstable involvement rates.",
            )
            vehicle_type_filter = st.session_state.get("vehicle_type_filter", "cars")
            vt_numeric = pd.to_numeric(vehicle_data["vehicle_type"], errors="coerce")
            if vehicle_type_filter == "cars":
                manufacturer_data = vehicle_data[vt_numeric.isin([8, 9, 10])].copy()
            elif vehicle_type_filter == "motorbikes":
                manufacturer_data = vehicle_data[vt_numeric.isin([2, 3, 4, 5, 23])].copy()
            else:
                manufacturer_data = vehicle_data[vt_numeric.isin([2, 3, 4, 5, 23, 8, 9, 10])].copy()

            if manufacturer_data.empty:
                st.info("No vehicle records match the selected vehicle type filter.")
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
                        avg_driver_age=("age_of_driver", lambda s: _valid_driver_age_series(s).mean()),
                        avg_speed_limit=("speed_limit", "mean"),
                    )
                    .reset_index()
                )
                model_collision_stats = _collision_level_serious_fatal_stats(
                    manufacturer_data[manufacturer_data["make_model_label"] != "Unknown"],
                    ["make_model_label"],
                )
                model_summary = model_vehicle_agg.merge(model_collision_stats, on="make_model_label", how="left")
                model_summary = model_summary[model_summary["collisions"] >= min_model_records].copy()
                if model_summary.empty:
                    st.info(f"No models with at least {min_model_records} records under current filters.")
                else:
                    st.caption(f"Models ranked by {INVOLVEMENT_RATE_LABEL.lower()} (minimum {min_model_records} records).")
                    top_models = model_summary.sort_values("serious_fatal_collision_rate_pct", ascending=False).head(20)
                    render_dataframe(
                        _format_stats_table(top_models, "make_model_label", "Make/model")[
                            [
                                "Make/model",
                                "Vehicle records",
                                "Collisions",
                                "Fatal",
                                "Serious",
                                INVOLVEMENT_RATE_LABEL,
                                "Avg driver age",
                                "Avg speed (mph)",
                            ]
                        ],
                        use_container_width=True,
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
                    segment_summary = segment_summary[segment_summary["collisions"] >= min_model_records].copy()

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

                    if show_bike and show_car:
                        chart_left, chart_right = st.columns(2)
                        with chart_left:
                            _plot_horizontal_bar(
                                bike_top,
                                "make_model_label",
                                "serious_fatal_collision_rate_pct",
                                "Models with highest serious/fatal involvement — motorbikes",
                                RATE_COLOR,
                                INVOLVEMENT_RATE_LABEL,
                                top_n=10,
                            )
                        with chart_right:
                            _plot_horizontal_bar(
                                car_top,
                                "make_model_label",
                                "serious_fatal_collision_rate_pct",
                                "Models with highest serious/fatal involvement — cars",
                                RATE_COLOR,
                                INVOLVEMENT_RATE_LABEL,
                                top_n=10,
                            )
                    elif show_bike:
                        _plot_horizontal_bar(
                            bike_top,
                            "make_model_label",
                            "serious_fatal_collision_rate_pct",
                            "Models with highest serious/fatal involvement — motorbikes",
                            RATE_COLOR,
                            INVOLVEMENT_RATE_LABEL,
                            top_n=10,
                        )
                    elif show_car:
                        _plot_horizontal_bar(
                            car_top,
                            "make_model_label",
                            "serious_fatal_collision_rate_pct",
                            "Models with highest serious/fatal involvement — cars",
                            RATE_COLOR,
                            INVOLVEMENT_RATE_LABEL,
                            top_n=10,
                        )
