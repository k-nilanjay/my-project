$content = @"

---

#### Day 21 -- August 7, 2026

**Status:** Complete

**Deliverables completed today:**
- [x] ``docs/powerbi_data_model.md`` -- Complete Star Schema design (2 Facts, 6 Dims, 11 relationships, 4 DAX groups)
- [x] ``README.md`` -- Day 21 appended (schema summary, design decisions, viva Q55-Q61)
- [x] ``CONTEXT.md`` -- Day 21 appended (this entry)
- [x] ``STATE_SUMMARY.md`` -- Overwritten Day 21 snapshot

---

##### Power BI Star Schema -- Technical Definition LOCKED Day 21

Model type: Star Schema (not Snowflake). Power BI DAX/VertiPaq optimised for single-hop Dim-to-Fact joins.

Data sources:
- data/manufacturing.db (7.4 MB, 7 tables)
- data/processed/criticality_scores.csv (5 rows x 16 cols)

##### Fact Tables

fact_sensor_readings (~47,957 rows, grain: one sensor measurement per 2h timestep):
  sensor_id         FK -> dim_sensors         [ACTIVE 1:Many]
  component_id      FK -> dim_components       [ACTIVE 1:Many, denormalized]
  ts                DATETIME date axis
  value             FLOAT Measure: raw sensor reading
  is_failure_event  INT(0/1) Flag: 1 at Weibull TTF
  R_derated         FLOAT Measure: Weibull R*(t) Arrhenius-adjusted
  AF                FLOAT Measure: Arrhenius factor (1.0 for Shaft)
  cascade_flag      INT(0/1) Flag: upstream failure elevates reading
  health_score      FLOAT Derived: R_derated * 100 (add in Power Query)

fact_downtime_events (143 rows, grain: one downtime period per component per shift):
  component_id             FK -> dim_components        [ACTIVE 1:Many]
  shift_id                 FK -> dim_production_shifts [ACTIVE 1:Many]
  root_cause_component_id  FK -> dim_components        [INACTIVE]
  duration_min             FLOAT Measure (pre-stored: (end_ts - start_ts)/60)
  downtime_category        VARCHAR Slicer (5 locked values):
                           unplanned_failure / planned_maintenance / changeover
                           / idle / cascade_upstream

##### Dimension Tables

dim_components (5 rows):
  component_id PK, component_name, position (Sort Column 1-5),
  maintenance_strategy, weibull_beta_mid, weibull_eta_hours,
  activation_energy_ev (NULL for Shaft), arrhenius_applicable (0 for Shaft)

dim_sensors (11 rows):
  sensor_id PK, component_id FK [ACTIVE 1:Many]
  sensor_type, unit, iso_alarm_threshold, iso_danger_threshold

dim_production_shifts (1,350 rows):
  shift_id PK, component_id FK [ACTIVE 1:Many]
  shift_date (primary slicer), planned_duration_min (Measure input: Availability denominator)

dim_production_counts (1,350 rows):
  shift_id FK -> dim_production_shifts [ACTIVE 1:1]
  component_id FK [ACTIVE 1:Many]
  total_units, good_units, defective_units, rework_units, ideal_cycle_time_min
  defect_source_component_id FK -> dim_components [INACTIVE]

dim_failure_log (15-19 rows):
  failure_id PK, component_id FK [ACTIVE 1:Many]
  failure_ts, failure_mode, ttf_hours (Measure), repair_duration_hours (Measure)

dim_criticality (5 rows -- from criticality_scores.csv):
  component VARCHAR -- JOIN KEY matching dim_components.component_name (1:1)
  composite_criticality FLOAT -- PRIMARY CCI MEASURE
  cci_rank, structural_risk_score (SRS), weibull_unreliability (1-R(t))
  threshold_breach_rate (TBR)
  cci_srs_contrib (0.40*srs_norm), cci_unrel_contrib (0.35*unreliability_norm)
  cci_tbr_contrib (0.25*tbr_norm)

##### Relationship Matrix LOCKED Day 21

ACTIVE RELATIONSHIPS (9):

  From                   | Column       | To                     | Column          | Cardinality | XFilter
  dim_components         | component_id | fact_sensor_readings   | component_id    | 1:Many      | Single
  dim_sensors            | sensor_id    | fact_sensor_readings   | sensor_id       | 1:Many      | Single
  dim_components         | component_id | fact_downtime_events   | component_id    | 1:Many      | Single
  dim_production_shifts  | shift_id     | fact_downtime_events   | shift_id        | 1:Many      | Single
  dim_components         | component_id | dim_production_shifts  | component_id    | 1:Many      | Single
  dim_production_shifts  | shift_id     | dim_production_counts  | shift_id        | 1:1         | Both
  dim_components         | component_id | dim_production_counts  | component_id    | 1:Many      | Single
  dim_components         | component_id | dim_failure_log        | component_id    | 1:Many      | Single
  dim_criticality        | component    | dim_components         | component_name  | 1:1         | Both

INACTIVE RELATIONSHIPS (2) -- activated via USERELATIONSHIP() in DAX:

  dim_components (component_id) -> fact_downtime_events (root_cause_component_id)
    Activated by: [Root Cause Downtime Min] measure
  dim_components (component_id) -> dim_production_counts (defect_source_component_id)
    Activated by: [Upstream Defect Units] measure

##### DAX Measure Groups Index -- Implementation Day 22

Group A -- Health and Reliability (fact_sensor_readings):
  [Avg Health Score]    = AVERAGE(fact_sensor_readings[health_score])
  [Min Health Score]    = MIN(fact_sensor_readings[health_score])
  [Avg R_Derated]       = AVERAGE(fact_sensor_readings[R_derated])
  [Failure Event Count] = CALCULATE(COUNTROWS(...), is_failure_event = 1)
  [Cascade Flag Rate]   = DIVIDE([Cascade Count], COUNTROWS(...), 0)

Group B -- OEE (fact_downtime_events + dim_production_shifts + dim_production_counts):
  [OEE Availability] = DIVIDE(PlannedMin - CALCULATE(SUM(duration_min), category<>'planned_maintenance'), PlannedMin, 0)
  [OEE Quality]      = DIVIDE(SUM(good_units), SUM(total_units), 0)
  [OEE Performance]  = DIVIDE(SUM(ICT_min * total_units), RunTimeMIn, 0)
  [OEE Composite]    = [Availability] * [Performance] * [Quality]
  [OEE Status]       = SWITCH(TRUE(), >=0.85,'WORLD CLASS', >=0.75,'ACCEPTABLE', >=0.65,'ALERT', 'CRITICAL')

Group C -- MTBF/MTTR (dim_failure_log):
  [MTBF Hours]             = DIVIDE([Total TTF Hours], [Failure Count], BLANK())
  [MTTR Hours]             = AVERAGE(dim_failure_log[repair_duration_hours])
  [Empirical Availability] = DIVIDE([MTBF],[MTBF]+[MTTR], BLANK())

Group D -- Criticality (dim_criticality + USERELATIONSHIP):
  [CCI Score] = SELECTEDVALUE(dim_criticality[composite_criticality], BLANK())
  [CCI Rank]  = SELECTEDVALUE(dim_criticality[cci_rank], BLANK())
  [Root Cause Downtime Min] = CALCULATE(SUM(duration_min),
      USERELATIONSHIP(dim_components[component_id], fact_downtime_events[root_cause_component_id]))
  [Upstream Defect Units] = CALCULATE(SUM(defective_units),
      USERELATIONSHIP(dim_components[component_id], dim_production_counts[defect_source_component_id]))

##### Key Decisions Locked Day 21

1. Star Schema not Snowflake: single-hop Dim-to-Fact. VertiPaq optimised for this.
2. 1:1 for dim_production_shifts to dim_production_counts: SQL UNIQUE constraint guarantees exactly one count per shift. Both XFilter safe at 1:1 grain.
3. 1:1 for dim_criticality to dim_components: string join on component_name. Both XFilter required so CCI slicer propagates to all operational tables.
4. Two INACTIVE relationships: root_cause_component_id and defect_source_component_id are secondary FKs to dim_components. Cannot both be active -- ambiguous filter path. USERELATIONSHIP() activates them per measure.
5. Denormalized component_id in fact_sensor_readings: prevents 2-hop path through dim_sensors for OEE Performance queries requiring component-level RPM aggregation.
6. Single XFilter on all 1:Many: prevents bidirectional filter ambiguity across multiple Dim-to-Fact paths.

Open items Day 22:
- [ ] Connect manufacturing.db and criticality_scores.csv in Power BI Desktop
- [ ] Build all 11 relationships in Model View with correct cardinalities and filter directions
- [ ] Add Power Query derived columns: health_score, pipeline_label, sensor_label, shift date parts
- [ ] Implement all Group A-D DAX measures
- [ ] Validate [OEE Composite] against sql/queries/oee_composite.sql output
- [ ] Validate [CCI Score] against criticality_scores.csv composite_criticality column
- [ ] Hide all surrogate key columns in Report View
- [ ] Begin Fleet Overview page layout

---

*End of Day 21 context entry. Power BI Star Schema fully designed. Day 22: Power BI Desktop -- connect data, build model, implement DAX, begin Fleet Overview page.*

---
"@

Add-Content -Path 'c:\Users\Hement Kitukale\Desktop\Resume project\CONTEXT.md' -Value `$content -Encoding UTF8
Write-Host "CONTEXT.md Day 21 appended successfully."
