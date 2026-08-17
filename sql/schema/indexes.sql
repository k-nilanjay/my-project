-- =============================================================================
-- sql/schema/indexes.sql — Manufacturing & Industrial Analytics FYP
-- Day 13: Query Review, Optimization & Testing
-- =============================================================================
-- PURPOSE:
--   Define and apply performance indexes for the existing 12-file SQL query
--   library. Every index below directly targets a JOIN predicate, GROUP BY
--   column set, or ORDER BY / window-function frame observed across the query
--   library built Days 4–12.
--
-- DEPLOYMENT:
--   Run ONCE against data/manufacturing.db after schema.sql and seed.sql.
--   All statements use CREATE INDEX IF NOT EXISTS — idempotent, safe to
--   re-run after dev resets.
--
-- SQLite note:
--   SQLite uses B-tree indexes for equality and range scans.
--   A composite index (a, b) satisfies ORDER BY a, b and WHERE a = ? AND b = ?
--   without a separate single-column index on a.
--   Covering indexes: if ALL columns in a SELECT are in the index (including
--   the WHERE / GROUP BY columns), SQLite can resolve the query from the index
--   alone (Index-Only Scan), skipping the table entirely.
--
-- SQL Server note:
--   Syntax is compatible — SQL Server also supports CREATE INDEX IF NOT EXISTS
--   via the same keyword (2016+). For older versions, wrap in
--   IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE ...).
--
-- ANALYSIS SUMMARY — hottest query patterns observed in the library:
--
--   1. downtime_events JOIN production_shifts ON shift_id + component_id
--      ► Used in: oee_availability, oee_composite, oee_performance,
--                 downtime_pareto (P1–P7), downtime_timeseries (T1–T7)
--
--   2. downtime_events GROUP BY downtime_category (+ component_id)
--      ► Used in: downtime_pareto (P1–P4), six_big_losses, oee_availability
--
--   3. downtime_events filter on root_cause_component_id (cascade attribution)
--      ► Used in: downtime_pareto P7 (self-join / correlated subquery)
--
--   4. production_shifts lookup by component_id + shift_date (time-series)
--      ► Used in: downtime_timeseries (T1–T7), oee_window_analytics
--
--   5. sensor_readings lookup by component_id + ts (time-window JOIN)
--      ► Used in: oee_performance (RPM fallback CTE), anomaly_rate_by_sensor
--
--   6. sensor_readings filter on is_anomaly, is_failure_event
--      ► Used in: anomaly_rate_by_sensor, failure_rate_by_component
--
--   7. failure_log lookup by component_id (MTBF computation)
--      ► Used in: mtbf_from_failure_log, failure_rate_by_component
--
--   8. production_counts JOIN on shift_id + component_id (OEE Quality / Perf)
--      ► Used in: oee_quality, oee_composite, oee_performance, six_big_losses
--
-- =============================================================================

PRAGMA foreign_keys = ON;

-- =============================================================================
-- SECTION 1: downtime_events indexes
-- =============================================================================
-- Rationale: downtime_events is the hottest table in the library. Every OEE
-- query, every Pareto query, and every time-series query touches it. It has
-- 142 rows in the current dataset but will grow with every simulation cycle.
-- The indexes below collectively cover all observed JOIN, GROUP BY, and
-- ORDER BY patterns.
-- =============================================================================

-- IDX-DE-01: Composite (shift_id, component_id)
-- ► Covers the primary JOIN predicate in ALL OEE queries:
--     LEFT JOIN downtime_events de
--         ON de.shift_id     = ps.shift_id
--         AND de.component_id = ps.component_id
-- ► Also accelerates GROUP BY (component_id, shift_id) in oee_availability
--   and oee_composite CTEs.
-- ► Leftmost key = shift_id (highest cardinality for a narrow lookup);
--   component_id as second key narrows to 1-of-5 per shift.
CREATE INDEX IF NOT EXISTS idx_dte_shift_comp
    ON downtime_events (shift_id, component_id);

-- IDX-DE-02: Composite (downtime_category, component_id)
-- ► Covers the primary GROUP BY + WHERE filter pattern in Pareto queries:
--     GROUP BY downtime_category, component_id
--   AND the CASE WHEN downtime_category = ... in oee_availability / six_big_losses.
-- ► Covering partial scan: SQLite can resolve the category filter from the index
--   before touching the heap for duration_min.
CREATE INDEX IF NOT EXISTS idx_dte_category_comp
    ON downtime_events (downtime_category, component_id);

-- IDX-DE-03: (component_id, downtime_category, duration_min) — covering for aggregation
-- ► Enables a covering Index-Only Scan for queries that compute
--   SUM(duration_min) WHERE downtime_category = ? GROUP BY component_id.
--   Targeted specifically at downtime_pareto P1–P4 aggregation CTEs.
-- ► The third key (duration_min) makes the index covering — the aggregation
--   step never needs to visit the table row.
CREATE INDEX IF NOT EXISTS idx_dte_comp_cat_dur
    ON downtime_events (component_id, downtime_category, duration_min);

-- IDX-DE-04: (start_ts) — for time-range queries
-- ► Covers time-window JOINs in oee_performance RPM fallback CTE:
--     sr.ts BETWEEN ps.planned_start_ts AND ps.planned_end_ts
--   (for rows where downtime_events is used to derive run-time windows).
-- ► Also accelerates any future time-partitioned reporting.
CREATE INDEX IF NOT EXISTS idx_dte_start_ts
    ON downtime_events (start_ts);

-- IDX-DE-05: (root_cause_component_id, component_id)
-- ► Covers the cascade attribution self-join in downtime_pareto P7:
--     INNER JOIN downtime_events AS cause_rows
--         ON cause_rows.root_cause_component_id = c.component_id
--   and the correlated subquery scanning for cascade_upstream rows by root cause.
-- ► NULL values for non-cascade rows are not indexed in SQLite (IS NOT NULL
--   predicate in the query naturally skips them), keeping the index lean.
CREATE INDEX IF NOT EXISTS idx_dte_root_cause_comp
    ON downtime_events (root_cause_component_id, component_id)
    WHERE root_cause_component_id IS NOT NULL;
-- NOTE: Partial index (WHERE root_cause_component_id IS NOT NULL) excludes the
-- ~70% of rows that have NULL root_cause (non-cascade events). This halves
-- index size and concentrates B-tree pages on the rows P7 actually reads.
-- SQLite supports partial indexes since version 3.8.0 (our minimum version).

-- =============================================================================
-- SECTION 2: production_shifts indexes
-- =============================================================================
-- Rationale: production_shifts is the date anchor for the entire time-series
-- layer. Every downtime_timeseries query (T1–T7) starts from this table.
-- The GROUP BY shift_date + component_id pattern appears in all T-series CTEs.
-- =============================================================================

-- IDX-PS-01: Composite (component_id, shift_date)
-- ► Covers GROUP BY component_id, shift_date ORDER BY shift_date in T1–T7.
-- ► Also covers the equality JOIN in oee_availability:
--     INNER JOIN components c ON c.component_id = ps.component_id
-- ► Leftmost key = component_id (5-value domain; filters to 270 rows per
--   component from 1,350 total) — excellent selectivity for per-component reports.
CREATE INDEX IF NOT EXISTS idx_ps_comp_date
    ON production_shifts (component_id, shift_date);

-- IDX-PS-02: Composite (shift_date, component_id) — inverted for fleet-wide time-series
-- ► Covers ORDER BY shift_date, component_id in system-level OEE queries:
--     oee_system_series GROUP BY shift_date
-- ► Covers the LEFT JOIN zero-fill pattern in T1, T3, T5 where the driving
--   table is ordered by date across all 5 components simultaneously.
-- ► Distinct from IDX-PS-01: leftmost key is shift_date for queries that
--   scan the full date range without a component filter first.
CREATE INDEX IF NOT EXISTS idx_ps_date_comp
    ON production_shifts (shift_date, component_id);

-- IDX-PS-03: (shift_id, component_id, planned_duration_min) — covering for OEE denominator
-- ► Enables covering scan for the shift-level planned_duration_min lookup in
--   oee_availability, oee_composite, oee_performance:
--     SELECT shift_id, component_id, planned_duration_min FROM production_shifts
-- ► Adding planned_duration_min as a third key makes this a covering index —
--   the query reads the denominator directly from the B-tree without a heap fetch.
CREATE INDEX IF NOT EXISTS idx_ps_shift_comp_dur
    ON production_shifts (shift_id, component_id, planned_duration_min);

-- =============================================================================
-- SECTION 3: sensor_readings indexes
-- =============================================================================
-- Rationale: sensor_readings is the largest table (47,957 rows). The primary
-- access patterns are: (1) time-window JOIN for RPM fallback in OEE Performance,
-- (2) anomaly flag filter for anomaly_rate_by_sensor, (3) failure event scan
-- for failure_rate_by_component. The UNIQUE (sensor_id, ts) constraint already
-- provides a B-tree on (sensor_id, ts) — the indexes below complement it.
-- =============================================================================

-- IDX-SR-01: Composite (component_id, ts)
-- ► Primary index for the RPM fallback CTE in oee_performance.sql:
--     WHERE sr.component_id = ps.component_id
--       AND sr.ts BETWEEN ps.planned_start_ts AND ps.planned_end_ts
-- ► Range scan on ts within a component_id equality — B-tree can satisfy
--   both the equality filter and the range bound in a single sweep.
-- ► Also covers anomaly_rate_by_sensor GROUP BY component_id.
CREATE INDEX IF NOT EXISTS idx_sr_comp_ts
    ON sensor_readings (component_id, ts);

-- IDX-SR-02: Composite (is_failure_event, component_id)
-- ► Covers the primary WHERE predicate in failure_rate_by_component:
--     WHERE is_failure_event = 1
-- ► Only ~19 rows (one per TTF event) satisfy is_failure_event = 1 in 47k rows.
--   Without this index SQLite performs a full table scan. With this index it
--   reads 19 index entries and 19 heap rows — a 2,500× row-count reduction.
CREATE INDEX IF NOT EXISTS idx_sr_fail_comp
    ON sensor_readings (is_failure_event, component_id)
    WHERE is_failure_event = 1;
-- Partial index on failure events only — keeps the index trivially small.

-- IDX-SR-03: Composite (is_anomaly, component_id, sensor_id)
-- ► Covers anomaly_rate_by_sensor.sql:
--     GROUP BY sr.component_id, sr.sensor_id
--     WHERE sr.is_anomaly = 1 (implied by the CASE WHEN aggregation)
-- ► Adding sensor_id makes this a covering index for the GROUP BY columns,
--   eliminating the heap fetch for the sensor_id value.
CREATE INDEX IF NOT EXISTS idx_sr_anomaly_comp_sensor
    ON sensor_readings (is_anomaly, component_id, sensor_id);

-- =============================================================================
-- SECTION 4: failure_log indexes
-- =============================================================================
-- Rationale: failure_log has 19 rows but is JOINed into aggregation queries
-- for MTBF and failure rate. The existing UNIQUE (component_id, cycle_number)
-- constraint provides the primary B-tree. The index below supplements it for
-- the aggregation path.
-- =============================================================================

-- IDX-FL-01: Composite (component_id, ttf_hours)
-- ► Covers mtbf_from_failure_log.sql aggregation:
--     GROUP BY component_id → SUM(ttf_hours), COUNT(*)
-- ► Adding ttf_hours makes this a covering index — both GROUP BY key and
--   aggregate source are in the index. No heap visits required.
-- ► Also accelerates failure_rate_by_component.sql COUNT per component.
CREATE INDEX IF NOT EXISTS idx_fl_comp_ttf
    ON failure_log (component_id, ttf_hours);

-- IDX-FL-02: (component_id, t_failure_abs)
-- ► Covers queries that filter by absolute simulation time to compute
--   inter-failure intervals (MTBF gap calculation):
--     ORDER BY component_id, t_failure_abs
--     LAG(t_failure_abs) OVER (PARTITION BY component_id ORDER BY t_failure_abs)
-- ► Matches the window function frame in mtbf_from_failure_log.sql (Q3 subquery).
CREATE INDEX IF NOT EXISTS idx_fl_comp_t_abs
    ON failure_log (component_id, t_failure_abs);

-- =============================================================================
-- SECTION 5: production_counts indexes
-- =============================================================================
-- Rationale: production_counts has a UNIQUE (component_id, shift_id) constraint
-- that SQLite already backs with a B-tree. The additional index below ensures
-- the OEE Quality / Performance join path is covered.
-- =============================================================================

-- IDX-PC-01: Composite (shift_id, component_id)
-- ► Covers the JOIN predicate in oee_quality.sql and oee_composite.sql:
--     INNER JOIN production_counts pc
--         ON pc.shift_id     = ps.shift_id
--         AND pc.component_id = ps.component_id
-- ► Note: UNIQUE (component_id, shift_id) exists with component_id first.
--   This index inverts the key order to component_id, shift_id → shift_id is
--   the leftmost key here, matching the JOIN predicate order when the query
--   iterates production_shifts first (shift_id as outer loop key).
CREATE INDEX IF NOT EXISTS idx_pc_shift_comp
    ON production_counts (shift_id, component_id);

-- =============================================================================
-- SECTION 6: sensors table (supporting index)
-- =============================================================================
-- sensors is a tiny 11-row table; SQLite full-scans it cheaply. However, the
-- JOIN in anomaly_rate_by_sensor is sensor_id → sensors.sensor_id (PK, already
-- indexed). The component_id index below helps GROUP BY aggregations that
-- join sensors to sensor_readings for component-level sensor metadata.

-- IDX-SN-01: (component_id, sensor_type)
-- ► Covers the predicate: WHERE s.component_id = ? AND s.sensor_type = ?
--   used when resolving alarm thresholds per sensor type in anomaly queries.
CREATE INDEX IF NOT EXISTS idx_sn_comp_type
    ON sensors (component_id, sensor_type);

-- =============================================================================
-- VERIFICATION BLOCK
-- =============================================================================
-- Run this SELECT after applying indexes to confirm they are registered.
-- Expected: 13 rows (one per CREATE INDEX IF NOT EXISTS statement above).

SELECT
    name              AS index_name,
    tbl_name          AS table_name,
    sql               AS ddl_snippet
FROM sqlite_master
WHERE type  = 'index'
  AND name LIKE 'idx_%'
ORDER BY tbl_name, name;

-- =============================================================================
-- INDEX IMPACT SUMMARY (for viva / documentation)
-- =============================================================================
--
-- Table              | Index               | Pattern Targeted                 | Est. Speedup
-- -------------------|---------------------|----------------------------------|-------------
-- downtime_events    | idx_dte_shift_comp  | OEE JOIN (shift+comp equality)   | High (142→~28 rows)
-- downtime_events    | idx_dte_category_comp | Pareto GROUP BY category+comp  | High
-- downtime_events    | idx_dte_comp_cat_dur  | SUM(duration_min) covering     | Covering scan
-- downtime_events    | idx_dte_start_ts    | Time-range window JOIN           | Medium
-- downtime_events    | idx_dte_root_cause_comp | Cascade P7 self-join        | High (partial idx)
-- production_shifts  | idx_ps_comp_date    | T-series per-component date scan | High (1350→270 rows)
-- production_shifts  | idx_ps_date_comp    | System-level fleet date scan     | High
-- production_shifts  | idx_ps_shift_comp_dur | OEE denominator covering      | Covering scan
-- sensor_readings    | idx_sr_comp_ts      | RPM fallback time-window JOIN    | High (47k→~130 rows)
-- sensor_readings    | idx_sr_fail_comp    | failure_rate scan (19 rows)     | Critical (2500× filter)
-- sensor_readings    | idx_sr_anomaly_comp_sensor | anomaly aggregation       | High + covering
-- failure_log        | idx_fl_comp_ttf     | MTBF GROUP BY covering           | Covering scan
-- failure_log        | idx_fl_comp_t_abs   | LAG() window on abs time         | Medium
-- production_counts  | idx_pc_shift_comp   | OEE Quality/Perf JOIN            | High
-- sensors            | idx_sn_comp_type    | Alarm threshold JOIN             | Low (11 rows, minor)
--
-- =============================================================================
-- END OF FILE
-- =============================================================================
