"""Vehicle Intelligence page."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from transforms import (
    add_vehicle_intelligence_features as _add_vehicle_intelligence_features,
    collision_level_serious_fatal_stats as _collision_level_serious_fatal_stats,
    safe_ratio as _safe_ratio,
)
from views.constants import TRIAGE_HARM_CAPTION
from charts.plotly_charts import plot_chart

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
    st.caption(TRIAGE_HARM_CAPTION)
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
        plot_chart(ratio_fig, use_container_width=True)
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
        plot_chart(speed_fig, use_container_width=True)

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
        plot_chart(heat, use_container_width=True)

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
    plot_chart(age_fig, use_container_width=True)

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
    plot_chart(loc_fig, use_container_width=True)

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
        plot_chart(sankey_fig, use_container_width=True)

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
                            plot_chart(bike_fig, use_container_width=True)
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
                            plot_chart(car_fig, use_container_width=True)
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
                        plot_chart(bike_fig, use_container_width=True)
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
                        plot_chart(car_fig, use_container_width=True)

