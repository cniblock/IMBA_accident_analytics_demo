-- Minimal object setup only (no roles/grants).
-- For full IT provisioning (warehouse, roles, grants, user), run:
--   scripts/snowflake_provision.sql

USE ROLE STATS19_LOADER;
USE WAREHOUSE STATS19_WH;
USE DATABASE ANALYTICS;
CREATE SCHEMA IF NOT EXISTS STATS19;
USE SCHEMA STATS19;

CREATE OR REPLACE FILE FORMAT stats19_parquet
  TYPE = PARQUET
  COMPRESSION = AUTO;

CREATE OR REPLACE STAGE stats19_stage
  FILE_FORMAT = stats19_parquet
  DIRECTORY = (ENABLE = TRUE);

-- After running scripts/load_snowflake.py, verify:
-- SELECT table_name, row_count FROM information_schema.tables
--   WHERE table_schema = 'STATS19' ORDER BY table_name;
