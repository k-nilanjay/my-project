-- =============================================================================
-- anomaly_rate_by_sensor.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Compute anomaly rate per sensor — the fraction of readings that exceed
--   the ISO alarm threshold (is_anomaly = 1 in sensor_readings).
--
-- FORMULA:
--   anomaly_rate = SUM(is_anomaly) / COUNT(*) per sensor
--   Units: dimensionless ratio ∈ [0.0, 1.0]
--
-- ANOMALY DEFINITION (locked Day 9, etl.py):
--   is_anomaly = 1  when value >= iso_alarm_threshold (from SENSOR_THRESHOLDS dict)
--   is_anomaly = 0  when value <  iso_alarm_threshold OR alarm is None (RPM sensor)
--
-- ISO ZONE DISTRIBUTION (for vibration sensors only):
--   Zone A: 0 – 2.3 mm/s   (new / acceptable)
--   Zone B: 2.3 – 4.5      (acceptable long-term)
--   Zone C: 4.5 – 7.1      (alarm — is_anomaly = 1)
--   Zone D: > 7.1           (danger — is_anomaly = 1)
--   Zone distribution is only shown for vibration sensors (sensor_ids 11,21,32,41,51).
--
-- DATA SOURCES:
--   sensor_readings — is_anomaly, iso_zone, value, sensor_id, component_id
--   sensors         — sensor_type, iso_alarm_threshold, iso_danger_threshold,
--                     unit_of_measure
--   components      — component_name
-- =============================================================================

SELECT
    s.sensor_id,
    c.component_name,
    c.component_id,
    s.sensor_type,
    s.unit_of_measure,
    s.iso_alarm_threshold,
    s.iso_danger_threshold,

    -- Total readings for this sensor
    COUNT(sr.reading_id)                                        AS total_readings,

    -- Anomaly count (value >= alarm threshold, computed at ETL load time)
    SUM(sr.is_anomaly)                                          AS n_anomalies,

    -- Danger zone count (value >= danger threshold)
    SUM(CASE
        WHEN s.iso_danger_threshold IS NOT NULL
         AND sr.value >= s.iso_danger_threshold
        THEN 1 ELSE 0
    END)                                                        AS n_danger_zone,

    -- Anomaly rate [0.0, 1.0] — fraction of readings above alarm threshold
    ROUND(
        CAST(SUM(sr.is_anomaly) AS FLOAT) / NULLIF(COUNT(sr.reading_id), 0),
        4
    )                                                           AS anomaly_rate,

    -- Anomaly percentage (for Power BI gauge / card visual)
    ROUND(
        100.0 * CAST(SUM(sr.is_anomaly) AS FLOAT) / NULLIF(COUNT(sr.reading_id), 0),
        2
    )                                                           AS anomaly_pct,

    -- Danger rate — fraction of readings above danger threshold
    ROUND(
        100.0 * CAST(SUM(CASE
            WHEN s.iso_danger_threshold IS NOT NULL
             AND sr.value >= s.iso_danger_threshold
            THEN 1 ELSE 0
        END) AS FLOAT) / NULLIF(COUNT(sr.reading_id), 0),
        2
    )                                                           AS danger_rate_pct,

    -- Descriptive statistics of the sensor readings
    ROUND(AVG(sr.value), 4)                                     AS avg_value,
    ROUND(MIN(sr.value), 4)                                     AS min_value,
    ROUND(MAX(sr.value), 4)                                     AS max_value,

    -- ISO Zone distribution (vibration sensors only — NULL for non-vibration)
    -- Vibration sensor IDs: 11, 21, 32, 41, 51
    ROUND(
        100.0 * SUM(CASE WHEN sr.iso_zone = 'A' THEN 1 ELSE 0 END)
              / NULLIF(COUNT(sr.reading_id), 0),
        1
    )                                                           AS zone_a_pct,
    ROUND(
        100.0 * SUM(CASE WHEN sr.iso_zone = 'B' THEN 1 ELSE 0 END)
              / NULLIF(COUNT(sr.reading_id), 0),
        1
    )                                                           AS zone_b_pct,
    ROUND(
        100.0 * SUM(CASE WHEN sr.iso_zone = 'C' THEN 1 ELSE 0 END)
              / NULLIF(COUNT(sr.reading_id), 0),
        1
    )                                                           AS zone_c_pct,
    ROUND(
        100.0 * SUM(CASE WHEN sr.iso_zone = 'D' THEN 1 ELSE 0 END)
              / NULLIF(COUNT(sr.reading_id), 0),
        1
    )                                                           AS zone_d_pct,

    -- Anomaly risk status label for Power BI conditional formatting
    -- Thresholds chosen for 365-day industrial simulation context
    CASE
        WHEN s.iso_alarm_threshold IS NULL
            THEN 'NO_THRESHOLD'
        WHEN CAST(SUM(sr.is_anomaly) AS FLOAT) / NULLIF(COUNT(sr.reading_id), 0) >= 0.20
            THEN 'HIGH_RISK'
        WHEN CAST(SUM(sr.is_anomaly) AS FLOAT) / NULLIF(COUNT(sr.reading_id), 0) >= 0.10
            THEN 'ELEVATED'
        WHEN CAST(SUM(sr.is_anomaly) AS FLOAT) / NULLIF(COUNT(sr.reading_id), 0) >= 0.05
            THEN 'MODERATE'
        WHEN CAST(SUM(sr.is_anomaly) AS FLOAT) / NULLIF(COUNT(sr.reading_id), 0) > 0.0
            THEN 'LOW'
        ELSE 'NOMINAL'
    END                                                         AS anomaly_status,

    -- Cascade-flagged anomaly count: readings that are anomalies AND part of a cascade
    -- Useful for isolating collateral damage from upstream failures
    SUM(CASE
        WHEN sr.is_anomaly = 1 AND sr.cascade_flag = 1
        THEN 1 ELSE 0
    END)                                                        AS cascade_anomalies,

    -- Non-cascade anomaly count: intrinsic failures not caused by upstream events
    SUM(CASE
        WHEN sr.is_anomaly = 1 AND sr.cascade_flag = 0
        THEN 1 ELSE 0
    END)                                                        AS intrinsic_anomalies

FROM sensor_readings sr
INNER JOIN sensors s
    ON s.sensor_id = sr.sensor_id
INNER JOIN components c
    ON c.component_id = sr.component_id

GROUP BY
    s.sensor_id,
    c.component_name,
    c.component_id,
    s.sensor_type,
    s.unit_of_measure,
    s.iso_alarm_threshold,
    s.iso_danger_threshold

ORDER BY
    -- Highest anomaly rate first — priority sorting for maintenance review
    anomaly_rate DESC,
    c.component_id ASC;

-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- 1. RPM sensor (sensor_id 22, Shaft) has iso_alarm_threshold = NULL.
--    is_anomaly is always 0 for RPM. anomaly_status = 'NO_THRESHOLD'.
-- 2. Zone percentages (zone_a_pct to zone_d_pct) are only meaningful for vibration
--    sensors (IDs 11, 21, 32, 41, 51) where iso_zone is computed at ETL load time.
--    For non-vibration sensors, all zone percentages will be 0.0 (no zone assigned).
-- 3. cascade_anomalies vs intrinsic_anomalies split is key for root-cause analysis:
--    - cascade_anomalies: excess vibration caused by upstream failures (not the sensor's
--      own degradation) — shown as elevated readings from Day 6 cascade_boost logic
--    - intrinsic_anomalies: the component's own wear/degradation
-- 4. For Power BI: sort by anomaly_pct descending. Use anomaly_status for traffic-light
--    conditional formatting on the Fleet Overview table.
-- 5. The is_anomaly flag was computed in etl.py at load time using SENSOR_THRESHOLDS
--    (locked Day 9). It matches the iso_alarm_threshold column in the sensors table.
-- =============================================================================
