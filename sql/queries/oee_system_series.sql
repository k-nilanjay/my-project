-- =============================================================================
-- oee_system_series.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Aggregate per-component OEE factors into a single SYSTEM-level OEE score
--   using the series pipeline aggregation rules locked in Day 2.
--
-- SERIES AGGREGATION RULES (locked Day 2, CONTEXT.md):
--   A_sys = MIN(A_1, A_2, A_3, A_4, A_5)
--     Rationale: Series reliability block — weakest-link principle.
--     If any component has A = 0 (fully down), the system cannot produce.
--
--   P_sys = MIN(P_1, P_2, P_3, P_4, P_5)
--     Rationale: Goldratt Theory of Constraints — system throughput is limited
--     by the bottleneck (slowest) component in the chain.
--
--   Q_sys = Q_1 × Q_2 × Q_3 × Q_4 × Q_5
--     Rationale: Independent multiplicative probability —
--     P(unit passes all 5 inspection points) = ∏ P_i(unit passes at i)
--
--   OEE_sys = A_sys × P_sys × Q_sys
--
-- VIVA DEFENCE NOTE:
--   The MIN(A) rule is more conservative than AVG(A). This correctly models the
--   industrial reality that a single breakdown halts the entire series line.
--   AVG(A) would mask the impact of a critical single-component failure.
--
-- BOTTLENECK IDENTIFICATION:
--   The query identifies which component is the Availability bottleneck
--   (lowest A), Performance bottleneck (lowest P), and Quality bottleneck
--   (lowest Q) for each shift date, enabling root-cause targeting.
--
-- SQL DATA SOURCES:
--   production_shifts, downtime_events, production_counts,
--   sensor_readings, components
--   (all three OEE factors are computed inline via CTEs)
--
-- OUTPUT COLUMNS:
--   shift_date,
--   system_availability, system_performance, system_quality, system_oee,
--   system_oee_pct, system_oee_status,
--   bottleneck_availability (component name), bottleneck_performance,
--   bottleneck_quality,
--   n_components_contributing
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 1: Per-component OEE factors per shift_date
-- (Same factor computation as oee_composite.sql — isolated here for clarity)
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

shift_base AS (
    SELECT
        ps.shift_id,
        ps.component_id,
        ps.shift_date,
        ps.planned_duration_min,
        ps.planned_duration_min - COALESCE(da.total_downtime_min, 0.0) AS run_time_min,
        COALESCE(da.total_downtime_min, 0.0) AS total_downtime_min
    FROM production_shifts ps
    LEFT JOIN downtime_agg da
        ON  da.shift_id     = ps.shift_id
        AND da.component_id = ps.component_id
),

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

component_factors AS (
    SELECT
        sb.component_id,
        c.component_name,
        sb.shift_date,
        sb.shift_id,

        -- Availability per component per shift
        sb.run_time_min / NULLIF(sb.planned_duration_min, 0.0) AS availability,

        -- Performance per component per shift
        CASE
            WHEN sb.run_time_min > 0.0 AND pc.total_units IS NOT NULL
            THEN MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units) / sb.run_time_min)
            WHEN ra.avg_rpm_rated > 0.0 AND ra.avg_rpm IS NOT NULL
            THEN MIN(1.0, ra.avg_rpm / ra.avg_rpm_rated)
            ELSE NULL
        END AS performance,

        -- Quality per component per shift
        CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0) AS quality

    FROM shift_base sb
    INNER JOIN components c
        ON c.component_id = sb.component_id
    LEFT JOIN production_counts pc
        ON  pc.shift_id     = sb.shift_id
        AND pc.component_id = sb.component_id
    LEFT JOIN rpm_avg ra
        ON  ra.shift_id     = sb.shift_id
        AND ra.component_id = sb.component_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 2: System-level aggregation per shift_date
-- ─────────────────────────────────────────────────────────────────────────────
system_agg AS (
    SELECT
        shift_date,

        -- Series rules applied here:
        MIN(availability) AS system_availability,   -- weakest-link principle
        MIN(performance)  AS system_performance,    -- throughput bottleneck
        -- Product of all 5 quality scores:
        -- SQLite does not have PRODUCT() aggregate; use EXP(SUM(LN(Q_i))) equivalence.
        -- Guard: if any Q_i is 0, the product is 0 — EXP(SUM(LN)) would return -inf.
        -- Use CASE to handle zero-quality shifts explicitly.
        CASE
            WHEN MIN(quality) = 0 THEN 0.0
            WHEN MIN(quality) IS NULL THEN NULL
            ELSE EXP(SUM(LN(NULLIF(quality, 0.0))))
        END AS system_quality,

        -- Count of components providing data this date
        COUNT(DISTINCT component_id) AS n_components_contributing

    FROM component_factors
    WHERE availability IS NOT NULL   -- exclude shifts with no production data
    GROUP BY shift_date
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 3: Bottleneck component identification per shift_date
-- ─────────────────────────────────────────────────────────────────────────────
-- Identifies which component had the LOWEST A, P, Q on each date.
-- In Power BI: used to annotate the bottleneck on the Fleet Overview page.
bottleneck_availability AS (
    SELECT
        cf.shift_date,
        cf.component_name AS availability_bottleneck,
        cf.availability   AS min_availability
    FROM component_factors cf
    INNER JOIN (
        SELECT shift_date, MIN(availability) AS min_a
        FROM component_factors
        WHERE availability IS NOT NULL
        GROUP BY shift_date
    ) m ON m.shift_date = cf.shift_date AND cf.availability = m.min_a
),

bottleneck_performance AS (
    SELECT
        cf.shift_date,
        cf.component_name AS performance_bottleneck,
        cf.performance    AS min_performance
    FROM component_factors cf
    INNER JOIN (
        SELECT shift_date, MIN(performance) AS min_p
        FROM component_factors
        WHERE performance IS NOT NULL
        GROUP BY shift_date
    ) m ON m.shift_date = cf.shift_date AND cf.performance = m.min_p
),

bottleneck_quality AS (
    SELECT
        cf.shift_date,
        cf.component_name AS quality_bottleneck,
        cf.quality        AS min_quality
    FROM component_factors cf
    INNER JOIN (
        SELECT shift_date, MIN(quality) AS min_q
        FROM component_factors
        WHERE quality IS NOT NULL
        GROUP BY shift_date
    ) m ON m.shift_date = cf.shift_date AND cf.quality = m.min_q
)

-- ─────────────────────────────────────────────────────────────────────────────
-- FINAL SELECT: System OEE with bottleneck annotations
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    sa.shift_date,
    sa.n_components_contributing,

    -- System OEE factors (%)
    ROUND(sa.system_availability * 100.0, 2) AS system_availability_pct,
    ROUND(sa.system_performance  * 100.0, 2) AS system_performance_pct,
    ROUND(sa.system_quality      * 100.0, 2) AS system_quality_pct,

    -- Composite system OEE
    sa.system_availability * sa.system_performance * sa.system_quality AS system_oee,
    ROUND(sa.system_availability * sa.system_performance * sa.system_quality * 100.0, 2) AS system_oee_pct,

    -- System OEE status tier
    CASE
        WHEN sa.system_availability * sa.system_performance * sa.system_quality >= 0.85 THEN 'WORLD_CLASS'
        WHEN sa.system_availability * sa.system_performance * sa.system_quality >= 0.75 THEN 'ACCEPTABLE'
        WHEN sa.system_availability * sa.system_performance * sa.system_quality >= 0.65 THEN 'ALERT'
        WHEN sa.system_availability * sa.system_performance * sa.system_quality IS NOT NULL THEN 'CRITICAL'
        ELSE 'NO_DATA'
    END AS system_oee_status,

    -- Bottleneck components (for drill-down annotation in Power BI)
    ba.availability_bottleneck,
    bp.performance_bottleneck,
    bq.quality_bottleneck,
    ROUND(ba.min_availability * 100.0, 2) AS bottleneck_availability_pct,
    ROUND(bp.min_performance  * 100.0, 2) AS bottleneck_performance_pct,
    ROUND(bq.min_quality      * 100.0, 2) AS bottleneck_quality_pct

FROM system_agg sa
LEFT JOIN bottleneck_availability ba ON ba.shift_date = sa.shift_date
LEFT JOIN bottleneck_performance  bp ON bp.shift_date = sa.shift_date
LEFT JOIN bottleneck_quality      bq ON bq.shift_date = sa.shift_date

ORDER BY sa.shift_date ASC;

-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- 1. EXP(SUM(LN(Q_i))) is the SQL-standard equivalent of a PRODUCT() aggregate.
--    It requires all Q_i > 0; the CASE guard handles the zero-quality edge case.
-- 2. The bottleneck CTEs select MIN() per date. If two components are tied for
--    minimum, both rows exist and the INNER JOIN may return multiple rows.
--    In Power BI, use TOPN(1, ...) or add a ROW_NUMBER() partition to pick one.
-- 3. n_components_contributing = 5 is the healthy state. Values < 5 indicate
--    a component had no shift data on that date — an ETL gap to investigate.
-- 4. System OEE trend (shift_date, system_oee_pct) is the primary KPI line
--    chart on the Power BI Fleet Overview page.
-- =============================================================================
