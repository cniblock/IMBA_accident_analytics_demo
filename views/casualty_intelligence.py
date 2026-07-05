"""Casualty Intelligence page."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from charts.plotly_charts import plot_chart
from data_loading import add_district_labels as _add_district_labels, district_name_only
from styles.dataframe import render_dataframe
from styles.metrics import render_metric, render_text_metric
from styles.theme import COLORS
from transforms import (
    REQUIRED_CASUALTY_VIEW_COLUMNS,
    casualty_priority_reason,
    casualty_priority_score,
    ensure_label_columns as _ensure_label_columns,
    safe_ratio as _safe_ratio,
    series_or_default as _series_or_default,
    validate_schema as _validate_schema,
)
from views.constants import (
    CASUALTY_RECORD_CONTEXT,
    CROSSING_FACILITY_CAVEAT,
    DEPRIVATION_CAVEAT,
    DISTRICT_CASUALTY_CAVEAT,
    HEATMAP_MIN_N_NOTE,
    HOURLY_KSI_CAVEAT,
    KSI_SHARE_DEFINITION,
    KSI_SHARE_LABEL,
    LINKAGE_PEDESTRIAN_NOTE,
    MISSING_AGE_NOTE,
    PRIORITY_QUEUE_CAPTION,
    REPORTING_MODE_DEFINITION,
)

VOLUME_COLOR = COLORS["accent"]
RATE_COLOR = "#E07A5F"
DATA_MISSING = "Data missing or out of range"
MIN_DEN = 30

CASUALTY_PRESETS = [
    "All casualties",
    "Vulnerable road users",
    "Pedestrians",
    "Cyclists",
    "Motorcyclists",
    "Under 16",
    "75+",
]

AGE_ORDER = [
    "0-5", "6-10", "11-15", "16-20", "21-25", "26-35",
    "36-45", "46-55", "56-65", "66-75", "Over 75", "Missing",
]
AGE_ORDER_CLEAN = [x for x in AGE_ORDER if x != "Missing"]

IMD_ORDER = [
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

CROSSING_SHORT_LABELS = {
    "Pedestrian light controlled crossing": "Light crossing",
    "Central refuge / traffic island": "Central refuge",
    "Traffic signal phase": "Traffic signal phase",
    "Footbridge or subway": "Footbridge/subway",
    "No crossing facility within 50 metres": "No facility within 50m",
    "Zebra crossing": "Zebra crossing",
    "School crossing patrol warden": "School crossing",
    "Pedestrian crossing at junction": "Crossing at junction",
}


def _is_data_quality_label(value: object) -> bool:
    text = str(value).strip()
    if not text or text in {DATA_MISSING, "Unknown", "Missing", "Data missing"}:
        return True
    return text.lower().startswith("data missing") or text.lower() == "unknown"


def _short_crossing_label(label: str) -> str:
    return CROSSING_SHORT_LABELS.get(label, label[:28] + ("…" if len(label) > 28 else ""))


def _format_hour_24(hour: int) -> str:
    return f"{int(hour):02d}:00"


def _plot_horizontal_bar(
    frame: pd.DataFrame,
    label_col: str,
    value_col: str,
    title: str,
    color: str,
    value_label: str,
    *,
    top_n: int = 12,
    hover_cols: list[str] | None = None,
) -> None:
    plot_df = frame.sort_values(value_col, ascending=True).tail(top_n)
    fig = px.bar(
        plot_df,
        x=value_col,
        y=label_col,
        orientation="h",
        title=title,
        labels={label_col: "", value_col: value_label},
        hover_data=hover_cols or [],
    )
    fig.update_traces(marker_color=color, hovertemplate=f"%{{y}}<br>{value_label} = %{{x:.1f}}<extra></extra>")
    fig.update_layout(
        margin=dict(l=10, r=20, t=40, b=20),
        yaxis=dict(categoryorder="total ascending"),
        showlegend=False,
    )
    plot_chart(fig, use_container_width=True)


def _filter_by_preset(data: pd.DataFrame, preset: str) -> pd.DataFrame:
    if preset == "All casualties":
        return data
    if preset == "Pedestrians":
        return data[data["casualty_class"] == 3]
    if preset == "Cyclists":
        return data[data["casualty_type"] == 1]
    if preset == "Motorcyclists":
        mask = data["casualty_type_label"].astype(str).str.contains("Motorcycle|motorcycle", regex=True, na=False)
        return data[mask]
    if preset == "Vulnerable road users":
        mask = (
            (data["casualty_class"] == 3)
            | (data["casualty_type"] == 1)
            | data["casualty_type_label"].astype(str).str.contains("Motorcycle|motorcycle|Horse|Mobility", regex=True, na=False)
        )
        return data[mask]
    if preset == "Under 16":
        return data[data["age_of_casualty"] <= 16]
    if preset == "75+":
        return data[data["age_of_casualty"] >= 75]
    return data


def _build_casualty_insights(data: pd.DataFrame) -> tuple[str, str, str]:
    top_type = data.groupby("casualty_type_label")["ksi_flag"].mean().sort_values(ascending=False).head(1)
    peak_hour = data.groupby("hour")["ksi_flag"].mean().sort_values(ascending=False).head(1)
    top_district = (
        data.assign(harm=np.where(data["fatal_flag"] == 1, 5, np.where(data["serious_flag"] == 1, 2, 0)))
        .groupby("district_display")["harm"]
        .sum()
        .sort_values(ascending=False)
        .head(1)
    )

    group_insight = "N/A"
    if not top_type.empty:
        group_insight = f"**{top_type.index[0]}** — {top_type.iloc[0] * 100:.1f}%"

    hour_insight = "N/A"
    if not peak_hour.empty:
        hour_insight = f"**{_format_hour_24(int(peak_hour.index[0]))}** — {peak_hour.iloc[0] * 100:.1f}%"

    district_insight = "N/A"
    district_full = "N/A"
    if not top_district.empty:
        district_full = str(top_district.index[0])
        district_insight = district_name_only(district_full)

    return group_insight, hour_insight, district_insight, district_full


def _add_ksi_flags(data: pd.DataFrame, ksi_definition: str) -> tuple[pd.DataFrame, str, str, str, str]:
    if ksi_definition == "Adjusted severity estimate" and "casualty_adjusted_severity_serious" in data.columns:
        data = data.copy()
        data["fatal_flag"] = (_series_or_default(data, "casualty_severity", 3) == 1).astype(float)
        data["serious_flag"] = _series_or_default(data, "casualty_adjusted_severity_serious", 0).clip(lower=0, upper=1)
        data["slight_flag"] = _series_or_default(data, "casualty_adjusted_severity_slight", 0).clip(lower=0, upper=1)
        data["ksi_flag"] = (data["fatal_flag"] + data["serious_flag"]).clip(upper=1)
        return (
            data,
            "Fatal",
            "Estimated Serious",
            "Estimated Slight",
            "Adjusted mode uses weighted serious/slight estimates from the STATS19 adjusted severity fields.",
        )
    data = data.copy()
    severity = _series_or_default(data, "casualty_severity", 3)
    data["fatal_flag"] = (severity == 1).astype(float)
    data["serious_flag"] = (severity == 2).astype(float)
    data["slight_flag"] = (severity == 3).astype(float)
    data["ksi_flag"] = (data["fatal_flag"] + data["serious_flag"]).clip(upper=1)
    return (
        data,
        "Fatal",
        "Serious",
        "Slight",
        "Reported mode uses the original STATS19 casualty severity codes.",
    )


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

    base_data = casualty_person_view.copy()
    base_data = _ensure_label_columns(
        base_data,
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
    if "district_display" not in base_data.columns:
        base_data = _add_district_labels(base_data)

    st.markdown(CASUALTY_RECORD_CONTEXT)

    preset = st.radio("Casualty view", CASUALTY_PRESETS, horizontal=True, index=0)
    ksi_definition = "Reported severity"

    data = _filter_by_preset(base_data.copy(), preset)

    if data.empty:
        st.info("No casualty records left after casualty filters.")
        return

    data, fatal_metric_label, serious_metric_label, slight_metric_label, rate_caption = _add_ksi_flags(
        data, ksi_definition
    )
    data["priority_score"] = casualty_priority_score(data)
    data["priority_reason"] = casualty_priority_reason(data)

    st.markdown("### Casualty snapshot")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_metric("Casualties", f"{len(data):,}")
    with c2:
        render_metric(fatal_metric_label, f"{int(data['fatal_flag'].sum()):,}")
    with c3:
        render_metric(
            serious_metric_label,
            f"{data['serious_flag'].sum():,.1f}" if ksi_definition == "Adjusted severity estimate" else f"{int(data['serious_flag'].sum()):,}",
        )
    with c4:
        render_metric(
            slight_metric_label,
            f"{data['slight_flag'].sum():,.1f}" if ksi_definition == "Adjusted severity estimate" else f"{int(data['slight_flag'].sum()):,}",
        )
    with c5:
        render_metric(KSI_SHARE_LABEL, f"{data['ksi_flag'].mean() * 100:.1f}%")
    st.caption(f"{rate_caption} {KSI_SHARE_DEFINITION}")

    extra1, extra2, extra3, extra4, extra5 = st.columns(5)
    with extra1:
        render_metric("Pedestrian KSI share", f"{(data[data['casualty_class'] == 3]['ksi_flag'].mean() * 100):.1f}%" if (data["casualty_class"] == 3).any() else "N/A")
    with extra2:
        render_metric("Cyclist KSI share", f"{(data[data['casualty_type'] == 1]['ksi_flag'].mean() * 100):.1f}%" if (data["casualty_type"] == 1).any() else "N/A")
    with extra3:
        render_metric("Under-16 KSI share", f"{(data[data['age_of_casualty'] <= 16]['ksi_flag'].mean() * 100):.1f}%" if (data["age_of_casualty"] <= 16).any() else "N/A")
    with extra4:
        render_metric("75+ KSI share", f"{(data[data['age_of_casualty'] >= 75]['ksi_flag'].mean() * 100):.1f}%" if (data["age_of_casualty"] >= 75).any() else "N/A")
    with extra5:
        render_metric("% casualties in darkness", f"{(data['is_dark'].mean() * 100):.1f}%")

    group_insight, hour_insight, district_insight, district_full = _build_casualty_insights(data)
    st.markdown("#### Insight summary")
    i1, i2, i3 = st.columns(3)
    with i1:
        render_text_metric("Highest KSI group", group_insight.replace("**", ""))
    with i2:
        render_text_metric("Peak KSI hour", hour_insight.replace("**", ""))
    with i3:
        render_text_metric(
            "Highest harm district",
            district_insight,
            title=district_full,
        )

    if "age_band_of_casualty_label" in data.columns:
        data["age_band_of_casualty_label"] = pd.Categorical(
            data["age_band_of_casualty_label"], categories=AGE_ORDER, ordered=True
        )

    with st.expander("Demographics and severity", expanded=True):
        missing_age_n = int((data["age_band_of_casualty_label"] == "Missing").sum()) if "age_band_of_casualty_label" in data.columns else 0
        age_band = (
            data.groupby("age_band_of_casualty_label", dropna=False)
            .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
            .reset_index()
        )
        age_band = age_band[
            (age_band["casualties"] >= MIN_DEN)
            & (age_band["age_band_of_casualty_label"] != "Missing")
        ].copy()
        age_band["ksi_share_pct"] = _safe_ratio(age_band["ksi"], age_band["casualties"]) * 100
        age_band_fig = px.bar(
            age_band,
            x="age_band_of_casualty_label",
            y="ksi_share_pct",
            hover_data=["casualties", "ksi"],
            title=f"KSI share by casualty age band (%) (n ≥ {MIN_DEN})",
            labels={
                "age_band_of_casualty_label": "Age band",
                "ksi_share_pct": KSI_SHARE_LABEL,
                "casualties": "Casualties",
                "ksi": "KSI",
            },
        )
        age_band_fig.update_traces(
            hovertemplate=(
                "Age band = %{x}<br>"
                f"{KSI_SHARE_LABEL} = %{{y:.1f}}<br>"
                "Casualties = %{customdata[0]}<br>"
                "KSI = %{customdata[1]}<extra></extra>"
            )
        )
        plot_chart(age_band_fig, use_container_width=True)
        if missing_age_n:
            st.caption(f"{MISSING_AGE_NOTE} ({missing_age_n:,} records with missing age in current filter).")

        st.markdown("#### Age and sex")
        age_sex = (
            data.groupby(["sex_of_casualty_label", "age_band_of_casualty_label"], dropna=False)
            .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
            .reset_index()
        )
        age_sex = age_sex[
            (age_sex["age_band_of_casualty_label"] != "Missing")
            & (~age_sex["sex_of_casualty_label"].astype(str).apply(_is_data_quality_label))
        ].copy()
        age_sex = age_sex[age_sex["casualties"] >= MIN_DEN].copy()
        age_sex["ksi_share_pct"] = _safe_ratio(age_sex["ksi"], age_sex["casualties"]) * 100
        if not age_sex.empty:
            sex_order = ["Male", "Female"]
            age_sex["age_band_of_casualty_label"] = pd.Categorical(
                age_sex["age_band_of_casualty_label"], categories=AGE_ORDER_CLEAN, ordered=True
            )
            age_sex["sex_of_casualty_label"] = pd.Categorical(
                age_sex["sex_of_casualty_label"], categories=sex_order, ordered=True
            )
            age_sex = age_sex.sort_values(["sex_of_casualty_label", "age_band_of_casualty_label"])
            sex_fig = px.density_heatmap(
                age_sex,
                x="age_band_of_casualty_label",
                y="sex_of_casualty_label",
                z="ksi_share_pct",
                histfunc="avg",
                category_orders={
                    "age_band_of_casualty_label": AGE_ORDER_CLEAN,
                    "sex_of_casualty_label": sex_order,
                },
                title=f"KSI share by age band and sex (%) (n ≥ {MIN_DEN})",
                color_continuous_scale="Oranges",
                labels={
                    "age_band_of_casualty_label": "Age band",
                    "sex_of_casualty_label": "Sex",
                    "ksi_share_pct": KSI_SHARE_LABEL,
                },
            )
            sex_fig.update_traces(
                hovertemplate=f"Age band = %{{x}}<br>Sex = %{{y}}<br>{KSI_SHARE_LABEL} = %{{z:.1f}}<extra></extra>"
            )
            plot_chart(sex_fig, use_container_width=True)
            st.caption(
                f"Unknown/missing sex excluded. {HEATMAP_MIN_N_NOTE}"
            )
            render_dataframe(
                age_sex.sort_values("ksi_share_pct", ascending=False).head(12).rename(
                    columns={
                        "sex_of_casualty_label": "Sex",
                        "age_band_of_casualty_label": "Age band",
                        "casualties": "Casualties",
                        "ksi": "KSI",
                        "ksi_share_pct": KSI_SHARE_LABEL,
                    }
                ),
                use_container_width=True,
            )

        if not casualty_linked_view.empty:
            linked_cols = [
                c for c in ["collision_index", "casualty_reference", "generic_make_model", "link_status"]
                if c in casualty_linked_view.columns
            ]
            linked_subset = casualty_linked_view[linked_cols].drop_duplicates().copy()
            profile = data[
                ["collision_index", "casualty_reference", "sex_of_casualty_label", "age_band_of_casualty_label", "ksi_flag"]
            ].merge(linked_subset, on=["collision_index", "casualty_reference"], how="left")
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
                    adverse_linked["ksi_share_pct"] = _safe_ratio(adverse_linked["ksi"], adverse_linked["casualties"]) * 100
                    top_linked = adverse_linked.sort_values(["ksi_share_pct", "casualties"], ascending=[False, False]).head(1).iloc[0]
                    st.caption(
                        f"Most adverse linked profile (n ≥ {min_den_linked}): "
                        f"**{top_linked['sex_of_casualty_label']}** + **{top_linked['age_band_of_casualty_label']}** "
                        f"in **{top_linked['generic_make_model']}** — {top_linked['ksi_share_pct']:.1f}% KSI share "
                        f"({int(top_linked['ksi'])}/{int(top_linked['casualties'])})."
                    )

    with st.expander("Casualty type trends", expanded=True):
        trend_view = st.radio(
            "Trend view",
            ["Stacked counts", "Indexed trend (first month = 100)"],
            horizontal=True,
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

        trends_fig: go.Figure | None = None
        if trend_view == "Stacked counts":
            trends_fig = px.area(
                trends,
                x="month",
                y="casualties",
                color="casualty_type_label",
                title="Monthly casualties by type",
                labels={"month": "Month", "casualties": "Casualties", "casualty_type_label": "Casualty type"},
            )
            trends_fig.update_traces(
                hovertemplate="Type = %{fullData.name}<br>Month = %{x|%Y-%m-%d}<br>Casualties = %{y}<extra></extra>"
            )
        else:
            pivot = trends.pivot(index="month", columns="casualty_type_label", values="casualties").fillna(0)
            if pivot.empty:
                st.info("Not enough monthly data for indexed trend.")
            else:
                base = pivot.iloc[0].replace(0, np.nan)
                indexed = pivot.div(base) * 100
                indexed_long = indexed.reset_index().melt(
                    id_vars="month", var_name="casualty_type_label", value_name="index_value"
                )
                trends_fig = px.line(
                    indexed_long,
                    x="month",
                    y="index_value",
                    color="casualty_type_label",
                    title="Indexed casualty trend by type (first month = 100)",
                    labels={"month": "Month", "index_value": "Index", "casualty_type_label": "Casualty type"},
                )
                trends_fig.update_traces(
                    hovertemplate="Type = %{fullData.name}<br>Month = %{x|%Y-%m-%d}<br>Index = %{y:.1f}<extra></extra>"
                )

        if trends_fig is not None:
            trends_fig.add_vline(x=pd.Timestamp("2020-04-01"), line_dash="dot", line_color="rgba(120,120,120,0.5)")
            trends_fig.add_annotation(
                x=pd.Timestamp("2020-04-01"),
                y=1.05,
                yref="paper",
                text="COVID mobility restrictions",
                showarrow=False,
                font=dict(size=10, color="rgba(120,120,120,0.9)"),
            )
            trends_fig.update_layout(
                legend=dict(
                    orientation="v",
                    yanchor="top",
                    y=1,
                    x=1.02,
                    xanchor="left",
                    title_text="Casualty type",
                ),
                margin=dict(t=60, r=175, l=10, b=40),
            )
            plot_chart(trends_fig, use_container_width=True)

        vrus = data[data["casualty_type_label"].isin(["Pedestrian", "Cyclist"])].copy()
        if not vrus.empty:
            st.markdown("#### Vulnerable user KSI by hour")
            hour_profile = (
                vrus.groupby("hour", dropna=False)
                .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
                .reset_index()
                .sort_values("hour")
            )
            hour_profile["ksi_share_pct"] = _safe_ratio(hour_profile["ksi"], hour_profile["casualties"]) * 100
            hour_fig = go.Figure()
            hour_fig.add_trace(
                go.Bar(
                    x=hour_profile["hour"],
                    y=hour_profile["casualties"],
                    name="Casualty volume",
                    marker_color=VOLUME_COLOR,
                    opacity=0.45,
                    yaxis="y",
                )
            )
            hour_fig.add_trace(
                go.Scatter(
                    x=hour_profile["hour"],
                    y=hour_profile["ksi_share_pct"],
                    name=KSI_SHARE_LABEL,
                    mode="lines+markers",
                    line=dict(color=RATE_COLOR, width=2),
                    yaxis="y2",
                    customdata=hour_profile[["casualties", "ksi"]].to_numpy(),
                    hovertemplate=(
                        "Hour = %{x}<br>"
                        f"{KSI_SHARE_LABEL} = %{{y:.1f}}<br>"
                        "Casualties = %{customdata[0]}<br>"
                        "KSI = %{customdata[1]}<extra></extra>"
                    ),
                )
            )
            hour_fig.update_layout(
                title="Vulnerable user casualties and KSI share by hour",
                xaxis=dict(title="Hour of day", dtick=1),
                yaxis=dict(title="Casualties", side="left"),
                yaxis2=dict(title=KSI_SHARE_LABEL, overlaying="y", side="right", range=[0, max(5, hour_profile["ksi_share_pct"].max() * 1.15)]),
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.22,
                    x=0.5,
                    xanchor="center",
                ),
                margin=dict(t=60, b=90, l=10, r=10),
            )
            plot_chart(hour_fig, use_container_width=True)
            st.caption(HOURLY_KSI_CAVEAT)

    with st.expander("Deprivation and geography", expanded=False):
        if "casualty_imd_decile_label" in data.columns:
            data["casualty_imd_decile_label"] = pd.Categorical(
                data["casualty_imd_decile_label"], categories=IMD_ORDER, ordered=True
            )
        imd = (
            data.groupby("casualty_imd_decile_label", dropna=False)
            .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
            .reset_index()
        )
        imd = imd[
            (imd["casualties"] >= MIN_DEN)
            & (~imd["casualty_imd_decile_label"].astype(str).apply(_is_data_quality_label))
        ].copy()
        if not imd.empty:
            imd["ksi_share_pct"] = _safe_ratio(imd["ksi"], imd["casualties"]) * 100
            imd_fig = px.bar(
                imd,
                x="casualty_imd_decile_label",
                y="ksi_share_pct",
                hover_data=["casualties", "ksi"],
                title=f"KSI share by deprivation decile (%) (n ≥ {MIN_DEN})",
                labels={
                    "casualty_imd_decile_label": "Deprivation decile",
                    "ksi_share_pct": KSI_SHARE_LABEL,
                    "casualties": "Casualties",
                    "ksi": "KSI",
                },
            )
            imd_fig.update_traces(
                hovertemplate=(
                    "Decile = %{x}<br>"
                    f"{KSI_SHARE_LABEL} = %{{y:.1f}}<br>"
                    "Casualties = %{customdata[0]}<br>"
                    "KSI = %{customdata[1]}<extra></extra>"
                )
            )
            plot_chart(imd_fig, use_container_width=True)
            st.caption(DEPRIVATION_CAVEAT)

        st.caption(DISTRICT_CASUALTY_CAVEAT)
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
            ped_rank["pedestrian_ksi_share_pct"] = _safe_ratio(ped_rank["pedestrian_ksi"], ped_rank["pedestrian_casualties"]) * 100
            render_dataframe(
                ped_rank.sort_values("pedestrian_ksi", ascending=False).head(12).rename(
                    columns={
                        "district_display": "District",
                        "pedestrian_casualties": "Pedestrian casualties",
                        "pedestrian_ksi": "Pedestrian KSI",
                        "pedestrian_ksi_share_pct": f"Pedestrian {KSI_SHARE_LABEL}",
                    }
                ),
                use_container_width=True,
                title="Top districts — pedestrian casualties",
            )

        district_harm = (
            data.groupby("district_display", dropna=False)
            .agg(fatal=("fatal_flag", "sum"), serious=("serious_flag", "sum"))
            .reset_index()
        )
        district_harm["harm_index"] = district_harm["serious"] * 2 + district_harm["fatal"] * 5
        render_dataframe(
            district_harm.sort_values("harm_index", ascending=False).head(12).rename(
                columns={
                    "district_display": "District",
                    "fatal": "Fatal casualties",
                    "serious": "Serious casualties",
                    "harm_index": "Harm index",
                }
            ),
            use_container_width=True,
            title="Top districts — harm index",
        )

    with st.expander("Pedestrian infrastructure lens", expanded=False):
        st.caption(CROSSING_FACILITY_CAVEAT)
        if "pedestrian_crossing_label" in data.columns:
            ped_infra = data[data["casualty_class"] == 3].copy()
            if not ped_infra.empty:
                cross = (
                    ped_infra.groupby("pedestrian_crossing_label", dropna=False)
                    .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
                    .reset_index()
                )
                cross = cross[
                    (cross["casualties"] >= MIN_DEN)
                    & (~cross["pedestrian_crossing_label"].astype(str).apply(_is_data_quality_label))
                ].copy()
                if not cross.empty:
                    cross["ksi_share_pct"] = _safe_ratio(cross["ksi"], cross["casualties"]) * 100
                    cross["crossing_short"] = cross["pedestrian_crossing_label"].astype(str).map(_short_crossing_label)
                    cross = cross.sort_values("casualties", ascending=False).head(8)
                    _plot_horizontal_bar(
                        cross,
                        "crossing_short",
                        "ksi_share_pct",
                        f"Pedestrian KSI share by crossing facility (%) (n ≥ {MIN_DEN}, top 8 by volume)",
                        RATE_COLOR,
                        KSI_SHARE_LABEL,
                        top_n=8,
                        hover_cols=["pedestrian_crossing_label", "casualties", "ksi"],
                    )

                cross_night = (
                    ped_infra.groupby(["pedestrian_crossing_label", "is_dark"], dropna=False)
                    .agg(casualties=("casualty_reference", "count"), ksi=("ksi_flag", "sum"))
                    .reset_index()
                )
                cross_night = cross_night[
                    (cross_night["casualties"] >= MIN_DEN)
                    & (~cross_night["pedestrian_crossing_label"].astype(str).apply(_is_data_quality_label))
                ].copy()
                if not cross_night.empty:
                    cross_night["ksi_share_pct"] = _safe_ratio(cross_night["ksi"], cross_night["casualties"]) * 100
                    cross_night["light_period"] = cross_night["is_dark"].map({0: "Daylight", 1: "Darkness"}).fillna("Unknown")
                    cross_night["crossing_short"] = cross_night["pedestrian_crossing_label"].astype(str).map(_short_crossing_label)
                    top_crossings = (
                        cross_night.groupby("pedestrian_crossing_label")["casualties"]
                        .sum()
                        .sort_values(ascending=False)
                        .head(6)
                        .index
                    )
                    cross_night = cross_night[cross_night["pedestrian_crossing_label"].isin(top_crossings)].copy()
                    cross_night = cross_night.sort_values("ksi_share_pct", ascending=True)
                    infra_fig = px.bar(
                        cross_night,
                        x="ksi_share_pct",
                        y="crossing_short",
                        color="light_period",
                        orientation="h",
                        barmode="group",
                        title=f"Pedestrian KSI share by crossing and light period (%) (n ≥ {MIN_DEN})",
                        labels={
                            "crossing_short": "Crossing facility",
                            "ksi_share_pct": KSI_SHARE_LABEL,
                            "light_period": "Light period",
                        },
                        category_orders={"light_period": ["Daylight", "Darkness"]},
                    )
                    infra_fig.update_layout(
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1, xanchor="right"),
                        margin=dict(l=10, r=20, t=60, b=20),
                        yaxis=dict(categoryorder="category ascending"),
                    )
                    plot_chart(infra_fig, use_container_width=True)

        ped_base = data.loc[data["casualty_class"] == 3].copy()
        if not ped_base.empty:
            sankey_scope = st.selectbox(
                "Pedestrian flow scope",
                ["All pedestrians", "KSI only", "Darkness only", "Under 16", "75+"],
            )
            min_flow = st.selectbox("Minimum flow (casualty records)", [5, 10, 20, 50], index=1)
            ped_flow = ped_base.copy()
            if sankey_scope == "KSI only":
                ped_flow = ped_flow[ped_flow["ksi_flag"] == 1]
            elif sankey_scope == "Darkness only":
                ped_flow = ped_flow[ped_flow["is_dark"] == 1]
            elif sankey_scope == "Under 16":
                ped_flow = ped_flow[ped_flow["age_of_casualty"] <= 16]
            elif sankey_scope == "75+":
                ped_flow = ped_flow[ped_flow["age_of_casualty"] >= 75]

            ped_flow = ped_flow[
                ["pedestrian_location_label", "pedestrian_movement_label", "casualty_severity_label"]
            ].dropna()
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
                p1 = p1[p1["value"] >= min_flow]
                p2 = p2[p2["value"] >= min_flow]
                if not p1.empty and not p2.empty:
                    labels = pd.Index(
                        pd.concat(
                            [
                                p1["pedestrian_location_label"],
                                p1["pedestrian_movement_label"],
                                p2["casualty_severity_label"],
                            ],
                            ignore_index=True,
                        ).unique()
                    )
                    node_map = {k: i for i, k in enumerate(labels)}
                    links_a = p1.assign(
                        source=lambda d: d["pedestrian_location_label"].map(node_map),
                        target=lambda d: d["pedestrian_movement_label"].map(node_map),
                        color="rgba(120,120,120,0.25)",
                    )
                    links_b = p2.assign(
                        source=lambda d: d["pedestrian_movement_label"].map(node_map),
                        target=lambda d: d["casualty_severity_label"].map(node_map),
                        color=lambda d: d["casualty_severity_label"].map(
                            {
                                "Fatal": "rgba(201,42,42,0.7)",
                                "Serious": "rgba(244,162,97,0.7)",
                                "Slight": "rgba(46,196,182,0.7)",
                            }
                        ).fillna("rgba(140,140,140,0.35)"),
                    )
                    links = pd.concat(
                        [links_a[["source", "target", "value", "color"]], links_b[["source", "target", "value", "color"]]],
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
                    ped_fig.update_layout(
                        title_text=f"Pedestrian flow: location → movement → severity ({sankey_scope.lower()})",
                        height=650,
                    )
                    plot_chart(ped_fig, use_container_width=True)
                    st.caption(
                        "Flow width represents casualty records; final link colour indicates severity. "
                        f"Low-volume flows below {min_flow} records are grouped or excluded."
                    )

    with st.expander("Data quality and priority review queue", expanded=False):
        st.caption(REPORTING_MODE_DEFINITION)
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
        report_summary["ksi_share_pct"] = _safe_ratio(report_summary["ksi"], report_summary["casualties"]) * 100
        report_summary = report_summary[
            ~report_summary[report_col].astype(str).apply(_is_data_quality_label)
        ].copy()
        render_dataframe(
            report_summary.rename(
                columns={
                    report_col: "Reporting mode",
                    "casualties": "Casualties",
                    "ksi": "KSI",
                    "ksi_share_pct": KSI_SHARE_LABEL,
                    "missing_age": "Missing age (%)",
                    "missing_sex": "Missing sex (%)",
                    "missing_imd": "Missing IMD (%)",
                }
            ),
            use_container_width=True,
            title="Reporting mode summary",
        )

        if not casualty_linked_view.empty and "link_status" in casualty_linked_view.columns:
            st.caption(LINKAGE_PEDESTRIAN_NOTE)
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
                        "casualty_class_label": "Casualty class",
                        "casualties": "Casualties",
                        "linkable": "Linkable to vehicle",
                        "linked": "Linked to vehicle",
                        "linked_of_linkable_pct": "Linked of linkable (%)",
                    }
                ),
                use_container_width=True,
                title="Vehicle linkage coverage by casualty class",
            )
            overall_linked = _safe_ratio(
                pd.Series([coverage["linked"].sum()]), pd.Series([coverage["linkable"].sum()])
            ).iloc[0] * 100
            st.caption(f"Vehicle-context linkage coverage among linkable casualties: {overall_linked:.1f}%")

        st.markdown("#### Priority review queue")
        st.caption(PRIORITY_QUEUE_CAPTION)
        st.caption("For analytical review only — not for identification of individuals.")
        queue = data.copy()
        queue["record_reference"] = queue["collision_index"].astype(str) + "-" + queue["casualty_reference"].astype(str)
        queue = queue.sort_values("priority_score", ascending=False)
        queue_display = queue[
            [
                "record_reference",
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
        ].head(200).copy()
        if "date" in queue_display.columns:
            queue_display["date"] = pd.to_datetime(queue_display["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        queue_display = queue_display.rename(
            columns={
                "record_reference": "Record reference",
                "date": "Date",
                "district_display": "District",
                "casualty_severity_label": "Severity",
                "casualty_class_label": "Class",
                "casualty_type_label": "Type",
                "age_of_casualty": "Age",
                "sex_of_casualty_label": "Sex",
                "casualty_distance_banding_label": "Distance band",
                "priority_reason": "Review reason",
                "priority_score": "Priority score",
            }
        )
        render_dataframe(queue_display, use_container_width=True)
        st.download_button(
            label="Download priority review queue (CSV)",
            data=queue_display.to_csv(index=False),
            file_name="priority_review_queue.csv",
            mime="text/csv",
        )
