-- =============================================================================
-- oee_performance.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Compute shift-level OEE Performance (P) for each component.
--
-- PRIMARY METHOD — Unit-Count (locked Day 2, CONTEXT.md):
--   P = (Ideal Cycle Time × Total Units Produced) / Run Time
--   P ∈ [0.0, 1.0]  (can theoretically exceed 1.0 if data is wrong — clamped below)
--
-- FALLBACK METHOD — RPM Proxy:
--   P_rpm = actual_rpm / rated_rpm
--   Used when production_counts data is unavailable (early simulation phases).
--   Both methods are shown in this query; the primary method takes precedence.
--
-- INTERPRETATION:
--   P < 1.0 indicates the component is producing fewer units (or at lower speed)
--   than its nameplate design target — a Performance Loss.
--   Primary causes in our pipeline (Six Big Losses mapping):
--     Loss 3 (Minor Stops):  Coupling micro-stops from misalignment
--     Loss 4 (Reduced Speed): Motor Housing thermal derating; Shaft imbalance
--
-- SERIES BOTTLENECK LAW (locked Day 2, CONTEXT.md):
--   P_sys = MIN(P_1, P_2, P_3, P_4, P_5)
--   The slowest component constrains total throughput (Goldratt Theory of Constraints).
--   See oee_system_series.sql for the MIN aggregation.
--
-- SQL DATA SOURCES:
--   production_shifts  — shift_id, shift_date, shift_label, planned_duration_min
--   production_counts  — total_units, ideal_cycle_time_min
--   downtime_events    — duration_min (to derive run_time_min)
--   sensor_readings    — rpm, rpm_rated (fallback RPM method)
--   components         — component_name
--
-- OUTPUT COLUMNS:
--   component_id, component_name, shift_id, shift_date, shift_label,
--   total_units, ideal_cycle_time_min, run_time_min,
--   performance_units, performance_rpm (fallback),
--   performance, performance_pct, performance_status
-- =============================================================================

-- CTE 1: Pre-compute run_time_min for each component+shift (same logic as oee_availability.sql)
-- This avoids re-joining the same tables in a correlated subquery.
WITH run_times AS (
    SELECT
        ps.shift_id,
        ps.component_id,
        ps.planned_duration_min,
        -- run_time = planned_duration - all non-PM downtime
        ps.planned_duration_min - COALESCE(SUM(
            CASE
                WHEN de.downtime_category != 'planned_maintenance'
                THEN de.duration_min
                ELSE 0.0
            END
        ), 0.0) AS run_time_min
    FROM production_shifts ps
    LEFT JOIN downtime_events de
        ON  de.shift_id     = ps.shift_id
        AND de.component_id = ps.component_id
    GROUP BY
        ps.shift_id,
        ps.component_id,
        ps.planned_duration_min
),

-- CTE 2: Average RPM per shift per component (fallback Performance method)
-- Rationale: sensor_readings records RPM at each reading interval.
-- We average across the shift window matching the shift's planned_start_ts / planned_end_ts.
rpm_averages AS (
    SELECT
        sr.component_id,
        ps.shift_id,
        AVG(sr.rpm)       AS avg_rpm,
        AVG(sr.rpm_rated) AS avg_rpm_rated   -- should be constant per component
    FROM sensor_readings sr
    INNER JOIN production_shifts ps
        ON  sr.component_id = ps.component_id
        AND sr.ts BETWEEN ps.planned_start_ts AND ps.planned_end_ts
    WHERE sr.rpm IS NOT NULL
      AND sr.rpm_rated IS NOT NULL
    GROUP BY
        sr.component_id,
        ps.shift_id
)

SELECT
    ps.component_id,
    c.component_name,
    ps.shift_id,
    ps.shift_date,
    ps.shift_label,

    -- Unit-count inputs
    pc.total_units,
    pc.ideal_cycle_time_min,
    rt.run_time_min,

    -- PRIMARY: Unit-count Performance
    -- P = (ideal_cycle_time_min × total_units) / run_time_min
    -- Clamped to 1.0 maximum (P > 1.0 indicates a data entry error or OT production)
    CASE
        WHEN rt.run_time_min > 0.0 AND pc.total_units IS NOT NULL
        THEN MIN(
            1.0,
            (pc.ideal_cycle_time_min * pc.total_units) / rt.run_time_min
        )
        ELSE NULL
    END AS performance_units,

    -- FALLBACK: RPM-proxy Performance
    -- P_rpm = avg_rpm / avg_rpm_rated
    -- Used when production_counts is not yet populated.
    CASE
        WHEN ra.avg_rpm_rated > 0.0 AND ra.avg_rpm IS NOT NULL
        THEN MIN(1.0, ra.avg_rpm / ra.avg_rpm_rated)
        ELSE NULL
    END AS performance_rpm,

    -- FINAL performance value: prefer unit-count; fall back to RPM proxy
    CASE
        WHEN rt.run_time_min > 0.0 AND pc.total_units IS NOT NULL
        THEN MIN(
            1.0,
            (pc.ideal_cycle_time_min * pc.total_units) / rt.run_time_min
        )
        WHEN ra.avg_rpm_rated > 0.0 AND ra.avg_rpm IS NOT NULL
        THEN MIN(1.0, ra.avg_rpm / ra.avg_rpm_rated)
        ELSE NULL
    END AS performance,

    -- Performance percentage
    ROUND(
        100.0 * CASE
            WHEN rt.run_time_min > 0.0 AND pc.total_units IS NOT NULL
            THEN MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units) / rt.run_time_min)
            WHEN ra.avg_rpm_rated > 0.0 AND ra.avg_rpm IS NOT NULL
            THEN MIN(1.0, ra.avg_rpm / ra.avg_rpm_rated)
            ELSE NULL
        END,
        2
    ) AS performance_pct,

    -- Performance status tier (same thresholds as Availability — Day 2 lock)
    CASE
        WHEN CASE
            WHEN rt.run_time_min > 0.0 AND pc.total_units IS NOT NULL
            THEN MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units) / rt.run_time_min)
            WHEN ra.avg_rpm_rated > 0.0 THEN MIN(1.0, ra.avg_rpm / ra.avg_rpm_rated)
            ELSE NULL
        END >= 0.85 THEN 'WORLD_CLASS'
        WHEN CASE
            WHEN rt.run_time_min > 0.0 AND pc.total_units IS NOT NULL
            THEN MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units) / rt.run_time_min)
            WHEN ra.avg_rpm_rated > 0.0 THEN MIN(1.0, ra.avg_rpm / ra.avg_rpm_rated)
            ELSE NULL
        END >= 0.75 THEN 'ACCEPTABLE'
        WHEN CASE
            WHEN rt.run_time_min > 0.0 AND pc.total_units IS NOT NULL
            THEN MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units) / rt.run_time_min)
            WHEN ra.avg_rpm_rated > 0.0 THEN MIN(1.0, ra.avg_rpm / ra.avg_rpm_rated)
            ELSE NULL
        END >= 0.65 THEN 'ALERT'
        WHEN CASE
            WHEN rt.run_time_min > 0.0 AND pc.total_units IS NOT NULL
            THEN MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units) / rt.run_time_min)
            WHEN ra.avg_rpm_rated > 0.0 THEN MIN(1.0, ra.avg_rpm / ra.avg_rpm_rated)
            ELSE NULL
        END IS NOT NULL THEN 'CRITICAL'
        ELSE 'NO_DATA'
    END AS performance_status,

    -- Flag indicating which method was used (for Power BI tooltip / data lineage)
    CASE
        WHEN rt.run_time_min > 0.0 AND pc.total_units IS NOT NULL THEN 'unit_count'
        WHEN ra.avg_rpm IS NOT NULL                                THEN 'rpm_proxy'
        ELSE 'unavailable'
    END AS performance_method

FROM production_shifts ps
INNER JOIN components c
    ON c.component_id = ps.component_id
INNER JOIN run_times rt
    ON  rt.shift_id     = ps.shift_id
    AND rt.component_id = ps.component_id
LEFT JOIN production_counts pc
    ON  pc.shift_id     = ps.shift_id
    AND pc.component_id = ps.component_id
LEFT JOIN rpm_averages ra
    ON  ra.shift_id     = ps.shift_id
    AND ra.component_id = ps.component_id

ORDER BY
    ps.shift_date ASC,
    ps.component_id ASC;

-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- 1. The run_time_min CTE mirrors oee_availability.sql logic exactly.
--    In oee_composite.sql, both are joined so run_time is computed once.
-- 2. MIN(1.0, ...) clamping is defensive — production_counts simulation must
--    enforce P <= 1.0 at data generation time (simulate.py) anyway.
-- 3. The performance_method column is a data-quality tracer, not a KPI.
--    Power BI can use it to colour-code "estimated" vs "measured" cells.
-- 4. rpm_rated should be constant per component; the AVG is a safety measure
--    in case of sensor metadata updates mid-run.
-- =============================================================================
