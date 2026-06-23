"""Data transforms, feature engineering, and view building for the STATS19 Intelligence Platform."""

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from config import CODE_MAPS
from data_loading import (
    add_district_labels,
    data_cache_fingerprint as _data_cache_fingerprint,
    find_dataset_dir,
    get_parquet_cache_dir,
    load_raw_tables,
    resolve_district_display,
)

# Columns required for core app functionality; missing these causes st.stop()


REQUIRED_COLLISION_VIEW_COLUMNS = [
    "collision_index",
    "date",
    "district_display",
    "serious_casualties",
    "slight_casualties",
]
# Core casualty columns; casualty page shows graceful error if missing
REQUIRED_CASUALTY_VIEW_COLUMNS = [
    "collision_index",
    "casualty_reference",
    "casualty_class",
    "casualty_type",
    "casualty_severity",
]
OPTIONAL_COLLISION_LABELS = [
    "weather_conditions_label",
    "light_conditions_label",
    "junction_detail_label",
    "first_road_class_label",
]
PREBUILT_VIEW_REQUIRED_COLUMNS = {
    "collision_view": [
        "collision_index",
        "fatal_casualties",
        "serious_casualties",
        "slight_casualties",
        "adjusted_serious_casualties",
        "adjusted_slight_casualties",
    ],
}


def _prebuilt_is_fresh(path, dataset_dir) -> bool:
    """True if prebuilt parquet exists and is newer than all source and enrichment inputs."""
    from pathlib import Path
    p = Path(path) if not hasattr(path, "exists") else path
    if not p.exists():
        return False
    prebuilt_mtime = p.stat().st_mtime_ns
    code_dir = Path(__file__).resolve().parent
    sources = [
        dataset_dir / "dft-road-casualty-statistics-collision-last-5-years.csv",
        dataset_dir / "dft-road-casualty-statistics-collision-provisional-2025.csv",
        dataset_dir / "dft-road-casualty-statistics-vehicle-last-5-years.csv",
        dataset_dir / "dft-road-casualty-statistics-vehicle-provisional-2025.csv",
        dataset_dir / "dft-road-casualty-statistics-casualty-last-5-years.csv",
        dataset_dir / "dft-road-casualty-statistics-casualty-provisional-2025.csv",
        dataset_dir / "Local_Authority_Districts_(April_2025)_Names_and_Codes_in_the_UK_v2.csv",
        dataset_dir / "dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2024.xlsx",
        code_dir / "data_loading.py",
        code_dir / "transforms.py",
    ]
    for src in sources:
        if src.exists() and src.stat().st_mtime_ns > prebuilt_mtime:
            return False
    return True


def _try_load_prebuilt_view(name: str, cache_fingerprint: tuple) -> pd.DataFrame | None:
    """Load prebuilt Parquet view if it exists and is fresh. Returns None to fall back to build."""
    _ = cache_fingerprint
    cache_dir = get_parquet_cache_dir()
    path = cache_dir / f"{name}.parquet"
    if not path.exists() or not _prebuilt_is_fresh(path, find_dataset_dir()):
        return None
    try:
        df = pd.read_parquet(path)
        required_columns = PREBUILT_VIEW_REQUIRED_COLUMNS.get(name, [])
        if required_columns and not has_required_columns(df, required_columns):
            return None
        return df
    except Exception:
        return None


def validate_schema(df, required: List[str], name: str = "DataFrame") -> List[str]:
    """Return list of missing required columns. Empty list means schema OK."""
    missing = [c for c in required if c not in df.columns]
    return missing


def has_required_columns(df, required: List[str]) -> bool:
    """Return True if df has all required columns."""
    return len(validate_schema(df, required)) == 0


def apply_code_labels(df: pd.DataFrame, maps: Dict[str, Dict[int, str]]) -> pd.DataFrame:
    out = df.copy()
    for col, mapper in maps.items():
        if col in out.columns:
            out[f"{col}_label"] = out[col].map(mapper).fillna("Unknown")
    return out


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    den = denominator.replace({0: np.nan})
    return (numerator / den).fillna(0)


def collision_level_serious_fatal_stats(
    vehicle_data: pd.DataFrame, group_cols: list[str]
) -> pd.DataFrame:
    """Compute serious/fatal counts and rate at collision level (numerator and denominator aligned)."""
    tmp = (
        vehicle_data.groupby(group_cols + ["collision_index"], dropna=False)
        .agg(
            fatal=("fatal_collision", "max"),
            serious=("serious_collision", "max"),
            serious_or_fatal=("serious_or_fatal_collision", "max"),
        )
        .reset_index()
    )
    summary = tmp.groupby(group_cols, dropna=False).agg(
        collisions=("collision_index", "count"),
        fatal_collisions=("fatal", "sum"),
        serious_collisions=("serious", "sum"),
        serious_or_fatal_collisions=("serious_or_fatal", "sum"),
    ).reset_index()
    summary["serious_fatal_collision_rate_pct"] = (
        safe_ratio(summary["serious_or_fatal_collisions"], summary["collisions"]) * 100
    )
    return summary


@st.cache_data(show_spinner=False)
def _guide_field_code_map(field_name: str, cache_fingerprint: tuple) -> Dict[int, str]:
    _ = cache_fingerprint
    dataset_dir = find_dataset_dir()
    guide_path = dataset_dir / "dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2024.xlsx"
    if not guide_path.exists():
        return {}
    try:
        guide = pd.read_excel(guide_path, sheet_name="2024_code_list", dtype="string")
        sub = guide[guide["field name"] == field_name][["code/format", "label"]].dropna(how="any")
        mapping: Dict[int, str] = {}
        for _, row in sub.iterrows():
            raw_code = row["code/format"]
            label = str(row["label"]).strip()
            try:
                code = int(float(raw_code))
            except Exception:
                continue
            mapping[code] = label
        return mapping
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def effective_code_maps(cache_fingerprint: tuple | None = None) -> Dict[str, Dict[int, str]]:
    from data_loading import data_cache_fingerprint

    if cache_fingerprint is None:
        cache_fingerprint = data_cache_fingerprint()
    maps = {k: dict(v) for k, v in CODE_MAPS.items()}
    guide_fields = [
        "police_force",
        "junction_detail",
        "first_road_class",
        "second_road_class",
        "junction_control",
        "junction_location",
        "pedestrian_crossing",
        "special_conditions_at_site",
        "carriageway_hazards",
        "did_police_officer_attend_scene_of_accident",
        "trunk_road_flag",
    ]
    for field in guide_fields:
        field_map = _guide_field_code_map(field, cache_fingerprint)
        if field_map:
            maps[field] = field_map
    junction_map = maps.get("junction_detail", {})
    if 19 not in junction_map:
        junction_map[19] = "Other junction (legacy code 19)"
        maps["junction_detail"] = junction_map
    return maps


def as_int_if_possible(value: object) -> object:
    try:
        if pd.isna(value):
            return value
        return int(float(value))
    except Exception:
        return value


def ensure_label_columns(
    df: pd.DataFrame,
    fields: list[str],
    maps: Dict[str, Dict[int, str]] | None = None,
) -> pd.DataFrame:
    """Ensure label columns exist for given code fields. Adds _label columns if missing."""
    if maps is None:
        maps = effective_code_maps()
    out = df.copy()
    for field in fields:
        label_col = f"{field}_label"
        if label_col not in out.columns and field in out.columns:
            mapper = maps.get(field, {})
            out[label_col] = out[field].map(mapper).fillna(out[field].astype("string"))
    return out


def series_or_default(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(default)
    return pd.Series(default, index=df.index)


def triage_score_features(df: pd.DataFrame) -> pd.Series:
    score = pd.Series(0.0, index=df.index)
    is_dark = series_or_default(df, "is_dark", 0)
    speed_limit = series_or_default(df, "speed_limit", 0)
    rural_flag = series_or_default(df, "urban_or_rural_area", 0)
    weather = series_or_default(df, "weather_conditions", 0)
    surface = series_or_default(df, "road_surface_conditions", 0)
    vehicle_type = series_or_default(df, "vehicle_type", 0)
    age_of_driver = series_or_default(df, "age_of_driver", np.nan)
    score += 20 * is_dark
    score += np.where(speed_limit >= 60, 20, np.where(speed_limit >= 40, 10, 0))
    score += np.where(rural_flag == 2, 12, 0)
    score += np.where(weather.isin([2, 3, 5, 6, 7]), 10, 0)
    score += np.where(surface.isin([2, 3, 4, 5, 6, 7]), 10, 0)
    score += np.where(vehicle_type.isin([2, 3, 4, 5, 23]), 12, 0)
    score += np.where((age_of_driver <= 24) | (age_of_driver >= 75), 8, 0)
    return score.round(1)


def harm_score_features(df: pd.DataFrame) -> pd.Series:
    score = triage_score_features(df) * 0.5
    severity = series_or_default(df, "collision_severity", 3)
    score += np.where(severity == 1, 35, np.where(severity == 2, 18, 0))
    skidding = series_or_default(df, "skidding_and_overturning", 0)
    leaving = series_or_default(df, "vehicle_leaving_carriageway", 0)
    hit_off = series_or_default(df, "hit_object_off_carriageway", 0)
    score += np.where(skidding > 0, 10, 0)
    score += np.where(leaving > 0, 10, 0)
    score += np.where(hit_off > 0, 8, 0)
    return score.round(1)


def add_vehicle_intelligence_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["fatal_collision"] = (series_or_default(out, "collision_severity", 3) == 1).astype(int)
    out["serious_collision"] = (series_or_default(out, "collision_severity", 3) == 2).astype(int)
    out["serious_or_fatal_collision"] = out["fatal_collision"] + out["serious_collision"]

    out["loss_of_control_flag"] = (
        (series_or_default(out, "skidding_and_overturning", 0) > 0)
        | (series_or_default(out, "vehicle_leaving_carriageway", 0) > 0)
    ).astype(int)
    out["roadway_departure_flag"] = (series_or_default(out, "vehicle_leaving_carriageway", 0) > 0).astype(int)
    out["impact_off_carriageway_flag"] = (series_or_default(out, "hit_object_off_carriageway", 0) > 0).astype(int)
    out["impact_in_carriageway_flag"] = (series_or_default(out, "hit_object_in_carriageway", 0) > 0).astype(int)

    manoeuvre = series_or_default(out, "vehicle_manoeuvre", -1)
    impact = series_or_default(out, "first_point_of_impact", -1)
    turning_conflict = manoeuvre.isin([7, 8, 9, 10]) & impact.isin([3, 4])
    rear_end = impact == 2
    front_high_speed = (impact == 1) & (series_or_default(out, "speed_limit", 0) >= 50)
    out["incident_signature"] = np.select(
        [
            (out["roadway_departure_flag"] == 1) & (out["impact_off_carriageway_flag"] == 1),
            out["loss_of_control_flag"] == 1,
            turning_conflict,
            rear_end,
            front_high_speed,
        ],
        [
            "Run-off-road",
            "Loss of control",
            "Turning conflict",
            "Rear-end profile",
            "High-speed front impact",
        ],
        default="Other profile",
    )

    out["triage_score"] = triage_score_features(out)
    out["harm_score"] = harm_score_features(out)
    return out


def casualty_priority_score(df: pd.DataFrame) -> pd.Series:
    severity = series_or_default(df, "casualty_severity", 3)
    age = series_or_default(df, "age_of_casualty", np.nan)
    dist = series_or_default(df, "casualty_distance_banding", -1)
    speed = series_or_default(df, "speed_limit", 0)
    is_dark = series_or_default(df, "is_dark", 0)
    ped = series_or_default(df, "casualty_class", 0) == 3
    score = pd.Series(0.0, index=df.index)
    score += np.where(severity == 1, 45, np.where(severity == 2, 22, 8))
    score += np.where((age <= 16) | (age >= 75), 8, 0)
    score += np.where(dist >= 4, 6, 0)
    score += np.where((ped) & (is_dark == 1) & (speed >= 40), 10, 0)
    return score.round(1)


def casualty_priority_reason(df: pd.DataFrame) -> pd.Series:
    severity = series_or_default(df, "casualty_severity", 3)
    age = series_or_default(df, "age_of_casualty", np.nan)
    dist = series_or_default(df, "casualty_distance_banding", -1)
    speed = series_or_default(df, "speed_limit", 0)
    is_dark = series_or_default(df, "is_dark", 0)
    ped = series_or_default(df, "casualty_class", 0) == 3

    reason = np.select(
        [
            severity == 1,
            severity == 2,
            (ped) & (is_dark == 1) & (speed >= 40),
            (age <= 16) | (age >= 75),
            dist >= 4,
        ],
        [
            "Fatal casualty",
            "Serious casualty",
            "Pedestrian at night on >=40mph road",
            "Vulnerable age band",
            "Far from home distance band",
        ],
        default="Contextual risk profile",
    )
    return pd.Series(reason, index=df.index)


def _build_veh_agg(vehicles: pd.DataFrame) -> pd.DataFrame:
    vehicle_tmp = vehicles.copy()
    vehicle_tmp["is_motorcycle"] = vehicle_tmp["vehicle_type"].isin([2, 3, 4, 5, 23]).astype(int)
    vehicle_tmp["is_car"] = pd.to_numeric(vehicle_tmp["vehicle_type"], errors="coerce").isin([8, 9, 10]).astype(int)
    return vehicle_tmp.groupby("collision_index", dropna=False).agg(
        vehicles_total=("vehicle_reference", "nunique"),
        pct_motorcycles=("is_motorcycle", "mean"),
        avg_driver_age=("age_of_driver", "mean"),
        has_car=("is_car", "max"),
        has_motorbike=("is_motorcycle", "max"),
    ).reset_index()


def _build_cas_agg(casualties: pd.DataFrame) -> pd.DataFrame:
    if "collision_index" not in casualties.columns:
        raise ValueError(
            "Casualty data must contain 'collision_index' to link to collisions. "
            f"Found columns: {list(casualties.columns)[:15]}..."
        )
    if casualties.empty:
        return pd.DataFrame(
            columns=[
                "collision_index",
                "casualties_total",
                "fatal_casualties",
                "serious_casualties",
                "slight_casualties",
                "adjusted_serious_casualties",
                "adjusted_slight_casualties",
                "avg_casualty_age",
            ]
        ).astype({"collision_index": "string"})

    cas_tmp = casualties.copy()
    cas_agg_spec: Dict[str, Tuple[str, str]] = {}

    if "casualty_reference" in cas_tmp.columns:
        cas_agg_spec["casualties_total"] = ("casualty_reference", "count")
    else:
        cas_agg_spec["casualties_total"] = (cas_tmp.columns[0], "count")

    if "casualty_severity" in cas_tmp.columns:
        severity = pd.to_numeric(cas_tmp["casualty_severity"], errors="coerce")
        cas_tmp["_fatal_flag"] = (severity == 1).astype(int)
        cas_tmp["_serious_flag"] = (severity == 2).astype(int)
        cas_tmp["_slight_flag"] = (severity == 3).astype(int)
        cas_agg_spec["fatal_casualties"] = ("_fatal_flag", "sum")
        cas_agg_spec["serious_casualties"] = ("_serious_flag", "sum")
        cas_agg_spec["slight_casualties"] = ("_slight_flag", "sum")
    else:
        cas_agg_spec["fatal_casualties"] = (cas_tmp.columns[0], "count")
        cas_agg_spec["serious_casualties"] = ("casualty_reference", "count")
        cas_agg_spec["slight_casualties"] = ("casualty_reference", "count")

    if "casualty_adjusted_severity_serious" in cas_tmp.columns:
        cas_agg_spec["adjusted_serious_casualties"] = ("casualty_adjusted_severity_serious", "sum")
    elif "casualty_reference" in cas_tmp.columns:
        cas_agg_spec["adjusted_serious_casualties"] = ("casualty_reference", "count")
    else:
        cas_agg_spec["adjusted_serious_casualties"] = (cas_tmp.columns[0], "count")

    if "casualty_adjusted_severity_slight" in cas_tmp.columns:
        cas_agg_spec["adjusted_slight_casualties"] = ("casualty_adjusted_severity_slight", "sum")
    elif "casualty_reference" in cas_tmp.columns:
        cas_agg_spec["adjusted_slight_casualties"] = ("casualty_reference", "count")
    else:
        cas_agg_spec["adjusted_slight_casualties"] = (cas_tmp.columns[0], "count")

    if "age_of_casualty" in cas_tmp.columns:
        cas_agg_spec["avg_casualty_age"] = ("age_of_casualty", "mean")
    elif cas_tmp.columns.any():
        cas_agg_spec["avg_casualty_age"] = (cas_tmp.columns[0], "count")
    else:
        cas_tmp["_dummy"] = 0
        cas_agg_spec["avg_casualty_age"] = ("_dummy", "mean")

    return cas_tmp.groupby("collision_index", dropna=False).agg(**cas_agg_spec).reset_index()


def _prebuilt_view_path(name: str) -> Path | None:
    """Path to prebuilt Parquet view if it exists and is usable."""
    from pathlib import Path
    cache_dir = get_parquet_cache_dir()
    path = cache_dir / f"{name}.parquet"
    return path if path.exists() else None


@st.cache_data(show_spinner=True)
def build_collision_view(cache_fingerprint: tuple) -> pd.DataFrame:
    """Build collision-level view (needed for filters and several pages)."""
    prebuilt = _try_load_prebuilt_view("collision_view", cache_fingerprint)
    if prebuilt is not None:
        return prebuilt
    collisions, vehicles, casualties = load_raw_tables(cache_fingerprint)
    veh_agg = _build_veh_agg(vehicles)
    cas_agg = _build_cas_agg(casualties)
    collision_view = (
        collisions.merge(veh_agg, on="collision_index", how="left")
        .merge(cas_agg, on="collision_index", how="left")
        .assign(
            vehicles_total=lambda d: d["vehicles_total"].fillna(0).astype(int),
            casualties_total=lambda d: d["casualties_total"].fillna(0).astype(int),
            fatal_casualties=lambda d: d["fatal_casualties"].fillna(0),
            serious_casualties=lambda d: d["serious_casualties"].fillna(0),
            slight_casualties=lambda d: d["slight_casualties"].fillna(0),
            adjusted_serious_casualties=lambda d: d["adjusted_serious_casualties"].fillna(0.0),
            adjusted_slight_casualties=lambda d: d["adjusted_slight_casualties"].fillna(0.0),
            pct_motorcycles=lambda d: d["pct_motorcycles"].fillna(0.0),
            fatal_or_serious_collision=lambda d: d["collision_severity"].isin([1, 2]).astype(int),
            has_car=lambda d: d["has_car"].fillna(0),
            has_motorbike=lambda d: d["has_motorbike"].fillna(0),
        )
    )
    effective_maps = effective_code_maps(cache_fingerprint)
    collision_view = apply_code_labels(collision_view, effective_maps)
    collision_view = add_district_labels(collision_view)
    return collision_view


@st.cache_data(show_spinner=True)
def build_vehicle_view(cache_fingerprint: tuple) -> pd.DataFrame:
    """Build vehicle-level view (lazy-loaded when Vehicle Intelligence is selected)."""
    prebuilt = _try_load_prebuilt_view("vehicle_view", cache_fingerprint)
    if prebuilt is not None:
        return prebuilt
    collisions, vehicles, casualties = load_raw_tables(cache_fingerprint)
    vehicle_view = collisions.merge(
        vehicles,
        on="collision_index",
        how="left",
        suffixes=("_collision", "_vehicle"),
    )
    vehicle_view = add_vehicle_intelligence_features(vehicle_view)
    effective_maps = effective_code_maps(cache_fingerprint)
    vehicle_view = apply_code_labels(vehicle_view, effective_maps)
    vehicle_view = add_district_labels(vehicle_view)
    return vehicle_view


@st.cache_data(show_spinner=True)
def build_casualty_views(cache_fingerprint: tuple) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Build casualty views (lazy-loaded when Casualty Intelligence is selected)."""
    cv = _try_load_prebuilt_view("casualty_view", cache_fingerprint)
    cp = _try_load_prebuilt_view("casualty_person_view", cache_fingerprint)
    if cv is not None and cp is not None:
        return cv, cp
    collisions, vehicles, casualties = load_raw_tables(cache_fingerprint)

    casualty_person_view = collisions.merge(
        casualties,
        on="collision_index",
        how="left",
        suffixes=("_collision", "_casualty"),
    )

    vehicle_cols = [
        "collision_index",
        "vehicle_reference",
        "vehicle_type",
        "vehicle_manoeuvre",
        "first_point_of_impact",
        "skidding_and_overturning",
        "hit_object_in_carriageway",
        "vehicle_leaving_carriageway",
        "hit_object_off_carriageway",
        "journey_purpose_of_driver",
        "sex_of_driver",
        "age_of_driver",
        "age_band_of_driver",
        "driver_imd_decile",
        "driver_distance_banding",
        "generic_make_model",
    ]
    vehicle_cols = [c for c in vehicle_cols if c in vehicles.columns]
    vehicle_lookup = vehicles[vehicle_cols].copy()
    vehicle_lookup["vehicle_reference_join"] = pd.to_numeric(
        vehicle_lookup.get("vehicle_reference"), errors="coerce"
    )

    casualty_view = casualty_person_view.copy()
    casualty_view["vehicle_reference_join"] = pd.to_numeric(
        casualty_view.get("vehicle_reference"), errors="coerce"
    )
    casualty_view["linkable_to_vehicle"] = (
        (casualty_view.get("casualty_class") != 3)
        & casualty_view["vehicle_reference_join"].notna()
        & (casualty_view["vehicle_reference_join"] > 0)
    )
    casualty_view["vehicle_reference_join"] = casualty_view["vehicle_reference_join"].where(
        casualty_view["linkable_to_vehicle"], np.nan
    )
    casualty_view = casualty_view.merge(
        vehicle_lookup.drop(columns=["vehicle_reference"], errors="ignore"),
        on=["collision_index", "vehicle_reference_join"],
        how="left",
        indicator=True,
        suffixes=("", "_vehicle"),
    )
    casualty_view["link_status"] = np.select(
        [
            casualty_view["linkable_to_vehicle"] == 0,
            casualty_view["_merge"] == "both",
        ],
        ["not_linkable", "linked"],
        default="unlinked",
    )
    casualty_view = casualty_view.drop(columns=["_merge"], errors="ignore")

    effective_maps = effective_code_maps(cache_fingerprint)
    casualty_view = apply_code_labels(casualty_view, effective_maps)
    casualty_person_view = apply_code_labels(casualty_person_view, effective_maps)
    casualty_view = add_district_labels(casualty_view)
    casualty_person_view = add_district_labels(casualty_person_view)

    return casualty_view, casualty_person_view


@st.cache_data(show_spinner=True)
def build_views(cache_fingerprint: tuple) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build all views (for backward compatibility). Prefer lazy builders for per-page loading."""
    collision_view = build_collision_view(cache_fingerprint)
    vehicle_view = build_vehicle_view(cache_fingerprint)
    casualty_view, casualty_person_view = build_casualty_views(cache_fingerprint)
    return collision_view, vehicle_view, casualty_view, casualty_person_view
