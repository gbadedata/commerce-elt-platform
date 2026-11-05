-- ============================================================
-- Optional: email the owner when the latest run has a critical failure.
-- Requires a notification integration and a verified email address.
-- Run as ACCOUNTADMIN, replacing <YOUR_VERIFIED_EMAIL>.
-- ============================================================
USE ROLE ACCOUNTADMIN;

CREATE NOTIFICATION INTEGRATION IF NOT EXISTS DQ_EMAIL_INT
    TYPE = EMAIL
    ENABLED = TRUE
    ALLOWED_RECIPIENTS = ('<YOUR_VERIFIED_EMAIL>');

CREATE OR REPLACE ALERT COMMERCE_DB.MONITORING.DQ_CRITICAL_ALERT
    WAREHOUSE = TRANSFORM_WH
    SCHEDULE = '60 MINUTE'
    IF (EXISTS (
        SELECT 1
        FROM COMMERCE_DB.MONITORING.V_DQ_LATEST
        WHERE DQ_SEVERITY = 'critical' AND STATUS <> 'pass'
    ))
    THEN CALL SYSTEM$SEND_EMAIL(
        'DQ_EMAIL_INT',
        '<YOUR_VERIFIED_EMAIL>',
        'Commerce data quality: critical failure',
        'Query COMMERCE_DB.MONITORING.V_DQ_LATEST for the failing rules and owners.'
    );

-- An alert is created suspended. Resume it only when you want it running,
-- and suspend it afterwards so that it stops using warehouse credits.
-- ALTER ALERT COMMERCE_DB.MONITORING.DQ_CRITICAL_ALERT RESUME;
-- ALTER ALERT COMMERCE_DB.MONITORING.DQ_CRITICAL_ALERT SUSPEND;
