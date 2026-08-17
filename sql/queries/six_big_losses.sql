-- =============================================================================
-- six_big_losses.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Categorise all production losses into the Six Big Losses taxonomy and
--   compute the time / percentage contribution of each loss category per shift
--   per component.  Output feeds the Power BI OEE Waterfall Chart.
--
-- SIX BIG LOSSES (TPM / JIPM standard — locked Day 2, CONTEXT.md):
--
--   Availability Losses:
--     Loss 1 — Unplanned Breakdowns   downtime_category = 'unplanned_failure'
--     Loss 2 — Setup & Changeover     downtime_category = 'changeover'
--
--   Performance Losses:
--     Loss 3 — Minor Stops & Idling   downtime_category = 'idle'
--                                     + cascade_upstream (collateral minor stops)
--     Loss 4 — Reduced Speed          Computed as: run_time − ideal_production_time
--                                     i.e., time "wasted" running below rated speed
--
--   Quality Losses:
--     Loss 5 — Production Defects     (defective_units × ideal_cycle_time_min)
--     Loss 6 — Start-up Rejects       (rework_units × ideal_cycle_time_min)
--
-- COMPONENT-TO-LOSS MAPPING (locked Day 2, CONTEXT.md):
--   Loss 1: Bearing, Gearbox           (wear-out failures cause unplanned stops)
--   Loss 2: Bearing (re-grease), Gearbox (oil change) (PM changeover periods)
--   Loss 3: Coupling                   (misalignment micro-stops)
--   Loss 4: Motor Housing (thermal derating), Shaft (imbalance-induced slowdown)
--   Loss 5: Gearbox (torque variation), Bearing (surface defects)
--   Loss 6: All components (post-PM warm-up start-up rejects)
--
-- OEE WATERFALL CHART LOGIC:
--   100% Planned Production Time
--   − Loss 1 (Breakdown minutes / planned × 100)     → remaining = Availability base
--   − Loss 2 (Changeover minutes / planned × 100)    → Availability
--   − Loss 3 (Idle + cascade minutes / run × 100)    → Performance base
--   − Loss 4 (Speed loss minutes / run × 100)        → Performance
--   − Loss 5 (Defect time / run × 100)               → Quality base
--   − Loss 6 (Rework time / run × 100)               → OEE %
--
-- SQL DATA SOURCES:
--   production_shifts, downtime_events, production_counts, components
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 1: Availability losses from downtime_events
-- ─────────────────────────────────────────────────────────────────────────────
WITH downtime_by_loss AS (
    SELECT
        de.component_id,
        de.shift_id,

        -- Loss 1: Unplanned Breakdowns
        SUM(CASE WHEN de.downtime_category = 'unplanned_failure'
                 THEN de.duration_min ELSE 0.0 END) AS loss1_breakdown_min,

        -- Loss 2: Setup & Changeover
        SUM(CASE WHEN de.downtime_category = 'changeover'
                 THEN de.duration_min ELSE 0.0 END) AS loss2_changeover_min,

        -- Loss 3 (partial): Idle time from downtime_events
        SUM(CASE WHEN de.downtime_category IN ('idle', 'cascade_upstream')
                 THEN de.duration_min ELSE 0.0 END) AS loss3_idle_min

    FROM downtime_events de
    GROUP BY de.component_id, de.shift_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 2: Planned production time and run time per shift
-- ─────────────────────────────────────────────────────────────────────────────
shift_base AS (
    SELECT
        ps.shift_id,
        ps.component_id,
        ps.shift_date,
        ps.shift_label,
        ps.planned_duration_min,

        -- Total non-PM downtime (sum of Loss 1 + Loss 2 + Loss 3)
        COALESCE(dl.loss1_breakdown_min, 0.0)
            + COALESCE(dl.loss2_changeover_min, 0.0)
            + COALESCE(dl.loss3_idle_min, 0.0) AS total_availability_loss_min,

        -- Run time = planned − (Loss1 + Loss2 + Loss3)
        ps.planned_duration_min
            - COALESCE(dl.loss1_breakdown_min, 0.0)
            - COALESCE(dl.loss2_changeover_min, 0.0)
            - COALESCE(dl.loss3_idle_min, 0.0) AS run_time_min,

        COALESCE(dl.loss1_breakdown_min, 0.0)   AS loss1_breakdown_min,
        COALESCE(dl.loss2_changeover_min, 0.0)  AS loss2_changeover_min,
        COALESCE(dl.loss3_idle_min, 0.0)        AS loss3_idle_min

    FROM production_shifts ps
    LEFT JOIN downtime_by_loss dl
        ON  dl.shift_id     = ps.shift_id
        AND dl.component_id = ps.component_id
),

-- ─────────────────────────────────────────────────────────────────────────────
-- CTE 3: Quality and performance loss from production_counts
-- ─────────────────────────────────────────────────────────────────────────────
quality_performance_losses AS (
    SELECT
        pc.component_id,
        pc.shift_id,
        pc.total_units,
        pc.good_units,
        pc.defective_units,
        pc.rework_units,
        pc.ideal_cycle_time_min,

        -- Ideal production time = total_units × ideal_cycle_time (what it SHOULD take)
        pc.total_units * pc.ideal_cycle_time_min AS ideal_production_min,

        -- Loss 5: Defect time — time consumed making units that were rejected
        pc.defective_units * pc.ideal_cycle_time_min AS loss5_defect_min,

        -- Loss 6: Rework time — time spent producing units needing rework
        pc.rework_units * pc.ideal_cycle_time_min AS loss6_rework_min

    FROM production_counts pc
)

-- ─────────────────────────────────────────────────────────────────────────────
-- FINAL SELECT: Six Big Losses per component per shift
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    sb.component_id,
    c.component_name,
    sb.shift_id,
    sb.shift_date,
    sb.shift_label,
    sb.planned_duration_min,
    sb.run_time_min,

    -- ── AVAILABILITY LOSSES ───────────────────────────────────────────────────

    -- Loss 1: Unplanned Breakdowns (minutes + % of planned time)
    sb.loss1_breakdown_min,
    ROUND(100.0 * sb.loss1_breakdown_min / NULLIF(sb.planned_duration_min, 0), 2) AS loss1_pct,

    -- Loss 2: Setup & Changeover
    sb.loss2_changeover_min,
    ROUND(100.0 * sb.loss2_changeover_min / NULLIF(sb.planned_duration_min, 0), 2) AS loss2_pct,

    -- ── PERFORMANCE LOSSES ────────────────────────────────────────────────────

    -- Loss 3: Minor Stops & Idling
    sb.loss3_idle_min,
    ROUND(100.0 * sb.loss3_idle_min / NULLIF(sb.planned_duration_min, 0), 2) AS loss3_pct,

    -- Loss 4: Reduced Speed
    -- Definition: time "lost" because unit production rate was below nameplate rate.
    -- = Run Time − Ideal Production Time (if positive; negative means running faster than rated)
    CASE
        WHEN qpl.ideal_production_min IS NOT NULL
        THEN MAX(0.0, sb.run_time_min - qpl.ideal_production_min)
        ELSE NULL
    END AS loss4_speed_min,
    CASE
        WHEN qpl.ideal_production_min IS NOT NULL AND sb.planned_duration_min > 0
        THEN ROUND(
            100.0 * MAX(0.0, sb.run_time_min - qpl.ideal_production_min) / sb.planned_duration_min,
            2)
        ELSE NULL
    END AS loss4_pct,

    -- ── QUALITY LOSSES ────────────────────────────────────────────────────────

    -- Loss 5: Production Defects (minutes of wasted production capacity)
    COALESCE(qpl.loss5_defect_min, 0.0) AS loss5_defect_min,
    ROUND(100.0 * COALESCE(qpl.loss5_defect_min, 0.0) / NULLIF(sb.planned_duration_min, 0), 2) AS loss5_pct,

    -- Loss 6: Start-up Rejects / Rework
    COALESCE(qpl.loss6_rework_min, 0.0) AS loss6_rework_min,
    ROUND(100.0 * COALESCE(qpl.loss6_rework_min, 0.0) / NULLIF(sb.planned_duration_min, 0), 2) AS loss6_pct,

    -- ── SUMMARY COLUMNS ───────────────────────────────────────────────────────

    -- Total loss (all 6 categories combined, in minutes)
    sb.loss1_breakdown_min + sb.loss2_changeover_min + sb.loss3_idle_min
        + COALESCE(MAX(0.0, sb.run_time_min - qpl.ideal_production_min), 0.0)
        + COALESCE(qpl.loss5_defect_min, 0.0)
        + COALESCE(qpl.loss6_rework_min, 0.0) AS total_loss_min,

    -- Effective OEE time (good production time)
    COALESCE(qpl.good_units * qpl.ideal_cycle_time_min, 0.0) AS effective_production_min,

    -- Computed OEE % from waterfall (cross-check against oee_composite.sql)
    ROUND(
        100.0 * COALESCE(qpl.good_units * qpl.ideal_cycle_time_min, 0.0) / NULLIF(sb.planned_duration_min, 0),
        2
    ) AS oee_pct_waterfall,

    -- Primary failure category label for this component+shift (for Power BI annotation)
    CASE
        WHEN sb.loss1_breakdown_min >= sb.loss2_changeover_min
         AND sb.loss1_breakdown_min >= sb.loss3_idle_min
         AND sb.loss1_breakdown_min >= COALESCE(qpl.loss5_defect_min, 0.0)
         AND sb.loss1_breakdown_min >= COALESCE(qpl.loss6_rework_min, 0.0)
         AND sb.loss1_breakdown_min > 0
        THEN 'Loss 1 — Unplanned Breakdown'
        WHEN sb.loss2_changeover_min >= sb.loss3_idle_min
         AND sb.loss2_changeover_min >= COALESCE(qpl.loss5_defect_min, 0.0)
         AND sb.loss2_changeover_min > 0
        THEN 'Loss 2 — Setup & Changeover'
        WHEN sb.loss3_idle_min > 0
        THEN 'Loss 3 — Minor Stops & Idling'
        WHEN COALESCE(qpl.loss5_defect_min, 0.0) > COALESCE(qpl.loss6_rework_min, 0.0)
        THEN 'Loss 5 — Production Defects'
        WHEN COALESCE(qpl.loss6_rework_min, 0.0) > 0
        THEN 'Loss 6 — Start-up Rejects'
        ELSE 'Loss 4 — Reduced Speed / No Major Loss'
    END AS dominant_loss_category

FROM shift_base sb
INNER JOIN components c
    ON c.component_id = sb.component_id
LEFT JOIN quality_performance_losses qpl
    ON  qpl.shift_id     = sb.shift_id
    AND qpl.component_id = sb.component_id

ORDER BY
    sb.shift_date ASC,
    sb.component_id ASC;

-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- 1. Power BI Waterfall Chart data:
--    Use columns loss1_pct through loss6_pct as the six waterfall bars.
--    Start from 100 (planned), subtract each loss in order → final bar = oee_pct.
-- 2. dominant_loss_category enables the "Root Cause at a Glance" slicer in the
--    Six Big Losses page.  Colour each loss category distinctly.
-- 3. Verify: loss1 + loss2 + loss3 + loss4 + loss5 + loss6 + oee_pct_waterfall ≈ 100.
--    Small rounding differences are expected; large discrepancies signal ETL issues.
-- 4. Loss 4 (Reduced Speed) requires production_counts data. If counts are absent,
--    loss4_speed_min = NULL and the waterfall cannot close. Use a placeholder = 0.
-- 5. SQLite: MAX() as a scalar function uses the built-in MAX(a, b) form.
--    In SQL Server, use CASE WHEN a >= b THEN a ELSE b END instead of MAX(a, b).
-- =============================================================================
