"""Sidebar filters and active-filter banner."""

import base64
from pathlib import Path

import pandas as pd
import streamlit as st

from config import CODE_MAPS
from data_loading import resolve_district_display as _resolve_district_display
from styles.container import FILTER_RADIO_CSS, NAV_RADIO_CSS, stylable_container
from transforms import as_int_if_possible as _as_int_if_possible

ROOT = Path(__file__).resolve().parent.parent

INTELLIGENCE_PAGES = [
    "Executive Overview",
    "GeoRisk Map",
    "Risk Factors",
    "Vehicle Intelligence",
    "Casualty Intelligence",
    "Data Quality & Refresh Status",
]

_VEHICLE_LABELS = {
    "cars": "Cars",
    "motorbikes": "Motorbikes",
    "both": "Cars & Motorbikes",
}


def _store_active_filters(
    *,
    total_count: int,
    filtered_count: int,
    vehicle_type_filter: str,
    start_date,
    end_date,
    selected_road_types: list,
    road_type_options: list,
    selected_districts: list,
) -> None:
    if len(selected_road_types) == len(road_type_options):
        road_label = f"All ({len(road_type_options)})"
    else:
        road_label = f"{len(selected_road_types)} selected"
    district_label = "All regions" if not selected_districts else f"{len(selected_districts)} district(s)"
    st.session_state["active_filters"] = {
        "vehicle_type": _VEHICLE_LABELS[vehicle_type_filter],
        "date_start": str(start_date),
        "date_end": str(end_date),
        "road_types": road_label,
        "districts": district_label,
        "filtered_collisions": filtered_count,
        "total_collisions": total_count,
    }


def render_sidebar_logo() -> None:
    logo_path = ROOT / "imba_logo.png"
    if logo_path.exists():
        logo_bytes = logo_path.read_bytes()
        logo_b64 = base64.b64encode(logo_bytes).decode()
        st.sidebar.markdown(
            f'<img src="data:image/png;base64,{logo_b64}" style="width:100%; border-radius:12px; object-fit:contain;" alt="IMBA logo" />',
            unsafe_allow_html=True,
        )


def render_intelligence_nav() -> str:
    st.sidebar.header("Intelligence Modules")
    with stylable_container("imba_intelligence_nav", NAV_RADIO_CSS, parent=st.sidebar):
        return st.radio(
            "Select intelligence module",
            options=INTELLIGENCE_PAGES,
            key="intelligence_module",
            label_visibility="collapsed",
        )


def apply_sidebar_filters(collision_view: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Global Filters")
    collision_view = collision_view.copy()
    total_count = len(collision_view)
    collision_view["has_car"] = collision_view.get("has_car", 0).fillna(0)
    collision_view["has_motorbike"] = collision_view.get("has_motorbike", 0).fillna(0)
    collision_view["district_filter_display"] = _resolve_district_display(
        collision_view["local_authority_ons_district"]
    )

    with st.sidebar.expander("Vehicle Type", expanded=True):
        with stylable_container("imba_vehicle_type_filter", FILTER_RADIO_CSS):
            vehicle_type_filter = st.radio(
                "Show collisions involving",
                options=["cars", "motorbikes", "both"],
                index=2,
                format_func=lambda x: _VEHICLE_LABELS[x],
                key="vehicle_type_filter",
            )

    min_date = collision_view["date"].min()
    max_date = collision_view["date"].max()

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
    if prior_selection is not None and len(prior_selection) > 0:
        remapped_prior = [
            code_to_display.get(str(item).strip().upper(), item) for item in prior_selection
        ]
        remapped_prior = [item for item in remapped_prior if item in districts]
        default_districts = remapped_prior
    else:
        default_districts = []

    with st.sidebar.expander("District Filter", expanded=True):
        selected_districts = st.multiselect(
            "Local authority district (ONS)",
            options=districts,
            default=default_districts,
            key=state_key,
            help="Leave empty to show all regions. Select districts to filter.",
        )

    if pd.isna(min_date) or pd.isna(max_date):
        mask = collision_view["road_type"].isin(selected_road_types)
        if selected_districts:
            mask &= collision_view["district_filter_display"].isin(selected_districts)
        if vehicle_type_filter == "cars":
            mask &= collision_view["has_car"] == 1
        elif vehicle_type_filter == "motorbikes":
            mask &= collision_view["has_motorbike"] == 1
        else:
            mask &= (collision_view["has_car"] == 1) | (collision_view["has_motorbike"] == 1)
        filtered = collision_view[mask].copy()
        _store_active_filters(
            total_count=total_count,
            filtered_count=len(filtered),
            vehicle_type_filter=vehicle_type_filter,
            start_date="–",
            end_date="–",
            selected_road_types=selected_road_types,
            road_type_options=road_type_options,
            selected_districts=selected_districts,
        )
        return filtered

    with st.sidebar.expander("Date Filter", expanded=True):
        date_range = st.date_input(
            "Date range",
            value=(min_date.date(), max_date.date()),
            min_value=min_date.date(),
            max_value=max_date.date(),
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
        mask &= (collision_view["has_car"] == 1) | (collision_view["has_motorbike"] == 1)

    filtered = collision_view[mask].copy()
    _store_active_filters(
        total_count=total_count,
        filtered_count=len(filtered),
        vehicle_type_filter=vehicle_type_filter,
        start_date=start_date,
        end_date=end_date,
        selected_road_types=selected_road_types,
        road_type_options=road_type_options,
        selected_districts=selected_districts,
    )
    return filtered


def render_active_filter_banner() -> None:
    active = st.session_state.get("active_filters")
    if not active:
        return
    st.info(
        f"**Active filters:** {active['vehicle_type']} · "
        f"{active['date_start']} to {active['date_end']} · "
        f"Road types: {active['road_types']} · "
        f"Districts: {active['districts']} · "
        f"**{active['filtered_collisions']:,}** of {active['total_collisions']:,} collisions shown"
    )
