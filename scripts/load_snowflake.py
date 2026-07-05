#!/usr/bin/env python3
"""
Upload parquet_cache/*.parquet to Snowflake and load into tables.

Prerequisites:
  pip install snowflake-connector-python
  python scripts/prepare_data.py   # build parquet first

Set connection env vars (PowerShell example):
  $env:SNOWFLAKE_ACCOUNT = "XY12345-UK_AZURE"
  $env:SNOWFLAKE_USER = "you@zebra.law"
  $env:SNOWFLAKE_PASSWORD = "..."
  $env:SNOWFLAKE_WAREHOUSE = "COMPUTE_WH"
  $env:SNOWFLAKE_DATABASE = "ANALYTICS"
  $env:SNOWFLAKE_SCHEMA = "STATS19"
  $env:SNOWFLAKE_ROLE = "YOUR_ROLE"

Run:
  python scripts/load_snowflake.py
  python scripts/load_snowflake.py --views-only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PARQUET_DIR = ROOT / "parquet_cache"
VIEW_FILES = {
    "collision_view.parquet",
    "vehicle_view.parquet",
    "casualty_view.parquet",
    "casualty_person_view.parquet",
}
RAW_FILES = {
    "collisions.parquet",
    "casualties.parquet",
    "vehicles.parquet",
}


def _env(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name, "").strip()
    if required and not value:
        raise SystemExit(f"Missing environment variable: {name}")
    return value or None


def _connect():
    try:
        import snowflake.connector
    except ImportError as exc:
        raise SystemExit(
            "Install the Snowflake connector first:\n  pip install snowflake-connector-python"
        ) from exc

    return snowflake.connector.connect(
        account=_env("SNOWFLAKE_ACCOUNT"),
        user=_env("SNOWFLAKE_USER"),
        password=_env("SNOWFLAKE_PASSWORD"),
        warehouse=_env("SNOWFLAKE_WAREHOUSE"),
        database=_env("SNOWFLAKE_DATABASE"),
        schema=_env("SNOWFLAKE_SCHEMA"),
        role=os.environ.get("SNOWFLAKE_ROLE") or None,
    )


def _setup_objects(cur) -> None:
    db = _env("SNOWFLAKE_DATABASE")
    schema = _env("SNOWFLAKE_SCHEMA")
    cur.execute(f"USE DATABASE {db}")
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    cur.execute(f"USE SCHEMA {schema}")
    cur.execute(
        """
        CREATE OR REPLACE FILE FORMAT stats19_parquet
          TYPE = PARQUET
          COMPRESSION = AUTO
        """
    )
    cur.execute(
        """
        CREATE OR REPLACE STAGE stats19_stage
          FILE_FORMAT = stats19_parquet
          DIRECTORY = (ENABLE = TRUE)
        """
    )


def _snowflake_put_path(parquet_path: Path) -> str:
    """Build a PUT path Snowflake accepts on Windows (spaces must not be URL-encoded)."""
    path_str = parquet_path.resolve().as_posix()
    return f"file://{path_str}"


def _put_file(cur, parquet_path: Path) -> str:
    """Upload local Parquet to stage. Returns staged filename."""
    if not parquet_path.is_file():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")
    staged_name = parquet_path.name
    file_path = _snowflake_put_path(parquet_path)
    cur.execute(
        f"PUT '{file_path}' @stats19_stage/{staged_name} "
        "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
    )
    return staged_name


def _load_table(cur, table_name: str, staged_name: str) -> None:
    stage_path = f"@stats19_stage/{staged_name}"
    cur.execute(f"DROP TABLE IF EXISTS {table_name}")
    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {table_name}
          USING TEMPLATE (
            SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
            FROM TABLE(
              INFER_SCHEMA(
                LOCATION => '{stage_path}',
                FILE_FORMAT => 'stats19_parquet',
                IGNORE_CASE => TRUE
              )
            )
          )
        """
    )
    # COPY uses = for format options; => is only for function/table args (INFER_SCHEMA).
    cur.execute(
        f"""
        COPY INTO {table_name}
          FROM '{stage_path}'
          FILE_FORMAT = (FORMAT_NAME = 'stats19_parquet')
          MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
        """
    )
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    row = cur.fetchone()
    count = row[0] if row else 0
    print(f"  Loaded {table_name}: {count:,} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load parquet_cache into Snowflake")
    parser.add_argument(
        "--views-only",
        action="store_true",
        help="Load only dashboard view Parquet files (recommended first)",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Also load raw collisions/casualties/vehicles Parquet",
    )
    args = parser.parse_args()

    if not PARQUET_DIR.is_dir():
        raise SystemExit(f"Missing {PARQUET_DIR}. Run: python scripts/prepare_data.py")

    if args.views_only:
        targets = VIEW_FILES
    elif args.include_raw:
        targets = VIEW_FILES | RAW_FILES
    else:
        targets = VIEW_FILES

    files = sorted(
        p for p in PARQUET_DIR.glob("*.parquet") if p.name in targets
    )
    missing = targets - {p.name for p in files}
    if missing:
        print(f"Warning: missing local files (skipped): {', '.join(sorted(missing))}")
    if not files:
        raise SystemExit("No Parquet files to load.")

    print(f"Loading {len(files)} file(s) into Snowflake...")
    conn = _connect()
    try:
        with conn.cursor() as cur:
            _setup_objects(cur)
            for parquet_path in files:
                table_name = parquet_path.stem.upper()
                print(f"Uploading {parquet_path.name}...")
                staged_name = _put_file(cur, parquet_path)
                print(f"Creating table {table_name}...")
                _load_table(cur, table_name, staged_name)
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
