-- =============================================================================
-- downtime_timeseries.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Day 12 — Time-series trend of downtime duration aggregated by ISO week and
--   calendar month. Exposes production degradation patterns, seasonal maintenance
--   clustering, and long-run reliability improvement (or deterioration) over the
--   90-day observation window.
--
-- TECHNIQUE INVENTORY:
--   CTEs           — stage weekly and monthly aggregation before trend calculation
--   JOINs          — link downtime_events to production_shifts (date resolution)
--                    and to components (dimension enrichment)
--   Subqueries     — rolling baseline and period-over-period comparison
--   strftime()     — SQLite date-part extraction (ISO week, month, year)
--   CASE WHEN      — trend direction labelling (IMPROVING / STABLE / DETERIORATING)
--   NULLIF()       — division-by-zero guard throughout
--
-- DATE STRATEGY:
--   downtime_events does not have a direct date column.
--   Date is resolved via JOIN to production_shifts (shift_date column).
--   This is the correct join path: downtime_events.shift_id → production_shifts.shift_id
--
-- OBSERVATION WINDOW:
--   90 days anchored at 2026-07-20 (Day 7 simulation start, locked Day 11)
--   → ISO weeks 30–43 of 2026
--   → Calendar months: July 2026, August 2026, September 2026, October 2026 (partial)
--
-- QUERY INVENTORY:
--   T1. Weekly downtime totals with rolling 4-week trend and week-over-week delta
--   T2. Monthly downtime totals — component breakdown per month
--   T3. Weekly downtime by category (unplanned / cascade / planned / idle)
--   T4. Per-component weekly trend — independent time-series per component
--   T5. Downtime rate trend — downtime minutes per planned hour (availability inverse)
--   T6. Weekly failure event count vs downtime duration (intensity trend)
--   T7. Month-over-month component comparison — identifies seasonal patterns
-- =============================================================================


-- =============================================================================
-- T1: WEEKLY DOWNTIME TOTALS — 4-week rolling average + WoW delta
-- =============================================================================
--
-- LOGIC:
--   CTE weekly_raw: join downtime_events → production_shifts to extract shift_date.
--                   Group by ISO week string (YYYY-Www format via strftime).
--   CTE weekly_numbered: assign a sequential week index using ROW_NUMBER() for
--                        correct sliding-window frame on non-contiguous ISO weeks.
--   Final SELECT: 4-week trailing average via AVG() OVER (ROWS BETWEEN 3 PRECEDING
--                 AND CURRENT ROW); WoW delta via LAG(total_downtime_min, 1).
--
-- WHY JOIN IS NEEDED:
--   downtime_events has shift_id but no date. The date lives in production_shifts.
--   This is a required JOIN for any time-based aggregation of downtime data.
--
-- WINDOW FRAME:
--   ROWS BETWEEN 3 PRECEDING AND CURRENT ROW = 4-week trailing window
--   (current week + 3 prior weeks). This is a physical row frame, not a range
--   frame, so it is robust even if some weeks have zero events (no gaps in
--   the ordered row sequence).
--
-- =============================================================================

WITH weekly_raw AS (
    -- Stage 1: aggregate downtime per ISO week
    SELECT
        strftime('%Y-W%W', ps.shift_date)         AS iso_week,
        strftime('%Y', ps.shift_date)             AS year_num,
        CAST(strftime('%W', ps.shift_date) AS INTEGER)
                                                   AS week_num,
        COUNT(de.downtime_id)                     AS downtime_events,
        COUNT(DISTINCT de.component_id)           AS components_affected,
        ROUND(SUM(de.duration_min), 2)            AS total_downtime_min,
        ROUND(SUM(CASE WHEN de.downtime_category = 'unplanned_failure'
                       THEN de.duration_min ELSE 0.0 END), 2)
                                                   AS unplanned_min,
        ROUND(SUM(CASE WHEN de.downtime_category = 'cascade_upstream'
                       THEN de.duration_min ELSE 0.0 END), 2)
                                                   AS cascade_min,
        ROUND(SUM(CASE WHEN de.downtime_category = 'planned_maintenance'
                       THEN de.duration_min ELSE 0.0 END), 2)
                                                   AS planned_min,
        ROUND(SUM(CASE WHEN de.downtime_category IN ('idle', 'changeover')
                       THEN de.duration_min ELSE 0.0 END), 2)
                                                   AS idle_changeover_min,

        -- Planned production minutes for this week (all components, all shifts)
        ROUND(SUM(DISTINCT ps.planned_duration_min), 2)
                                                   AS planned_capacity_min
    FROM production_shifts ps
    LEFT JOIN downtime_events de ON ps.shift_id = de.shift_id
    GROUP BY strftime('%Y-W%W', ps.shift_date)
),

weekly_numbered AS (
    -- Stage 2: add sequential row index for stable sliding-window frame
    SELECT
        wr.*,
        ROW_NUMBER() OVER (ORDER BY wr.iso_week)  AS week_seq
    FROM weekly_raw wr
),

weekly_smoothed AS (
    -- Stage 3: calculate rolling averages before comparing them
    SELECT
        wn.*,
        AVG(wn.total_downtime_min) OVER (
            ORDER BY wn.week_seq
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS rolling_4wk_avg
    FROM weekly_numbered wn
)

-- Stage 4: trend calculations
SELECT
    ws.iso_week,
    ws.year_num,
    ws.week_num,
    ws.week_seq,
    ws.downtime_events,
    ws.components_affected,
    ws.total_downtime_min,
    ws.unplanned_min,
    ws.cascade_min,
    ws.planned_min,
    ws.idle_changeover_min,

    -- 4-week trailing rolling average (smoothed trend line)
    ROUND(ws.rolling_4wk_avg, 2)                   AS rolling_4wk_avg_min,

    -- 2-week trailing rolling average (shorter, more reactive signal)
    ROUND(
        AVG(ws.total_downtime_min) OVER (
            ORDER BY ws.week_seq
            ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
        ), 2
    )                                              AS rolling_2wk_avg_min,

    -- Cumulative running total (escalation curve)
    ROUND(
        SUM(ws.total_downtime_min) OVER (
            ORDER BY ws.week_seq
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                              AS cumulative_downtime_min,

    -- Week-over-week absolute delta
    ROUND(
        ws.total_downtime_min - LAG(ws.total_downtime_min, 1) OVER (
            ORDER BY ws.week_seq
        ), 2
    )                                              AS wow_delta_min,

    -- Trend direction using 4-week average comparison with prior 4-week window
    CASE
        WHEN ws.rolling_4wk_avg > LAG(ws.rolling_4wk_avg, 4) OVER (ORDER BY ws.week_seq) * 1.05
        THEN 'DETERIORATING'
        WHEN ws.rolling_4wk_avg < LAG(ws.rolling_4wk_avg, 4) OVER (ORDER BY ws.week_seq) * 0.95
        THEN 'IMPROVING'
        ELSE 'STABLE'
    END                                            AS trend_direction

FROM weekly_smoothed ws
ORDER BY ws.week_seq;


-- =============================================================================
-- T2: MONTHLY DOWNTIME TOTALS — per-component breakdown
-- =============================================================================
--
-- LOGIC:
--   CTE monthly_base: group by (YYYY-MM, component_id) — one row per component
--                     per month.
--   CTE monthly_fleet: sum across components per month — fleet-level row per month.
--   Final SELECT: join component rows to fleet totals; compute each component's
--                 share of the month's total downtime.
--
-- WHY MONTH GRANULARITY:
--   Weekly view (T1) is better for operational monitoring.
--   Monthly view is better for management reporting and MoM KPI comparisons.
--   Both are provided as separate queries for Power BI flexibility.
--
-- =============================================================================

WITH monthly_base AS (
    SELECT
        strftime('%Y-%m', ps.shift_date)           AS year_month,
        strftime('%Y', ps.shift_date)              AS year_num,
        CAST(strftime('%m', ps.shift_date) AS INTEGER)
                                                   AS month_num,
        de.component_id,
        c.component_name,
        c.maintenance_strategy,
        COUNT(de.downtime_id)                      AS downtime_events,
        ROUND(SUM(de.duration_min), 2)             AS total_downtime_min,
        ROUND(SUM(CASE WHEN de.downtime_category = 'unplanned_failure'
                       THEN de.duration_min ELSE 0.0 END), 2)
                                                   AS unplanned_min
    FROM production_shifts ps
    LEFT JOIN downtime_events de ON ps.shift_id = de.shift_id
    INNER JOIN components c ON de.component_id = c.component_id
    WHERE de.downtime_id IS NOT NULL
    GROUP BY strftime('%Y-%m', ps.shift_date),
             de.component_id, c.component_name, c.maintenance_strategy
),

monthly_fleet AS (
    -- Fleet-level monthly total for share calculation
    SELECT
        year_month,
        ROUND(SUM(total_downtime_min), 2)          AS fleet_downtime_min,
        SUM(downtime_events)                       AS fleet_event_count
    FROM monthly_base
    GROUP BY year_month
)

SELECT
    mb.year_month,
    mb.year_num,
    mb.month_num,
    mb.component_id,
    mb.component_name,
    mb.maintenance_strategy,
    mb.downtime_events,
    mb.total_downtime_min,
    mb.unplanned_min,
    mf.fleet_downtime_min,
    mf.fleet_event_count,

    -- This component's share of the month's fleet downtime
    ROUND(mb.total_downtime_min / NULLIF(mf.fleet_downtime_min, 0) * 100.0, 2)
                                                   AS pct_of_month_downtime,

    -- Month-over-month delta per component
    ROUND(
        mb.total_downtime_min - LAG(mb.total_downtime_min, 1) OVER (
            PARTITION BY mb.component_id
            ORDER BY mb.year_month
        ), 2
    )                                              AS mom_delta_min,

    -- RANK within month: which component was worst this month?
    RANK() OVER (
        PARTITION BY mb.year_month
        ORDER BY mb.total_downtime_min DESC
    )                                              AS monthly_rank

FROM monthly_base mb
INNER JOIN monthly_fleet mf ON mb.year_month = mf.year_month
ORDER BY mb.year_month, mb.component_id;


-- =============================================================================
-- T3: WEEKLY DOWNTIME BY CATEGORY (stacked series for Power BI area chart)
-- =============================================================================
--
-- LOGIC:
--   One row per (ISO week, downtime_category) — long-format output ready for
--   Power BI stacked area or bar chart.
--   CTE week_cat_raw: cross JOIN to ensure every (week, category) pair appears,
--                     even weeks with zero events in that category.
--   Uses LEFT JOIN to produce zero-fill rows where needed.
--
-- OUTPUT FORMAT (long):
--   iso_week | downtime_category | total_min | pct_of_week_total
--   This format is ideal for Power BI legend-based stacked charts.
--
-- =============================================================================

WITH all_weeks AS (
    -- Distinct ISO weeks in the observation window
    SELECT DISTINCT strftime('%Y-W%W', shift_date) AS iso_week
    FROM production_shifts
    ORDER BY iso_week
),

all_categories AS (
    -- Distinct downtime categories (locked Day 2)
    SELECT 'unplanned_failure'   AS downtime_category UNION ALL
    SELECT 'planned_maintenance'                      UNION ALL
    SELECT 'changeover'                               UNION ALL
    SELECT 'idle'                                     UNION ALL
    SELECT 'cascade_upstream'
),

week_cat_actual AS (
    -- Actual observed downtime per (week, category)
    SELECT
        strftime('%Y-W%W', ps.shift_date)     AS iso_week,
        de.downtime_category,
        ROUND(SUM(de.duration_min), 2)         AS total_downtime_min,
        COUNT(de.downtime_id)                  AS event_count
    FROM production_shifts ps
    INNER JOIN downtime_events de ON ps.shift_id = de.shift_id
    GROUP BY strftime('%Y-W%W', ps.shift_date), de.downtime_category
),

week_totals AS (
    SELECT iso_week, SUM(total_downtime_min) AS week_total_min
    FROM week_cat_actual
    GROUP BY iso_week
)

SELECT
    aw.iso_week,
    ac.downtime_category,
    COALESCE(wca.total_downtime_min, 0.0)      AS total_downtime_min,
    COALESCE(wca.event_count, 0)               AS event_count,
    ROUND(
        COALESCE(wca.total_downtime_min, 0.0)
        / NULLIF(wt.week_total_min, 0) * 100.0, 2
    )                                          AS pct_of_week_total,

    -- Running cumulative per category (for escalation analysis)
    ROUND(
        SUM(COALESCE(wca.total_downtime_min, 0.0)) OVER (
            PARTITION BY ac.downtime_category
            ORDER BY aw.iso_week
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                          AS cumulative_by_category_min

FROM all_weeks aw
CROSS JOIN all_categories ac
LEFT JOIN week_cat_actual wca
       ON aw.iso_week = wca.iso_week
      AND ac.downtime_category = wca.downtime_category
LEFT JOIN week_totals wt ON aw.iso_week = wt.iso_week
ORDER BY aw.iso_week, ac.downtime_category;


-- =============================================================================
-- T4: PER-COMPONENT WEEKLY TREND — independent time-series per component
-- =============================================================================
--
-- LOGIC:
--   One time-series per component. CTE component_weekly: group by (component_id,
--   ISO week). Outer SELECT applies window functions PARTITIONED BY component_id
--   so each component has its own independent rolling average and cumulative total.
--   This separation allows Power BI to plot 5 separate trend lines on the same chart
--   without cross-contamination between component windows.
--
-- WHY PARTITION BY COMPONENT:
--   Without PARTITION BY, the rolling average would mix different components' weeks
--   together. PARTITION BY component_id creates independent calculation windows —
--   the trend for Bearing is computed only over Bearing's weeks.
--
-- =============================================================================

WITH component_weekly AS (
    SELECT
        ps.shift_date,
        strftime('%Y-W%W', ps.shift_date)          AS iso_week,
        de.component_id,
        c.component_name,
        c.position_in_chain,
        ROUND(SUM(de.duration_min), 2)             AS total_downtime_min,
        COUNT(de.downtime_id)                      AS event_count,
        ROUND(SUM(CASE WHEN de.downtime_category = 'unplanned_failure'
                       THEN de.duration_min ELSE 0.0 END), 2)
                                                   AS unplanned_min
    FROM production_shifts ps
    INNER JOIN downtime_events de ON ps.shift_id = de.shift_id
    INNER JOIN components c ON de.component_id = c.component_id
    GROUP BY strftime('%Y-W%W', ps.shift_date),
             de.component_id, c.component_name, c.position_in_chain
),

component_weekly_seq AS (
    -- Assign per-component sequential index for stable window frames
    SELECT
        cw.*,
        ROW_NUMBER() OVER (
            PARTITION BY cw.component_id
            ORDER BY cw.iso_week
        )                                          AS comp_week_seq
    FROM component_weekly cw
)

SELECT
    cws.iso_week,
    cws.component_id,
    cws.component_name,
    cws.position_in_chain,
    cws.comp_week_seq,
    cws.total_downtime_min,
    cws.event_count,
    cws.unplanned_min,

    -- Per-component 4-week rolling average (independent window per component)
    ROUND(
        AVG(cws.total_downtime_min) OVER (
            PARTITION BY cws.component_id
            ORDER BY cws.comp_week_seq
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ), 2
    )                                              AS rolling_4wk_avg_min,

    -- Per-component cumulative total
    ROUND(
        SUM(cws.total_downtime_min) OVER (
            PARTITION BY cws.component_id
            ORDER BY cws.comp_week_seq
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                              AS cumulative_min,

    -- Week-over-week change per component
    ROUND(
        cws.total_downtime_min - LAG(cws.total_downtime_min, 1) OVER (
            PARTITION BY cws.component_id
            ORDER BY cws.comp_week_seq
        ), 2
    )                                              AS wow_delta_min,

    -- Relative ranking within this week across all components
    RANK() OVER (
        PARTITION BY cws.iso_week
        ORDER BY cws.total_downtime_min DESC
    )                                              AS weekly_rank_in_fleet

FROM component_weekly_seq cws
ORDER BY cws.component_id, cws.comp_week_seq;


-- =============================================================================
-- T5: DOWNTIME RATE TREND — downtime minutes per planned production hour
-- =============================================================================
--
-- LOGIC:
--   Downtime rate = total_downtime_min / total_planned_min_for_week.
--   Unlike absolute minutes (T1), the rate normalises for weeks with different
--   planned capacity (e.g., a week with more shifts has more total planned time).
--   This is the inverse of Availability: downtime_rate = 1 - A.
--
--   CTE rate_base: aggregate both downtime minutes and planned minutes per week.
--   Final SELECT: compute rate and apply rolling average for trend signal.
--
--   KEY JOIN: downtime_events → production_shifts is the backbone.
--   LEFT JOIN ensures weeks with zero downtime appear (rate = 0.0).
--
-- INTERPRETATION:
--   downtime_rate = 0.00 → perfect availability (A = 1.0)
--   downtime_rate = 0.05 → 5% of planned time lost → A = 95%
--
-- =============================================================================

WITH rate_base AS (
    SELECT
        strftime('%Y-W%W', ps.shift_date)         AS iso_week,
        ROUND(SUM(ps.planned_duration_min), 2)    AS total_planned_min,
        ROUND(SUM(COALESCE(de.duration_min, 0)), 2)
                                                   AS total_downtime_min,
        COUNT(de.downtime_id)                     AS downtime_events
    FROM production_shifts ps
    LEFT JOIN downtime_events de ON ps.shift_id = de.shift_id
    GROUP BY strftime('%Y-W%W', ps.shift_date)
),

rate_seq AS (
    SELECT
        rb.*,
        ROUND(rb.total_downtime_min / NULLIF(rb.total_planned_min, 0), 6)
                                                   AS downtime_rate,
        ROUND(1.0 - rb.total_downtime_min / NULLIF(rb.total_planned_min, 0), 6)
                                                   AS weekly_availability,
        ROW_NUMBER() OVER (ORDER BY rb.iso_week)  AS week_seq
    FROM rate_base rb
)

SELECT
    rs.iso_week,
    rs.week_seq,
    rs.total_planned_min,
    rs.total_downtime_min,
    rs.downtime_events,
    rs.downtime_rate,
    rs.weekly_availability,

    -- 4-week rolling mean of downtime rate (smoothed availability trend)
    ROUND(
        AVG(rs.downtime_rate) OVER (
            ORDER BY rs.week_seq
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ), 6
    )                                              AS rolling_4wk_rate,

    -- Rolling availability (inverse: 1 - rolling rate)
    ROUND(
        1.0 - AVG(rs.downtime_rate) OVER (
            ORDER BY rs.week_seq
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ), 6
    )                                              AS rolling_4wk_availability,

    -- Week-over-week rate delta (positive = more downtime = deterioration)
    ROUND(
        rs.downtime_rate - LAG(rs.downtime_rate, 1) OVER (ORDER BY rs.week_seq),
        6
    )                                              AS wow_rate_delta,

    -- Flag weeks exceeding 10% downtime rate (availability < 90%)
    CASE WHEN rs.downtime_rate > 0.10 THEN 'AVAILABILITY_ALERT' ELSE 'NORMAL' END
                                                   AS availability_status

FROM rate_seq rs
ORDER BY rs.week_seq;


-- =============================================================================
-- T6: WEEKLY FAILURE EVENT COUNT vs DOWNTIME DURATION (intensity trend)
-- =============================================================================
--
-- LOGIC:
--   Two metrics per week: count of unplanned_failure events AND their total duration.
--   Their ratio = avg downtime per failure event = a proxy for repair effectiveness.
--   If count rises but avg duration falls → maintenance response is improving.
--   If both rise → cascade or systemic deterioration.
--
--   CTE intensity_base: filter to unplanned_failure only for this comparison.
--   The query joins to production_shifts for the week key.
--   Subquery in the SELECT retrieves fleet mean duration for comparison.
--
-- =============================================================================

WITH intensity_base AS (
    SELECT
        strftime('%Y-W%W', ps.shift_date)         AS iso_week,
        COUNT(de.downtime_id)                     AS failure_event_count,
        ROUND(SUM(de.duration_min), 2)            AS total_failure_downtime_min,
        ROUND(AVG(de.duration_min), 2)            AS avg_duration_per_event_min,
        ROUND(MAX(de.duration_min), 2)            AS max_event_min,
        COUNT(DISTINCT de.component_id)           AS components_failed
    FROM production_shifts ps
    INNER JOIN downtime_events de ON ps.shift_id = de.shift_id
    WHERE de.downtime_category = 'unplanned_failure'
    GROUP BY strftime('%Y-W%W', ps.shift_date)
),

intensity_seq AS (
    SELECT
        ib.*,
        ROW_NUMBER() OVER (ORDER BY ib.iso_week) AS week_seq
    FROM intensity_base ib
),

fleet_avg_duration AS (
    -- Scalar: fleet-wide mean failure event duration (benchmark for comparison)
    SELECT ROUND(AVG(avg_duration_per_event_min), 2) AS fleet_mean_event_min
    FROM intensity_base
)

SELECT
    ins.iso_week,
    ins.week_seq,
    ins.failure_event_count,
    ins.total_failure_downtime_min,
    ins.avg_duration_per_event_min,
    ins.max_event_min,
    ins.components_failed,
    fad.fleet_mean_event_min,

    -- 4-week rolling event count (failure frequency trend)
    ROUND(
        AVG(CAST(ins.failure_event_count AS FLOAT)) OVER (
            ORDER BY ins.week_seq
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ), 2
    )                                              AS rolling_4wk_event_count,

    -- 4-week rolling average duration (repair effectiveness trend)
    ROUND(
        AVG(ins.avg_duration_per_event_min) OVER (
            ORDER BY ins.week_seq
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ), 2
    )                                              AS rolling_4wk_avg_duration_min,

    -- Above or below fleet mean: flag expensive weeks
    CASE
        WHEN ins.avg_duration_per_event_min > fad.fleet_mean_event_min * 1.20
        THEN 'ABOVE_MEAN_EXPENSIVE'
        WHEN ins.avg_duration_per_event_min < fad.fleet_mean_event_min * 0.80
        THEN 'BELOW_MEAN_EFFICIENT'
        ELSE 'NEAR_MEAN'
    END                                            AS duration_band,

    -- Intensity score: event_count × avg_duration (combines frequency and severity)
    ROUND(ins.failure_event_count * ins.avg_duration_per_event_min, 2)
                                                   AS intensity_score,

    -- Rolling intensity (4-week)
    ROUND(
        AVG(ins.failure_event_count * ins.avg_duration_per_event_min) OVER (
            ORDER BY ins.week_seq
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ), 2
    )                                              AS rolling_4wk_intensity

FROM intensity_seq ins
CROSS JOIN fleet_avg_duration fad
ORDER BY ins.week_seq;


-- =============================================================================
-- T7: MONTH-OVER-MONTH COMPONENT COMPARISON (MoM trend table)
-- =============================================================================
--
-- LOGIC:
--   Uses a subquery-in-FROM (derived table) to compute monthly totals per component.
--   Outer query applies LAG(1) OVER (PARTITION BY component_id ORDER BY year_month)
--   to get the previous month's value for the MoM delta.
--   MoM % change = (current - previous) / previous × 100.
--   Seasons: months Jul–Sep = SUMMER, Oct–Dec = AUTUMN (for 90-day window only).
--   Identifies components whose downtime is worsening month-over-month vs improving.
--
-- SELF-CONTAINED NOTE:
--   This query does NOT reuse the monthly_base CTE from T2. It is intentionally
--   written as a standalone query with a subquery so it can be executed in isolation
--   without running T2 first. The logic is equivalent but expressed differently
--   to demonstrate the subquery pattern alongside the CTE pattern.
--
-- =============================================================================

SELECT
    mom.year_month,
    mom.component_id,
    mom.component_name,
    mom.monthly_downtime_min,
    mom.unplanned_min,

    -- Previous month's downtime for this component (LAG over months per component)
    LAG(mom.monthly_downtime_min, 1) OVER (
        PARTITION BY mom.component_id
        ORDER BY mom.year_month
    )                                              AS prev_month_downtime_min,

    -- Month-over-month absolute change
    ROUND(
        mom.monthly_downtime_min - LAG(mom.monthly_downtime_min, 1) OVER (
            PARTITION BY mom.component_id
            ORDER BY mom.year_month
        ), 2
    )                                              AS mom_delta_min,

    -- Month-over-month % change (positive = more downtime = deteriorating)
    ROUND(
        (mom.monthly_downtime_min - LAG(mom.monthly_downtime_min, 1) OVER (
             PARTITION BY mom.component_id
             ORDER BY mom.year_month
         ))
        / NULLIF(LAG(mom.monthly_downtime_min, 1) OVER (
             PARTITION BY mom.component_id
             ORDER BY mom.year_month
          ), 0) * 100.0, 2
    )                                              AS mom_pct_change,

    -- Trend classification based on MoM %
    CASE
        WHEN mom.monthly_downtime_min > LAG(mom.monthly_downtime_min, 1) OVER (
                 PARTITION BY mom.component_id ORDER BY mom.year_month
             ) * 1.10
        THEN 'DETERIORATING'
        WHEN mom.monthly_downtime_min < LAG(mom.monthly_downtime_min, 1) OVER (
                 PARTITION BY mom.component_id ORDER BY mom.year_month
             ) * 0.90
        THEN 'IMPROVING'
        WHEN LAG(mom.monthly_downtime_min, 1) OVER (
                 PARTITION BY mom.component_id ORDER BY mom.year_month
             ) IS NULL
        THEN 'BASELINE_MONTH'
        ELSE 'STABLE'
    END                                            AS mom_trend,

    -- Rank within month: which component is worst this month?
    RANK() OVER (
        PARTITION BY mom.year_month
        ORDER BY mom.monthly_downtime_min DESC
    )                                              AS monthly_rank

FROM (
    -- Derived table: monthly aggregation per component
    SELECT
        strftime('%Y-%m', ps.shift_date)           AS year_month,
        de.component_id,
        c.component_name,
        ROUND(SUM(de.duration_min), 2)             AS monthly_downtime_min,
        ROUND(SUM(CASE WHEN de.downtime_category = 'unplanned_failure'
                       THEN de.duration_min ELSE 0.0 END), 2)
                                                   AS unplanned_min
    FROM production_shifts ps
    INNER JOIN downtime_events de ON ps.shift_id = de.shift_id
    INNER JOIN components c ON de.component_id = c.component_id
    GROUP BY strftime('%Y-%m', ps.shift_date),
             de.component_id, c.component_name
) AS mom
ORDER BY mom.component_id, mom.year_month;
