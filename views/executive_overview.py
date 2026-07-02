"""Executive Overview page."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from charts.plotly_charts import plot_chart, SEVERITY_COLORS
from data_loading import district_name_only
from styles.dataframe import render_dataframe
from styles.metrics import render_text_metric
from styles.theme import COLORS
from views.constants import (
    HARM_INDEX_CAPTION,
    METRIC_UNITS_CAPTION,
    NIGHT_TIME_DEFINITION,
    UNADJUSTED_COUNTS_CAPTION,
)

DISTRICT_RANK_OPTIONS = {
    "Harm Index": "harm_index",
    "KSI casualties": "ksi",
    "Collision count": "collisions",
    "Fatal casualties": "fatal",
    "Serious casualties": "serious",
    "KSI per 1,000 collisions": "ksi_per_1k",
}

HARM_MONTHLY_CHART_HEIGHT = 280
# Left exposure chart spans the same vertical space as two stacked harm charts + Streamlit gap.
EXPOSURE_MONTHLY_CHART_HEIGHT = HARM_MONTHLY_CHART_HEIGHT * 2 + 32


def _pct_change(current: float, prior: float) -> float | None:
    if prior == 0:
        return None if current == 0 else 100.0
    return (current - prior) / prior * 100.0


def _split_recent_periods(df: pd.DataFrame, months: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Last N months vs the prior N months (by max date in df)."""
    dated = df.dropna(subset=["date"]).copy()
    if dated.empty:
        return dated.iloc[0:0], dated.iloc[0:0]
    max_date = dated["date"].max()
    current_start = max_date - pd.DateOffset(months=months)
    prior_start = current_start - pd.DateOffset(months=months)
    current = dated[(dated["date"] > current_start) & (dated["date"] <= max_date)]
    prior = dated[(dated["date"] > prior_start) & (dated["date"] <= current_start)]
    return current, prior


def _period_delta(
    df: pd.DataFrame,
    value_fn,
    months: int = 12,
    inverse: bool = True,
) -> dict:
    current, prior = _split_recent_periods(df, months=months)
    if current.empty or prior.empty:
        return {}
    pct = _pct_change(float(value_fn(current)), float(value_fn(prior)))
    if pct is None:
        return {}
    return {
        "delta": f"{pct:.1f}% vs prev 12 mo",
        "delta_color": "inverse" if inverse else "normal",
    }


def _sum_col(df: pd.DataFrame, col: str) -> float:
    return float(df[col].sum()) if col in df.columns else 0.0


def _collision_count(df: pd.DataFrame) -> float:
    return float(len(df))


def _ksi_sum(df: pd.DataFrame) -> float:
    fatal = _sum_col(df, "fatal_casualties")
    serious = _sum_col(df, "serious_casualties")
    return fatal + serious


def _ksi_rate_per_1k(df: pd.DataFrame) -> float:
    n = len(df)
    if n == 0:
        return 0.0
    return _ksi_sum(df) / n * 1000.0


def _dark_share_pct(df: pd.DataFrame) -> float:
    if len(df) == 0 or "is_dark" not in df.columns:
        return 0.0
    return float(df["is_dark"].mean() * 100)


def _add_covid_vline(fig: go.Figure, monthly: pd.DataFrame) -> None:
    covid_ts = pd.Timestamp("2020-04-01")
    if len(monthly) == 0 or not (monthly["date"].min() <= covid_ts <= monthly["date"].max()):
        return
    fig.add_vline(
        x=covid_ts.timestamp() * 1000,
        line_dash="dot",
        line_width=1,
        line_color="rgba(148, 163, 184, 0.55)",
        annotation_text="Apr 2020",
        annotation_font_size=9,
        annotation_font_color="rgba(148, 163, 184, 0.9)",
        annotation_position="top right",
    )


def _build_district_risk_table(collision_view: pd.DataFrame) -> pd.DataFrame:
    fatal_col = "fatal_casualties" if "fatal_casualties" in collision_view.columns else None
    risk_agg = {
        "collisions": ("collision_index", "count"),
        "serious": ("serious_casualties", "sum"),
        "slight": ("slight_casualties", "sum"),
    }
    if fatal_col:
        risk_agg["fatal"] = (fatal_col, "sum")
    risk = (
        collision_view.groupby("district_display", dropna=False)
        .agg(**risk_agg)
        .reset_index()
    )
    if "fatal" not in risk.columns:
        risk["fatal"] = 0
    risk["ksi"] = risk["fatal"] + risk["serious"]
    risk["harm_index"] = risk["fatal"] * 5 + risk["serious"] * 2 + risk["slight"]
    risk["ksi_per_1k"] = np.where(
        risk["collisions"] > 0,
        risk["ksi"] / risk["collisions"] * 1000.0,
        0.0,
    )
    force_col = (
        "police_force_label"
        if "police_force_label" in collision_view.columns
        else "police_force"
        if "police_force" in collision_view.columns
        else None
    )
    if force_col:
        district_force = (
            collision_view.groupby("district_display", dropna=False)[force_col]
            .agg(lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else "Unknown")
            .reset_index(name="police_force_display")
        )
        risk = risk.merge(district_force, on="district_display", how="left")
    else:
        risk["police_force_display"] = "Unknown"
    return risk


def _format_district_table(risk: pd.DataFrame) -> pd.DataFrame:
    out = risk.copy()
    for col in ["collisions", "fatal", "serious", "slight", "ksi", "harm_index"]:
        if col in out.columns:
            out[col] = np.rint(out[col]).astype("int64")
    if "ksi_per_1k" in out.columns:
        out["ksi_per_1k"] = out["ksi_per_1k"].round(1)
    return out.rename(
        columns={
            "district_display": "District",
            "police_force_display": "Police Force",
            "collisions": "Collision records",
            "fatal": "Fatal casualties",
            "serious": "Serious casualties",
            "slight": "Slight casualties",
            "ksi": "KSI casualties",
            "harm_index": "Harm Index",
            "ksi_per_1k": "KSI per 1,000 collisions",
        }
    )


def _build_collision_alerts(df: pd.DataFrame) -> tuple[pd.DataFrame | None, pd.Timestamp | None, list]:
    dated = df.dropna(subset=["date"]).copy()
    dated["month"] = dated["date"].dt.to_period("M").dt.to_timestamp()
    months = sorted(dated["month"].unique())
    if len(months) < 7:
        return None, None, months

    focus_month = months[-4]
    baseline_months = [m for m in months if m < focus_month][-3:]
    if not baseline_months:
        return None, focus_month, months

    focus_data = (
        dated[dated["month"] == focus_month]
        .groupby("district_display", dropna=False)
        .size()
        .reset_index(name="focus")
    )
    baseline_data = (
        dated[dated["month"].isin(baseline_months)]
        .groupby("district_display", dropna=False)
        .size()
        .reset_index(name="baseline_total")
    )
    baseline_data["baseline_avg"] = baseline_data["baseline_total"] / len(baseline_months)
    alerts = (
        focus_data.merge(baseline_data[["district_display", "baseline_avg"]], on="district_display", how="outer")
        .fillna(0)
        .assign(
            change=lambda d: d["focus"] - d["baseline_avg"],
            pct_change=lambda d: np.where(
                d["baseline_avg"] > 0,
                (d["focus"] - d["baseline_avg"]) / d["baseline_avg"] * 100.0,
                np.nan,
            ),
        )
    )
    return alerts, focus_month, months


def _build_ksi_alerts(df: pd.DataFrame) -> tuple[pd.DataFrame | None, pd.Timestamp | None]:
    dated = df.dropna(subset=["date"]).copy()
    if "fatal_casualties" not in dated.columns:
        return None, None
    dated["month"] = dated["date"].dt.to_period("M").dt.to_timestamp()
    dated["ksi"] = dated["fatal_casualties"].fillna(0) + dated["serious_casualties"].fillna(0)
    months = sorted(dated["month"].unique())
    if len(months) < 7:
        return None, None

    focus_month = months[-4]
    baseline_months = [m for m in months if m < focus_month][-3:]
    if not baseline_months:
        return None, focus_month

    focus_data = (
        dated[dated["month"] == focus_month]
        .groupby("district_display", dropna=False)["ksi"]
        .sum()
        .reset_index(name="focus")
    )
    baseline_data = (
        dated[dated["month"].isin(baseline_months)]
        .groupby("district_display", dropna=False)["ksi"]
        .sum()
        .reset_index(name="baseline_total")
    )
    baseline_data["baseline_avg"] = baseline_data["baseline_total"] / len(baseline_months)
    alerts = (
        focus_data.merge(baseline_data[["district_display", "baseline_avg"]], on="district_display", how="outer")
        .fillna(0)
        .assign(
            change=lambda d: d["focus"] - d["baseline_avg"],
            pct_change=lambda d: np.where(
                d["baseline_avg"] > 0,
                (d["focus"] - d["baseline_avg"]) / d["baseline_avg"] * 100.0,
                np.nan,
            ),
        )
    )
    return alerts, focus_month


def _attach_police_force(alerts: pd.DataFrame, collision_view: pd.DataFrame) -> pd.DataFrame:
    force_col = (
        "police_force_label"
        if "police_force_label" in collision_view.columns
        else "police_force"
        if "police_force" in collision_view.columns
        else None
    )
    if not force_col:
        return alerts.assign(police_force_display="Unknown")
    district_force = (
        collision_view.groupby("district_display", dropna=False)[force_col]
        .agg(lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else "Unknown")
        .reset_index(name="police_force_display")
    )
    return alerts.merge(district_force, on="district_display", how="left")


def _format_alerts_table(alerts: pd.DataFrame, focus_label: str) -> pd.DataFrame:
    out = alerts.sort_values("change", ascending=False).head(10).copy()
    out["Focus month"] = focus_label
    out["Prior 3-mo avg"] = out["baseline_avg"].round(1)
    out["Change vs baseline"] = out["change"].round(1)
    out["Change (%)"] = out["pct_change"].round(1)
    return out.rename(
        columns={
            "district_display": "District",
            "focus": "Focus month count",
            "police_force_display": "Police Force",
        }
    )


def page_executive_overview(
    collision_view: pd.DataFrame,
    operational_stats: dict | None = None,
) -> None:
    st.title("Executive Overview")
    st.caption(METRIC_UNITS_CAPTION)

    total_collisions = len(collision_view)
    fatal = int(_sum_col(collision_view, "fatal_casualties"))
    serious = int(_sum_col(collision_view, "serious_casualties"))
    ksi = fatal + serious
    ksi_rate = _ksi_rate_per_1k(collision_view)
    dark_pct = _dark_share_pct(collision_view)

    risk_by_district = _build_district_risk_table(collision_view)
    top_district_name = (
        risk_by_district.sort_values("harm_index", ascending=False).iloc[0]["district_display"]
        if len(risk_by_district)
        else "–"
    )
    top_district_short = district_name_only(top_district_name) if top_district_name != "–" else "–"

    alerts_full, focus_month, months = _build_collision_alerts(collision_view)
    ksi_alerts_full, ksi_focus_month = _build_ksi_alerts(collision_view)
    districts_worsening_count = (
        int((alerts_full["change"] > 0).sum()) if alerts_full is not None else 0
    )

    weekly = (
        collision_view.dropna(subset=["date"])
        .assign(week=lambda d: d["date"].dt.to_period("W").dt.start_time)
        .groupby("week", dropna=False)
        .size()
        .reset_index(name="collisions")
        .sort_values("week")
    )
    cases_this_week = int(weekly.iloc[-1]["collisions"]) if len(weekly) else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric(
        "Collision records",
        f"{total_collisions:,}",
        help="STATS19 collision events in the current filter selection.",
        **_period_delta(collision_view, _collision_count),
    )
    col2.metric(
        "KSI casualties",
        f"{ksi:,}",
        help="Killed or seriously injured people (fatal + serious casualties).",
        **_period_delta(collision_view, _ksi_sum),
    )
    col3.metric(
        "Fatal casualties",
        f"{fatal:,}",
        help="People killed across all collisions in the current filter selection.",
        **_period_delta(collision_view, lambda d: _sum_col(d, "fatal_casualties")),
    )
    col4.metric(
        "KSI rate per 1,000 collisions",
        f"{ksi_rate:.1f}",
        help="KSI casualties divided by collision records, scaled per 1,000 events.",
        **_period_delta(collision_view, _ksi_rate_per_1k),
    )
    col5.metric(
        "Night-time collision share",
        f"{dark_pct:.1f}%",
        help=NIGHT_TIME_DEFINITION,
        **_period_delta(collision_view, _dark_share_pct, inverse=False),
    )

    st.caption("KPI deltas compare the **last 12 months** to the **prior 12 months** (by latest date in view).")

    os1, os2, os3, os4, os5 = st.columns(5)
    os1.metric("Collisions in latest week", f"{cases_this_week:,}")
    os2.metric("Districts with worsening trend", districts_worsening_count)
    with os3:
        render_text_metric(
            "Highest-risk district",
            top_district_short,
            help_text="Top district by Harm Index in the current filters.",
            title=str(top_district_name),
        )
    if operational_stats is not None:
        os4.metric("Last data refresh", operational_stats.get("max_date_str", "–"))
        os5.metric("Records ingested this cycle", f"{operational_stats.get('total_records', 0):,}")
    else:
        os4.metric("Last data refresh", "–")
        os5.metric("Records ingested this cycle", "–")

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

    tc1, tc2 = st.columns(2)
    with tc1:
        exposure_fig = px.line(monthly, x="date", y="collisions", title="Collision records per month (Exposure)")
        exposure_fig.update_traces(line_color=COLORS["accent"])
        exposure_fig.update_layout(
            xaxis_title="",
            yaxis_title="Collision records",
            margin=dict(t=40, b=30, l=50, r=20),
            showlegend=False,
            height=EXPOSURE_MONTHLY_CHART_HEIGHT,
        )
        exposure_fig.update_traces(hovertemplate="%{x|%b %Y}<br>Collision records = %{y}<extra></extra>")
        _add_covid_vline(exposure_fig, monthly)
        plot_chart(exposure_fig, use_container_width=True)

    with tc2:
        if "fatalities" in monthly.columns:
            fatal_fig = px.line(
                monthly,
                x="date",
                y="fatalities",
                title="Fatal casualties per month",
            )
            fatal_fig.update_traces(line_color=SEVERITY_COLORS["Fatal"], hovertemplate="%{x|%b %Y}<br>Fatal = %{y}<extra></extra>")
            fatal_fig.update_layout(
                xaxis_title="",
                yaxis_title="Fatal casualties",
                margin=dict(t=40, b=10, l=50, r=20),
                showlegend=False,
                height=HARM_MONTHLY_CHART_HEIGHT,
            )
            _add_covid_vline(fatal_fig, monthly)
            plot_chart(fatal_fig, use_container_width=True)

            serious_fig = px.line(
                monthly,
                x="date",
                y="serious",
                title="Serious casualties per month",
            )
            serious_fig.update_traces(
                line_color=SEVERITY_COLORS["Serious"],
                hovertemplate="%{x|%b %Y}<br>Serious = %{y}<extra></extra>",
            )
            serious_fig.update_layout(
                xaxis_title="",
                yaxis_title="Serious casualties",
                margin=dict(t=10, b=30, l=50, r=20),
                showlegend=False,
                height=HARM_MONTHLY_CHART_HEIGHT,
            )
            _add_covid_vline(serious_fig, monthly)
            plot_chart(serious_fig, use_container_width=True)
        else:
            st.info("Harm metrics (fatal and serious casualties) not available in this dataset.")

    if monthly["date"].min() <= pd.Timestamp("2020-04-01") <= monthly["date"].max():
        st.caption(
            "Vertical marker: UK COVID mobility restrictions from **April 2020** — useful context, not a data breakpoint."
        )

    st.subheader("Top Risk Districts")
    rank_label = st.selectbox(
        "Rank districts by",
        list(DISTRICT_RANK_OPTIONS.keys()),
        index=0,
    )
    rank_col = DISTRICT_RANK_OPTIONS[rank_label]
    st.markdown(HARM_INDEX_CAPTION)
    st.caption(UNADJUSTED_COUNTS_CAPTION)

    rank_display_col = {
        "harm_index": "Harm Index",
        "ksi": "KSI casualties",
        "collisions": "Collision records",
        "fatal": "Fatal casualties",
        "serious": "Serious casualties",
        "ksi_per_1k": "KSI per 1,000 collisions",
    }[rank_col]
    top_risk = (
        _format_district_table(risk_by_district)
        .sort_values(rank_display_col, ascending=False)
        .head(10)
    )
    display_cols = [
        "District",
        "Collision records",
        "Fatal casualties",
        "Serious casualties",
        "KSI casualties",
        "KSI per 1,000 collisions",
        "Harm Index",
        "Police Force",
    ]
    render_dataframe(top_risk[[c for c in display_cols if c in top_risk.columns]], use_container_width=True)

    st.subheader("Operational Alerts")
    if alerts_full is not None and len(alerts_full) > 0:
        focus_label = focus_month.strftime("%b %Y")
        collision_alerts = _format_alerts_table(
            _attach_police_force(alerts_full, collision_view),
            focus_label,
        )
        st.markdown("**Collision volume increases**")
        st.caption(
            f"Districts with the largest rise in **collision records** in **{focus_label}** "
            f"vs their prior 3-month average (avoids incomplete recent months)."
        )
        render_dataframe(
            collision_alerts[
                [
                    "District",
                    "Focus month",
                    "Focus month count",
                    "Prior 3-mo avg",
                    "Change vs baseline",
                    "Change (%)",
                    "Police Force",
                ]
            ],
            use_container_width=True,
        )

        if ksi_alerts_full is not None and ksi_focus_month is not None:
            ksi_focus_label = ksi_focus_month.strftime("%b %Y")
            ksi_alerts = _format_alerts_table(
                _attach_police_force(ksi_alerts_full, collision_view),
                ksi_focus_label,
            )
            st.markdown("**KSI casualty increases**")
            st.caption(
                f"Districts with the largest rise in **KSI casualties** in **{ksi_focus_label}** "
                f"vs their prior 3-month average."
            )
            render_dataframe(
                ksi_alerts[
                    [
                        "District",
                        "Focus month",
                        "Focus month count",
                        "Prior 3-mo avg",
                        "Change vs baseline",
                        "Change (%)",
                        "Police Force",
                    ]
                ],
                use_container_width=True,
            )
    elif len(months) >= 7:
        st.info("Not enough historical data to compute month-over-baseline comparison.")
    else:
        st.info("Need at least 7 months of data for the month-versus-baseline comparison.")

    st.subheader("Report Export")
    st.caption("Generate downloads using the **current sidebar filters** and selections on this page.")
    exec_summary = pd.DataFrame(
        [
            {"Metric": "Collision records", "Value": total_collisions},
            {"Metric": "KSI casualties", "Value": ksi},
            {"Metric": "Fatal casualties", "Value": fatal},
            {"Metric": "Serious casualties", "Value": serious},
            {"Metric": "KSI rate per 1,000 collisions", "Value": round(ksi_rate, 1)},
            {"Metric": "Night-time collision share (%)", "Value": round(dark_pct, 1)},
        ]
    )
    with st.expander("Download automated report packs", expanded=False):
        st.markdown(
            "- **Executive summary CSV** — headline KPIs for the filtered period\n"
            "- **District risk CSV** — ranked district table (current ranking metric)\n"
            "- **Filtered collision extract** — full collision-level records for downstream analysis"
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
                label="District risk CSV",
                data=top_risk.to_csv(index=False),
                file_name="district_risk_export.csv",
                mime="text/csv",
            )
        with c3:
            st.download_button(
                label="Filtered collision extract",
                data=collision_view.to_csv(index=False),
                file_name="filtered_collision_extract.csv",
                mime="text/csv",
            )
