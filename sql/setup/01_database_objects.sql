-- ============================================================
-- STEP 5.3 — Database, schemas, warehouses, resource monitor
-- Run as ACCOUNTADMIN
-- ============================================================

-- Database and schemas
CREATE DATABASE IF NOT EXISTS COMMERCE_DB;

CREATE SCHEMA IF NOT EXISTS COMMERCE_DB.RAW;
CREATE SCHEMA IF NOT EXISTS COMMERCE_DB.STAGING;
CREATE SCHEMA IF NOT EXISTS COMMERCE_DB.INTERMEDIATE;
CREATE SCHEMA IF NOT EXISTS COMMERCE_DB.MARTS;
CREATE SCHEMA IF NOT EXISTS COMMERCE_DB.MONITORING;

-- Two warehouses — one for loading, one for transforming
-- AUTO_SUSPEND = 30 seconds (not the default 600)
-- This is your cost control — a warehouse that idles costs nothing after 30s
CREATE WAREHOUSE IF NOT EXISTS TRANSFORM_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 30
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Used by dbt for all transformation workloads';

CREATE WAREHOUSE IF NOT EXISTS LOAD_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 30
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Used exclusively by Snowpipe for raw ingestion';

-- Resource monitor — hard cap at 5 credits/month (~$10)
-- Alerts at 80%, suspends at 100%
CREATE RESOURCE MONITOR IF NOT EXISTS PORTFOLIO_MONITOR
    WITH CREDIT_QUOTA = 5
    FREQUENCY = MONTHLY
    START_TIMESTAMP = IMMEDIATELY
    TRIGGERS
        ON 80 PERCENT DO NOTIFY
        ON 100 PERCENT DO SUSPEND;

ALTER WAREHOUSE TRANSFORM_WH SET RESOURCE_MONITOR = PORTFOLIO_MONITOR;
ALTER WAREHOUSE LOAD_WH SET RESOURCE_MONITOR = PORTFOLIO_MONITOR;