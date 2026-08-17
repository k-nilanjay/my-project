-- =============================================================================
-- oee_window_analytics.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Day 11 advanced SQL analytics using window functions (RANK, LAG, moving
--   averages) to compute sequential MTBF, MTTR, downtime trends, and OEE
--   time-series analysis from the populated production tables.
--
-- WINDOW FUNCTIONS USED:
--   RANK()           — rank components/shifts by MTBF, MTTR, OEE
--   ROW_NUMBER()     — sequential failure numbering per component
--   LAG()            — inter-failure gap (basis for sequential MTBF calculation)
--   AVG() OVER       — 7-shift and 30-shift moving averages for OEE trend lines
--   SUM() OVER       — cumulative downtime tracking
--   NTILE()          — quartile banding for OEE performance tiers
--
-- DATA SOURCES (now populated):
--   production_shifts, downtime_events, production_counts, failure_log,
--   components
--
-- QUERY INVENTORY:
--   Q1. Sequential MTBF from failure_log (LAG-based inter-failure gap)
--   Q2. Sequential MTTR trend per component (LAG + RANK)
--   Q3. Downtime trend — 7-shift rolling average of downtime minutes
--   Q4. OEE rolling 7-shift and 30-shift moving averages
--   Q5. Component MTBF ranking (RANK on mean empirical MTBF)
--   Q6. Cumulative downtime tracker per component
--   Q7. OEE quartile banding with NTILE(4)
-- =============================================================================


-- =============================================================================
-- Q1: SEQUENTIAL MTBF — LAG-based inter-failure gap per component
-- =============================================================================
--
-- FORMULA:
--   Sequential MTBF_n = TTF_n (hours from end of previous repair to next failure)
--   For cycle 1: MTBF_1 = TTF_1 (component starts fresh from t=0)
--   For cycle n>1: MTBF_n = TTF_n (absolute gap = TTF as drawn from Weibull)
--
--   Running cumulative MTBF (empirical, improving with each observation):
--   MTBF_cum_n = AVG(TTF_1, TTF_2, ..., TTF_n)
--             = (cumulative_ttf_hours) / cycle_number
--
-- WINDOW FUNCTIONS:
--   LAG(ttf_hours) OVER (PARTITION BY component_id ORDER BY cycle_number)
--     → previous cycle's TTF for comparison
--   AVG(ttf_hours) OVER (PARTITION BY component_id ORDER BY cycle_number
--                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
--     → cumulative running average MTBF
--
-- =============================================================================

SELECT
    fl.component_id,
    c.component_name,
    c.maintenance_strategy,
    fl.cycle_number,
    ROUND(fl.ttf_hours, 2)                                 AS ttf_hours,

    -- LAG: previous cycle TTF for inter-failure comparison
    ROUND(
        LAG(fl.ttf_hours, 1) OVER (
            PARTITION BY fl.component_id
            ORDER BY fl.cycle_number
        ), 2
    )                                                       AS prev_ttf_hours,

    -- Change in TTF vs previous cycle (positive = longer inter-failure gap = improving)
    ROUND(
        fl.ttf_hours - LAG(fl.ttf_hours, 1) OVER (
            PARTITION BY fl.component_id
            ORDER BY fl.cycle_number
        ), 2
    )                                                       AS ttf_delta_hours,

    -- Cumulative running mean MTBF (improves estimate as more failures are observed)
    ROUND(
        AVG(fl.ttf_hours) OVER (
            PARTITION BY fl.component_id
            ORDER BY fl.cycle_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                                       AS mtbf_cumulative_h,

    -- Weibull parametric MTBF (reference, from CONTEXT.md Day 10 — embedded constants)
    ROUND(
        CASE fl.component_id
            WHEN 1 THEN fl.eta_effective_h * 0.89298   -- Bearing  β=3.00 Γ(1+1/3)
            WHEN 3 THEN fl.eta_effective_h * 0.88591   -- Mot.Hsg  β=2.15
            WHEN 4 THEN fl.eta_effective_h * 0.90021   -- Coupling β=1.75
            WHEN 5 THEN fl.eta_effective_h * 0.88726   -- Gearbox  β=2.50
            ELSE NULL
        END, 2
    )                                                       AS mtbf_weibull_h,

    -- Ratio: empirical cumulative / parametric (sanity gauge; expect 0.80–1.25)
    ROUND(
        AVG(fl.ttf_hours) OVER (
            PARTITION BY fl.component_id
            ORDER BY fl.cycle_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )
        /
        NULLIF(
            CASE fl.component_id
                WHEN 1 THEN fl.eta_effective_h * 0.89298
                WHEN 3 THEN fl.eta_effective_h * 0.88591
                WHEN 4 THEN fl.eta_effective_h * 0.90021
                WHEN 5 THEN fl.eta_effective_h * 0.88726
                ELSE NULL
            END, 0
        ), 3
    )                                                       AS mtbf_empirical_vs_parametric_ratio,

    -- RANK: worst-to-best TTF ranking within each cycle across all components
    RANK() OVER (
        PARTITION BY fl.cycle_number
        ORDER BY fl.ttf_hours ASC
    )                                                       AS ttf_rank_asc_worst_first

FROM failure_log fl
INNER JOIN components c
    ON c.component_id = fl.component_id
WHERE fl.ttf_hours IS NOT NULL

ORDER BY
    fl.component_id,
    fl.cycle_number;


-- =============================================================================
-- Q2: SEQUENTIAL MTTR TREND — LAG-based repair duration analysis
-- =============================================================================
--
-- FORMULA:
--   MTTR_n = repair_hours for cycle n
--   Cumulative MTTR_n = AVG(repair_hours_1 ... repair_hours_n)
--   MTTR trend flag: if MTTR increases cycle-over-cycle → maintenance escalation risk
--
-- WINDOW FUNCTIONS:
--   LAG(repair_hours) OVER — previous repair duration
--   AVG(repair_hours) OVER ROWS UNBOUNDED PRECEDING — running mean MTTR
--   RANK() OVER — rank components by latest cumulative MTTR
-- =============================================================================

SELECT
    fl.component_id,
    c.component_name,
    c.maintenance_strategy,
    fl.cycle_number,
    ROUND(fl.repair_hours, 2)                              AS repair_hours,

    -- LAG: previous cycle repair time
    ROUND(
        LAG(fl.repair_hours, 1) OVER (
            PARTITION BY fl.component_id
            ORDER BY fl.cycle_number
        ), 2
    )                                                       AS prev_repair_hours,

    -- Repair escalation: positive = getting worse (taking longer to fix)
    ROUND(
        fl.repair_hours - LAG(fl.repair_hours, 1) OVER (
            PARTITION BY fl.component_id
            ORDER BY fl.cycle_number
        ), 2
    )                                                       AS repair_delta_hours,

    -- Cumulative running mean MTTR
    ROUND(
        AVG(fl.repair_hours) OVER (
            PARTITION BY fl.component_id
            ORDER BY fl.cycle_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                                       AS mttr_cumulative_h,

    -- Approximate theoretical availability from current cumulative MTBF/MTTR
    -- A ≈ MTBF / (MTBF + MTTR)  — [locked Day 3, reliability.py]
    ROUND(
        AVG(fl.ttf_hours) OVER (
            PARTITION BY fl.component_id
            ORDER BY fl.cycle_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )
        /
        NULLIF(
            AVG(fl.ttf_hours) OVER (
                PARTITION BY fl.component_id
                ORDER BY fl.cycle_number
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )
            +
            AVG(fl.repair_hours) OVER (
                PARTITION BY fl.component_id
                ORDER BY fl.cycle_number
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ), 0
        )
        * 100.0, 2
    )                                                       AS availability_pct_from_mtbf_mttr,

    -- RANK by cumulative MTTR across components at each cycle (worst = highest MTTR)
    RANK() OVER (
        PARTITION BY fl.cycle_number
        ORDER BY fl.repair_hours DESC
    )                                                       AS mttr_rank_desc_worst_first

FROM failure_log fl
INNER JOIN components c
    ON c.component_id = fl.component_id
WHERE fl.repair_hours IS NOT NULL

ORDER BY
    fl.component_id,
    fl.cycle_number;


-- =============================================================================
-- Q3: DOWNTIME TREND — 7-shift rolling average of downtime minutes per component
-- =============================================================================
--
-- FORMULA:
--   rolling_avg_downtime_7shift = AVG(total_downtime_min) over the last 7 shifts
--     (ordered by shift date + label; label order: A → B → C)
--
--   Trend direction:
--     +ve slope = downtime increasing (deterioration)
--     -ve slope = downtime decreasing (improvement / repair success)
--
-- WINDOW FUNCTIONS:
--   AVG(total_downtime_min) OVER ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
--     → 7-shift trailing window
--   SUM(total_downtime_min) OVER ROWS UNBOUNDED PRECEDING
--     → cumulative downtime tracker (for Pareto analysis)
--   LAG(rolling_avg, 7) → compare today's rolling avg to 7 shifts ago
-- =============================================================================

WITH shift_downtime AS (
    -- Aggregate downtime per shift per component (exclude planned_maintenance)
    SELECT
        ps.shift_id,
        ps.component_id,
        c.component_name,
        ps.shift_date,
        ps.shift_label,
        ps.planned_duration_min,
        COALESCE(
            SUM(CASE WHEN de.downtime_category != 'planned_maintenance'
                     THEN de.duration_min ELSE 0.0 END),
            0.0
        )                                                   AS total_downtime_min,
        SUM(CASE WHEN de.downtime_category = 'unplanned_failure'
                 THEN de.duration_min ELSE 0.0 END)         AS failure_downtime_min,
        SUM(CASE WHEN de.downtime_category = 'cascade_upstream'
                 THEN de.duration_min ELSE 0.0 END)         AS cascade_downtime_min,
        SUM(CASE WHEN de.downtime_category = 'idle'
                 THEN de.duration_min ELSE 0.0 END)         AS idle_downtime_min
    FROM production_shifts ps
    INNER JOIN components c ON c.component_id = ps.component_id
    LEFT JOIN downtime_events de
        ON  de.shift_id     = ps.shift_id
        AND de.component_id = ps.component_id
    GROUP BY ps.shift_id, ps.component_id, c.component_name,
             ps.shift_date, ps.shift_label, ps.planned_duration_min
),
-- FIX (Day 13): Materialize the 7-shift rolling average in a separate CTE.
-- LAG() cannot be applied directly on top of another window function (AVG() OVER)
-- in the same SELECT scope — SQLite (and standard SQL) prohibit nested window calls.
-- Wrapping in a CTE first materializes the rolling avg as a plain column,
-- making it a valid LAG() operand in the outer SELECT.
shift_rolling AS (
    SELECT
        sd.*,
        ROUND(
            AVG(sd.total_downtime_min) OVER (
                PARTITION BY sd.component_id
                ORDER BY sd.shift_date, sd.shift_label
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ), 1
        )                                                   AS rolling_avg_7shift_down_min,
        ROUND(
            AVG(sd.total_downtime_min) OVER (
                PARTITION BY sd.component_id
                ORDER BY sd.shift_date, sd.shift_label
                ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ), 1
        )                                                   AS rolling_avg_30shift_down_min,
        ROUND(
            SUM(sd.total_downtime_min) OVER (
                PARTITION BY sd.component_id
                ORDER BY sd.shift_date, sd.shift_label
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ), 1
        )                                                   AS cumulative_downtime_min
    FROM shift_downtime sd
)
SELECT
    sr.component_id,
    sr.component_name,
    sr.shift_date,
    sr.shift_label,
    sr.shift_id,
    ROUND(sr.total_downtime_min, 1)                        AS total_downtime_min,
    ROUND(sr.failure_downtime_min, 1)                      AS failure_downtime_min,
    ROUND(sr.cascade_downtime_min, 1)                      AS cascade_downtime_min,
    ROUND(sr.idle_downtime_min, 1)                         AS idle_downtime_min,

    sr.rolling_avg_7shift_down_min,
    sr.rolling_avg_30shift_down_min,
    sr.cumulative_downtime_min,

    -- 7-shift trend: LAG applied on the pre-materialized rolling average (CTE fix)
    ROUND(
        sr.rolling_avg_7shift_down_min
        - LAG(sr.rolling_avg_7shift_down_min, 7) OVER (
            PARTITION BY sr.component_id
            ORDER BY sr.shift_date, sr.shift_label
        ), 1
    )                                                       AS downtime_trend_7shift,

    -- Availability from this shift
    ROUND(
        (sr.planned_duration_min - sr.total_downtime_min)
        / NULLIF(sr.planned_duration_min, 0) * 100.0, 1
    )                                                       AS availability_pct

FROM shift_rolling sr
ORDER BY sr.component_id, sr.shift_date, sr.shift_label;


-- =============================================================================
-- Q4: OEE ROLLING AVERAGES — 7-shift and 30-shift moving averages
-- =============================================================================
--
-- FORMULA:
--   OEE_shift = A × P × Q   (per shift, per component)
--   OEE_7shift_avg = AVG(OEE_shift) over previous 7 shifts
--   OEE_30shift_avg = AVG(OEE_shift) over previous 30 shifts
--
-- WINDOW FUNCTIONS:
--   AVG(oee) OVER ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
--   AVG(oee) OVER ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
--   RANK() OVER PARTITION BY shift_date ORDER BY oee DESC
--     → daily component ranking by OEE
-- =============================================================================

-- STEP 1: Compute downtime aggregation for OEE
WITH dt AS (
    SELECT shift_id, component_id,
           SUM(CASE WHEN downtime_category != 'planned_maintenance'
                    THEN duration_min ELSE 0.0 END) AS down_min
    FROM downtime_events
    GROUP BY shift_id, component_id
),
-- STEP 2: Compute per-shift OEE components (no window functions yet)
oee_per_shift AS (
    SELECT
        ps.shift_id,
        ps.component_id,
        c.component_name,
        ps.shift_date,
        ps.shift_label,
        ps.planned_duration_min,

        -- Availability
        (ps.planned_duration_min - COALESCE(dt.down_min, 0.0))
        / NULLIF(ps.planned_duration_min, 0.0)             AS availability,

        -- Run time
        ps.planned_duration_min - COALESCE(dt.down_min, 0.0) AS run_time_min,

        -- Performance (unit-count primary method)
        MIN(1.0,
            (pc.ideal_cycle_time_min * pc.total_units)
            / NULLIF(ps.planned_duration_min - COALESCE(dt.down_min, 0.0), 0.0)
        )                                                   AS performance,

        -- Quality
        CAST(pc.good_units AS FLOAT)
        / NULLIF(pc.total_units, 0)                        AS quality,

        -- Composite OEE
        (ps.planned_duration_min - COALESCE(dt.down_min, 0.0))
        / NULLIF(ps.planned_duration_min, 0.0)
        *
        MIN(1.0,
            (pc.ideal_cycle_time_min * pc.total_units)
            / NULLIF(ps.planned_duration_min - COALESCE(dt.down_min, 0.0), 0.0)
        )
        *
        (CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0))
                                                            AS oee

    FROM production_shifts ps
    INNER JOIN components c ON c.component_id = ps.component_id
    LEFT JOIN dt
        ON dt.shift_id = ps.shift_id AND dt.component_id = ps.component_id
    LEFT JOIN production_counts pc
        ON pc.shift_id = ps.shift_id AND pc.component_id = ps.component_id
),
-- FIX (Day 13): Materialize the 7-shift and 30-shift rolling OEE averages in a
-- separate CTE. LAG() cannot be applied directly on top of another window
-- function (AVG() OVER) in the same SELECT scope — this is the nested window
-- anti-pattern that breaks both SQLite and standard SQL.
-- Materializing first creates a plain column (oee_rolling_avg_7shift) that LAG
-- can reference legally in the outer SELECT.
oee_with_rolling AS (
    SELECT
        ops.*,
        ROUND(
            AVG(ops.oee) OVER (
                PARTITION BY ops.component_id
                ORDER BY ops.shift_date, ops.shift_label
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) * 100.0, 2
        )                                                   AS oee_rolling_avg_7shift_pct,
        ROUND(
            AVG(ops.oee) OVER (
                PARTITION BY ops.component_id
                ORDER BY ops.shift_date, ops.shift_label
                ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) * 100.0, 2
        )                                                   AS oee_rolling_avg_30shift_pct
    FROM oee_per_shift ops
)
SELECT
    owr.component_id,
    owr.component_name,
    owr.shift_date,
    owr.shift_label,
    owr.shift_id,

    -- Raw shift OEE components
    ROUND(owr.availability  * 100.0, 2)                    AS availability_pct,
    ROUND(owr.performance   * 100.0, 2)                    AS performance_pct,
    ROUND(owr.quality       * 100.0, 2)                    AS quality_pct,
    ROUND(owr.oee           * 100.0, 2)                    AS oee_pct,

    -- Pre-computed rolling averages (from CTE above)
    owr.oee_rolling_avg_7shift_pct,
    owr.oee_rolling_avg_30shift_pct,

    -- OEE delta: current 7-shift avg minus 7-shift avg from 7 rows earlier
    -- LAG applied to the materialized CTE column — no nested window function
    ROUND(
        owr.oee_rolling_avg_7shift_pct
        - LAG(owr.oee_rolling_avg_7shift_pct, 7) OVER (
            PARTITION BY owr.component_id
            ORDER BY owr.shift_date, owr.shift_label
        ), 2
    )                                                       AS oee_trend_7shift_pp,

    -- Daily ranking: which component has best OEE on this shift_date?
    RANK() OVER (
        PARTITION BY owr.shift_date, owr.shift_label
        ORDER BY owr.oee DESC
    )                                                       AS daily_oee_rank,

    -- OEE status tier (locked Day 2)
    CASE
        WHEN owr.oee >= 0.85 THEN 'WORLD_CLASS'
        WHEN owr.oee >= 0.75 THEN 'ACCEPTABLE'
        WHEN owr.oee >= 0.65 THEN 'ALERT'
        WHEN owr.oee IS NOT NULL THEN 'CRITICAL'
        ELSE 'NO_DATA'
    END                                                     AS oee_status

FROM oee_with_rolling owr
ORDER BY owr.component_id, owr.shift_date, owr.shift_label;


-- =============================================================================
-- Q5: COMPONENT MTBF RANKING — RANK on mean empirical MTBF
-- =============================================================================
--
-- PURPOSE:
--   Rank components from most-reliable (longest mean TTF) to least-reliable.
--   Include Weibull parametric MTBF for comparison.
--   CoV (coefficient of variation) quantifies TTF predictability.
--
-- WINDOW FUNCTIONS:
--   RANK() OVER ORDER BY avg_ttf_h DESC — higher MTBF = better rank
-- =============================================================================

WITH component_mtbf AS (
    SELECT
        fl.component_id,
        c.component_name,
        c.maintenance_strategy,
        COUNT(*)                                            AS n_failures,
        ROUND(AVG(fl.ttf_hours), 1)                        AS avg_ttf_h,
        ROUND(MIN(fl.ttf_hours), 1)                        AS min_ttf_h,
        ROUND(MAX(fl.ttf_hours), 1)                        AS max_ttf_h,

        -- CoV = σ/μ using SQL Var(X) = E[X²] - E[X]² identity (locked Day 10)
        ROUND(
            SQRT(
                AVG(fl.ttf_hours * fl.ttf_hours)
                - AVG(fl.ttf_hours) * AVG(fl.ttf_hours)
            )
            / NULLIF(AVG(fl.ttf_hours), 0), 3
        )                                                   AS cov_ttf,

        -- Weibull MTBF (parametric)
        ROUND(
            CASE fl.component_id
                WHEN 1 THEN AVG(fl.eta_effective_h) * 0.89298
                WHEN 3 THEN AVG(fl.eta_effective_h) * 0.88591
                WHEN 4 THEN AVG(fl.eta_effective_h) * 0.90021
                WHEN 5 THEN AVG(fl.eta_effective_h) * 0.88726
                ELSE NULL
            END, 1
        )                                                   AS mtbf_weibull_h,

        -- Approx failure rate λ = 1/MTBF (per 1000 operating hours)
        ROUND(1000.0 / NULLIF(AVG(fl.ttf_hours), 0), 4)   AS lambda_per_1000h

    FROM failure_log fl
    INNER JOIN components c ON c.component_id = fl.component_id
    WHERE fl.ttf_hours IS NOT NULL
    GROUP BY fl.component_id, c.component_name, c.maintenance_strategy
)
SELECT
    cm.component_id,
    cm.component_name,
    cm.maintenance_strategy,
    cm.n_failures,
    cm.avg_ttf_h,
    cm.min_ttf_h,
    cm.max_ttf_h,
    cm.cov_ttf,
    cm.mtbf_weibull_h,
    cm.lambda_per_1000h,

    -- Reliability ranking: 1 = most reliable (longest MTBF)
    RANK() OVER (ORDER BY cm.avg_ttf_h DESC)               AS reliability_rank,

    -- Failure risk ranking: 1 = highest risk (shortest MTBF)
    RANK() OVER (ORDER BY cm.avg_ttf_h ASC)                AS risk_rank,

    -- Predictability ranking: 1 = most predictable (lowest CoV)
    RANK() OVER (ORDER BY cm.cov_ttf ASC)                  AS predictability_rank,

    -- Combined risk score: weighted RANK sum (unweighted here — equal weight)
    RANK() OVER (ORDER BY cm.avg_ttf_h ASC)
    + RANK() OVER (ORDER BY cm.cov_ttf DESC)               AS combined_priority_score

FROM component_mtbf cm
ORDER BY cm.avg_ttf_h DESC;


-- =============================================================================
-- Q6: CUMULATIVE DOWNTIME TRACKER — running total per component
-- =============================================================================
--
-- PURPOSE:
--   Track how cumulative downtime evolves across the 90-day window.
--   Used in Power BI to show the "cost of downtime" accumulation curve.
--   Separate tracking for unplanned vs cascade vs idle categories.
--
-- WINDOW FUNCTION:
--   SUM() OVER ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
-- =============================================================================

WITH shift_downtime_detail AS (
    SELECT
        ps.shift_id,
        ps.component_id,
        c.component_name,
        ps.shift_date,
        ps.shift_label,
        COALESCE(SUM(CASE WHEN de.downtime_category = 'unplanned_failure'
                          THEN de.duration_min ELSE 0 END), 0) AS fail_down_min,
        COALESCE(SUM(CASE WHEN de.downtime_category = 'cascade_upstream'
                          THEN de.duration_min ELSE 0 END), 0) AS casc_down_min,
        COALESCE(SUM(CASE WHEN de.downtime_category = 'idle'
                          THEN de.duration_min ELSE 0 END), 0) AS idle_down_min,
        COALESCE(SUM(CASE WHEN de.downtime_category = 'planned_maintenance'
                          THEN de.duration_min ELSE 0 END), 0) AS pm_down_min
    FROM production_shifts ps
    INNER JOIN components c ON c.component_id = ps.component_id
    LEFT JOIN downtime_events de
        ON de.shift_id = ps.shift_id AND de.component_id = ps.component_id
    GROUP BY ps.shift_id, ps.component_id, c.component_name,
             ps.shift_date, ps.shift_label
)
SELECT
    sdd.component_id,
    sdd.component_name,
    sdd.shift_date,
    sdd.shift_label,
    sdd.shift_id,

    ROUND(sdd.fail_down_min, 1)                            AS failure_down_min,
    ROUND(sdd.casc_down_min, 1)                            AS cascade_down_min,
    ROUND(sdd.idle_down_min, 1)                            AS idle_down_min,
    ROUND(sdd.pm_down_min, 1)                              AS pm_down_min,

    -- Cumulative unplanned failure downtime (escalation indicator)
    ROUND(
        SUM(sdd.fail_down_min) OVER (
            PARTITION BY sdd.component_id
            ORDER BY sdd.shift_date, sdd.shift_label
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 1
    )                                                       AS cumul_failure_down_min,

    -- Cumulative cascade downtime (upstream impact propagation)
    ROUND(
        SUM(sdd.casc_down_min) OVER (
            PARTITION BY sdd.component_id
            ORDER BY sdd.shift_date, sdd.shift_label
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 1
    )                                                       AS cumul_cascade_down_min,

    -- Cumulative all-cause downtime
    ROUND(
        SUM(sdd.fail_down_min + sdd.casc_down_min + sdd.idle_down_min) OVER (
            PARTITION BY sdd.component_id
            ORDER BY sdd.shift_date, sdd.shift_label
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 1
    )                                                       AS cumul_total_down_min,

    -- Downtime as % of planned time (shift-level)
    ROUND(
        (sdd.fail_down_min + sdd.casc_down_min + sdd.idle_down_min)
        / 480.0 * 100.0, 1
    )                                                       AS downtime_pct_this_shift

FROM shift_downtime_detail sdd
ORDER BY sdd.component_id, sdd.shift_date, sdd.shift_label;


-- =============================================================================
-- Q7: OEE QUARTILE BANDING — NTILE(4) performance tier distribution
-- =============================================================================
--
-- PURPOSE:
--   Partition all shifts into four quartiles by OEE score.
--   Q4 (best 25%) is target performance; Q1 (worst 25%) is intervention zone.
--   Used in Power BI distribution histogram and Pareto analysis.
--
-- WINDOW FUNCTION:
--   NTILE(4) OVER ORDER BY oee DESC  → Q1 (best) through Q4 (worst)
--   ROW_NUMBER() OVER — unique shift sequence number for trend overlay
-- =============================================================================

WITH oee_base AS (
    WITH dt AS (
        SELECT shift_id, component_id,
               SUM(CASE WHEN downtime_category != 'planned_maintenance'
                        THEN duration_min ELSE 0.0 END) AS down_min
        FROM downtime_events GROUP BY shift_id, component_id
    )
    SELECT
        ps.shift_id,
        ps.component_id,
        c.component_name,
        ps.shift_date,
        ps.shift_label,
        (ps.planned_duration_min - COALESCE(dt.down_min, 0.0))
        / NULLIF(ps.planned_duration_min, 0.0)
        *
        MIN(1.0,
            (pc.ideal_cycle_time_min * pc.total_units)
            / NULLIF(ps.planned_duration_min - COALESCE(dt.down_min, 0.0), 0.0))
        *
        (CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0)) AS oee
    FROM production_shifts ps
    INNER JOIN components c ON c.component_id = ps.component_id
    LEFT JOIN dt ON dt.shift_id = ps.shift_id AND dt.component_id = ps.component_id
    LEFT JOIN production_counts pc
        ON pc.shift_id = ps.shift_id AND pc.component_id = ps.component_id
    WHERE pc.total_units IS NOT NULL  -- only shifts with production data
)
SELECT
    ob.component_id,
    ob.component_name,
    ob.shift_date,
    ob.shift_label,
    ob.shift_id,
    ROUND(ob.oee * 100.0, 2)                               AS oee_pct,

    -- OEE status tier
    CASE
        WHEN ob.oee >= 0.85 THEN 'WORLD_CLASS'
        WHEN ob.oee >= 0.75 THEN 'ACCEPTABLE'
        WHEN ob.oee >= 0.65 THEN 'ALERT'
        ELSE 'CRITICAL'
    END                                                     AS oee_status,

    -- Quartile banding: 1 = top 25% (best performers), 4 = bottom 25%
    NTILE(4) OVER (
        PARTITION BY ob.component_id
        ORDER BY ob.oee DESC
    )                                                       AS oee_quartile,

    -- Component-wide OEE percentile (0–100)
    ROUND(
        CAST(
            ROW_NUMBER() OVER (
                PARTITION BY ob.component_id
                ORDER BY ob.oee ASC
            ) AS FLOAT
        )
        / COUNT(*) OVER (PARTITION BY ob.component_id)
        * 100.0, 1
    )                                                       AS oee_percentile,

    -- Sequential shift number per component (for Power BI X-axis ordering)
    ROW_NUMBER() OVER (
        PARTITION BY ob.component_id
        ORDER BY ob.shift_date, ob.shift_label
    )                                                       AS shift_sequence_number

FROM oee_base ob
ORDER BY ob.component_id, ob.shift_date, ob.shift_label;


-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- Each query above (Q1–Q7) is self-contained and can be run independently
-- in SQLite (DB Browser) or pasted into Power BI's Advanced Editor for a
-- native query data source.
--
-- SQLite compatibility:
--   - All window functions (RANK, LAG, AVG OVER, SUM OVER, NTILE, ROW_NUMBER)
--     are supported since SQLite 3.25.0 (2018-09-15).
--   - Nested CTEs (WITH inside WITH) require SQLite 3.35+ or wrapping in
--     a subquery.  For compatibility, the inner CTEs in Q4 and Q7 can be
--     extracted to separate queries or saved as views.
--
-- Power BI consumption:
--   - Q3 (downtime trend) and Q4 (OEE rolling averages) are the primary
--     sources for time-series line charts on the Fleet Overview page.
--   - Q5 (MTBF ranking) feeds the component reliability comparison bar chart.
--   - Q7 (quartile banding) drives the OEE distribution histogram.
-- =============================================================================
