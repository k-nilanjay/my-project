-- =============================================================================
-- oee_quality.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Compute shift-level OEE Quality (Q) — First-Pass Yield — for each component.
--
-- FORMULA (locked Day 2, CONTEXT.md):
--   Q = good_units / total_units
--   Q ∈ [0.0, 1.0]
--
--   where: good_units = total_units − defective_units − rework_units
--   This invariant is enforced at schema level (schema.sql CHECK constraint).
--
-- INTERPRETATION:
--   Q measures how many units pass quality inspection on the FIRST pass.
--   Rework units are counted as quality losses (they consumed run time but did
--   not yield a good unit without additional processing — Loss 5/6 in Six Big Losses).
--
-- DEFECT ATTRIBUTION (locked Day 2, CONTEXT.md):
--   defect_source_component_id links a quality loss recorded at any inspection
--   point back to its root-cause upstream component.
--   NULL = defect is self-caused by this component.
--   If Gearbox torque variation causes Bearing surface stress that produces a
--   defect at the Bearing inspection point, the Gearbox is the defect source.
--
-- SERIES QUALITY RULE (locked Day 2, CONTEXT.md):
--   Q_sys = Q_1 × Q_2 × Q_3 × Q_4 × Q_5   (independent multiplicative model)
--   Each stage independently passes or fails units: P(all pass) = ∏ P_i(pass).
--   See oee_system_series.sql for the product aggregation.
--
-- SIX BIG LOSSES MAPPING:
--   Loss 5 — Production Defects:  defective_units > 0 (Gearbox, Bearing)
--   Loss 6 — Start-up Rejects:    rework_units > 0 (all components post-PM warm-up)
--
-- SQL DATA SOURCES:
--   production_counts  — total_units, good_units, defective_units, rework_units,
--                        defect_source_component_id
--   production_shifts  — shift_date, shift_label (join context)
--   components         — component_name
--
-- OUTPUT COLUMNS:
--   component_id, component_name, shift_id, shift_date, shift_label,
--   total_units, good_units, defective_units, rework_units,
--   quality, quality_pct, quality_status,
--   defect_source_component_id, defect_source_name
-- =============================================================================

SELECT
    ps.component_id,
    c.component_name,
    ps.shift_id,
    ps.shift_date,
    ps.shift_label,

    -- Raw unit counts (from production_counts)
    pc.total_units,
    pc.good_units,
    pc.defective_units,
    pc.rework_units,

    -- Quality = First-Pass Yield
    -- NULLIF guard: if total_units = 0 (no production this shift), Q is NULL not a divide-by-zero
    CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0) AS quality,

    -- Quality percentage
    ROUND(
        100.0 * CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0),
        2
    ) AS quality_pct,

    -- Quality loss breakdown
    pc.defective_units AS loss5_production_defects,
    pc.rework_units    AS loss6_startup_rejects,

    -- Combined quality loss (defective + rework as % of total) — for waterfall chart
    ROUND(
        100.0 * CAST(pc.defective_units + pc.rework_units AS FLOAT) / NULLIF(pc.total_units, 0),
        2
    ) AS quality_loss_pct,

    -- Quality status tier (same four-tier system as A and P — locked Day 2)
    CASE
        WHEN CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0) >= 0.85 THEN 'WORLD_CLASS'
        WHEN CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0) >= 0.75 THEN 'ACCEPTABLE'
        WHEN CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0) >= 0.65 THEN 'ALERT'
        WHEN pc.total_units > 0                                                 THEN 'CRITICAL'
        ELSE 'NO_PRODUCTION'
    END AS quality_status,

    -- Defect attribution columns
    pc.defect_source_component_id,
    c_src.component_name AS defect_source_name,
    -- Self vs. cascade quality flag
    CASE
        WHEN pc.defect_source_component_id IS NULL THEN 'self_caused'
        ELSE 'cascade_from_upstream'
    END AS defect_origin_type

FROM production_shifts ps
INNER JOIN components c
    ON c.component_id = ps.component_id
INNER JOIN production_counts pc
    ON  pc.shift_id     = ps.shift_id
    AND pc.component_id = ps.component_id
-- Outer join to get the defect source component name (may be NULL for self-caused defects)
LEFT JOIN components c_src
    ON c_src.component_id = pc.defect_source_component_id

ORDER BY
    ps.shift_date ASC,
    ps.component_id ASC;

-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- 1. This query joins INNER to production_counts, so shifts with no count record
--    are excluded. Use a LEFT JOIN version if you need to show 'NO_DATA' rows.
-- 2. For the aggregate Root Cause Analysis view in Power BI (Quality Drill-Down page):
--    GROUP BY defect_source_component_id, SUM(defective_units + rework_units)
--    to build the attribution waterfall.
-- 3. The good_units invariant (good + defective + rework = total) is enforced in
--    schema.sql. If this SELECT ever returns quality > 1.0, it signals a seed/ETL
--    data corruption — run the etl.py validation check immediately.
-- 4. SQLite: CAST(col AS FLOAT) used for integer division safety.
-- =============================================================================
