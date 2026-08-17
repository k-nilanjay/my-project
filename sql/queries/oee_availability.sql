-- =============================================================================
-- oee_availability.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Compute shift-level OEE Availability (A) for each component.
--
-- FORMULA (locked Day 2, CONTEXT.md):
--   A = (Planned Production Time − Total Downtime) / Planned Production Time
--   A ∈ [0.0, 1.0]
--
-- DOWNTIME INCLUSION RULE (locked Day 2):
--   ALL downtime categories are included in A computation:
--     'unplanned_failure'   → Loss 1 (Unplanned Breakdowns)
--     'changeover'          → Loss 2 (Setup & Changeover)
--     'idle'                → Minor idling
--     'cascade_upstream'    → Collateral downtime from upstream failure
--   EXCLUDED: 'planned_maintenance' (already subtracted from planned_duration_min
--             when the shift window is defined — PM windows are not production shifts).
--
-- CASCADE TAGGING NOTE:
--   A component receiving 'cascade_upstream' downtime records its full downtime
--   duration. This correctly reduces system Availability below the failing
--   component's own Availability — consistent with the series reliability model.
--
-- SQL DATA SOURCES:
--   production_shifts  — planned_duration_min (denominator)
--   downtime_events    — duration_min, downtime_category (numerator subtractor)
--   components         — component_name (display)
--
-- OUTPUT COLUMNS:
--   component_id, component_name, shift_id, shift_date, shift_label,
--   planned_duration_min, total_downtime_min, run_time_min,
--   availability, availability_pct, availability_status
-- =============================================================================

SELECT
    ps.component_id,
    c.component_name,
    ps.shift_id,
    ps.shift_date,
    ps.shift_label,
    ps.planned_duration_min,

    -- Total downtime: sum all downtime categories EXCEPT planned_maintenance.
    -- planned_maintenance is scheduled and already outside the planned production window.
    COALESCE(SUM(
        CASE
            WHEN de.downtime_category != 'planned_maintenance'
            THEN de.duration_min
            ELSE 0.0
        END
    ), 0.0) AS total_downtime_min,

    -- Run time = Planned Production Time minus all non-PM downtime
    ps.planned_duration_min - COALESCE(SUM(
        CASE
            WHEN de.downtime_category != 'planned_maintenance'
            THEN de.duration_min
            ELSE 0.0
        END
    ), 0.0) AS run_time_min,

    -- Availability ratio  ∈ [0.0, 1.0]
    -- NULLIF guard prevents division-by-zero if planned_duration_min is somehow 0.
    (
        ps.planned_duration_min - COALESCE(SUM(
            CASE
                WHEN de.downtime_category != 'planned_maintenance'
                THEN de.duration_min
                ELSE 0.0
            END
        ), 0.0)
    ) / NULLIF(ps.planned_duration_min, 0.0) AS availability,

    -- Availability percentage (for Power BI gauge / card visuals)
    ROUND(
        100.0 * (
            ps.planned_duration_min - COALESCE(SUM(
                CASE
                    WHEN de.downtime_category != 'planned_maintenance'
                    THEN de.duration_min
                    ELSE 0.0
                END
            ), 0.0)
        ) / NULLIF(ps.planned_duration_min, 0.0),
        2
    ) AS availability_pct,

    -- OEE status tier (locked Day 2, CONTEXT.md):
    --   >= 85% → WORLD_CLASS   (theoretical benchmark: world-class plants achieve ≥ 85% OEE)
    --   75-84% → ACCEPTABLE    (industry average band; still profitable)
    --   65-74% → ALERT         (below acceptable; warrants investigation)
    --   <  65% → CRITICAL      (significant losses; intervention required)
    --
    -- Availability alone reaching CRITICAL means run time < 65% of planned — severe downtime.
    CASE
        WHEN (
            ps.planned_duration_min - COALESCE(SUM(
                CASE WHEN de.downtime_category != 'planned_maintenance' THEN de.duration_min ELSE 0.0 END
            ), 0.0)
        ) / NULLIF(ps.planned_duration_min, 0.0) >= 0.85 THEN 'WORLD_CLASS'
        WHEN (
            ps.planned_duration_min - COALESCE(SUM(
                CASE WHEN de.downtime_category != 'planned_maintenance' THEN de.duration_min ELSE 0.0 END
            ), 0.0)
        ) / NULLIF(ps.planned_duration_min, 0.0) >= 0.75 THEN 'ACCEPTABLE'
        WHEN (
            ps.planned_duration_min - COALESCE(SUM(
                CASE WHEN de.downtime_category != 'planned_maintenance' THEN de.duration_min ELSE 0.0 END
            ), 0.0)
        ) / NULLIF(ps.planned_duration_min, 0.0) >= 0.65 THEN 'ALERT'
        ELSE 'CRITICAL'
    END AS availability_status

FROM production_shifts ps

-- LEFT JOIN: shifts with zero downtime events must still appear (A = 1.0 for those shifts)
LEFT JOIN downtime_events de
    ON  de.shift_id     = ps.shift_id
    AND de.component_id = ps.component_id

-- Components lookup for display name
INNER JOIN components c
    ON c.component_id = ps.component_id

GROUP BY
    ps.component_id,
    c.component_name,
    ps.shift_id,
    ps.shift_date,
    ps.shift_label,
    ps.planned_duration_min

ORDER BY
    ps.shift_date ASC,
    ps.component_id ASC;

-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- 1. This query is consumed by oee_composite.sql via a CTE or subquery alias.
-- 2. The run_time_min column feeds oee_performance.sql as the denominator for P.
-- 3. For the system-level series aggregation, see oee_system_series.sql.
--    System A = MIN(A_i) over all 5 components per shift_date.
-- 4. SQLite compatibility: COALESCE and NULLIF are supported. No window functions needed here.
-- =============================================================================
