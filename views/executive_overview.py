"""Executive Overview page."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from charts.plotly_charts import plot_chart, SEVERITY_COLORS
from styles.theme import COLORS
from views.constants import HARM_INDEX_CAPTION

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
        exposure_fig.update_traces(line_color=COLORS["accent"])
        exposure_fig.update_layout(
            xaxis_title="", yaxis_title="Collisions",
            margin=dict(t=40, b=30, l=50, r=20), showlegend=False,
        )
        exposure_fig.update_traces(hovertemplate="%{x|%b %Y}<br>Collisions = %{y}<extra></extra>")
        _add_covid_vline(exposure_fig)
        plot_chart(exposure_fig, use_container_width=True)

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
                color_discrete_map={
                    "Fatalities": SEVERITY_COLORS["Fatal"],
                    "Serious injuries": SEVERITY_COLORS["Serious"],
                },
            )
            harm_fig.update_layout(
                xaxis_title="", yaxis_title="Count",
                margin=dict(t=40, b=30, l=50, r=20),
                legend_title="",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            harm_fig.update_traces(hovertemplate="%{x|%b %Y}<br>%{fullData.name} = %{y}<extra></extra>")
            _add_covid_vline(harm_fig)
            plot_chart(harm_fig, use_container_width=True)
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
    st.caption(HARM_INDEX_CAPTION)
    st.dataframe(top_risk.reset_index(drop=True), use_container_width=True)

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
        st.dataframe(
            alerts_display[["District", "Collisions (focus mo)", "Prior 3‑mo avg", "Change vs baseline"]].reset_index(drop=True),
            use_container_width=True,
        )
    elif len(months) >= 7 and len(baseline_months) == 0:
        st.info("Not enough historical data to compute month-over-baseline comparison.")
    else:
        st.info("Need at least 7 months of data for the month-versus-baseline comparison.")
