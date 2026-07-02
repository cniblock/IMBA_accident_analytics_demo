"""Casualty Intelligence page."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_loading import add_district_labels as _add_district_labels
from transforms import (
    REQUIRED_CASUALTY_VIEW_COLUMNS,
    casualty_priority_reason,
    casualty_priority_score,
    ensure_label_columns as _ensure_label_columns,
    safe_ratio as _safe_ratio,
    series_or_default as _series_or_default,
    validate_schema as _validate_schema,
)
from views.constants import PRIORITY_QUEUE_CAPTION
from charts.plotly_charts import plot_chart
from styles.dataframe import render_dataframe

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
    plot_chart(age_band_fig, use_container_width=True)

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
        plot_chart(sex_fig, use_container_width=True)
        render_dataframe(
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
    plot_chart(trends_fig, use_container_width=True)

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
        plot_chart(imd_fig, use_container_width=True)

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
    render_dataframe(
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
        title="Reporting mode summary",
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
        render_dataframe(
            ped_rank.sort_values("pedestrian_ksi", ascending=False).head(12).rename(
                columns={
                    "district_display": "District",
                    "pedestrian_casualties": "Pedestrian Casualties",
                    "pedestrian_ksi": "Pedestrian KSI",
                    "pedestrian_ksi_rate_pct": "Pedestrian KSI Rate (%)",
                }
            ),
            use_container_width=True,
            title="Top districts — pedestrian casualties",
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
    render_dataframe(
        district_harm.sort_values("harm_index", ascending=False).head(12).rename(
            columns={
                "district_display": "District",
                "fatal": "Fatal Casualties",
                "serious": "Serious Casualties",
                "harm_index": "Harm Index",
            }
        ),
        use_container_width=True,
        title="Top districts — harm index",
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
        plot_chart(hour_fig, use_container_width=True)

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
                plot_chart(cross_fig, use_container_width=True)

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
                plot_chart(infra_fig, use_container_width=True)

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
        plot_chart(ped_fig, use_container_width=True)

    st.markdown("### Priority Case Queue")
    st.caption(PRIORITY_QUEUE_CAPTION)
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
    render_dataframe(queue_display, use_container_width=True)
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
        render_dataframe(
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
        )
        overall_linked = _safe_ratio(pd.Series([coverage["linked"].sum()]), pd.Series([coverage["linkable"].sum()])).iloc[0] * 100
        st.caption(f"Vehicle-context linkage coverage among linkable casualties: {overall_linked:.1f}%")

