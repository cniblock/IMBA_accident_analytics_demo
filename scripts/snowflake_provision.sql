-- =============================================================================
-- STATS19 Snowflake provisioning — Zebra Law / IMBA accident analytics
-- =============================================================================
-- Run in Snowsight. Typical order:
--   1. Part A as SECURITYADMIN (role + user)
--   2. Part B as SYSADMIN (warehouse, database, schema, stage)
--   3. Part C as SECURITYADMIN or SYSADMIN (grants)
--   4. Part D — verification (run as the loader user/role)
--
-- Maps to client env vars used by scripts/load_snowflake.py:
--
--   SNOWFLAKE_ACCOUNT    Not set in SQL. Snowsight → Admin → Accounts.
--                        Example: XY12345-UK_AZURE
--   SNOWFLAKE_USER       Part A — existing corporate user or new user below
--   SNOWFLAKE_PASSWORD   Set outside Snowflake (PowerShell $env:...) or SSO
--   SNOWFLAKE_WAREHOUSE  Part B — STATS19_WH (or grant USAGE on COMPUTE_WH)
--   SNOWFLAKE_DATABASE   Part B — ANALYTICS
--   SNOWFLAKE_SCHEMA     Part B — STATS19
--   SNOWFLAKE_ROLE       Part A — STATS19_LOADER
--
-- Loader needs: USAGE on warehouse; USAGE + CREATE on schema; READ/WRITE on
-- stage; ability to CREATE/DROP/REPLACE tables, file formats, and stages.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- CONFIG — edit these values once, then run the script
-- -----------------------------------------------------------------------------

SET stats19_user      = 'IMBADYNAMICS';         -- SNOWFLAKE_USER (login name from Snowsight)
SET stats19_role      = 'STATS19_LOADER';       -- SNOWFLAKE_ROLE (or ACCOUNTADMIN for initial POC)
SET stats19_warehouse = 'COMPUTE_WH';           -- SNOWFLAKE_WAREHOUSE (existing default warehouse)
SET stats19_database  = 'ANALYTICS';            -- SNOWFLAKE_DATABASE
SET stats19_schema    = 'STATS19';              -- SNOWFLAKE_SCHEMA

-- Optional read-only role for dashboard / Streamlit consumers
SET stats19_reader_role = 'STATS19_READER';


-- =============================================================================
-- PART A — SECURITYADMIN: role and user access
-- =============================================================================

USE ROLE SECURITYADMIN;

-- Loader role (runs PUT, COPY INTO, CREATE TABLE from scripts/load_snowflake.py)
CREATE ROLE IF NOT EXISTS IDENTIFIER($stats19_role)
  COMMENT = 'Load and refresh STATS19 Parquet tables in ANALYTICS.STATS19';

-- Read-only role (SELECT on tables after load)
CREATE ROLE IF NOT EXISTS IDENTIFIER($stats19_reader_role)
  COMMENT = 'Read STATS19 analytics tables for dashboards and reporting';

-- Grant loader role to an existing Snowflake user (typical for Zebra SSO users)
-- User must already exist; create in Part A optional block if needed.
GRANT ROLE IDENTIFIER($stats19_role) TO USER IDENTIFIER($stats19_user);

-- Optional: allow other admins to assume the loader role
-- GRANT ROLE IDENTIFIER($stats19_role) TO ROLE SYSADMIN;

-- Optional: create a dedicated password user (skip if using corporate SSO only)
/*
CREATE USER IF NOT EXISTS IDENTIFIER($stats19_user)
  PASSWORD = 'CHANGE_ME_ON_FIRST_LOGIN'
  MUST_CHANGE_PASSWORD = TRUE
  DEFAULT_ROLE = $stats19_role
  DEFAULT_WAREHOUSE = $stats19_warehouse
  DEFAULT_NAMESPACE = $stats19_database || '.' || $stats19_schema
  COMMENT = 'STATS19 Parquet loader service account';
GRANT ROLE IDENTIFIER($stats19_role) TO USER IDENTIFIER($stats19_user);
*/


-- =============================================================================
-- PART B — SYSADMIN: warehouse, database, schema, file format, stage
-- =============================================================================

USE ROLE SYSADMIN;

-- Skip this block if COMPUTE_WH already exists (your default warehouse).
-- CREATE WAREHOUSE IF NOT EXISTS IDENTIFIER($stats19_warehouse)
--   WAREHOUSE_SIZE      = 'XSMALL'
--   ...

CREATE DATABASE IF NOT EXISTS IDENTIFIER($stats19_database)
  COMMENT = 'Zebra analytics databases including STATS19 road casualty data';

USE DATABASE IDENTIFIER($stats19_database);

CREATE SCHEMA IF NOT EXISTS IDENTIFIER($stats19_schema)
  COMMENT = 'STATS19 dashboard views and optional raw tables';

USE SCHEMA IDENTIFIER($stats19_schema);

CREATE OR REPLACE FILE FORMAT stats19_parquet
  TYPE = PARQUET
  COMPRESSION = AUTO
  COMMENT = 'Parquet files from parquet_cache/ (prepare_data.py)';

CREATE OR REPLACE STAGE stats19_stage
  FILE_FORMAT = stats19_parquet
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Internal stage for PUT from scripts/load_snowflake.py';


-- =============================================================================
-- PART C — Grants for loader and reader roles
-- =============================================================================
-- IMPORTANT: Re-run the CONFIG SET lines (top of file) in this worksheet first.
-- Snowflake session variables do not persist across worksheets/sessions.
--
-- If Part A was skipped, either run Part A first OR use ACCOUNTADMIN as loader
-- role and skip Part C entirely (ACCOUNTADMIN already has full access).

USE ROLE ACCOUNTADMIN;

-- Warehouse
GRANT USAGE, OPERATE ON WAREHOUSE IDENTIFIER($stats19_warehouse)
  TO ROLE IDENTIFIER($stats19_role);

GRANT USAGE ON WAREHOUSE IDENTIFIER($stats19_warehouse)
  TO ROLE IDENTIFIER($stats19_reader_role);

-- Database
GRANT USAGE ON DATABASE IDENTIFIER($stats19_database)
  TO ROLE IDENTIFIER($stats19_role);

GRANT USAGE ON DATABASE IDENTIFIER($stats19_database)
  TO ROLE IDENTIFIER($stats19_reader_role);

-- Schema — one privilege type per GRANT (avoids compilation errors)
USE DATABASE IDENTIFIER($stats19_database);

GRANT USAGE ON SCHEMA IDENTIFIER($stats19_schema)
  TO ROLE IDENTIFIER($stats19_role);

GRANT CREATE TABLE ON SCHEMA IDENTIFIER($stats19_schema)
  TO ROLE IDENTIFIER($stats19_role);

GRANT CREATE STAGE ON SCHEMA IDENTIFIER($stats19_schema)
  TO ROLE IDENTIFIER($stats19_role);

GRANT CREATE FILE FORMAT ON SCHEMA IDENTIFIER($stats19_schema)
  TO ROLE IDENTIFIER($stats19_role);

GRANT USAGE ON SCHEMA IDENTIFIER($stats19_schema)
  TO ROLE IDENTIFIER($stats19_reader_role);

-- Stage and file format (use schema context — do not chain IDENTIFIER().IDENTIFIER())
USE SCHEMA IDENTIFIER($stats19_schema);

GRANT READ, WRITE ON STAGE stats19_stage
  TO ROLE IDENTIFIER($stats19_role);

GRANT USAGE ON FILE FORMAT stats19_parquet
  TO ROLE IDENTIFIER($stats19_role);

GRANT USAGE ON STAGE stats19_stage
  TO ROLE IDENTIFIER($stats19_reader_role);

-- Tables (safe even when no tables exist yet)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA IDENTIFIER($stats19_schema)
  TO ROLE IDENTIFIER($stats19_role);

GRANT SELECT ON ALL TABLES IN SCHEMA IDENTIFIER($stats19_schema)
  TO ROLE IDENTIFIER($stats19_reader_role);

GRANT SELECT ON FUTURE TABLES IN SCHEMA IDENTIFIER($stats19_schema)
  TO ROLE IDENTIFIER($stats19_reader_role);


-- =============================================================================
-- PART D — Verification (run as loader user or USE ROLE STATS19_LOADER)
-- =============================================================================

USE ROLE IDENTIFIER($stats19_role);
USE WAREHOUSE IDENTIFIER($stats19_warehouse);
USE DATABASE IDENTIFIER($stats19_database);
USE SCHEMA IDENTIFIER($stats19_schema);

SELECT CURRENT_USER()   AS snowflake_user,
       CURRENT_ROLE()   AS snowflake_role,
       CURRENT_WAREHOUSE() AS warehouse,
       CURRENT_DATABASE()  AS database,
       CURRENT_SCHEMA()    AS schema;

SHOW GRANTS TO ROLE IDENTIFIER($stats19_role);

SHOW STAGES;
SHOW FILE FORMATS;

-- After running: python scripts/load_snowflake.py --views-only
/*
SELECT table_name, row_count, bytes
FROM information_schema.tables
WHERE table_catalog = 'ANALYTICS'
  AND table_schema = 'STATS19'
ORDER BY table_name;

SELECT 'COLLISION_VIEW' AS tbl, COUNT(*) AS rows FROM collision_view
UNION ALL SELECT 'VEHICLE_VIEW', COUNT(*) FROM vehicle_view
UNION ALL SELECT 'CASUALTY_VIEW', COUNT(*) FROM casualty_view
UNION ALL SELECT 'CASUALTY_PERSON_VIEW', COUNT(*) FROM casualty_person_view;
*/


-- =============================================================================
-- CLIENT SETUP (PowerShell) — hand to the person running the loader
-- =============================================================================
/*
  cd "path\to\IMBA_accident_analytics_demo"

  $env:SNOWFLAKE_ACCOUNT   = "YOUR_ACCOUNT_LOCATOR"  -- Admin → Accounts (copy locator)
  $env:SNOWFLAKE_USER      = "IMBADYNAMICS"
  $env:SNOWFLAKE_PASSWORD  = "..."                   -- your Snowflake password
  $env:SNOWFLAKE_WAREHOUSE = "COMPUTE_WH"
  $env:SNOWFLAKE_DATABASE  = "ANALYTICS"
  $env:SNOWFLAKE_SCHEMA    = "STATS19"
  $env:SNOWFLAKE_ROLE      = "ACCOUNTADMIN"          -- or STATS19_LOADER after Part A+C

  pip install -r requirements-snowflake.txt
  python scripts/prepare_data.py          # if parquet_cache/ is empty
  python scripts/load_snowflake.py --views-only
*/
