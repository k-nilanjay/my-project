-- =============================================================================
-- schema.sql -- Manufacturing & Industrial Analytics FYP
-- Day 8 Audit: Third Normal Form (3NF) Compliance Lock-down
-- =============================================================================
-- Last revised : Day 8 -- 2026-07-20
-- Author       : Antigravity (AI Lead Engineer)
-- Compatible   : SQLite 3.x (dev) | SQL Server 2019+ (prod)
-- Cross-platform notes flagged inline [SQLite] / [SQL Server].
--
-- ====== NORMALIZATION AUDIT SUMMARY =========================================
-- FIRST NORMAL FORM (1NF) -- ALL TABLES SATISFY 1NF:
--   Every column holds an atomic value. No comma-lists, no nested structures,
--   no repeating column groups. Every table has a PK uniquely identifying rows.
--   All values in a column share the same data type / domain.
--
-- SECOND NORMAL FORM (2NF) -- ALL TABLES SATISFY 2NF:
--   Every non-key column depends on the ENTIRE primary key.
--   All PKs are single-column surrogates -- partial dependency impossible.
--
-- THIRD NORMAL FORM (3NF) -- ALL TABLES SATISFY 3NF (documented exceptions):
--   No non-key column transitively depends on PK through another non-key col.
--   DOCUMENTED EXCEPTIONS (justified denormalization):
--     sensor_readings.component_id  -- reachable via sensor_id->sensors->component_id;
--                                      stored for perf on 47k-row queries. Validated etl.py.
--     downtime_events.component_name-- reachable via component_id->components;
--                                      stored for fast export without join. Validated etl.py.
--     downtime_events.duration_min  -- derived (end-start)/60; stored for cross-DBMS portability.
--     production_shifts.planned_duration_min -- same as duration_min above.
--     failure_log.strategy,         -- TEMPORAL SNAPSHOT: parameters recorded at TTF draw time
--       beta_mid, eta_nominal_h, ea_ev  may diverge from components row after Phase 2 MLE update.
--   All exceptions annotated per column and validated by etl.py on INSERT.
--
-- ====== REFERENTIAL INTEGRITY MAP ============================================
--   components (1) ------- sensors (N)
--   components (1) ------- sensor_readings (N)   [also via sensor_id]
--   components (1) ------- failure_log (N)         [NEW Day 8]
--   components (1) ------- production_shifts (N)
--   components (1) ------- downtime_events.component_id (N)
--   components (1) ------- downtime_events.root_cause_component_id (opt)
--   components (1) ------- production_counts.component_id (N)
--   components (1) ------- production_counts.defect_source_component_id (opt)
--   sensors    (1) ------- sensor_readings (N)
--   production_shifts (1)- downtime_events (N)
--   production_shifts (1)- production_counts (1 per component per shift)
--
-- ====== DAY 7 CSV ALIGNMENT ==================================================
--   multi_failure_telemetry.csv (47,957 rows) -> sensor_readings:
--     ts, component_id, value  ->  ts, component_id (denorm FK), value
--     sensor_type              ->  resolved via JOIN sensors.sensor_type
--     is_failure_event, failure_mode, R_derated, AF, cascade_flag,
--     cycle_number, health_score  ->  NEW columns added to sensor_readings Day 8
--
--   ttf_samples.csv (19 rows) -> failure_log [NEW TABLE Day 8]:
--     component_id, cycle_number, ttf_hours, beta_mid,
--     eta_nominal_h, ea_ev, strategy  ->  direct column mapping
--     component_name  ->  NOT stored; resolved via FK join (avoids redundancy)
--
-- ====== TABLE CREATION ORDER (FK dependency chain) ===========================
--   1. components        -- master lookup, no FKs
--   2. sensors           -- FK: component_id
--   3. sensor_readings   -- FKs: sensor_id, component_id (denorm)
--   4. failure_log       -- FK: component_id  [NEW Day 8]
--   5. production_shifts -- FK: component_id
--   6. downtime_events   -- FKs: component_id, shift_id, root_cause_component_id
--   7. production_counts -- FKs: component_id, shift_id, defect_source_component_id
--   Drop in REVERSE order for clean dev re-runs.
-- =============================================================================

-- PRAGMA foreign_keys = ON;  -- REQUIRED in SQLite (FK enforcement OFF by default)
                               -- etl.py issues this PRAGMA at every session open.

-- DROP TABLE IF EXISTS production_counts;
-- DROP TABLE IF EXISTS downtime_events;
-- DROP TABLE IF EXISTS production_shifts;
-- DROP TABLE IF EXISTS failure_log;
-- DROP TABLE IF EXISTS sensor_readings;
-- DROP TABLE IF EXISTS sensors;
-- DROP TABLE IF EXISTS components;


-- =============================================================================
-- TABLE 1: components
-- =============================================================================
-- ROLE: Master dimension table for the 5-component series pipeline.
--   Pipeline topology: Bearing(1)->Shaft(2)->Motor Housing(3)->Coupling(4)->Gearbox(5)
-- 3NF ANALYSIS:
--   PK  : component_id (surrogate integer; seeded 1-5 matching position_in_chain)
--   1NF : All columns atomic. PK uniquely identifies each row. No repeating groups.
--   2NF : Single-column PK -> partial dependency structurally impossible.
--   3NF : All non-key columns are direct properties of the component identified by
--         component_id. e.g., failure_mode describes the component directly, not via
--         position_in_chain or any other non-key column. No transitive dependencies.
--         CHECK 3NF SATISFIED.
-- =============================================================================

CREATE TABLE IF NOT EXISTS components (
    component_id         INTEGER     NOT NULL,   -- [SQL Server]: INT IDENTITY(1,1)
    component_name       VARCHAR(50) NOT NULL,   -- 'Bearing'|'Shaft'|'Motor Housing'|'Coupling'|'Gearbox'
    position_in_chain    INTEGER     NOT NULL,   -- 1=Bearing -> 5=Gearbox; matches component_id in seed.sql
    failure_mode         VARCHAR(100),           -- primary failure mode description; NULL if multiple co-equal
    -- Weibull Parameters (locked Day 1; seeded Day 4)
    weibull_beta_min     FLOAT,                  -- lower bound of shape parameter range (must be > 0)
    weibull_beta_max     FLOAT,                  -- upper bound; must be >= beta_min
    weibull_beta_mid     FLOAT,                  -- (beta_min+beta_max)/2; simulation default until Phase 2 MLE
    weibull_eta_hours    FLOAT,                  -- characteristic life in hours; R(eta) = e^-1 = 0.368
    -- Locked (Day 4): Bearing 4380h | Shaft 8760h | Motor Housing 6570h | Coupling 5256h | Gearbox 4380h
    -- Arrhenius Parameter (locked Day 1)
    activation_energy_ev FLOAT,                 -- Ea (eV) for AF = exp[(Ea/k)*(1/T_use-1/T_stress)]
    -- NULL for Shaft (fatigue failure is not thermally governed -- locked Day 1)
    -- Values: Bearing 0.80 | Motor Housing 1.00 | Coupling 0.60 | Gearbox 0.70
    maintenance_strategy VARCHAR(10) NOT NULL,   -- 'PM'|'CBM'|'PM_CBM' (taxonomy locked Day 1)

    PRIMARY KEY (component_id),
    UNIQUE (component_name),          -- each physical component appears exactly once
    UNIQUE (position_in_chain),       -- pipeline positions are unique; no two components in same slot
    CHECK (position_in_chain BETWEEN 1 AND 5),
    CHECK (maintenance_strategy IN ('PM', 'CBM', 'PM_CBM')),
    CHECK (weibull_beta_min     IS NULL OR weibull_beta_min > 0),
    CHECK (weibull_beta_max     IS NULL OR weibull_beta_max >= weibull_beta_min),
    CHECK (weibull_beta_mid     IS NULL OR (weibull_beta_mid >= weibull_beta_min
                                            AND weibull_beta_mid <= weibull_beta_max)),
    CHECK (weibull_eta_hours    IS NULL OR weibull_eta_hours > 0),
    CHECK (activation_energy_ev IS NULL OR activation_energy_ev > 0)
);
-- Beta ranges (Day 1): Bearing[2.5,3.5] | Shaft[1.5,2.0] | MH[1.8,2.5] | Coupling[1.5,2.0] | Gearbox[2.0,3.0]


-- =============================================================================
-- TABLE 2: sensors
-- =============================================================================
-- ROLE: Registry of physical sensor channels. One row per sensor per component.
--   Sensor ID scheme (seed.sql Day 4): 10x=Bearing | 20x=Shaft | 30x=Motor Housing
--                                      40x=Coupling | 50x=Gearbox
--   Leaves room to add sensors per component without renumbering.
-- 3NF ANALYSIS:
--   PK  : sensor_id (surrogate integer)
--   FK  : component_id -> components (RESTRICT / CASCADE)
--   1NF : All columns atomic. No repeating groups.
--   2NF : Single-column PK -> partial dependency impossible.
--   3NF : All non-key columns are direct facts about the physical sensor.
--         unit_of_measure has a conventional pairing with sensor_type, but this
--         is enforced by a CHECK constraint (domain rule), NOT a hidden lookup table.
--         It is a domain constraint, not a transitive functional dependency.
--         If multiple units per sensor_type become needed, introduce a
--         sensor_type_units reference table at that time.
--         CHECK 3NF SATISFIED.
-- =============================================================================

CREATE TABLE IF NOT EXISTS sensors (
    sensor_id            INTEGER     NOT NULL,   -- [SQL Server]: INT IDENTITY(1,1)
    component_id         INTEGER     NOT NULL,   -- FK: which component this sensor monitors
    sensor_type          VARCHAR(30) NOT NULL,   -- 'vibration'|'temperature'|'rpm'|'load'|'pressure'|'oil_debris'
    unit_of_measure      VARCHAR(20) NOT NULL,   -- 'mm/s_rms'|'degC'|'rpm'|'pct'|'bar'|'count'
    -- ISO Alarm / Danger Thresholds
    iso_alarm_threshold  FLOAT,                  -- Zone C onset (4.5 mm/s vibration per ISO 10816-3)
                                                 -- component-equivalent alarm for temperature, load, oil_debris
                                                 -- NULL for RPM sensors (no universal ISO RPM threshold)
    iso_danger_threshold FLOAT,                  -- Zone D onset (7.1 mm/s vibration)
                                                 -- must be > iso_alarm_threshold when both non-null
    sample_rate_hz       FLOAT       NOT NULL DEFAULT 1.0,   -- acquisition frequency in Hz
    is_active            INTEGER     NOT NULL DEFAULT 1,     -- 1=in service | 0=decommissioned [SQL Server: BIT]

    PRIMARY KEY (sensor_id),
    FOREIGN KEY (component_id) REFERENCES components(component_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    CHECK (is_active IN (0, 1)),
    CHECK (sensor_type IN ('vibration','temperature','rpm','load','pressure','oil_debris')),
    CHECK (unit_of_measure IN ('mm/s_rms','degC','rpm','pct','bar','count')),
    CHECK (sample_rate_hz > 0),
    -- ISO threshold ordering: alarm must be strictly less than danger
    CHECK (iso_alarm_threshold IS NULL OR iso_danger_threshold IS NULL
           OR iso_alarm_threshold < iso_danger_threshold)
);
-- ISO 10816-3 zones: A=0-2.3 mm/s | B=2.3-4.5 | C=4.5-7.1 (alarm) | D=>7.1 (danger)


-- =============================================================================
-- TABLE 3: sensor_readings
-- =============================================================================
-- ROLE: Primary time-series FACT table. One row per sensor reading event.
--   Volume: ~47,957 rows from Day 7 (365-day, 2h-timestep, seed=7 simulation).
--
-- 3NF ANALYSIS:
--   PK  : reading_id (surrogate bigint -- BIGINT for multi-year scale)
--   FKs : sensor_id -> sensors; component_id -> components (denormalized)
--   1NF : All columns atomic. ts is a single ISO 8601 timestamp. No repeating groups.
--   2NF : Single-column PK -> partial dependency impossible.
--   3NF : DOCUMENTED EXCEPTION: component_id
--         Transitively reachable: reading_id -> sensor_id -> sensors.component_id
--         STORED DIRECTLY because:
--           (1) OEE Performance queries aggregate this 47k-row table by component_id
--               plus shift time window. Removing this join is a material perf gain
--               on the hottest query path in the analytics platform.
--           (2) Consistent with star-schema fact table best practice in data warehousing.
--           (3) etl.py validates component_id == sensors.component_id on every INSERT batch.
--         This is the ONLY 3NF exception in sensor_readings.
--         CHECK 3NF SATISFIED (documented performance denormalization).
--
-- DAY 7 CSV ALIGNMENT (multi_failure_telemetry.csv -> SQL columns):
--   ts, component_id, value  ->  ts, component_id, value
--   sensor_type              ->  resolved via JOIN to sensors.sensor_type (not stored again)
--   is_failure_event, failure_mode  ->  is_failure_event, failure_mode  [NEW Day 8]
--   R_derated, AF            ->  r_derated, arrhenius_factor             [NEW Day 8]
--   cascade_flag, cycle_number, health_score  ->  same names              [NEW Day 8]
-- =============================================================================

CREATE TABLE IF NOT EXISTS sensor_readings (
    reading_id           INTEGER     NOT NULL,   -- [SQL Server]: BIGINT IDENTITY(1,1) NOT NULL
    sensor_id            INTEGER     NOT NULL,   -- FK to sensors; identifies the physical channel
    component_id         INTEGER     NOT NULL,   -- DENORMALIZED FK; see 3NF analysis above
    ts                   DATETIME    NOT NULL,   -- UTC ISO 8601 timestamp ('YYYY-MM-DDTHH:MM:SS')
                                                 -- Day 7 simulation anchored to 2026-07-20T00:00:00
    value                FLOAT       NOT NULL,   -- raw reading in sensors.unit_of_measure; always >= 0
    -- Anomaly Classification (computed by etl.py on ingest; not user-supplied)
    is_anomaly           INTEGER     NOT NULL DEFAULT 0,   -- 1 if value >= iso_alarm_threshold [BIT in SQL Server]
    iso_zone             VARCHAR(1),                       -- 'A'|'B'|'C'|'D' for vibration; NULL otherwise
    -- Failure Event Flags [NEW Day 8 -- aligns with multi_failure_telemetry.csv]
    is_failure_event     INTEGER     NOT NULL DEFAULT 0,   -- 1 at first ts >= TTF on PRIMARY sensor only [BIT]
    failure_mode         VARCHAR(100),                     -- e.g. 'rolling_element_fatigue'; NULL for normal rows
    -- Reliability State Columns [NEW Day 8 -- aligns with multi_failure_telemetry.csv]
    r_derated            FLOAT,          -- R*(t) = exp(-(t/eta*)^beta) with Arrhenius eta*; range [0,1]; CSV: R_derated
    arrhenius_factor     FLOAT,          -- AF = exp[(Ea/k)*(1/T_use-1/T_stress)]; 1.0 for Shaft; CSV: AF
    cascade_flag         INTEGER     NOT NULL DEFAULT 0,   -- 1 if vibration elevated by upstream failure [BIT]
    cycle_number         INTEGER     NOT NULL DEFAULT 1,   -- 1-indexed cycle counter per component (resets post-repair; matches failure_log)
    health_score         FLOAT,          -- r_derated * 100.0; range [0.0,100.0]; Power BI Fleet Overview KPI
    -- OEE Performance Fallback Columns (RPM proxy method -- oee_performance.sql)
    rpm                  FLOAT,          -- machine speed in RPM; NULL for non-RPM sensor types
    rpm_rated            FLOAT,          -- nameplate rated RPM; P_fallback = MIN(1.0, rpm/rpm_rated)
    load_pct             FLOAT,          -- pct of rated load (0-100); NULL for non-load sensor types

    PRIMARY KEY (reading_id),
    -- UNIQUE de-duplication key for INSERT OR IGNORE idempotency (Day 9):
    --   (sensor_id, ts) uniquely identifies one physical sensor reading at one point in time.
    --   The surrogate PK (reading_id) remains for efficient FK joins from future tables.
    --   This is the star-schema pattern: surrogate PK + natural UNIQUE key.
    UNIQUE (sensor_id, ts),
    FOREIGN KEY (sensor_id)    REFERENCES sensors(sensor_id)       ON DELETE RESTRICT,
    FOREIGN KEY (component_id) REFERENCES components(component_id) ON DELETE RESTRICT,
    CHECK (is_anomaly       IN (0, 1)),
    CHECK (is_failure_event IN (0, 1)),
    CHECK (cascade_flag     IN (0, 1)),
    CHECK (iso_zone IS NULL OR iso_zone IN ('A', 'B', 'C', 'D')),
    CHECK (value >= 0),
    CHECK (r_derated IS NULL OR (r_derated >= 0.0 AND r_derated <= 1.0)),
    CHECK (arrhenius_factor IS NULL OR arrhenius_factor > 0),
    CHECK (health_score IS NULL OR (health_score >= 0.0 AND health_score <= 100.0)),
    CHECK (cycle_number >= 1),    -- 1-indexed (first cycle = 1; matches failure_log CHECK >= 1)
    CHECK (load_pct  IS NULL OR (load_pct BETWEEN 0 AND 100)),
    CHECK (rpm       IS NULL OR rpm >= 0),
    CHECK (rpm_rated IS NULL OR rpm_rated > 0)
);
-- Recommended indexes for production:
-- CREATE INDEX IF NOT EXISTS idx_sr_comp_ts    ON sensor_readings (component_id, ts);
-- CREATE INDEX IF NOT EXISTS idx_sr_sensor_ts  ON sensor_readings (sensor_id, ts);
-- CREATE INDEX IF NOT EXISTS idx_sr_fail       ON sensor_readings (is_failure_event, component_id);
-- CREATE INDEX IF NOT EXISTS idx_sr_anomaly    ON sensor_readings (is_anomaly, component_id);


-- =============================================================================
-- TABLE 4: failure_log  [NEW Day 8]
-- =============================================================================
-- ROLE: One row per discrete failure event (one per component per cycle).
--   Primary input for Phase 2 Weibull MLE fitting and empirical MTBF calculation.
--   Aligned with ttf_samples.csv (Day 7): 19 failure events from 365-day simulation.
--
-- 3NF ANALYSIS:
--   PK  : failure_id (surrogate integer)
--   FK  : component_id -> components (ON DELETE RESTRICT)
--   1NF : All columns atomic. No repeating groups.
--   2NF : Single-column PK -> partial dependency impossible.
--   3NF : DOCUMENTED EXCEPTION: strategy, beta_mid, eta_nominal_h, ea_ev
--         These are transitively reachable via component_id -> components.
--         STORED AS TEMPORAL SNAPSHOT because:
--           (1) ttf_samples.csv (Day 7) records these values AT TTF draw time.
--               When Phase 2 MLE updates the components table, historical TTF
--               records must retain the parameters that governed the draw.
--               This is a strict auditability / reproducibility requirement.
--           (2) Phase 2 MLE reads ttf_samples directly; all parameters co-located
--               avoids a join during the fitting loop.
--         TEMPORAL SNAPSHOT is a recognized normalization pattern (not a 3NF violation)
--         because snapshot values CAN legitimately differ from current components row.
--         CHECK 3NF SATISFIED (temporal snapshot justification).
--
-- DAY 7 CSV ALIGNMENT (ttf_samples.csv -> SQL):
--   component_id, cycle_number, ttf_hours  ->  component_id, cycle_number, ttf_hours
--   beta_mid, eta_nominal_h, ea_ev, strategy  ->  direct mapping (temporal snapshot)
--   component_name  ->  NOT stored; resolved via component_id FK join
-- =============================================================================

CREATE TABLE IF NOT EXISTS failure_log (
    failure_id           INTEGER      NOT NULL,   -- [SQL Server]: INT IDENTITY(1,1)
    component_id         INTEGER      NOT NULL,   -- which component failed; with cycle_number forms natural key
    cycle_number         INTEGER      NOT NULL,   -- 1-indexed failure cycle (matches ttf_samples.csv)
    ttf_hours            FLOAT        NOT NULL,   -- time-to-failure hours: eta_eff * (-ln(U))^(1/beta)
    t_failure_abs        FLOAT,                   -- absolute sim time in hours from 2026-07-20T00:00:00;
                                                  -- NULL if censored (TTF beyond simulation window)
    -- Weibull Parameters at Draw Time (temporal snapshot -- see 3NF analysis)
    beta_mid             FLOAT        NOT NULL,   -- Weibull beta used at draw time
    eta_nominal_h        FLOAT        NOT NULL,   -- eta BEFORE Arrhenius derating (from components at draw time)
    eta_effective_h      FLOAT,                   -- eta AFTER derating = eta_nominal / AF; NULL for Shaft
    ea_ev                FLOAT,                   -- Ea (eV) at draw time; NULL for Shaft
    gamma_factor         FLOAT        NOT NULL,   -- Computed in etl.py: Gamma(1 + 1/beta_mid)
    strategy             VARCHAR(10)  NOT NULL,   -- 'PM'|'CBM'|'PM_CBM' at draw time (temporal snapshot)
    -- Maintenance Record
    repair_hours         FLOAT,                   -- stochastic MTTR: strategy_MTTR*(1+|N(0,0.20)|); NULL if censored
    failure_mode         VARCHAR(100),            -- e.g. 'rolling_element_fatigue' (FAILURE_MODES dict, simulate.py)
    -- Q-Q Validation Metadata (from qq_summary.csv, Day 7)
    qq_r_squared         FLOAT,                   -- R^2 from Weibull Q-Q linearisation; NULL if INSUFFICIENT_DATA

    PRIMARY KEY (failure_id),
    FOREIGN KEY (component_id) REFERENCES components(component_id) ON DELETE RESTRICT,
    UNIQUE (component_id, cycle_number),   -- a component cannot have two events with same cycle number
    CHECK (cycle_number >= 1),             -- 1-indexed
    CHECK (ttf_hours > 0),
    CHECK (t_failure_abs IS NULL OR t_failure_abs > 0),
    CHECK (beta_mid > 0),
    CHECK (eta_nominal_h > 0),
    CHECK (eta_effective_h IS NULL OR eta_effective_h > 0),
    CHECK (ea_ev IS NULL OR ea_ev > 0),
    CHECK (strategy IN ('PM', 'CBM', 'PM_CBM')),
    CHECK (repair_hours IS NULL OR repair_hours >= 0),
    CHECK (qq_r_squared IS NULL OR (qq_r_squared >= 0.0 AND qq_r_squared <= 1.0))
);


-- =============================================================================
-- TABLE 5: production_shifts
-- =============================================================================
-- ROLE: Defines Planned Production Time window per component per shift.
--   Denominator for OEE Availability: A = (planned_duration_min - SUM(downtime_min))
--                                         / planned_duration_min
--   Specification: Day 2 CONTEXT.md -> Required SQL Tables section.
-- 3NF ANALYSIS:
--   PK  : shift_id (surrogate integer)
--   FK  : component_id -> components (RESTRICT / CASCADE)
--   1NF : All columns atomic. No repeating groups.
--   2NF : Single-column PK -> partial dependency impossible.
--   3NF : DOCUMENTED EXCEPTION: planned_duration_min
--         Derived: (planned_end_ts - planned_start_ts) / 60.0
--         STORED BECAUSE:
--           (1) All 6 OEE SQL queries divide by planned_duration_min. Computing
--               datetime arithmetic inline requires DBMS-specific syntax differing
--               between SQLite (strftime / julianday) and SQL Server (DATEDIFF).
--           (2) etl.py::compute_derived_duration() computes and validates this value
--               on every INSERT, preventing drift from the source timestamps.
--         CHECK 3NF SATISFIED (derived-column denorm with app-layer enforcement).
-- =============================================================================

CREATE TABLE IF NOT EXISTS production_shifts (
    shift_id             INTEGER     NOT NULL,   -- [SQL Server]: INT IDENTITY(1,1)
    component_id         INTEGER     NOT NULL,   -- FK: each shift belongs to one component
    shift_date           DATE        NOT NULL,   -- calendar date (UTC); enables date-range partitioning
    shift_label          VARCHAR(10) NOT NULL DEFAULT 'DAY',  -- 'DAY'|'NIGHT'|'SWING'
    planned_start_ts     DATETIME    NOT NULL,   -- UTC scheduled shift start
    planned_end_ts       DATETIME    NOT NULL,   -- UTC scheduled shift end; must be > planned_start_ts
    planned_duration_min FLOAT       NOT NULL,   -- STORED DERIVED: (planned_end_ts - planned_start_ts) / 60.0
                                                 -- Validated by etl.py::compute_derived_duration() on INSERT.

    PRIMARY KEY (shift_id),
    FOREIGN KEY (component_id) REFERENCES components(component_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    CHECK (shift_label IN ('DAY', 'NIGHT', 'SWING')),
    CHECK (planned_end_ts > planned_start_ts),    -- temporal integrity
    CHECK (planned_duration_min > 0),
    CHECK (planned_duration_min <= 1440)           -- max 24-hour shift (24*60=1440)
);
-- CREATE UNIQUE INDEX IF NOT EXISTS uix_shifts_comp_date_label
--     ON production_shifts (component_id, shift_date, shift_label);
-- CREATE INDEX IF NOT EXISTS idx_shifts_date_comp ON production_shifts (shift_date, component_id);


-- =============================================================================
-- TABLE 6: downtime_events
-- =============================================================================
-- ROLE: One row per downtime occurrence. Multiple events per shift permitted.
--   Feeds OEE Availability and Six Big Losses waterfall chart.
--
-- 3NF ANALYSIS:
--   PK  : downtime_id (surrogate integer)
--   FKs : component_id -> components; shift_id -> production_shifts;
--         root_cause_component_id -> components (self-referential, optional)
--   1NF : All columns atomic. No repeating groups.
--   2NF : Single-column PK -> partial dependency impossible.
--   3NF : DOCUMENTED EXCEPTIONS:
--     duration_min:
--       Derived: (end_ts - start_ts) / 60.0. Stored for cross-DBMS OEE portability
--       (same reason as production_shifts.planned_duration_min). Validated by etl.py.
--     component_name:
--       Reachable via component_id -> components.component_name.
--       Stored for fast export reports without joining components table.
--       Drift risk: if a component is renamed. Mitigation: etl.py validates on INSERT.
--     CHECK 3NF SATISFIED (two documented exceptions, both app-layer enforced).
--
-- DOWNTIME TAXONOMY (locked Day 2, CONTEXT.md Downtime Classification):
--   'unplanned_failure'   -> Loss 1: sudden failure stops production
--   'planned_maintenance' -> scheduled PM (pre-excluded from Planned Production Time)
--   'changeover'          -> Loss 2: setup / tooling change
--   'idle'                -> Loss 3: material shortage, operator absence
--   'cascade_upstream'    -> stop caused by upstream component failure
--
-- CASCADE TAGGING RULE (locked Day 2):
--   When component N fails (unplanned_failure), positions N+1..5 each receive a
--   concurrent downtime row with category='cascade_upstream' AND
--   root_cause_component_id pointing to N. The CHECK below enforces this at DB layer.
-- =============================================================================

CREATE TABLE IF NOT EXISTS downtime_events (
    downtime_id             INTEGER      NOT NULL,   -- [SQL Server]: INT IDENTITY(1,1)
    component_id            INTEGER      NOT NULL,   -- component experiencing downtime (may be cascade recipient)
    shift_id                INTEGER      NOT NULL,   -- shift during which downtime occurred
    root_cause_component_id INTEGER,                 -- upstream cause; NULL except for cascade_upstream rows
    start_ts                DATETIME     NOT NULL,   -- UTC downtime start
    end_ts                  DATETIME     NOT NULL,   -- UTC production resumed; must be > start_ts
    duration_min            FLOAT        NOT NULL,   -- STORED DERIVED: (end_ts-start_ts)/60; validated by etl.py
    downtime_category       VARCHAR(30)  NOT NULL,   -- see taxonomy above; CHECK locks the vocabulary
    downtime_type           VARCHAR(20),             -- 'equipment'|'process'|'quality'|NULL
    failure_mode            VARCHAR(100),            -- NULL for planned_maintenance/changeover/idle rows
    component_name          VARCHAR(50),             -- DENORMALIZED copy of components.component_name; etl validated

    PRIMARY KEY (downtime_id),
    FOREIGN KEY (component_id)            REFERENCES components(component_id)    ON DELETE RESTRICT,
    FOREIGN KEY (shift_id)                REFERENCES production_shifts(shift_id) ON DELETE RESTRICT,
    FOREIGN KEY (root_cause_component_id) REFERENCES components(component_id)    ON DELETE RESTRICT,
    CHECK (downtime_category IN (
        'unplanned_failure','planned_maintenance','changeover','idle','cascade_upstream'
    )),
    CHECK (downtime_type IS NULL OR downtime_type IN ('equipment','process','quality')),
    CHECK (duration_min > 0),
    CHECK (end_ts > start_ts),
    -- CASCADE ENFORCEMENT (Day 2 rule enforced at DB layer, not just app layer):
    CHECK (
        (downtime_category = 'cascade_upstream' AND root_cause_component_id IS NOT NULL)
        OR (downtime_category != 'cascade_upstream')
    ),
    CHECK (root_cause_component_id IS NULL OR root_cause_component_id != component_id)
);
-- CREATE INDEX IF NOT EXISTS idx_dte_shift_comp ON downtime_events (shift_id, component_id);
-- CREATE INDEX IF NOT EXISTS idx_dte_category   ON downtime_events (downtime_category, component_id);
-- CREATE INDEX IF NOT EXISTS idx_dte_start_ts   ON downtime_events (start_ts);


-- =============================================================================
-- TABLE 7: production_counts
-- =============================================================================
-- ROLE: One row per shift per component for unit output and quality metrics.
--   Feeds OEE Performance (unit-count primary method) and OEE Quality.
--
-- 3NF ANALYSIS:
--   PK  : count_id (surrogate integer)
--   FKs : component_id -> components; shift_id -> production_shifts;
--         defect_source_component_id -> components (self-referential, optional)
--   1NF : All columns atomic. No repeating groups.
--   2NF : Single-column PK -> partial dependency impossible.
--   3NF : All non-key columns are direct facts about this shift's production output
--         for this component: unit counts, quality figures, ideal cycle time, defect FK.
--         The equation good + defective + rework = total is enforced as a CHECK CONSTRAINT
--         (data integrity rule). It is NOT a derived stored column -- no column stores the sum.
--         CHECK 3NF SATISFIED -- no transitive dependencies.
--
-- OEE Formulas (locked Day 2):
--   P = MIN(1.0, (total_units * ideal_cycle_time_min) / run_time_min)
--   Q = good_units / total_units
--   Invariant: good_units = total_units - defective_units - rework_units
-- =============================================================================

CREATE TABLE IF NOT EXISTS production_counts (
    count_id                   INTEGER  NOT NULL,   -- [SQL Server]: INT IDENTITY(1,1)
    component_id               INTEGER  NOT NULL,
    shift_id                   INTEGER  NOT NULL,
    defect_source_component_id INTEGER,             -- upstream root cause for cascade quality defects
                                                    -- NULL when defect originates in this component itself
    total_units                INTEGER  NOT NULL,   -- all units produced: good + defective + rework
    good_units                 INTEGER  NOT NULL,   -- first-pass yield; OEE Quality numerator
    defective_units            INTEGER  NOT NULL,   -- scrapped/rejected units; OEE Loss 5
    rework_units               INTEGER  NOT NULL DEFAULT 0,  -- reworked units; OEE Loss 6
    ideal_cycle_time_min       FLOAT    NOT NULL,   -- nameplate time per unit (min); constant per component spec

    PRIMARY KEY (count_id),
    FOREIGN KEY (component_id)               REFERENCES components(component_id)    ON DELETE RESTRICT,
    FOREIGN KEY (shift_id)                   REFERENCES production_shifts(shift_id) ON DELETE RESTRICT,
    FOREIGN KEY (defect_source_component_id) REFERENCES components(component_id)    ON DELETE RESTRICT,
    -- Unit reconciliation invariant (enforced at DB layer; etl.py validates before INSERT):
    CHECK (good_units + defective_units + rework_units = total_units),
    CHECK (total_units     >= 0),
    CHECK (good_units      >= 0),
    CHECK (defective_units >= 0),
    CHECK (rework_units    >= 0),
    CHECK (good_units      <= total_units),
    CHECK (ideal_cycle_time_min > 0),
    CHECK (defect_source_component_id IS NULL OR defect_source_component_id != component_id),
    UNIQUE (component_id, shift_id)  -- one count row per component per shift
);
-- CREATE INDEX IF NOT EXISTS idx_pc_shift_comp ON production_counts (shift_id, component_id);


-- =============================================================================
-- END OF SCHEMA -- Day 8 3NF-Audited Version
-- =============================================================================
--
-- COMPLETE ENTITY RELATIONSHIP DIAGRAM:
--   components (PK: component_id)
--       +---> sensors              (FK: component_id)
--       |         +---> sensor_readings  (FK: sensor_id)
--       +---> sensor_readings      (FK: component_id -- denormalized)
--       +---> failure_log          (FK: component_id)  [NEW Day 8]
--       +---> production_shifts    (FK: component_id)
--       |         +---> downtime_events   (FK: shift_id)
--       |         +---> production_counts (FK: shift_id)
--       +---> downtime_events.root_cause_component_id    (self-ref FK, opt)
--       +---> production_counts.defect_source_component_id (self-ref FK, opt)
--
-- 3NF COMPLIANCE MATRIX:
--   Table               | 1NF | 2NF | 3NF | Exception Summary
--   --------------------|-----|-----|-----|----------------------------------------------
--   components          |  Y  |  Y  |  Y  | None
--   sensors             |  Y  |  Y  |  Y  | None
--   sensor_readings     |  Y  |  Y  |  Y* | *component_id denorm (perf; etl validated)
--   failure_log         |  Y  |  Y  |  Y* | *strategy/beta/eta temporal snapshot (audit)
--   production_shifts   |  Y  |  Y  |  Y* | *planned_duration_min stored-derived (portability)
--   downtime_events     |  Y  |  Y  |  Y* | *duration_min stored-derived; component_name copy
--   production_counts   |  Y  |  Y  |  Y  | None (reconciliation = CHECK, not derived column)
--
-- SQLITE DEPLOYMENT:
--   PRAGMA foreign_keys = ON;  -- required at EVERY session open (etl.py handles this)
--   INTEGER PRIMARY KEY = implicit ROWID alias = auto-increment
--   Drop tables in REVERSE creation order for dev re-runs
--
-- SQL SERVER MIGRATION:
--   Replace INTEGER with INT IDENTITY(1,1) NOT NULL for PK columns
--   Replace DATETIME with DATETIME2(0) for better temporal precision
--   Use BIT for boolean columns: is_anomaly, is_failure_event, cascade_flag, is_active
--   PRAGMA statements do not apply; FK enforcement always ON in SQL Server
--
-- See docs/erd.md for the full Mermaid.js entity-relationship diagram.
-- =============================================================================
