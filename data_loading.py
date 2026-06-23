"""Data loading, caching, and district lookup for the STATS19 Intelligence Platform."""

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from config import DATASET_CANDIDATES, LAD_LOOKUP, LEGACY_LAD_CROSSWALK

# Parquet cache subdir (faster load, downcast types)
PARQUET_CACHE_DIR = "parquet_cache"


def find_dataset_dir() -> Path:
    for candidate in DATASET_CANDIDATES:
        if candidate.exists() and candidate.is_dir():
            return candidate
    base = Path(__file__).resolve().parent
    datasets = base / "datasets"
    datasets.mkdir(parents=True, exist_ok=True)
    return datasets


def get_parquet_cache_dir() -> Path:
    """Directory for Parquet cache and prebuilt views."""
    return find_dataset_dir().parent / PARQUET_CACHE_DIR


def _downcast_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Downcast dtypes for memory and I/O efficiency."""
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == "int64":
            c_min, c_max = out[col].min(), out[col].max()
            if pd.isna(c_min) and pd.isna(c_max):
                continue
            if not pd.isna(c_min) and not pd.isna(c_max):
                if c_min >= -128 and c_max <= 127:
                    out[col] = out[col].astype("int8")
                elif c_min >= -32768 and c_max <= 32767:
                    out[col] = out[col].astype("int16")
                elif c_min >= 0 and c_max <= 65535:
                    out[col] = out[col].astype("uint16")
                elif c_min >= -2147483648 and c_max <= 2147483647:
                    out[col] = out[col].astype("int32")
        elif out[col].dtype == "float64":
            out[col] = out[col].astype("float32")
        elif out[col].dtype == "object" and out[col].nunique() < len(out) * 0.5:
            out[col] = out[col].astype("category")
    return out


def _load_parquet_or_csv(
    base_csv: Path,
    provisional_csv: Path,
    parquet_path: Path,
    dtype_common: dict,
    post_process=None,
) -> pd.DataFrame:
    """
    Prefer Parquet if fresh. Else load CSV, optionally save Parquet for next time.
    post_process: optional callable(df) -> df, run after load (for collisions: date, hour, is_dark, etc.)
    """
    use_parquet = parquet_path.exists()
    base_exists = base_csv.exists()
    if use_parquet:
        base_mtime = base_csv.stat().st_mtime_ns if base_exists else 0
        prov_mtime = provisional_csv.stat().st_mtime_ns if provisional_csv.exists() else 0
        parquet_mtime = parquet_path.stat().st_mtime_ns
        if parquet_mtime >= base_mtime and parquet_mtime >= prov_mtime:
            df = pd.read_parquet(parquet_path)
            if post_process:
                df = post_process(df)
            return df
    if not base_exists:
        return pd.DataFrame()

    df = pd.read_csv(base_csv, dtype=dtype_common, low_memory=False)
    if provisional_csv.exists():
        prov = pd.read_csv(provisional_csv, dtype=dtype_common, low_memory=False)
        df = pd.concat([df, prov], ignore_index=True, sort=False)
    if post_process:
        df = post_process(df)
    df = _downcast_dataframe(df)

    cache_dir = parquet_path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(parquet_path, index=False)
    except Exception:
        pass
    return df


def data_cache_fingerprint() -> tuple:
    """Build a cache fingerprint from all relevant source files for correct invalidation."""
    dataset_dir = find_dataset_dir()
    parquet_dir = get_parquet_cache_dir()
    files = [
        dataset_dir / "dft-road-casualty-statistics-collision-last-5-years.csv",
        dataset_dir / "dft-road-casualty-statistics-vehicle-last-5-years.csv",
        dataset_dir / "dft-road-casualty-statistics-casualty-last-5-years.csv",
        dataset_dir / "dft-road-casualty-statistics-collision-provisional-2025.csv",
        dataset_dir / "dft-road-casualty-statistics-vehicle-provisional-2025.csv",
        dataset_dir / "dft-road-casualty-statistics-casualty-provisional-2025.csv",
        dataset_dir / "Local_Authority_Districts_(April_2025)_Names_and_Codes_in_the_UK_v2.csv",
        parquet_dir / "collision_view.parquet",
        parquet_dir / "collisions.parquet",
        parquet_dir / "vehicles.parquet",
        parquet_dir / "casualties.parquet",
        dataset_dir / "dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2024.xlsx",
    ]
    result = []
    for p in files:
        if p.exists():
            result.append((str(p), p.stat().st_mtime_ns, p.stat().st_size))
        else:
            result.append((str(p), None, None))
    return tuple(result)


@st.cache_data(show_spinner=False)
def get_lad_lookup() -> Dict[str, str]:
    lookup = dict(LAD_LOOKUP)
    try:
        dataset_dir = find_dataset_dir()
        lookup_path = dataset_dir / "Local_Authority_Districts_(April_2025)_Names_and_Codes_in_the_UK_v2.csv"
        if lookup_path.exists():
            lad_df = pd.read_csv(lookup_path, dtype="string", low_memory=False)
            if {"LAD25CD", "LAD25NM"}.issubset(set(lad_df.columns)):
                fresh = lad_df.dropna(subset=["LAD25CD", "LAD25NM"]).drop_duplicates(
                    subset=["LAD25CD"], keep="last"
                )
                fresh["LAD25CD"] = fresh["LAD25CD"].astype("string").str.strip().str.upper()
                lookup.update(dict(zip(fresh["LAD25CD"], fresh["LAD25NM"])))
    except Exception:
        pass
    return lookup


def add_district_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "local_authority_ons_district" not in out.columns:
        return out

    lad_lookup = get_lad_lookup()
    code = out["local_authority_ons_district"].astype("string").str.strip().str.upper()
    out["district_name"] = code.map(lad_lookup)
    out["district_current_authority"] = out["district_name"]
    for legacy_code, details in LEGACY_LAD_CROSSWALK.items():
        is_legacy = code == legacy_code
        if is_legacy.any():
            out.loc[is_legacy, "district_name"] = details["district_name"]
            out.loc[is_legacy, "district_current_authority"] = details["current_authority"]
    out["district_display"] = code.fillna("Unknown")
    mapped_mask = out["district_name"].notna()
    out.loc[mapped_mask, "district_display"] = (
        out.loc[mapped_mask, "district_name"] + " (" + code.loc[mapped_mask] + ")"
    )
    return out


def district_authority_lookup_frame(collision_view: pd.DataFrame) -> pd.DataFrame:
    """Build a safe district->current-authority lookup."""
    base = collision_view[["district_display"]].drop_duplicates().copy()
    if "district_current_authority" in collision_view.columns:
        auth = (
            collision_view[["district_display", "district_current_authority"]]
            .drop_duplicates(subset=["district_display"])
            .rename(columns={"district_current_authority": "Current Authority"})
        )
    else:
        auth = base.assign(**{"Current Authority": "Unknown"})
    return auth


def resolve_district_display(code_series: pd.Series) -> pd.Series:
    code = code_series.astype("string").str.strip().str.upper()
    lad_lookup = get_lad_lookup()
    name = code.map(lad_lookup)
    for legacy_code, details in LEGACY_LAD_CROSSWALK.items():
        name = name.mask(code == legacy_code, details["district_name"])
    display = code.fillna("Unknown")
    mapped_mask = name.notna()
    display.loc[mapped_mask] = name.loc[mapped_mask] + " (" + code.loc[mapped_mask] + ")"
    return display


def _collision_post_process(df: pd.DataFrame) -> pd.DataFrame:
    """Apply collision-specific transformations after load."""
    df["collision_index"] = df["collision_index"].astype("string")
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df["time_dt"] = pd.to_datetime(df["time"], format="%H:%M", errors="coerce")
    df["hour"] = df["time_dt"].dt.hour.astype(np.int16)
    df["is_dark"] = df["light_conditions"].isin([4, 5, 6, 7]).astype(np.int8)
    df["is_weekend"] = df["day_of_week"].isin([1, 7]).astype(np.int8)
    return df


@st.cache_data(show_spinner=True, ttl=3600)
def load_raw_tables(cache_fingerprint: tuple) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load raw tables. Prefers Parquet (auto-generated from CSV on first run).
    Cached per session with 1hr TTL to avoid reloading on every Streamlit rerun.
    """
    _ = cache_fingerprint
    dataset_dir = find_dataset_dir()
    cache_dir = get_parquet_cache_dir()

    dtype_common = {
        "collision_index": "string",
        "lsoa_of_accident_location": "string",
        "lsoa_of_driver": "string",
        "lsoa_of_casualty": "string",
        "local_authority_ons_district": "string",
    }

    collisions = _load_parquet_or_csv(
        dataset_dir / "dft-road-casualty-statistics-collision-last-5-years.csv",
        dataset_dir / "dft-road-casualty-statistics-collision-provisional-2025.csv",
        cache_dir / "collisions.parquet",
        dtype_common,
        post_process=_collision_post_process,
    )
    if collisions.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    vehicles = _load_parquet_or_csv(
        dataset_dir / "dft-road-casualty-statistics-vehicle-last-5-years.csv",
        dataset_dir / "dft-road-casualty-statistics-vehicle-provisional-2025.csv",
        cache_dir / "vehicles.parquet",
        dtype_common,
        post_process=lambda d: d.assign(collision_index=d["collision_index"].astype("string")),
    )

    casualties = _load_parquet_or_csv(
        dataset_dir / "dft-road-casualty-statistics-casualty-last-5-years.csv",
        dataset_dir / "dft-road-casualty-statistics-casualty-provisional-2025.csv",
        cache_dir / "casualties.parquet",
        dtype_common,
        post_process=lambda d: d.assign(collision_index=d["collision_index"].astype("string")),
    )

    collisions = add_district_labels(collisions)
    return collisions, vehicles, casualties
