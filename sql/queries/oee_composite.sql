-- =============================================================================
-- oee_composite.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Compute the full, composite OEE score (A × P × Q) at shift level
--   for each component.  This is the single-number KPI dashboard query.
--
-- FORMULA (locked Day 2, CONTEXT.md):
--   OEE = Availability × Performance × Quality
--
--   A = (planned_duration_min − total_downtime_min) / planned_duration_min
--   P = (ideal_cycle_time_min × total_units) / run_time_min   [unit-count primary]
--   Q = good_units / total_units
--
-- OEE STATUS TIERS (locked Day 2):
--   >= 85% → WORLD_CLASS   85% is the industry benchmark for excellent plants
--   75-84% → ACCEPTABLE    Most competitive plants operate in this range
--   65-74% → ALERT         Below competitive; targeted improvement needed
--   <  65% → CRITICAL      Significant loss — intervention required
--
-- DESIGN NOTE:
--   All three factors (A, P, Q) are computed inline in a single pass using CTEs
--   rather than referencing the individual query files.  This is intentional:
--   - oee_availability.sql / oee_performance.sql / oee_quality.sql are each
--     stand-alone diagnostic queries for Power BI pages.
--   - This composite file is the master KPI query for the Fleet Overview page.
--   Keeping them separate avoids view creation DDL and works in both SQLite and SSMS.
--
-- SQL DATA SOURCES:
--   production_shifts, downtime_events, production_counts,
--   sensor_readings (RPM fallback), components
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 1: Downtime aggregation per component per shift
-- ─────────────────────────────────────────────────────────────────────────────
WITH downtime_agg AS (
    SELECT
        de.shift_id,
        de.component_id,
        SUM(CASE WHEN de.downtime_category != 'planned_maintenance'
                 THEN de.duration_min ELSE 0.0 END) AS total_downtime_min
    FROM downtime_events de
    GROUP BY de.shift_id, de.component_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 2: Run time per component per shift
-- ─────────────────────────────────────────────────────────────────────────────
shift_run_time AS (
    SELECT
        ps.shift_id,
        ps.component_id,
        ps.planned_duration_min,
        ps.planned_duration_min - COALESCE(da.total_downtime_min, 0.0) AS run_time_min
    FROM production_shifts ps
    LEFT JOIN downtime_agg da
        ON  da.shift_id     = ps.shift_id
        AND da.component_id = ps.component_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 3: RPM averages per component per shift (Performance fallback)
-- ─────────────────────────────────────────────────────────────────────────────
rpm_avg AS (
    SELECT
        sr.component_id,
        ps.shift_id,
        AVG(sr.rpm)       AS avg_rpm,
        AVG(sr.rpm_rated) AS avg_rpm_rated
    FROM sensor_readings sr
    INNER JOIN production_shifts ps
        ON  sr.component_id = ps.component_id
        AND sr.ts BETWEEN ps.planned_start_ts AND ps.planned_end_ts
    WHERE sr.rpm IS NOT NULL AND sr.rpm_rated IS NOT NULL
    GROUP BY sr.component_id, ps.shift_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 4: Individual OEE factor computation per shift per component
-- ─────────────────────────────────────────────────────────────────────────────
oee_factors AS (
    SELECT
        ps.component_id,
        c.component_name,
        ps.shift_id,
        ps.shift_date,
        ps.shift_label,

        -- ── AVAILABILITY ─────────────────────────────────────────────────────
        ps.planned_duration_min                          AS planned_duration_min,
        COALESCE(da.total_downtime_min, 0.0)             AS total_downtime_min,
        srt.run_time_min,

        -- A = run_time / planned_duration
        srt.run_time_min / NULLIF(ps.planned_duration_min, 0.0) AS availability,

        -- ── PERFORMANCE ──────────────────────────────────────────────────────
        pc.total_units,
        pc.ideal_cycle_time_min,

        -- P (unit-count primary; RPM fallback)
        CASE
            WHEN srt.run_time_min > 0.0 AND pc.total_units IS NOT NULL
            THEN MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units) / srt.run_time_min)
            WHEN ra.avg_rpm_rated > 0.0 AND ra.avg_rpm IS NOT NULL
            THEN MIN(1.0, ra.avg_rpm / ra.avg_rpm_rated)
            ELSE NULL
        END AS performance,

        -- ── QUALITY ──────────────────────────────────────────────────────────
        pc.good_units,
        pc.defective_units,
        pc.rework_units,

        -- Q = good / total
        CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0) AS quality

    FROM production_shifts ps
    INNER JOIN components c
        ON c.component_id = ps.component_id
    LEFT JOIN downtime_agg da
        ON  da.shift_id     = ps.shift_id
        AND da.component_id = ps.component_id
    INNER JOIN shift_run_time srt
        ON  srt.shift_id     = ps.shift_id
        AND srt.component_id = ps.component_id
    LEFT JOIN production_counts pc
        ON  pc.shift_id     = ps.shift_id
        AND pc.component_id = ps.component_id
    LEFT JOIN rpm_avg ra
        ON  ra.shift_id     = ps.shift_id
        AND ra.component_id = ps.component_id
)

-- ─────────────────────────────────────────────────────────────────────────────
-- FINAL SELECT: Composite OEE with status tier
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    f.component_id,
    f.component_name,
    f.shift_id,
    f.shift_date,
    f.shift_label,

    -- Individual OEE factors
    ROUND(f.availability * 100.0, 2) AS availability_pct,
    ROUND(f.performance  * 100.0, 2) AS performance_pct,
    ROUND(f.quality      * 100.0, 2) AS quality_pct,

    -- Raw inputs for drill-down
    f.planned_duration_min,
    f.total_downtime_min,
    f.run_time_min,
    f.total_units,
    f.good_units,
    f.defective_units,
    f.rework_units,

    -- Composite OEE score
    -- NULL if any factor is NULL (production data missing for this shift)
    f.availability * f.performance * f.quality AS oee,

    ROUND(f.availability * f.performance * f.quality * 100.0, 2) AS oee_pct,

    -- OEE Status tier (locked Day 2)
    CASE
        WHEN f.availability * f.performance * f.quality >= 0.85 THEN 'WORLD_CLASS'
        WHEN f.availability * f.performance * f.quality >= 0.75 THEN 'ACCEPTABLE'
        WHEN f.availability * f.performance * f.quality >= 0.65 THEN 'ALERT'
        WHEN f.availability * f.performance * f.quality IS NOT NULL THEN 'CRITICAL'
        ELSE 'NO_DATA'
    END AS oee_status,

    -- OEE loss decomposition (percentage points lost per factor)
    -- Used by Power BI waterfall chart to show A-loss, P-loss, Q-loss contributions
    ROUND((1.0 - f.availability) * 100.0, 2) AS loss_availability_pp,
    ROUND(f.availability * (1.0 - f.performance) * 100.0, 2) AS loss_performance_pp,
    ROUND(f.availability * f.performance * (1.0 - f.quality) * 100.0, 2) AS loss_quality_pp

FROM oee_factors f

ORDER BY
    f.shift_date ASC,
    f.component_id ASC;

-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- 1. Power BI Fleet Overview page (Page 1) connects to this query result.
--    The oee_pct and oee_status columns drive the KPI card and gauge visuals.
-- 2. The loss decomposition columns (loss_*_pp) feed the OEE waterfall chart
--    in conjunction with six_big_losses.sql for granular loss attribution.
-- 3. IMPORTANT: shifts where production_counts has no row will show availability
--    and (if RPM data exists) performance, but quality will be NULL → oee NULL.
--    This is the correct behaviour: we cannot claim a quality score without
--    inspection data. Power BI should filter on oee_status != 'NO_DATA' for KPIs.
-- 4. This query can be saved as a VIEW in SQL Server for Power BI DirectQuery mode:
--    CREATE VIEW vw_oee_composite AS <this SELECT>;
-- =============================================================================
