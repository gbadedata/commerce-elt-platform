-- ============================================================
-- Run as ACCOUNTADMIN after files 01 and 02.
-- Access for the data quality flow and a key-pair service user.
-- Files 03 and 04 are for the S3 route and are not needed here.
-- ============================================================
USE ROLE ACCOUNTADMIN;

-- The loader creates raw tables and reads the shared file format.
CREATE FILE FORMAT IF NOT EXISTS COMMERCE_DB.RAW.CSV_FORMAT
    TYPE = CSV
    FIELD_DELIMITER = ','
    SKIP_HEADER = 1
    NULL_IF = ('', 'NULL', 'null', 'None')
    EMPTY_FIELD_AS_NULL = TRUE
    DATE_FORMAT = AUTO
    TIMESTAMP_FORMAT = AUTO
    FIELD_OPTIONALLY_ENCLOSED_BY = '"';

GRANT USAGE ON FILE FORMAT COMMERCE_DB.RAW.CSV_FORMAT TO ROLE LOADER_ROLE;

-- Raw tables are recreated on every load, so existing-table grants are not enough.
GRANT SELECT ON FUTURE TABLES IN SCHEMA COMMERCE_DB.RAW TO ROLE TRANSFORMER_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA COMMERCE_DB.MARTS TO ROLE REPORTER_ROLE;

-- Reporting can read trusted marts and quality results, but not staging, where personal data lives.
GRANT USAGE ON SCHEMA COMMERCE_DB.MONITORING TO ROLE REPORTER_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA COMMERCE_DB.MONITORING TO ROLE REPORTER_ROLE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA COMMERCE_DB.MONITORING TO ROLE REPORTER_ROLE;
-- A role needs a warehouse to run queries. A real setup would give reporting its own.
GRANT USAGE ON WAREHOUSE TRANSFORM_WH TO ROLE REPORTER_ROLE;

-- Service user with key-pair authentication. Paste the public key body, without the
-- BEGIN and END lines, from the file created in docs/RUNBOOK_SNOWFLAKE.md.
CREATE USER IF NOT EXISTS COMMERCE_SVC
    TYPE = SERVICE
    RSA_PUBLIC_KEY = '<PASTE_PUBLIC_KEY_BODY>'
    DEFAULT_ROLE = TRANSFORMER_ROLE
    DEFAULT_WAREHOUSE = TRANSFORM_WH
    COMMENT = 'Runs the load and data quality flow';

GRANT ROLE LOADER_ROLE TO USER COMMERCE_SVC;
GRANT ROLE TRANSFORMER_ROLE TO USER COMMERCE_SVC;

-- New users get every granted role active by default through secondary roles.
-- Turning that off means each step of the pipeline really runs with one role only.
ALTER USER COMMERCE_SVC SET DEFAULT_SECONDARY_ROLES = ();
