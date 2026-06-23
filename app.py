"""STATS19 Intelligence Platform — Streamlit entry point."""

import pandas as pd
import streamlit as st

from data_loading import data_cache_fingerprint, has_provisional_data, load_raw_tables
from transforms import REQUIRED_COLLISION_VIEW_COLUMNS, build_casualty_views, build_collision_view, build_vehicle_view, validate_schema
from views import (
    page_casualty_intelligence,
    page_executive_overview,
    page_georisk_map,
    page_pipeline_health,
    page_risk_factors,
    page_vehicle_intelligence,
)
from views.sidebar import (
    apply_sidebar_filters,
    render_active_filter_banner,
    render_intelligence_nav,
    render_sidebar_logo,
)
from charts.plotly_charts import init_plotly_theme
from styles.theme import inject_theme
from views.constants import PROVISIONAL_DATA_NOTICE

st.set_page_config(
    page_title="STATS19 Intelligence Platform",
    page_icon="🚦",
    layout="wide",
)


def main() -> None:
    inject_theme()
    init_plotly_theme()

    cache_fingerprint = data_cache_fingerprint()
    try:
        collision_view = build_collision_view(cache_fingerprint)
    except (ValueError, KeyError) as e:
        st.error(
            f"Data loading failed: {e} "
            "Please check that your casualty and collision CSVs use the expected STATS19 schema "
            "(collision_index, casualty_reference, casualty_severity, casualty_class, casualty_type, age_of_casualty)."
        )
        st.stop()
    except (MemoryError, OSError):
        st.error(
            "Data loading failed (out of memory or system limit). On Streamlit Cloud free tier, try: "
            "1) Add **Build command**: `python scripts/prepare_data.py` in app settings, 2) Redeploy."
        )
        st.stop()
    except Exception as e:
        st.error(f"Data loading failed: {type(e).__name__}: {e}")
        st.stop()

    missing_collision = validate_schema(collision_view, REQUIRED_COLLISION_VIEW_COLUMNS)
    if missing_collision:
        st.error(
            f"Schema validation failed: missing required columns in collision view: **{', '.join(missing_collision)}**. "
            "These columns are required for Executive Overview, GeoRisk Map, Risk Factors, Vehicle Intelligence, "
            "and sidebar filtering. The app cannot run without them."
        )
        st.stop()

    render_sidebar_logo()
    page = render_intelligence_nav()
    st.sidebar.divider()
    filtered_collision = apply_sidebar_filters(collision_view)

    st.markdown(
        '<h1 class="imba-page-title">UK Gov Road Safety Open Data (Last 5 Years)</h1>',
        unsafe_allow_html=True,
    )
    if has_provisional_data():
        st.caption(PROVISIONAL_DATA_NOTICE)
    render_active_filter_banner()

    collisions_raw, vehicles_raw, casualties_raw = load_raw_tables(cache_fingerprint)
    max_date = (
        collision_view["date"].max()
        if "date" in collision_view.columns and collision_view["date"].notna().any()
        else None
    )
    operational_stats = {
        "total_records": len(collisions_raw) + len(vehicles_raw) + len(casualties_raw),
        "max_date_str": max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else "–",
    }

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
        safe_page(
            "Casualty Intelligence",
            page_casualty_intelligence,
            filtered_casualty_person,
            filtered_casualty_linked,
        )
    elif page == "Data Quality & Refresh Status":
        safe_page(
            "Data Quality & Refresh Status",
            page_pipeline_health,
            collisions_raw,
            vehicles_raw,
            casualties_raw,
            collision_view,
        )


if __name__ == "__main__":
    main()
