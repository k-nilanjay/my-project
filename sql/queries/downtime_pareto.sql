-- =============================================================================
-- downtime_pareto.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Day 12 — Pareto ranking of downtime events by component and failure cause.
--   Implements the 80/20 Pareto principle (Juran, 1954): identify the vital few
--   components / failure modes responsible for the majority of downtime minutes.
--
-- TECHNIQUE INVENTORY:
--   CTEs        — isolate intermediate aggregations for clarity and reuse
--   JOINs       — enrich downtime_events with components dimension
--   Subqueries  — compute fleet-level totals for cumulative % calculation
--   CASE WHEN   — categorize Pareto tier (vital few vs useful many)
--   ROUND()     — controlled decimal precision throughout
--
-- DATA SOURCES:
--   downtime_events   — 142 rows (populated Day 11)
--   components        — 5 rows (seed.sql)
--   production_shifts — 1,350 rows (populated Day 11)
--
-- QUERY INVENTORY:
--   P1. Component-level Pareto — total downtime minutes per component, ranked
--   P2. Failure-cause Pareto   — downtime by downtime_category, ranked
--   P3. Component × cause matrix — cross-tab of component vs cause with CTE chain
--   P4. Failure-mode Pareto     — downtime ranked by failure_mode string
--   P5. Shift-label Pareto      — which shift type (DAY/SWING/NIGHT) loses most
--   P6. Unplanned vs planned    — split by downtime_type (equipment/process/quality)
--   P7. Cascade attribution     — cascade downtime traced back to root-cause component
-- =============================================================================


-- =============================================================================
-- P1: COMPONENT-LEVEL PARETO
-- Total downtime minutes per component, with cumulative % and Pareto tier
-- =============================================================================
--
-- LOGIC:
--   Step 1 (CTE component_downtime): Aggregate total and unplanned downtime per
--          component via JOIN to components for name resolution.
--   Step 2 (CTE ranked): RANK() by total downtime DESC — most costly component = 1.
--          Also compute each component's share of fleet total (subquery in SELECT).
--   Step 3 (final SELECT): Cumulative running total via SUM() OVER (ORDER BY rank),
--          then Pareto tier (≤80% cumulative = VITAL_FEW, else USEFUL_MANY).
--
-- KEY JOIN:
--   downtime_events INNER JOIN components ON component_id
--   LEFT JOIN production_shifts ON shift_id → to capture total planned minutes
--   for comparison with downtime (Availability denominator context)
--
-- =============================================================================

WITH component_downtime AS (
    -- Step 1: aggregate downtime per component
    SELECT
        de.component_id,
        c.component_name,
        c.maintenance_strategy,
        c.position_in_chain,
        COUNT(*)                                              AS downtime_event_count,
        ROUND(SUM(de.duration_min), 2)                       AS total_downtime_min,
        ROUND(SUM(
            CASE WHEN de.downtime_category = 'unplanned_failure'
                 THEN de.duration_min ELSE 0.0 END
        ), 2)                                                 AS unplanned_downtime_min,
        ROUND(SUM(
            CASE WHEN de.downtime_category = 'planned_maintenance'
                 THEN de.duration_min ELSE 0.0 END
        ), 2)                                                 AS planned_downtime_min,
        ROUND(SUM(
            CASE WHEN de.downtime_category = 'cascade_upstream'
                 THEN de.duration_min ELSE 0.0 END
        ), 2)                                                 AS cascade_downtime_min
    FROM downtime_events de
    INNER JOIN components c ON de.component_id = c.component_id
    GROUP BY de.component_id, c.component_name, c.maintenance_strategy,
             c.position_in_chain
),

fleet_total AS (
    -- Step 2a: fleet-wide total for percentage denominator
    SELECT SUM(total_downtime_min) AS fleet_total_downtime_min
    FROM component_downtime
),

ranked AS (
    -- Step 2b: rank each component by total downtime descending
    SELECT
        cd.*,
        ft.fleet_total_downtime_min,
        ROUND(cd.total_downtime_min / ft.fleet_total_downtime_min * 100.0, 2)
                                                              AS pct_of_fleet_downtime,
        RANK() OVER (ORDER BY cd.total_downtime_min DESC)    AS downtime_rank
    FROM component_downtime cd
    CROSS JOIN fleet_total ft
)

-- Step 3: cumulative running total and Pareto tier classification
SELECT
    r.downtime_rank,
    r.component_name,
    r.maintenance_strategy,
    r.position_in_chain,
    r.downtime_event_count,
    r.total_downtime_min,
    r.unplanned_downtime_min,
    r.planned_downtime_min,
    r.cascade_downtime_min,
    r.pct_of_fleet_downtime,

    -- Cumulative % (running sum of share, ordered by rank)
    ROUND(
        SUM(r.pct_of_fleet_downtime) OVER (
            ORDER BY r.downtime_rank
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                                         AS cumulative_pct,

    -- Pareto tier: components accounting for ≤80% cumulative = vital few
    CASE
        WHEN SUM(r.pct_of_fleet_downtime) OVER (
                 ORDER BY r.downtime_rank
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
             ) <= 80.0
        THEN 'VITAL_FEW'
        ELSE 'USEFUL_MANY'
    END                                                       AS pareto_tier,

    -- Mean downtime per event (useful for repair cost modelling)
    ROUND(r.total_downtime_min / NULLIF(r.downtime_event_count, 0), 2)
                                                              AS avg_downtime_per_event_min,

    -- Unplanned downtime as proportion of this component's total (measure of unexpectedness)
    ROUND(
        r.unplanned_downtime_min / NULLIF(r.total_downtime_min, 0) * 100.0, 2
    )                                                         AS unplanned_pct_of_component

FROM ranked r
ORDER BY r.downtime_rank;


-- =============================================================================
-- P2: FAILURE-CAUSE PARETO (downtime_category)
-- =============================================================================
--
-- LOGIC:
--   CTE cause_agg: group downtime_events by downtime_category; sum duration.
--   Subquery for fleet total (same cross-join pattern as P1).
--   Final SELECT: rank by total duration, compute cumulative%, assign Pareto tier.
--
-- CATEGORIES (locked Day 2):
--   'unplanned_failure'  — sudden equipment stop
--   'planned_maintenance'— scheduled PM window
--   'changeover'         — setup/tooling change
--   'idle'               — shift gap / material shortage
--   'cascade_upstream'   — collateral stop from upstream failure
--
-- =============================================================================

WITH cause_agg AS (
    SELECT
        downtime_category,
        COUNT(*)                              AS event_count,
        ROUND(SUM(duration_min), 2)           AS total_downtime_min,
        COUNT(DISTINCT component_id)          AS affected_components
    FROM downtime_events
    GROUP BY downtime_category
),

cause_total AS (
    SELECT SUM(total_downtime_min) AS grand_total_min
    FROM cause_agg
),

cause_ranked AS (
    SELECT
        ca.downtime_category,
        ca.event_count,
        ca.total_downtime_min,
        ca.affected_components,
        ROUND(ca.total_downtime_min / ct.grand_total_min * 100.0, 2) AS pct_of_total,
        RANK() OVER (ORDER BY ca.total_downtime_min DESC)             AS cause_rank
    FROM cause_agg ca
    CROSS JOIN cause_total ct
)

SELECT
    cr.cause_rank,
    cr.downtime_category,
    cr.event_count,
    cr.total_downtime_min,
    cr.affected_components,
    cr.pct_of_total,

    ROUND(
        SUM(cr.pct_of_total) OVER (
            ORDER BY cr.cause_rank
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                                         AS cumulative_pct,

    CASE
        WHEN SUM(cr.pct_of_total) OVER (
                 ORDER BY cr.cause_rank
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
             ) <= 80.0
        THEN 'VITAL_FEW'
        ELSE 'USEFUL_MANY'
    END                                                       AS pareto_tier,

    ROUND(cr.total_downtime_min / NULLIF(cr.event_count, 0), 2)
                                                              AS avg_min_per_event

FROM cause_ranked cr
ORDER BY cr.cause_rank;


-- =============================================================================
-- P3: COMPONENT × CAUSE CROSS-TAB MATRIX
-- Pivoted via CASE WHEN aggregation — which component contributes most to each cause?
-- =============================================================================
--
-- LOGIC:
--   CTE matrix_base: one row per (component, cause) pair with sum of duration.
--   Final SELECT: pivot categories to columns using SUM(CASE WHEN ...) pattern.
--   JOIN to components for name and position ordering.
--   Subquery computes component's share of each category total for relative sizing.
--
-- NOTE: This is a conditional aggregation pivot (CASE WHEN inside SUM).
--   No PIVOT keyword used — SQLite-compatible approach.
--
-- =============================================================================

WITH matrix_base AS (
    SELECT
        de.component_id,
        c.component_name,
        c.position_in_chain,
        de.downtime_category,
        ROUND(SUM(de.duration_min), 2)   AS total_min
    FROM downtime_events de
    INNER JOIN components c ON de.component_id = c.component_id
    GROUP BY de.component_id, c.component_name, c.position_in_chain,
             de.downtime_category
),

category_totals AS (
    -- Total per category across all components (for denominator in pct columns)
    SELECT
        downtime_category,
        SUM(total_min) AS category_total_min
    FROM matrix_base
    GROUP BY downtime_category
)

SELECT
    mb.component_id,
    mb.component_name,
    mb.position_in_chain,

    -- Pivot columns: sum each category per component
    ROUND(SUM(CASE WHEN mb.downtime_category = 'unplanned_failure'
                   THEN mb.total_min ELSE 0.0 END), 2)   AS unplanned_failure_min,
    ROUND(SUM(CASE WHEN mb.downtime_category = 'planned_maintenance'
                   THEN mb.total_min ELSE 0.0 END), 2)   AS planned_maintenance_min,
    ROUND(SUM(CASE WHEN mb.downtime_category = 'changeover'
                   THEN mb.total_min ELSE 0.0 END), 2)   AS changeover_min,
    ROUND(SUM(CASE WHEN mb.downtime_category = 'idle'
                   THEN mb.total_min ELSE 0.0 END), 2)   AS idle_min,
    ROUND(SUM(CASE WHEN mb.downtime_category = 'cascade_upstream'
                   THEN mb.total_min ELSE 0.0 END), 2)   AS cascade_upstream_min,

    -- Row total across all categories for this component
    ROUND(SUM(mb.total_min), 2)                          AS component_total_min,

    -- Component's share of the total unplanned failure minutes (identifies worst offender per category)
    ROUND(
        SUM(CASE WHEN mb.downtime_category = 'unplanned_failure'
                 THEN mb.total_min ELSE 0.0 END)
        / NULLIF(
            (SELECT category_total_min FROM category_totals
             WHERE downtime_category = 'unplanned_failure'), 0
        ) * 100.0, 2
    )                                                    AS pct_of_fleet_unplanned

FROM matrix_base mb
GROUP BY mb.component_id, mb.component_name, mb.position_in_chain
ORDER BY mb.position_in_chain;


-- =============================================================================
-- P4: FAILURE-MODE PARETO (failure_mode string column)
-- =============================================================================
--
-- LOGIC:
--   Filter to rows where failure_mode IS NOT NULL (excludes idle/changeover rows).
--   CTE fm_agg: aggregate by failure_mode string.
--   JOIN back to components via downtime_events to show which components
--   exhibit each mode.
--   Subquery scalar: total unplanned failure minutes for percentage base.
--
-- FAILURE MODE VALUES (from FAILURE_MODES dict in simulate.py / data_generator.py):
--   'rolling_element_fatigue'   — Bearing
--   'fatigue_imbalance'         — Shaft
--   'winding_insulation_failure'— Motor Housing
--   'elastomer_ageing'          — Coupling
--   'gear_tooth_pitting'        — Gearbox
--   NULL                        — non-failure events (planned, idle, cascade)
--
-- =============================================================================

WITH fm_agg AS (
    SELECT
        de.failure_mode,
        COUNT(*)                                   AS event_count,
        COUNT(DISTINCT de.component_id)            AS component_count,
        ROUND(SUM(de.duration_min), 2)             AS total_downtime_min,
        ROUND(AVG(de.duration_min), 2)             AS avg_downtime_per_event_min,
        ROUND(MIN(de.duration_min), 2)             AS min_event_min,
        ROUND(MAX(de.duration_min), 2)             AS max_event_min
    FROM downtime_events de
    WHERE de.failure_mode IS NOT NULL
      AND de.failure_mode != ''
    GROUP BY de.failure_mode
),

fm_total AS (
    SELECT SUM(total_downtime_min) AS mode_total_min
    FROM fm_agg
),

fm_ranked AS (
    SELECT
        fa.*,
        ROUND(fa.total_downtime_min / ft.mode_total_min * 100.0, 2) AS pct_of_failure_downtime,
        RANK() OVER (ORDER BY fa.total_downtime_min DESC)             AS failure_mode_rank
    FROM fm_agg fa
    CROSS JOIN fm_total ft
)

SELECT
    fr.failure_mode_rank,
    fr.failure_mode,
    fr.event_count,
    fr.component_count,
    fr.total_downtime_min,
    fr.avg_downtime_per_event_min,
    fr.min_event_min,
    fr.max_event_min,
    fr.pct_of_failure_downtime,

    ROUND(
        SUM(fr.pct_of_failure_downtime) OVER (
            ORDER BY fr.failure_mode_rank
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                                         AS cumulative_pct,

    CASE
        WHEN SUM(fr.pct_of_failure_downtime) OVER (
                 ORDER BY fr.failure_mode_rank
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
             ) <= 80.0
        THEN 'VITAL_FEW'
        ELSE 'USEFUL_MANY'
    END                                                       AS pareto_tier

FROM fm_ranked fr
ORDER BY fr.failure_mode_rank;


-- =============================================================================
-- P5: SHIFT-LABEL PARETO (which shift type loses the most production time?)
-- =============================================================================
--
-- LOGIC:
--   JOIN downtime_events → production_shifts to resolve shift_label per event.
--   Aggregate by shift_label (DAY / SWING / NIGHT).
--   Compare each shift's downtime against its total planned capacity
--   (planned_duration_min × number of shifts in that label category).
--
-- KEY JOIN:
--   downtime_events.shift_id → production_shifts.shift_id
--   Aggregation: GROUP BY production_shifts.shift_label
--
-- =============================================================================

WITH shift_downtime AS (
    SELECT
        ps.shift_label,
        COUNT(DISTINCT ps.shift_id)                   AS shift_count,
        COUNT(de.downtime_id)                         AS downtime_event_count,
        ROUND(SUM(ps.planned_duration_min), 2)        AS total_planned_min,
        ROUND(SUM(de.duration_min), 2)                AS total_downtime_min
    FROM production_shifts ps
    LEFT JOIN downtime_events de ON ps.shift_id = de.shift_id
    GROUP BY ps.shift_label
),

shift_total AS (
    SELECT SUM(total_downtime_min) AS grand_downtime_min
    FROM shift_downtime
),

shift_ranked AS (
    SELECT
        sd.*,
        ROUND(sd.total_downtime_min / NULLIF(st.grand_downtime_min, 0) * 100.0, 2)
                                                     AS pct_of_fleet_downtime,
        RANK() OVER (ORDER BY sd.total_downtime_min DESC)
                                                     AS shift_rank
    FROM shift_downtime sd
    CROSS JOIN shift_total st
)

SELECT
    sr.shift_rank,
    sr.shift_label,
    sr.shift_count,
    sr.downtime_event_count,
    sr.total_planned_min,
    sr.total_downtime_min,
    sr.pct_of_fleet_downtime,

    -- Downtime intensity: minutes of downtime per shift occurrence
    ROUND(sr.total_downtime_min / NULLIF(sr.shift_count, 0), 4)
                                                     AS avg_downtime_per_shift_min,

    -- Availability proxy: what % of planned time was actually available?
    ROUND(
        (sr.total_planned_min - sr.total_downtime_min)
        / NULLIF(sr.total_planned_min, 0) * 100.0, 2
    )                                                AS availability_pct,

    ROUND(
        SUM(sr.pct_of_fleet_downtime) OVER (
            ORDER BY sr.shift_rank
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                                AS cumulative_pct

FROM shift_ranked sr
ORDER BY sr.shift_rank;


-- =============================================================================
-- P6: UNPLANNED vs PLANNED DOWNTIME SPLIT PER COMPONENT
-- =============================================================================
--
-- LOGIC:
--   Uses a subquery to pre-calculate total downtime per component.
--   Outer query joins the subquery to compute the unplanned/planned split %.
--   No CTE here — demonstrates subquery-in-FROM (derived table) pattern.
--
-- FORMULA:
--   Unplanned downtime ratio = unplanned_min / total_min
--   > 50%  → UNPLANNED_DOMINANT (reactive maintenance culture)
--   ≤ 50%  → PLANNED_DOMINANT   (proactive maintenance culture)
--   (industry benchmark: unplanned should be < 30% of total for mature assets)
--
-- =============================================================================

SELECT
    comp_totals.component_id,
    comp_totals.component_name,
    comp_totals.maintenance_strategy,
    comp_totals.total_downtime_min,
    comp_totals.unplanned_min,
    comp_totals.planned_min,
    comp_totals.cascade_min,
    comp_totals.idle_changeover_min,

    ROUND(comp_totals.unplanned_min / NULLIF(comp_totals.total_downtime_min, 0) * 100.0, 2)
                                                              AS unplanned_pct,
    ROUND(comp_totals.planned_min   / NULLIF(comp_totals.total_downtime_min, 0) * 100.0, 2)
                                                              AS planned_pct,
    ROUND(comp_totals.cascade_min   / NULLIF(comp_totals.total_downtime_min, 0) * 100.0, 2)
                                                              AS cascade_pct,

    -- Cultural classification: is this component reactively or proactively maintained?
    CASE
        WHEN comp_totals.unplanned_min / NULLIF(comp_totals.total_downtime_min, 0) > 0.50
        THEN 'UNPLANNED_DOMINANT'
        ELSE 'PLANNED_DOMINANT'
    END                                                       AS maintenance_culture,

    -- Industry benchmark flag: unplanned > 30% = below benchmark
    CASE
        WHEN comp_totals.unplanned_min / NULLIF(comp_totals.total_downtime_min, 0) > 0.30
        THEN 'BELOW_BENCHMARK'
        ELSE 'MEETS_BENCHMARK'
    END                                                       AS benchmark_status

FROM (
    -- Derived table: aggregate downtime categories per component
    SELECT
        de.component_id,
        c.component_name,
        c.maintenance_strategy,
        ROUND(SUM(de.duration_min), 2)                          AS total_downtime_min,
        ROUND(SUM(CASE WHEN de.downtime_category = 'unplanned_failure'
                       THEN de.duration_min ELSE 0.0 END), 2)  AS unplanned_min,
        ROUND(SUM(CASE WHEN de.downtime_category = 'planned_maintenance'
                       THEN de.duration_min ELSE 0.0 END), 2)  AS planned_min,
        ROUND(SUM(CASE WHEN de.downtime_category = 'cascade_upstream'
                       THEN de.duration_min ELSE 0.0 END), 2)  AS cascade_min,
        ROUND(SUM(CASE WHEN de.downtime_category IN ('idle', 'changeover')
                       THEN de.duration_min ELSE 0.0 END), 2)  AS idle_changeover_min
    FROM downtime_events de
    INNER JOIN components c ON de.component_id = c.component_id
    GROUP BY de.component_id, c.component_name, c.maintenance_strategy
) AS comp_totals
ORDER BY comp_totals.unplanned_min DESC;


-- =============================================================================
-- P7: CASCADE ATTRIBUTION PARETO
-- Which root-cause component generates the most cascade downtime on downstream peers?
-- =============================================================================
--
-- LOGIC:
--   Filter to downtime_category = 'cascade_upstream' only.
--   JOIN downtime_events → components (as victim) → components (as root cause).
--   Self-join pattern: two aliases of components table.
--   CTE root_cascade_agg: aggregate cascade downtime by root_cause_component_id.
--   Shows both the root-cause component and how many downstream components were hit.
--
-- SELF-JOIN PATTERN:
--   components AS victim (the downstream component that stopped)
--   components AS root   (the upstream trigger component)
--   Link: downtime_events.root_cause_component_id = root.component_id
--
-- =============================================================================

WITH cascade_events AS (
    -- Filter to cascade-only events; resolve both victim and root-cause names
    SELECT
        de.downtime_id,
        de.component_id                           AS victim_component_id,
        victim.component_name                     AS victim_component_name,
        victim.position_in_chain                  AS victim_position,
        de.root_cause_component_id,
        root_cause.component_name                 AS root_cause_component_name,
        root_cause.position_in_chain              AS root_cause_position,
        de.duration_min,
        de.shift_id
    FROM downtime_events de
    INNER JOIN components victim    ON de.component_id             = victim.component_id
    INNER JOIN components root_cause ON de.root_cause_component_id = root_cause.component_id
    WHERE de.downtime_category = 'cascade_upstream'
      AND de.root_cause_component_id IS NOT NULL
),

root_cascade_agg AS (
    -- Aggregate cascade burden by root-cause component
    SELECT
        ce.root_cause_component_id,
        ce.root_cause_component_name,
        ce.root_cause_position,
        COUNT(*)                                              AS cascade_events_caused,
        COUNT(DISTINCT ce.victim_component_id)               AS distinct_victims,
        ROUND(SUM(ce.duration_min), 2)                       AS total_cascade_downtime_min,
        ROUND(AVG(ce.duration_min), 2)                       AS avg_cascade_event_min
    FROM cascade_events ce
    GROUP BY ce.root_cause_component_id, ce.root_cause_component_name,
             ce.root_cause_position
),

cascade_total AS (
    SELECT SUM(total_cascade_downtime_min) AS fleet_cascade_total_min
    FROM root_cascade_agg
)

SELECT
    RANK() OVER (ORDER BY rca.total_cascade_downtime_min DESC) AS cascade_rank,
    rca.root_cause_component_name,
    rca.root_cause_position,
    rca.cascade_events_caused,
    rca.distinct_victims,
    rca.total_cascade_downtime_min,
    rca.avg_cascade_event_min,
    ROUND(rca.total_cascade_downtime_min / NULLIF(ct.fleet_cascade_total_min, 0) * 100.0, 2)
                                                              AS pct_of_fleet_cascade,

    -- Cascade multiplier: how many minutes of downstream downtime per minute of root failure?
    --   Requires joining to root component's own unplanned downtime for comparison.
    ROUND(rca.total_cascade_downtime_min / NULLIF(
        (SELECT SUM(de2.duration_min)
         FROM downtime_events de2
         WHERE de2.component_id = rca.root_cause_component_id
           AND de2.downtime_category = 'unplanned_failure'), 0
    ), 3)                                                     AS cascade_multiplier

FROM root_cascade_agg rca
CROSS JOIN cascade_total ct
ORDER BY rca.total_cascade_downtime_min DESC;
