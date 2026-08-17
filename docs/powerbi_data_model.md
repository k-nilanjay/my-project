# Power BI Data Model — Star Schema Design
## Manufacturing & Industrial Analytics FYP
### Day 21 — August 7, 2026 | Phase 2.3 Power BI Fleet Overview

> **Purpose:** This document defines the exact Star Schema to be implemented in Power BI Desktop when connecting `data/manufacturing.db` and `data/processed/criticality_scores.csv`. It specifies every Fact table, Dimension table, joining key, cardinality, and cross-filter direction required for the Fleet Overview dashboard and all downstream pages.

---

## 1. Overview & Design Rationale

### Why Star Schema (not Snowflake)?

Power BI's DAX engine is optimised for Star Schemas. A Snowflake schema (normalised dimensions) requires Power BI to traverse multiple JOIN hops at query time, degrading VertiPaq compression and increasing DAX formula complexity. Our data volume (~48,000 sensor rows, 5 components) is modest enough that a single-hop Star is both performant and sufficient.

**Core principle:** Every Fact table connects to Dimension tables via a single foreign key. Dimensions are never joined to each other in the model — all cross-dimension filtering flows through the Fact table.

### Data Sources to Connect

| Source File | Connection Type | Tables/Views Exposed |
|---|---|---|
| `data/manufacturing.db` | Power BI ODBC/Python connector | `components`, `sensors`, `sensor_readings`, `production_shifts`, `downtime_events`, `production_counts`, `failure_log` |
| `data/processed/criticality_scores.csv` | Power BI Text/CSV connector | `criticality_scores` (5 rows x 16 columns) |

> **Note for Power BI connection:** Use the ODBC connector with a SQLite3 ODBC driver, or export manufacturing.db tables to CSV via a Power Query script for a flat-file approach. Recommended: flat CSV exports for FYP to avoid driver dependency.

---

## 2. Complete Table Inventory

### Fact Tables (2)

| Table Name (Power BI) | Source | Grain (one row per) | Row Count |
|---|---|---|---|
| `fact_sensor_readings` | `manufacturing.db -> sensor_readings` | One sensor measurement per sensor per 2-hour timestep | ~47,957 |
| `fact_downtime_events` | `manufacturing.db -> downtime_events` | One continuous downtime period per component per shift | 143 |

### Dimension Tables (6)

| Table Name (Power BI) | Source | Grain (one row per) | Row Count |
|---|---|---|---|
| `dim_components` | `manufacturing.db -> components` | One component in the 5-node pipeline | 5 |
| `dim_sensors` | `manufacturing.db -> sensors` | One physical sensor instrument | 11 |
| `dim_production_shifts` | `manufacturing.db -> production_shifts` | One 8-hour shift per component | 1,350 |
| `dim_production_counts` | `manufacturing.db -> production_counts` | One production count record per component per shift | 1,350 |
| `dim_failure_log` | `manufacturing.db -> failure_log` | One recorded failure event | 15-19 |
| `dim_criticality` | `criticality_scores.csv` | One criticality score row per component | 5 |

> `dim_production_counts` is classified as a Dimension (not a Fact) because its grain is one-row-per-component-per-shift and it contains mostly descriptive quality attributes. However, computed OEE measures (A, P, Q) will be derived from it via DAX.

---

## 3. Fact Table Definitions

### 3.1 `fact_sensor_readings`

**Source:** `sensor_readings` table in `manufacturing.db`

**Purpose:** The primary transactional Fact table. Stores every time-stamped sensor measurement for all 5 components across the 365-day simulation window. Powers Fleet Overview health scores, sensor trend charts, and threshold breach KPIs.

| Column | Data Type | Role | Notes |
|---|---|---|---|
| `reading_id` | INTEGER | Surrogate Key (PK) | Auto-increment; hidden in Report View |
| `sensor_id` | INTEGER | **Foreign Key -> dim_sensors** | Joins to `dim_sensors.sensor_id` |
| `component_id` | INTEGER | **Foreign Key -> dim_components** | Denormalized FK — enables direct component filter |
| `ts` | DATETIME | Date/Time | UTC ISO 8601; used as the date axis in trend charts |
| `value` | FLOAT | **Measure** | Sensor reading in native units (mm/s, degC, rpm, %, count/mL) |
| `is_failure_event` | INTEGER (0/1) | **Flag** | 1 = timestep at which component failure occurred |
| `failure_mode` | VARCHAR | Attribute | e.g. "rolling_element_fatigue", "winding_insulation" |
| `R_derated` | FLOAT | **Measure** | Weibull R*(t) — Arrhenius-adjusted reliability at this timestep |
| `AF` | FLOAT | **Measure** | Arrhenius acceleration factor; 1.0 for Shaft |
| `cascade_flag` | INTEGER (0/1) | **Flag** | 1 = reading elevated by upstream component failure |
| `health_score` | FLOAT | **Measure** | `R_derated x 100` (%) — primary KPI for Fleet Overview |

**Power Query derived columns to add (M language):**
```
health_score  = [R_derated] * 100
date_key      = Date.From([ts])
```

---

### 3.2 `fact_downtime_events`

**Source:** `downtime_events` table in `manufacturing.db`

**Purpose:** Records every planned and unplanned downtime period per component. Powers the OEE Availability calculation, Six Big Losses waterfall chart, and downtime timeline visual.

| Column | Data Type | Role | Notes |
|---|---|---|---|
| `downtime_id` | INTEGER | Surrogate Key (PK) | Auto-increment |
| `component_id` | INTEGER | **Foreign Key -> dim_components** | Primary filter dimension |
| `shift_id` | INTEGER | **Foreign Key -> dim_production_shifts** | Links downtime to its enclosing shift |
| `root_cause_component_id` | INTEGER | **Foreign Key -> dim_components** (INACTIVE) | NOT NULL for cascade_upstream; NULL otherwise |
| `start_ts` | DATETIME | Date/Time | Downtime start timestamp |
| `end_ts` | DATETIME | Date/Time | Downtime end timestamp |
| `duration_min` | FLOAT | **Measure** | Pre-stored: (end_ts - start_ts) / 60; denominator in Availability DAX |
| `downtime_category` | VARCHAR | **Slicer / Attribute** | 'unplanned_failure', 'planned_maintenance', 'changeover', 'idle', 'cascade_upstream' |
| `downtime_type` | VARCHAR | Attribute | 'equipment', 'process', 'quality' |
| `failure_mode` | VARCHAR | Attribute | Specific failure mode string |
| `component_name` | VARCHAR | Attribute | Denormalized — fast label display without JOIN |

> **Dual-role FK:** `root_cause_component_id` connects to `dim_components` as a second, INACTIVE relationship. Activated in DAX via `USERELATIONSHIP()` for root-cause drill-downs.

---

## 4. Dimension Table Definitions

### 4.1 `dim_components`

**Source:** `components` table in `manufacturing.db`

**Purpose:** Master lookup for the 5 pipeline components. The central dimension — almost every visual filters through it.

| Column | Data Type | Role | Notes |
|---|---|---|---|
| `component_id` | INTEGER | **Primary Key** | 1=Bearing, 2=Shaft, 3=Motor Housing, 4=Coupling, 5=Gearbox |
| `component_name` | VARCHAR | **Display Label** | Used as slicer and chart axis |
| `position` | INTEGER | **Sort Order** | 1-5; set as Sort Column for component_name |
| `maintenance_strategy` | VARCHAR | Slicer / Attribute | 'PM', 'CBM', 'PM_CBM' |
| `weibull_beta_min` | FLOAT | Attribute | Design parameter |
| `weibull_beta_max` | FLOAT | Attribute | Design parameter |
| `weibull_beta_mid` | FLOAT | Attribute | (min + max) / 2 — used in Weibull DAX measures |
| `weibull_eta_hours` | FLOAT | Attribute | Characteristic life (hours) |
| `activation_energy_ev` | FLOAT | Attribute | Arrhenius Ea (eV); NULL for Shaft |
| `arrhenius_applicable` | INTEGER (0/1) | Attribute | 0 for Shaft; 1 for all others |
| `is_active` | INTEGER (0/1) | Attribute | Always 1 currently |

**Power Query derived column:**
```
pipeline_label = "Pos " & Text.From([position]) & ": " & [component_name]
// e.g. "Pos 1: Bearing" — for ordered legend labels
```

---

### 4.2 `dim_sensors`

**Source:** `sensors` table in `manufacturing.db`

**Purpose:** Lookup for the 11 sensor instruments. Allows filtering by sensor type independently of component.

| Column | Data Type | Role | Notes |
|---|---|---|---|
| `sensor_id` | INTEGER | **Primary Key** | 11-53, grouped by component (10x per component) |
| `component_id` | INTEGER | **Foreign Key -> dim_components** | Every sensor belongs to exactly one component |
| `sensor_type` | VARCHAR | **Slicer / Attribute** | 'vibration', 'temperature', 'rpm', 'load', 'oil_debris' |
| `unit` | VARCHAR | Display Label | 'mm/s_rms', 'degC', 'rpm', 'pct', 'count' |
| `iso_alarm_threshold` | FLOAT | Reference Value | Zone C / alarm threshold (ISO 10816-3) |
| `iso_danger_threshold` | FLOAT | Reference Value | Zone D / danger threshold |

**Power Query derived column:**
```
sensor_label = [component_name] & " - " & [sensor_type] & " (" & [unit] & ")"
// e.g. "Bearing - vibration (mm/s_rms)"
```

---

### 4.3 `dim_production_shifts`

**Source:** `production_shifts` table in `manufacturing.db`

**Purpose:** The time-grain anchor for OEE calculation. Each row is one shift for one component. Links `fact_downtime_events` and `dim_production_counts` into a common time reference.

| Column | Data Type | Role | Notes |
|---|---|---|---|
| `shift_id` | INTEGER | **Primary Key** | Auto-increment |
| `component_id` | INTEGER | **Foreign Key -> dim_components** | Shift is specific to one component |
| `shift_date` | DATE | **Date / Slicer** | Primary date field for OEE trend charts |
| `planned_start_ts` | DATETIME | Attribute | Shift window start |
| `planned_end_ts` | DATETIME | Attribute | Shift window end |
| `planned_duration_min` | FLOAT | **Measure input** | Pre-stored planned production time; denominator in Availability |

**Power Query derived columns:**
```
shift_month   = Date.Month([shift_date])
shift_week    = Date.WeekOfYear([shift_date])
shift_quarter = Date.QuarterOfYear([shift_date])
```

---

### 4.4 `dim_production_counts`

**Source:** `production_counts` table in `manufacturing.db`

**Purpose:** Quality and performance input data per shift per component. Used to compute OEE Performance (P) and Quality (Q) factors in DAX.

| Column | Data Type | Role | Notes |
|---|---|---|---|
| `count_id` | INTEGER | **Primary Key** | Auto-increment |
| `component_id` | INTEGER | **Foreign Key -> dim_components** | Component this count belongs to |
| `shift_id` | INTEGER | **Foreign Key -> dim_production_shifts** | 1:1 with shift (UNIQUE constraint enforced in SQL) |
| `total_units` | INTEGER | **Measure input** | Denominator for Quality |
| `good_units` | INTEGER | **Measure input** | Numerator for Quality |
| `defective_units` | INTEGER | **Measure input** | Loss 5 (production defects) |
| `rework_units` | INTEGER | **Measure input** | Loss 6 (start-up rejects / rework) |
| `ideal_cycle_time_min` | FLOAT | **Measure input** | Nameplate design time per unit |
| `defect_source_component_id` | INTEGER | **Foreign Key -> dim_components** (INACTIVE) | Upstream defect attribution; NULL if self-caused |

---

### 4.5 `dim_failure_log`

**Source:** `failure_log` table in `manufacturing.db`

**Purpose:** One row per discrete failure event from Weibull TTF injection. Used for MTBF calculation, failure frequency timeline, and failure mode distribution visuals.

| Column | Data Type | Role | Notes |
|---|---|---|---|
| `failure_id` | INTEGER | **Primary Key** | Auto-increment |
| `component_id` | INTEGER | **Foreign Key -> dim_components** | |
| `failure_ts` | DATETIME | Date/Time | Timestamp of failure event |
| `failure_mode` | VARCHAR | **Attribute / Slicer** | Rolling-element fatigue, winding insulation, etc. |
| `ttf_hours` | FLOAT | **Measure** | Time-to-failure for this cycle |
| `cycle_number` | INTEGER | Attribute | Which failure cycle this was for the component |
| `repair_duration_hours` | FLOAT | **Measure** | MTTR input |
| `maintenance_strategy_applied` | VARCHAR | Attribute | 'PM', 'CBM', 'PM_CBM' |

---

### 4.6 `dim_criticality`

**Source:** `data/processed/criticality_scores.csv`

**Purpose:** The Composite Criticality Index (CCI) output from Phase 2.2 Python processing. Connects to `dim_components` via component name match. Enriches every component-level visual with the multi-dimensional criticality ranking.

| Column | Data Type | Role | Notes |
|---|---|---|---|
| `cci_rank` | INTEGER | **Sort / Display** | 1 = highest criticality |
| `component` | VARCHAR | **Join Key** | Matches `dim_components.component_name` |
| `structural_risk_score` | FLOAT | **Measure** | SRS from graph centrality (Day 18) |
| `weibull_unreliability` | FLOAT | **Measure** | 1 - R(t) at t=2,920 h |
| `threshold_breach_rate` | FLOAT | **Measure** | TBR from telemetry (Day 17) |
| `srs_norm` | FLOAT | Measure | Max-normalised SRS |
| `unreliability_norm` | FLOAT | Measure | Max-normalised unreliability |
| `tbr_norm` | FLOAT | Measure | Max-normalised TBR |
| `cci_srs_contrib` | FLOAT | Measure | 0.40 x srs_norm |
| `cci_unrel_contrib` | FLOAT | Measure | 0.35 x unreliability_norm |
| `cci_tbr_contrib` | FLOAT | Measure | 0.25 x tbr_norm |
| `composite_criticality` | FLOAT | **Primary Measure** | CCI = sum of three weighted contributions |
| `w_srs` | FLOAT | Attribute | Weight used (0.40) — hidden |
| `w_unreliability` | FLOAT | Attribute | Weight used (0.35) — hidden |
| `w_tbr` | FLOAT | Attribute | Weight used (0.25) — hidden |
| `t_eval_hours` | FLOAT | Attribute | Evaluation age (2,920 h) |

**Power Query transformation (add component_id for optional numeric join):**
```
component_id_lookup = Table.AddColumn(Source, "component_id", each
    if [component] = "Bearing"        then 1
    else if [component] = "Shaft"         then 2
    else if [component] = "Motor Housing" then 3
    else if [component] = "Coupling"      then 4
    else if [component] = "Gearbox"       then 5
    else null)
```

---

## 5. Relationship Map (Star Schema)

### 5.1 Active Relationships (9)

| From (Dimension) | Key Column | To (Fact/Dim) | Key Column | Cardinality | Cross-Filter Direction | Active? |
|---|---|---|---|---|---|---|
| `dim_components` | `component_id` | `fact_sensor_readings` | `component_id` | **1 : Many** | Single (Dim -> Fact) | YES |
| `dim_sensors` | `sensor_id` | `fact_sensor_readings` | `sensor_id` | **1 : Many** | Single (Dim -> Fact) | YES |
| `dim_components` | `component_id` | `fact_downtime_events` | `component_id` | **1 : Many** | Single (Dim -> Fact) | INACTIVE |
| `dim_production_shifts` | `shift_id` | `fact_downtime_events` | `shift_id` | **1 : Many** | Single (Dim -> Fact) | YES |
| `dim_components` | `component_id` | `dim_production_shifts` | `component_id` | **1 : Many** | Single (Dim -> Shift) | YES |
| `dim_production_shifts` | `shift_id` | `dim_production_counts` | `shift_id` | **1 : 1** | Both | YES |
| `dim_components` | `component_id` | `dim_production_counts` | `component_id` | **1 : Many** | Single (Dim -> Fact) | DROPPED |
| `dim_components` | `component_id` | `dim_failure_log` | `component_id` | **1 : Many** | Single (Dim -> Fact) | YES |
| `dim_criticality` | `component` | `dim_components` | `component_name` | **1 : 1** | Both | YES |
| `dim_calendar` | `date` | `fact_sensor_readings` | `date_key` | **1 : Many** | Single (Dim -> Fact) | YES |
| `dim_calendar` | `date` | `dim_production_shifts` | `shift_date` | **1 : Many** | Single (Dim -> Fact) | YES |
| `dim_calendar` | `date` | `dim_failure_log` | `failure_date_key` | **1 : Many** | Single (Dim -> Fact) | YES |

### 5.2 Inactive Relationships (2)

These exist in the model but are disabled by default to prevent ambiguous filter paths. Activated in specific DAX measures via `USERELATIONSHIP()`.

| From (Dimension) | Key Column | To (Fact) | Key Column | Cardinality | Activated By |
|---|---|---|---|---|---|
| `dim_components` | `component_id` | `fact_downtime_events` | `root_cause_component_id` | **1 : Many** | `[Root Cause Downtime Min]` DAX measure |
| `dim_components` | `component_id` | `dim_production_counts` | `defect_source_component_id` | **1 : Many** | `[Upstream Defect Units]` DAX measure |

---

## 6. Visual Star Schema Diagram

```
                         +------------------------+
                         |    dim_components      |
                         |  PK: component_id      |
                         |  component_name        |
                         |  position (sort col)   |
                         |  maintenance_strategy  |
                         |  weibull_beta_mid      |
                         |  weibull_eta_hours     |
                         +-----------+------------+
                                     | 1
              +----------------------+---------------------------+
              |                      |                           |
              | *                    | *                         | *
  +-----------v-----------+  +-------v-----------------+  +-----v----------------+
  | fact_sensor_readings  |  | fact_downtime_events    |  | dim_failure_log      |
  |  FK: sensor_id        |  |  FK: component_id (ACT) |  |  FK: component_id    |
  |  FK: component_id     |  |  FK: shift_id           |  |  failure_ts          |
  |  ts (datetime)        |  |  duration_min  [M]      |  |  ttf_hours  [M]      |
  |  value  [M]           |  |  downtime_category      |  |  repair_dur_hrs [M]  |
  |  health_score  [M]    |  |  FK: root_cause_comp_id~|  +----------------------+
  |  R_derated  [M]       |  |      (INACTIVE) ~~~     |
  |  cascade_flag  [F]    |  +--------+----------------+
  +-----------+-----------+           | *
              | *         +----------+v-----------------------+
  +-----------v---------+ | dim_production_shifts             |
  |    dim_sensors      | |  PK: shift_id                     |
  |  PK: sensor_id      | |  FK: component_id (DELETED)       |
  |  FK: component_id   | |  shift_date  [Slicer]             |
  |  sensor_type        | |  planned_duration_min  [M]        |
  |  iso_alarm_thresh   | +----+------------------------------+
  |  iso_danger_thresh  |      | 1:1 (Both directions)
  +---------------------+ +----v------------------------------+
                          | dim_production_counts             |
                          |  FK: shift_id  (1:1)              |
                          |  FK: component_id (DELETED)       |
                          |  total_units  [M]                 |
                          |  good_units  [M]                  |
                          |  defective_units  [M]             |
                          |  ideal_cycle_time_min  [M]        |
                          |  FK: defect_source_comp_id ~~~    |
                          |      (INACTIVE)                   |
                          +-----------------------------------+

  +----------------------+
  |   dim_criticality    |   (1:1, Both directions)
  |  component [join key]+<---> dim_components.component_name
  |  composite_criticality|
  |  cci_rank             |
  |  structural_risk_score|
  |  weibull_unreliability|
  |  threshold_breach_rate|
  +----------------------+

  [M] = Measure field    [F] = Flag field    ~~~ = Inactive relationship
  (ACT) = Active relationship  (1:1) = One-to-one cardinality
```

---

## 7. Cardinality Detail Notes

### 7.1 `dim_production_shifts` <-> `dim_production_counts` : 1:1 (Both)

The SQL layer enforces `UNIQUE(component_id, shift_id)` on `production_counts`. Exactly one count record exists per component per shift. In Power BI this is a 1:1 relationship with **Both** cross-filter direction — selecting a shift filters counts and vice versa without ambiguity. This enables OEE Quality (`Q = good_units / total_units`) to be computed in DAX from a single-row context without aggregation risk.

### 7.2 `dim_criticality` <-> `dim_components` : 1:1 (Both)

Both tables have exactly 5 rows (one per component). The join is on `component_name = component` (string match in Power Query). **Both** cross-filter direction is safe because the relationship is 1:1 — selecting a component in any visual simultaneously populates its SQL-sourced properties and its CCI score. This is the key bridge between the physical pipeline data and Phase 2.2 analytics output.

### 7.3 `dim_sensors` -> `fact_sensor_readings` : 1:Many (Single)

One sensor instrument generates many readings over 365 days. Single cross-filter direction (Dim to Fact) is standard. Filtering to `sensor_type = 'vibration'` filters `fact_sensor_readings` to vibration rows only. The reverse (a reading filtering the sensor master table) would be semantically meaningless and create circular filter ambiguity.

### 7.4 Why `fact_sensor_readings` has two FK columns pointing to `dim_components`

`sensor_readings.component_id` is a **denormalized FK** — technically redundant (derivable via `sensor_id -> dim_sensors -> component_id`). It is retained because:
- OEE Performance queries need `AVG(rpm)` grouped by `component_id` — without denormalization this requires a 2-hop path through `dim_sensors`
- Power BI's VertiPaq compresses integer columns very efficiently — storage cost is negligible at 48K rows
- The direct `fact_sensor_readings -> dim_components` relationship allows component slicers to filter sensor data without passing through `dim_sensors`, preventing potential filter conflicts

### 7.5 Inactive Relationships — When to Use `USERELATIONSHIP()`

**Root cause analysis:** When the question is "Which upstream component CAUSED the most downtime?" — activate the `root_cause_component_id` relationship in a DAX measure. Without `USERELATIONSHIP()`, the default active relationship filters by the component that EXPERIENCED downtime, not the one that triggered it.

**Defect attribution:** When the question is "Which component generated the most upstream defects?" — activate `defect_source_component_id`. Without it, `component_id` in `dim_production_counts` identifies where the defect was RECORDED, not where it originated.

---

## 8. Proposed DAX Measures (Index)

These measures will be implemented in Power BI on Day 22. Listed here to confirm the schema supports each one without additional table or column modifications.

### Group A — Health & Reliability Measures (source: `fact_sensor_readings`)

```dax
[Avg Health Score] =
    AVERAGE(fact_sensor_readings[health_score])

[Min Health Score] =
    MIN(fact_sensor_readings[health_score])

[Avg R_Derated] =
    AVERAGE(fact_sensor_readings[R_derated])

[Failure Event Count] =
    CALCULATE(
        COUNTROWS(fact_sensor_readings),
        fact_sensor_readings[is_failure_event] = 1
    )

[Cascade Readings Count] =
    CALCULATE(
        COUNTROWS(fact_sensor_readings),
        fact_sensor_readings[cascade_flag] = 1
    )

[Cascade Flag Rate] =
    DIVIDE([Cascade Readings Count], COUNTROWS(fact_sensor_readings), 0)
```

### Group B — OEE Measures (source: `fact_downtime_events`, `dim_production_shifts`, `dim_production_counts`)

```dax
[Total Downtime Min] =
    CALCULATE(
        SUM(fact_downtime_events[duration_min]),
        fact_downtime_events[downtime_category] <> "planned_maintenance"
    )

[Planned Production Min] =
    SUM(dim_production_shifts[planned_duration_min])

[OEE Availability] =
    DIVIDE(
        [Planned Production Min] - [Total Downtime Min],
        [Planned Production Min],
        BLANK()
    )

[OEE Quality] =
    DIVIDE(
        SUM(dim_production_counts[good_units]),
        SUM(dim_production_counts[total_units]),
        BLANK()
    )

[Run Time Min] =
    [Planned Production Min] - [Total Downtime Min]

[OEE Performance] =
    DIVIDE(
        SUM(dim_production_counts[ideal_cycle_time_min])
            * SUM(dim_production_counts[total_units]),
        [Run Time Min],
        0
    )

[OEE Composite] =
    [OEE Availability] * [OEE Performance] * [OEE Quality]

[OEE Status] =
    SWITCH(
        TRUE(),
        [OEE Composite] >= 0.85, "WORLD CLASS",
        [OEE Composite] >= 0.75, "ACCEPTABLE",
        [OEE Composite] >= 0.65, "ALERT",
        "CRITICAL"
    )
```

### Group C — MTBF / MTTR Measures (source: `dim_failure_log`)

```dax
[Failure Count] =
    COUNTROWS(dim_failure_log)

[Total TTF Hours] =
    SUM(dim_failure_log[ttf_hours])

[MTBF Hours] =
    DIVIDE([Total TTF Hours], [Failure Count], BLANK())

[MTTR Hours] =
    AVERAGE(dim_failure_log[repair_duration_hours])

[Empirical Availability] =
    DIVIDE([MTBF Hours], [MTBF Hours] + [MTTR Hours], BLANK())
```

### Group D — Criticality Measures (source: `dim_criticality`, bridged via `dim_components`)

```dax
[CCI Score] =
    SELECTEDVALUE(dim_criticality[composite_criticality], BLANK())

[CCI Rank] =
    SELECTEDVALUE(dim_criticality[cci_rank], BLANK())

[SRS Score] =
    SELECTEDVALUE(dim_criticality[structural_risk_score], BLANK())

[Weibull Unreliability] =
    SELECTEDVALUE(dim_criticality[weibull_unreliability], BLANK())

[Root Cause Downtime Min] =
    CALCULATE(
        SUM(fact_downtime_events[duration_min]),
        USERELATIONSHIP(
            dim_components[component_id],
            fact_downtime_events[root_cause_component_id]
        )
    )

[Upstream Defect Units] =
    CALCULATE(
        SUM(dim_production_counts[defective_units]),
        USERELATIONSHIP(
            dim_components[component_id],
            dim_production_counts[defect_source_component_id]
        )
    )
```

---

## 9. Power BI Page -> Table Dependency Map

| Dashboard Page | Primary Fact Table | Primary Dimension Tables | Key Measures |
|---|---|---|---|
| **Fleet Overview** | `fact_sensor_readings` | `dim_components`, `dim_criticality` | `[Avg Health Score]`, `[CCI Score]`, `[OEE Composite]` |
| **Sensor Trends** | `fact_sensor_readings` | `dim_sensors`, `dim_components` | `[Avg R_Derated]`, `[Cascade Flag Rate]` |
| **Bearing Deep-Dive** | `fact_sensor_readings` | `dim_components` (Bearing) | `[Avg Health Score]`, `[MTBF Hours]` |
| **Motor Housing Thermal** | `fact_sensor_readings` | `dim_components` (Motor Housing) | `[Avg Health Score]`, `[Cascade Flag Rate]` |
| **OEE Dashboard** | `fact_downtime_events`, `dim_production_counts` | `dim_production_shifts`, `dim_components` | `[OEE Availability]`, `[OEE Performance]`, `[OEE Quality]`, `[OEE Composite]` |
| **Downtime & Six Big Losses** | `fact_downtime_events` | `dim_components`, `dim_production_shifts` | `[Total Downtime Min]`, `[Root Cause Downtime Min]` |
| **Failure Log & MTBF** | `dim_failure_log` | `dim_components` | `[MTBF Hours]`, `[MTTR Hours]`, `[Failure Count]` |
| **Criticality Analysis** | `dim_criticality` | `dim_components` | `[CCI Score]`, `[SRS Score]`, `[Weibull Unreliability]` |

---

## 10. Model Settings & Best Practices

### 10.1 Cross-Filter Direction Summary

| Relationship | Direction | Reason |
|---|---|---|
| `dim_components` -> `fact_sensor_readings` | **Single** | Prevent ambiguity with dim_sensors path |
| `dim_sensors` -> `fact_sensor_readings` | **Single** | Standard Fact table direction |
| `dim_components` -> `fact_downtime_events` | **Single** | Fact table — bidirectional not needed |
| `dim_production_shifts` <-> `dim_production_counts` | **Both** | 1:1 grain — safe; needed for OEE DAX context |
| `dim_criticality` <-> `dim_components` | **Both** | 1:1 lookup — needed so CCI card filters components |
| `dim_components` -> `dim_production_shifts` | **Single** | Dimension filters time grain |
| `dim_components` -> `dim_failure_log` | **Single** | Standard Dim to Fact |

### 10.2 Recommended Power BI Model Settings

```
Data Model Settings:
  Auto Date/Time:               OFF  (date grain managed manually via shift_date)
  Assume referential integrity: OFF  (SQLite FK only enforced with PRAGMA ON)
  Storage mode:                 Import (not DirectQuery - 48K rows is manageable)
  Performance Analyzer:         ON during DAX development
```

### 10.3 Columns to Hide in Report View

Mark as Hidden after confirming all relationships work:
- All surrogate keys: `reading_id`, `downtime_id`, `count_id`, `shift_id`, `failure_id`
- Internal flags: `is_active` (dim_components), `w_srs`, `w_unreliability`, `w_tbr` (dim_criticality)
- Raw normalised sub-scores: `srs_norm`, `unreliability_norm`, `tbr_norm` (show contribution columns instead)

### 10.4 Formatting & Display Conventions

| Column / Measure | Format | Example |
|---|---|---|
| `health_score`, `composite_criticality` | Percentage, 1 decimal | 78.4% |
| `[OEE Availability]`, `[OEE Performance]`, `[OEE Quality]` | Percentage, 1 decimal | 91.2% |
| `[MTBF Hours]`, `[MTTR Hours]`, `ttf_hours` | Decimal (1 place) | 1,338.0 |
| `value` (sensor readings) | Decimal (2 places) | 3.72 |
| `duration_min` | Whole number | 47 |
| `cci_rank` | Whole number | 1 |

---

## 11. Open Items for Day 22

- [ ] Implement all Group A-D DAX measures in Power BI Desktop
- [ ] Validate `[OEE Composite]` output against `sql/queries/oee_composite.sql` results
- [ ] Verify `[CCI Score]` DAX matches `criticality_scores.csv:composite_criticality` exactly
- [ ] Set `position` as Sort Column for `component_name` in `dim_components`
- [ ] Mark all surrogate key columns as Hidden in Report View
- [ ] Test `USERELATIONSHIP()` for root-cause downtime drill-down on Gearbox failure events
- [ ] Create a Calendar table in Power Query if time intelligence functions (SAMEPERIODLASTYEAR, DATESYTD) are required

---

*End of Power BI Data Model Design — Day 21, August 7, 2026.*
*Next step: Open Power BI Desktop, connect both data sources, build this model in the Model View, and validate all relationships before writing any DAX measures.*
