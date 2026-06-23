"""Data Quality and Refresh Status page."""

import pandas as pd
import streamlit as st

from config import CODE_MAPS
from data_loading import has_provisional_data
from views.constants import PROVISIONAL_DATA_NOTICE

def page_pipeline_health(
    collisions: pd.DataFrame,
    vehicles: pd.DataFrame,
    casualties: pd.DataFrame,
    collision_view: pd.DataFrame,
) -> None:
    st.title("Data Quality & Refresh Status")
    st.caption(
        "Reflects the full loaded datasets and is not affected by sidebar analytical filters."
    )
    st.caption(f"Data loaded at: {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if has_provisional_data():
        st.warning(PROVISIONAL_DATA_NOTICE)

    max_date = collision_view["date"].max() if "date" in collision_view.columns and collision_view["date"].notna().any() else None
    max_date_str = max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else "–"
    total_records = len(collisions) + len(vehicles) + len(casualties)
    st.markdown("---")
    st.caption(
        f"**Last refresh:** {max_date_str} (data as of) | "
        f"**Records ingested this cycle:** {total_records:,} | "
        "**Source:** STATS19"
    )
    st.markdown("---")

    row1, row2, row3 = st.columns(3)
    row1.metric("Collisions rows", f"{len(collisions):,}")
    row2.metric("Vehicles rows", f"{len(vehicles):,}")
    row3.metric("Casualties rows", f"{len(casualties):,}")

    collisions_keys = set(collisions["collision_index"].dropna().astype(str))
    vehicles_keys = set(vehicles["collision_index"].dropna().astype(str))
    casualties_keys = set(casualties["collision_index"].dropna().astype(str))

    join_checks = pd.DataFrame(
        [
            {
                "metric": "Vehicles matching collisions",
                "value_pct": 100 * (len(vehicles_keys & collisions_keys) / max(1, len(vehicles_keys))),
            },
            {
                "metric": "Casualties matching collisions",
                "value_pct": 100 * (len(casualties_keys & collisions_keys) / max(1, len(casualties_keys))),
            },
            {
                "metric": "Collisions with geocodes",
                "value_pct": 100 * (collision_view["latitude"].notna().mean()),
            },
            {
                "metric": "Vehicles with missing driver age",
                "value_pct": 100 * (vehicles["age_of_driver"].isna().mean()),
            },
        ]
    )
    st.subheader("Join Integrity / Quality Metrics")
    st.dataframe(join_checks.style.format({"value_pct": "{:.2f}%"}), use_container_width=True, hide_index=True)

    collision_counts = (
        collision_view[["collision_index", "number_of_casualties", "casualties_total"]]
        .assign(
            number_of_casualties=lambda d: d["number_of_casualties"].fillna(0),
            casualties_total=lambda d: d["casualties_total"].fillna(0),
        )
        .assign(casualty_count_diff=lambda d: (d["number_of_casualties"] - d["casualties_total"]).abs())
    )
    mismatch_rate = 100 * (collision_counts["casualty_count_diff"] > 0).mean()
    duplicates_rate = 100 * (
        collisions.duplicated(subset=["collision_index"]).mean()
    )
    st.metric("Collisions casualty-count mismatch", f"{mismatch_rate:.2f}%")
    st.metric("Duplicate collision_index rows", f"{duplicates_rate:.4f}%")

    st.subheader("Code Decoding Dictionary (sample)")
    dict_rows = []
    for col, mapper in CODE_MAPS.items():
        for key, label in mapper.items():
            dict_rows.append({"column": col, "code": key, "label": label})
    st.dataframe(pd.DataFrame(dict_rows), use_container_width=True, hide_index=True)
