# DAX & Power Query M Scripts
## Manufacturing & Industrial Analytics FYP — Day 22

> **Purpose:** This document is the single source of truth for all Power Query M transformations and DAX measure definitions used in the Power BI model. It supplements `docs/powerbi_data_model.md` (the Day 21 schema design) with the exact code that must be entered in Power BI Desktop.
>
> Since `.pbix` is a binary format that cannot be version-controlled as text, this `.md` file **is** the code artifact for Day 22. Every formula here should be copy-pasted verbatim into Power BI Desktop.

---

## Table of Contents

1. [Power Query M — Derived Columns per Table](#1-power-query-m--derived-columns-per-table)
   - 1.1 `fact_sensor_readings`
   - 1.2 `dim_components`
   - 1.3 `dim_production_shifts`
   - 1.4 `dim_criticality`
   - 1.5 `fact_downtime_events`
   - 1.6 `dim_failure_log`
   - 1.7 `dim_production_counts`
   - 1.8 `dim_calendar`
   - 1.9 `dim_sensors`
2. [DAX Measure Group A — Health & Reliability](#2-dax-measure-group-a--health--reliability)
3. [DAX Measure Group B — OEE](#3-dax-measure-group-b--oee)
4. [DAX Measure Group C — MTBF / MTTR](#4-dax-measure-group-c--mtbf--mttr)
5. [DAX Measure Group D — Criticality (with USERELATIONSHIP)](#5-dax-measure-group-d--criticality-with-userelationship)
6. [Relationship Reference](#6-relationship-reference)
7. [USERELATIONSHIP() Logic Explained](#7-userelationship-logic-explained)
8. [Validation Checklist](#8-validation-checklist)

---

## 1. Power Query M — Derived Columns per Table

Power Query transformations are applied in the **Power Query Editor** (`Home → Transform Data`). Each section below gives the full M query for the relevant table.

### How to Apply

1. In Power Query Editor, select the table.
2. Open **Advanced Editor** (`Home → Advanced Editor`).
3. Paste the full M query below, replacing the existing code.
4. Click **Done → Close & Apply**.

---

### 1.1 `fact_sensor_readings`

**Derived columns added:**
- `health_score` — `R_derated × 100` expressed as a percentage (primary Fleet Overview KPI)
- `date_key` — `DATE` type extracted from the `ts` datetime column (enables daily granularity slicing)
- `shift_hour` — integer hour extracted from `ts` (enables shift-period grouping)
- `shift_period` — categorical shift period label (Night / Day / Evening)
- `iso_zone` — categorical vibration severity label (ISO 10816-3 zones A/B/C/D); null for non-vibration sensors

```m
let
    Source = Csv.Document(
        File.Contents("C:\Users\Hement Kitukale\Desktop\Resume project\data\processed\sensor_readings_export.csv"),
        [Delimiter=",", Columns=17, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),

    // --- Cast column types ---
    TypedTable = Table.TransformColumnTypes(PromotedHeaders, {
        {"reading_id",        Int64.Type},
        {"sensor_id",         Int64.Type},
        {"component_id",      Int64.Type},
        {"ts",                type datetime},
        {"value",             type number},
        {"is_anomaly",        Int64.Type},
        {"iso_zone",          type text},
        {"is_failure_event",  Int64.Type},
        {"failure_mode",      type text},
        {"r_derated",         type number},
        {"arrhenius_factor",  type number},
        {"cascade_flag",      Int64.Type},
        {"cycle_number",      Int64.Type},
        {"health_score",      type number},
        {"rpm",               type number},
        {"rpm_rated",         type number},
        {"load_pct",          type number}
    }),

    // --- Rename columns to match DAX expectations ---
    RenamedDAXCols = Table.RenameColumns(TypedTable, {
        {"r_derated", "R_derated"},
        {"arrhenius_factor", "AF"}
    }),

    // --- Derived column: health_score (recalculate to guarantee formula consistency) ---
    // R_derated * 100 expressed as percentage points
    AddHealthScore = Table.AddColumn(RenamedDAXCols, "health_score_calc", each
        if [R_derated] = null then null
        else [R_derated] * 100,
        type number
    ),

    // Drop CSV health_score and replace with recalculated version
    RemovedOriginalHealth = Table.RemoveColumns(AddHealthScore, {"health_score"}),
    RenamedHealthScore = Table.RenameColumns(RemovedOriginalHealth,
        {{"health_score_calc", "health_score"}}),

    // --- Derived column: date_key (DATE from datetime ts) ---
    AddDateKey = Table.AddColumn(RenamedHealthScore, "date_key", each
        DateTime.Date([ts]),
        type date
    ),

    // --- Derived column: shift_hour (integer hour 0-23) ---
    AddShiftHour = Table.AddColumn(AddDateKey, "shift_hour", each
        Time.Hour(DateTime.Time([ts])),
        Int64.Type
    ),

    // --- Derived column: shift_period label ---
    AddShiftPeriod = Table.AddColumn(AddShiftHour, "shift_period", each
        if [shift_hour] >= 0  and [shift_hour] < 8  then "Night  (00-08)"
        else if [shift_hour] >= 8  and [shift_hour] < 16 then "Day    (08-16)"
        else "Evening (16-24)",
        type text
    ),

    // --- Map iso_zone to descriptive labels ---
    AddISOZoneLabel = Table.AddColumn(AddShiftPeriod, "iso_zone_label", each
        if [iso_zone] = "A" then "A - New / Acceptable"
        else if [iso_zone] = "B" then "B - Long-term OK"
        else if [iso_zone] = "C" then "C - Alarm"
        else if [iso_zone] = "D" then "D - Danger"
        else null,
        type text
    ),
    RemovedRawIso = Table.RemoveColumns(AddISOZoneLabel, {"iso_zone"}),
    RenamedIso = Table.RenameColumns(RemovedRawIso, {{"iso_zone_label", "iso_zone"}})

in
    RenamedIso
```

**Key M decisions:**
- `health_score` is recalculated in M (not trusted from CSV) to guarantee `R_derated * 100` formula consistency. The CSV value is dropped and replaced.
- `date_key` is `type date` (not datetime) to enable a clean relationship with a future Date dimension table if one is added in Phase 3.
- `iso_zone` is `null` for non-vibration sensors. Power BI conditional formatting rules should filter `iso_zone IS NOT NULL` before applying ISO zone colour coding.

---

### 1.2 `dim_components`

**Derived columns added:**
- `pipeline_label` — ordered text label for visual legends (e.g., `"Pos 1: Bearing"`)
- `strategy_label` — human-readable expansion of the maintenance strategy code
- `beta_mid` — midpoint of the Weibull beta range for display purposes
- `arrhenius_applicable` — text flag indicating thermal model applicability

```m
let
    Source = Csv.Document(
        File.Contents("C:\Users\Hement Kitukale\Desktop\Resume project\data\processed\components_export.csv"),
        [Delimiter=",", Columns=10, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),

    TypedTable = Table.TransformColumnTypes(PromotedHeaders, {
        {"component_id",         Int64.Type},
        {"component_name",       type text},
        {"position_in_chain",    Int64.Type},
        {"failure_mode",         type text},
        {"weibull_beta_min",     type number},
        {"weibull_beta_max",     type number},
        {"weibull_beta_mid",     type number},
        {"weibull_eta_hours",    type number},
        {"activation_energy_ev", type number},
        {"maintenance_strategy", type text}
    }),

    // --- Rename columns to match DAX / Visual expectations ---
    RenamedDAXCols = Table.RenameColumns(TypedTable, {
        {"position_in_chain", "position"},
        {"weibull_eta_hours", "eta_hours"},
        {"weibull_beta_mid", "beta_mid"}
    }),

    // --- Derived column: pipeline_label ---
    // Format: "Pos N: ComponentName"
    // IMPORTANT: After loading, set dim_components[position] as Sort Column for
    // dim_components[component_name] in Model View > Column Tools. This enforces
    // pipeline order (Bearing->Shaft->...) in all visuals instead of alphabetical sort.
    AddPipelineLabel = Table.AddColumn(TypedTable, "pipeline_label", each
        "Pos " & Text.From([position]) & ": " & [component_name],
        type text
    ),

    // --- Derived column: strategy_label (human-readable) ---
    AddStrategyLabel = Table.AddColumn(AddPipelineLabel, "strategy_label", each
        if [maintenance_strategy] = "PM"     then "Preventive Maintenance"
        else if [maintenance_strategy] = "CBM"    then "Condition-Based Maintenance"
        else if [maintenance_strategy] = "PM_CBM" then "Preventive + Condition-Based"
        else "Unknown",
        type text
    ),

    // --- Derived column: arrhenius_applicable flag ---
    // Shaft has activation_energy_ev = NULL (fatigue failure - not thermally governed)
    AddArrheniusLabel = Table.AddColumn(AddStrategyLabel, "arrhenius_applicable", each
        if [activation_energy_ev] = null then "No (Fatigue-governed)"
        else "Yes (Thermal model active)",
        type text
    )

in
    AddArrheniusLabel
```

**Key M decision:** After loading, go to **Model View → dim_components → component_name → Column Tools → Sort by Column → position**. This single step is mandatory to prevent alphabetical sorting from replacing the correct pipeline order across all visuals.

---

### 1.3 `dim_production_shifts`

**Derived columns added:**
- `shift_month` — integer month (1-12) for monthly OEE trend slicers
- `shift_week` — ISO week number (1-53) for weekly trend analysis
- `shift_quarter` — quarter number (1-4) for quarterly executive summary
- `shift_month_name` — abbreviated month name (Jan, Feb...) for axis labels
- `shift_date_label` — formatted date string "YYYY-MM-DD" for tooltip display
- `shift_number_in_day` — 1/2/3 indicating which 8-hour shift within the day

```m
let
    Source = Csv.Document(
        File.Contents("C:\Users\Hement Kitukale\Desktop\Resume project\data\processed\production_shifts_export.csv"),
        [Delimiter=",", Columns=7, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),

    TypedTable = Table.TransformColumnTypes(PromotedHeaders, {
        {"shift_id",             Int64.Type},
        {"component_id",         Int64.Type},
        {"shift_date",           type date},
        {"shift_label",          type text},
        {"planned_start_ts",     type datetime},
        {"planned_end_ts",       type datetime},
        {"planned_duration_min", type number}
    }),

    // --- Derived column: shift_month (integer 1-12) ---
    AddShiftMonth = Table.AddColumn(TypedTable, "shift_month", each
        Date.Month([shift_date]),
        Int64.Type
    ),

    // --- Derived column: shift_week (ISO week of year 1-53, Monday start) ---
    AddShiftWeek = Table.AddColumn(AddShiftMonth, "shift_week", each
        Date.WeekOfYear([shift_date], Day.Monday),
        Int64.Type
    ),

    // --- Derived column: shift_quarter (1-4) ---
    AddShiftQuarter = Table.AddColumn(AddShiftWeek, "shift_quarter", each
        Date.QuarterOfYear([shift_date]),
        Int64.Type
    ),

    // --- Derived column: shift_month_name (abbreviated, e.g. "Jan") ---
    // After loading, set Sort Column = shift_month (integer) in Model View
    // to prevent alphabetical sorting of month names in visuals
    AddMonthName = Table.AddColumn(AddShiftQuarter, "shift_month_name", each
        Date.ToText([shift_date], "MMM"),
        type text
    ),

    // --- Derived column: shift_date_label (display string YYYY-MM-DD) ---
    AddDateLabel = Table.AddColumn(AddMonthName, "shift_date_label", each
        Date.ToText([shift_date], "yyyy-MM-dd"),
        type text
    ),

    // --- Derived column: shift_number_in_day (1, 2, or 3) ---
    // Shift 1 = 00:00-08:00, Shift 2 = 08:00-16:00, Shift 3 = 16:00-24:00
    AddShiftNumber = Table.AddColumn(AddDateLabel, "shift_number_in_day", each
        let h = Time.Hour(DateTime.Time([planned_start_ts]))
        in if h < 8 then 1 else if h < 16 then 2 else 3,
        Int64.Type
    )

in
    AddShiftNumber
```

**Key M decision:** `shift_week` uses `Day.Monday` as the week-start parameter (ISO 8601 standard, consistent with European industrial reporting norms). `shift_month_name` must be sorted by `shift_month` in Model View to prevent alphabetical axis ordering.

---

### 1.4 `dim_criticality`

**Derived columns added:**
- `component_id` — integer lookup for optional numeric join (active join uses string key)
- `cci_label` — formatted CCI score string for data labels
- `cci_tier` — categorical risk tier label (Critical / High / Moderate / Low)
- `cci_tier_order` — integer sort key for `cci_tier`

```m
let
    Source = Csv.Document(
        File.Contents("C:\Users\Hement Kitukale\Desktop\Resume project\data\processed\criticality_scores.csv"),
        [Delimiter=",", Columns=17, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),

    TypedTable = Table.TransformColumnTypes(PromotedHeaders, {
        {"cci_rank",                 Int64.Type},
        {"component",                type text},
        {"structural_risk_score",    type number},
        {"weibull_unreliability",    type number},
        {"threshold_breach_rate",    type number},
        {"srs_norm",                 type number},
        {"unreliability_norm",       type number},
        {"tbr_norm",                 type number},
        {"cci_srs_contrib",          type number},
        {"cci_unrel_contrib",        type number},
        {"cci_tbr_contrib",          type number},
        {"composite_criticality",    type number},
        {"w_srs",                    type number},
        {"w_unreliability",          type number},
        {"w_tbr",                    type number},
        {"t_eval_hours",             type number},
        {"weibull_mtbf_hours",       type number}
    }),

    // --- Derived column: component_id integer lookup ---
    // Active relationship uses string join (component = component_name).
    // This integer column is for diagnostic use only.
    AddComponentId = Table.AddColumn(TypedTable, "component_id", each
        if      [component] = "Bearing"        then 1
        else if [component] = "Shaft"          then 2
        else if [component] = "Motor Housing"  then 3
        else if [component] = "Coupling"       then 4
        else if [component] = "Gearbox"        then 5
        else null,
        Int64.Type
    ),

    // --- Derived column: cci_label (formatted score string for data labels) ---
    AddCCILabel = Table.AddColumn(AddComponentId, "cci_label", each
        "CCI: " & Text.From(Number.Round([composite_criticality], 3)),
        type text
    ),

    // --- Derived column: cci_tier (risk categorization for conditional formatting) ---
    // CCI range: 0.0 - 1.0 (normalized composite). Thresholds are illustrative;
    // adjust after inspecting actual composite_criticality distribution from criticality_scores.csv
    AddCCITier = Table.AddColumn(AddCCILabel, "cci_tier", each
        if      [composite_criticality] >= 0.75 then "Critical"
        else if [composite_criticality] >= 0.50 then "High"
        else if [composite_criticality] >= 0.25 then "Moderate"
        else "Low",
        type text
    ),

    // --- Derived column: cci_tier_order (integer sort key for cci_tier) ---
    AddTierOrder = Table.AddColumn(AddCCITier, "cci_tier_order", each
        if      [cci_tier] = "Critical" then 1
        else if [cci_tier] = "High"     then 2
        else if [cci_tier] = "Moderate" then 3
        else 4,
        Int64.Type
    )

in
    AddTierOrder
```

---

### 1.5 `fact_downtime_events`

**Derived columns added:**
- `duration_hours` — `duration_min / 60` for MTBF co-analysis
- `is_cascade` — integer flag: 1 if `downtime_category = 'cascade_upstream'`
- `is_unplanned` — integer flag: 1 if `downtime_category = 'unplanned_failure'`
- `downtime_category_label` — human-readable label for legend display

```m
let
    Source = Csv.Document(
        File.Contents("C:\Users\Hement Kitukale\Desktop\Resume project\data\processed\downtime_events_export.csv"),
        [Delimiter=",", Columns=11, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),

    TypedTable = Table.TransformColumnTypes(PromotedHeaders, {
        {"downtime_id",             Int64.Type},
        {"component_id",            Int64.Type},
        {"shift_id",                Int64.Type},
        {"start_ts",                type datetime},
        {"end_ts",                  type datetime},
        {"duration_min",            type number},
        {"downtime_category",       type text},
        {"downtime_type",           type text},
        {"failure_mode",            type text},
        {"root_cause_component_id", Int64.Type},
        {"component_name",          type text}
    }),

    // --- Derived column: duration_hours ---
    AddDurationHours = Table.AddColumn(TypedTable, "duration_hours", each
        [duration_min] / 60,
        type number
    ),

    // --- Derived column: is_cascade flag ---
    AddIsCascade = Table.AddColumn(AddDurationHours, "is_cascade", each
        if [downtime_category] = "cascade_upstream" then 1 else 0,
        Int64.Type
    ),

    // --- Derived column: is_unplanned flag ---
    AddIsUnplanned = Table.AddColumn(AddIsCascade, "is_unplanned", each
        if [downtime_category] = "unplanned_failure" then 1 else 0,
        Int64.Type
    ),

    // --- Derived column: downtime_category_label ---
    AddCategoryLabel = Table.AddColumn(AddIsUnplanned, "downtime_category_label", each
        if      [downtime_category] = "unplanned_failure"   then "Unplanned Failure"
        else if [downtime_category] = "planned_maintenance"  then "Planned Maintenance"
        else if [downtime_category] = "changeover"           then "Setup / Changeover"
        else if [downtime_category] = "idle"                 then "Idle / Shortage"
        else if [downtime_category] = "cascade_upstream"     then "Cascade (Upstream Failure)"
        else "Unknown",
        type text
    )

in
    AddCategoryLabel
```

---

### 1.6 `dim_failure_log`

**Derived columns added:**
- `failure_year_month` — "YYYY-MM" string for trend grouping
- `failure_date_key` — DATE type for timeline visuals

```m
let
    Source = Csv.Document(
        File.Contents("C:\Users\Hement Kitukale\Desktop\Resume project\data\processed\failure_log_export.csv"),
        [Delimiter=",", Columns=13, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),

    TypedTable = Table.TransformColumnTypes(PromotedHeaders, {
        {"failure_id",            Int64.Type},
        {"component_id",          Int64.Type},
        {"cycle_number",          Int64.Type},
        {"ttf_hours",             type number},
        {"t_failure_abs",         type number},
        {"beta_mid",              type number},
        {"eta_nominal_h",         type number},
        {"eta_effective_h",       type number},
        {"ea_ev",                 type number},
        {"strategy",              type text},
        {"repair_hours",          type number},
        {"failure_mode",          type text},
        {"qq_r_squared",          type number}
    }),

    // --- Rename columns to match DAX expectations ---
    RenamedDAXCols = Table.RenameColumns(TypedTable, {
        {"repair_hours", "repair_duration_hours"}
    }),

    // --- Derived column: failure_timestamp (sim start + t_failure_abs hours) ---
    // DECISION MADE: Simulation anchored to 2026-07-20 00:00:00 per schema.sql
    // Null guard required because t_failure_abs is empty in CSV (throws Expression.Error in #duration)
    AddFailureTimestamp = Table.AddColumn(RenamedDAXCols, "failure_timestamp", each
        if [t_failure_abs] = null then null
        else #datetime(2026, 7, 20, 0, 0, 0) + #duration(0, [t_failure_abs], 0, 0),
        type datetime
    ),

    // --- Derived column: failure_year_month (for MTBF trend by month) ---
    AddYearMonth = Table.AddColumn(AddFailureTimestamp, "failure_year_month", each
        Date.ToText(DateTime.Date([failure_timestamp]), "yyyy-MM"),
        type text
    ),

    // --- Derived column: failure_date_key (DATE for timeline visuals) ---
    AddDateKey = Table.AddColumn(AddYearMonth, "failure_date_key", each
        DateTime.Date([failure_timestamp]),
        type date
    )

in
    AddDateKey
```

---

### 1.7 `dim_production_counts`

**Derived columns added:**
- None directly required by DAX, but types must be cast correctly to ensure OEE measures compute successfully.

```m
let
    Source = Csv.Document(
        File.Contents("C:\Users\Hement Kitukale\Desktop\Resume project\data\processed\production_counts_export.csv"),
        [Delimiter=",", Columns=9, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),

    TypedTable = Table.TransformColumnTypes(PromotedHeaders, {
        {"count_id",                   Int64.Type},
        {"component_id",               Int64.Type},
        {"shift_id",                   Int64.Type},
        {"defect_source_component_id", Int64.Type},
        {"total_units",                Int64.Type},
        {"good_units",                 Int64.Type},
        {"defective_units",            Int64.Type},
        {"rework_units",               Int64.Type},
        {"ideal_cycle_time_min",       type number}
    })

in
    TypedTable
```

---

### 1.8 `dim_calendar`

**Derived columns added:**
- `date` — DATE type primary key (contiguous 365 days)
- `year` / `month` / `month_name` — standard time hierarchy
- `year_month_key` — integer sort key (YYYYMM) to prevent axis wrapping
- `year_month` — formatted string (YYYY-MMM) for chronological visual axes

```m
let
    // DECISION MADE: 365-day simulation range anchored to 2026-07-20 per schema.sql
    StartDate = #date(2026, 7, 20),
    EndDate = #date(2027, 7, 20),
    NumberOfDays = Duration.Days(EndDate - StartDate) + 1,
    Dates = List.Dates(StartDate, NumberOfDays, #duration(1, 0, 0, 0)),
    Source = Table.FromList(Dates, Splitter.SplitByNothing(), {"date"}, null, ExtraValues.Error),
    TypedTable = Table.TransformColumnTypes(Source, {{"date", type date}}),
    AddYear = Table.AddColumn(TypedTable, "year", each Date.Year([date]), Int64.Type),
    AddMonth = Table.AddColumn(AddYear, "month", each Date.Month([date]), Int64.Type),
    AddMonthName = Table.AddColumn(AddMonth, "month_name", each Date.ToText([date], "MMM"), type text),
    AddYearMonthKey = Table.AddColumn(AddMonthName, "year_month_key", each [year] * 100 + [month], Int64.Type),
    AddYearMonth = Table.AddColumn(AddYearMonthKey, "year_month", each Text.From([year]) & "-" & Date.ToText([date], "MMM"), type text)
in
    AddYearMonth
```

**Key M decision:** This contiguous Date table is required for DAX Time Intelligence (`DATEADD`). After loading, create an **Active 1:Many relationship** from `dim_calendar[date]` to `fact_sensor_readings[date_key]`.

---

### 1.9 `dim_sensors`

**Derived columns added:**
- `sensor_label` — combined string for display (e.g. `"1 - vibration (mm/s_rms)"`)

```m
let
    Source = Csv.Document(
        File.Contents("C:\\Users\\Hement Kitukale\\Desktop\\Resume project\\data\\processed\\sensors_export.csv"),
        [Delimiter=",", Columns=8, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    
    TypedTable = Table.TransformColumnTypes(PromotedHeaders, {
        {"sensor_id",            Int64.Type},
        {"component_id",         Int64.Type},
        {"sensor_type",          type text},
        {"unit_of_measure",      type text},
        {"iso_alarm_threshold",  type number},
        {"iso_danger_threshold", type number},
        {"sample_rate_hz",       type number},
        {"is_active",            Int64.Type}
    }),
    
    RemovedColumns = Table.RemoveColumns(TypedTable, {"sample_rate_hz", "is_active"}),

    // --- Derived column: sensor_label ---
    // Format: "SensorID - sensor_type (unit_of_measure)"
    AddSensorLabel = Table.AddColumn(RemovedColumns, "sensor_label", each
        Text.From([sensor_id]) & " - " & [sensor_type] & " (" & [unit_of_measure] & ")",
        type text
    )

in
    AddSensorLabel
```

---

### 1.10 `_Six_Big_Losses` (Disconnected Stub Table)

**Derived columns added:**
- None (hardcoded static table)
- Used to supply category labels for the OEE Decomposition Waterfall Chart (Panel C).

```m
let
    Source = #table(type table [#"Loss Type" = text, #"Sort Order" = Int64.Type], {{"Ideal OEE", 1}, {"Availability Loss", 2}, {"Performance Loss", 3}, {"Quality Loss", 4}})
in
    Source
```

**Key M decision:** A disconnected table is required to act as the Category axis for the Waterfall chart, allowing a `SWITCH()` measure to route to the correct underlying DAX measure (B-09, B-10, B-11).

---

### 1.11 `_Radar_Metrics` (Disconnected Stub Table)

**Derived columns added:**
- None (hardcoded static table)
- Used to supply the Category axis for the Risk Profile Radar Chart (Panel B).

```m
let
    Source = #table(type table [#"Metric Name" = text, #"Sort Order" = Int64.Type], {{"CCI", 1}, {"SRS", 2}, {"TBR", 3}, {"Weibull F(t)", 4}})
in
    Source
```

**Key M decision:** Radar charts in Power BI require a single Category field for the axes. This disconnected table provides those axes, and two DAX `SWITCH()` measures (D-11, D-12) will route each axis to the correct underlying component or fleet-average measure.

---

## 2. DAX Measure Group A — Health & Reliability

**Source table:** `fact_sensor_readings`
**Measure home table:** Create a dedicated empty table named `_Measures_A_Health` and place all Group A measures inside it to keep the Fields pane organized.

```dax
-- ============================================================
-- MEASURE GROUP A: Health & Reliability
-- Source: fact_sensor_readings
-- ============================================================


-- A-01: Average Health Score (primary Fleet Overview KPI)
-- Returns AVERAGE(health_score) in the current filter context.
-- Filter context is typically: one component x one time period.
-- health_score = R_derated * 100, range 0-100 (%).
-- Values < 60 indicate high degradation risk.
[Avg Health Score] =
AVERAGE( fact_sensor_readings[health_score] )


-- A-02: Minimum Health Score (worst-case reading in context)
-- Surfaces the single worst-health reading within the filter.
-- Use on Fleet Overview with conditional formatting at < 50%.
[Min Health Score] =
MIN( fact_sensor_readings[health_score] )


-- A-03: Average Derated Reliability (R* dimensionless 0-1)
-- R_derated = Weibull R(t) adjusted by Arrhenius acceleration factor.
-- Equivalent to Avg Health Score / 100; retained separately for analytical
-- precision and to avoid rounding artefacts in cascaded calculations.
[Avg R_Derated] =
AVERAGE( fact_sensor_readings[R_derated] )


-- A-04: Failure Event Count
-- Counts rows where is_failure_event = 1 within filter context.
-- CALCULATE() applies the row-level filter on top of the current context.
[Failure Event Count] =
CALCULATE(
    COUNTROWS( fact_sensor_readings ),
    fact_sensor_readings[is_failure_event] = 1
)


-- A-04b: Failure Marker Plot Y
-- Anchors failure markers onto the Health Score trendline in Panel E.
-- If a failure occurred, returns the [Avg Health Score], else BLANK().
-- This replaces raw [Failure Event Count] as the bound series.
[Failure Marker Plot Y] =
IF(
    [Failure Event Count] > 0,
    [Avg Health Score],
    BLANK()
)


-- A-05: Cascade Flag Rate
-- Proportion of sensor readings flagged as elevated due to upstream failure.
-- DIVIDE() third argument (0) returns 0 when denominator is zero.
-- High cascade rate for downstream components (Coupling, Gearbox) is expected
-- and is a direct diagnostic signal of upstream failure propagation.
[Cascade Flag Rate] =
DIVIDE(
    CALCULATE(
        COUNTROWS( fact_sensor_readings ),
        fact_sensor_readings[cascade_flag] = 1
    ),
    COUNTROWS( fact_sensor_readings ),
    0
)


-- A-06: Health Score Standard Deviation
-- Measures degradation variance. High StdDev with moderate Avg Health Score
-- indicates erratic sensor behaviour - a diagnostic signal.
[Health Score StdDev] =
STDEV.P( fact_sensor_readings[health_score] )


-- A-07: Readings Above Alarm Threshold
-- Counts readings where sensor value breached the ISO alarm level.
-- Requires the active relationship dim_sensors -> fact_sensor_readings
-- so that RELATED() can access dim_sensors[iso_alarm] per reading row.
[Alarm Breach Count] =
CALCULATE(
    COUNTROWS( fact_sensor_readings ),
    FILTER(
        fact_sensor_readings,
        NOT ISBLANK( RELATED( dim_sensors[iso_alarm_threshold] ) ) &&
        fact_sensor_readings[value] > RELATED( dim_sensors[iso_alarm_threshold] )
    )
)


-- A-08: Readings In Danger Zone
-- Counts readings where value > ISO danger threshold (ISO 10816-3 Zone D).
-- Distinct from Alarm: Danger = immediate action required.
[Danger Zone Count] =
CALCULATE(
    COUNTROWS( fact_sensor_readings ),
    FILTER(
        fact_sensor_readings,
        NOT ISBLANK( RELATED( dim_sensors[iso_danger_threshold] ) ) &&
        fact_sensor_readings[value] > RELATED( dim_sensors[iso_danger_threshold] )
    )
)


-- A-09: Average Arrhenius Acceleration Factor
-- Mean AF in context. AF = 1.0 for Shaft (no thermal model).
-- AF > 1.0 means operating temperature is accelerating wear faster than nameplate.
-- AF > 2.0 on Motor Housing or Bearing is a viva-ready diagnostic finding
-- (corresponds to the rule-of-thumb: +10 deg C => ~2x failure rate for Ea ~0.7 eV).
[Avg AF] =
AVERAGE( fact_sensor_readings[AF] )


-- A-10: Health Score Period Delta (month-over-month change)
-- Compares current period vs previous month average health score.
-- Returns a signed percentage-point change.
-- Returns BLANK() if no previous period data exists.
-- Note: DATEADD() requires fact_sensor_readings[date_key] (DATE column added in M).
[Health Score Period Delta] =
VAR CurrentPeriodAvg =
    AVERAGE( fact_sensor_readings[health_score] )
VAR PreviousPeriodAvg =
    CALCULATE(
        AVERAGE( fact_sensor_readings[health_score] ),
        DATEADD( dim_calendar[date], -1, MONTH )
    )
RETURN
    IF(
        ISBLANK( CurrentPeriodAvg ) || ISBLANK( PreviousPeriodAvg ),
        BLANK(),
        CurrentPeriodAvg - PreviousPeriodAvg
    )


-- A-11: Combined Alerts Status
-- Priority-weighted status measure to prevent Danger breaches from being diluted.
-- Evaluates Danger count first, then Alarm count.
[Combined Alerts] =
VAR DangerCount = [Danger Zone Count]
VAR AlarmCount = [Alarm Breach Count]
RETURN
    SWITCH(
        TRUE(),
        DangerCount > 0, "Critical",
        AlarmCount > 5, "Warning",
        AlarmCount > 0, "Caution",
        "Normal"
    )


-- A-12: Combined Alert Count
-- Returns the total count of alarm breaches. Because Danger thresholds are 
-- strictly greater than Alarm thresholds, the Alarm measure inherently includes 
-- Danger-level readings. Adding them would cause double-counting.
[Combined Alert Count] = [Alarm Breach Count]


-- A-13: Alert Count Color
-- Companion color measure for KPI Card 5 font conditional formatting.
-- Evaluates directly off the [Combined Alert Count] value (fleet level context).
[Alert Count Color] =
VAR AlertCount = [Combined Alert Count]
RETURN
    SWITCH(
        TRUE(),
        ISBLANK(AlertCount), "#2E7D32",
        AlertCount > 5, "#C62828",
        AlertCount > 0, "#F57F17",
    )


-- A-14: Alarm Band Shade
-- Returns 100 (full y-axis height) when is_anomaly readings exist in the daily context,
-- else BLANK. Used as an Area series on Panel E to shade alarm breach periods.
[Alarm Band Shade] =
VAR AnomalyCount = 
    CALCULATE(
        COUNTROWS( fact_sensor_readings ),
        fact_sensor_readings[is_anomaly] = 1
    )
RETURN
    IF(
        ISBLANK( AnomalyCount ) || AnomalyCount = 0,
        BLANK(),
        100
    )
```

---

## 3. DAX Measure Group B — OEE

**Source tables:** `fact_downtime_events`, `dim_production_shifts`, `dim_production_counts`
**Measure home table:** `_Measures_B_OEE`

> **Filter context note:** OEE measures evaluate within the current filter context — typically one component x one shift when the visual row grain is `dim_production_shifts[shift_date]`. When aggregated across multiple shifts (monthly view), SUM() and MIN() produce aggregate-level OEE — not an average of shift-level OEEs. This is correct behaviour: aggregate A = total good time / total planned time. This distinction is a likely viva question.

```dax
-- ============================================================
-- MEASURE GROUP B: OEE (Overall Equipment Effectiveness)
-- Formula: OEE = Availability x Performance x Quality
-- Sources: fact_downtime_events, dim_production_shifts,
--          dim_production_counts
-- ============================================================


-- B-01: Total Downtime Minutes (excluding Planned Maintenance)
-- Planned Maintenance windows are pre-excluded from Planned Production Time
-- in the SQL schema. Must also be excluded in DAX to avoid double-counting.
[Total Downtime Min] =
CALCULATE(
    SUM( fact_downtime_events[duration_min] ),
    fact_downtime_events[downtime_category] <> "planned_maintenance"
)


-- B-02: Total Planned Production Minutes
-- Denominator for Availability calculation.
[Planned Production Min] =
SUM( dim_production_shifts[planned_duration_min] )


-- B-03: Run Time Minutes
-- Run Time = Planned Production Time - Unplanned Downtime.
-- Denominator for Performance calculation.
-- MAX(0, ...) prevents negative run time if downtime exceeds planned time.
[Run Time Min] = 
IF(
    ISBLANK( [Planned Production Min] ),
    BLANK(),
    MAX( 0, [Planned Production Min] - [Total Downtime Min] )
)


-- B-04: OEE Availability (A)
-- A = Run Time / Planned Production Time
-- DIVIDE() third argument (BLANK) returns BLANK when planned time is zero.
-- Format as percentage in Power BI (range: 0-1).
[OEE Availability] =
DIVIDE(
    [Run Time Min],
    [Planned Production Min],
    BLANK()
)


-- B-05: OEE Quality (Q) = First-Pass Yield
-- Q = Good Units / Total Units
-- SUM() over dim_production_counts is safe: the SQL UNIQUE(component_id, shift_id)
-- constraint ensures one row per component per shift, so SUM = value of that row in context.
[OEE Quality] =
DIVIDE(
    SUM( dim_production_counts[good_units] ),
    SUM( dim_production_counts[total_units] ),
    BLANK()
)


-- B-06: OEE Performance (P)
-- P = (Ideal Cycle Time x Total Units) / Run Time
-- MIN(1, ...) clamps P to <= 1.0 (prevents P > 1 if actual rate briefly exceeds nameplate).
-- IMPORTANT: SUM(ICT) * SUM(total_units) is the correct aggregation pattern here.
-- With the UNIQUE constraint guaranteeing one row per shift in context,
-- SUM(ICT) = ICT and SUM(total_units) = total_units for that shift.
[OEE Performance] =
VAR IdealTime =
    SUMX(
        dim_production_counts,
        dim_production_counts[ideal_cycle_time_min] * dim_production_counts[total_units]
    )
VAR RunTime = [Run Time Min]
RETURN
    IF(
        ISBLANK( RunTime ) || RunTime = 0 || ISBLANK( IdealTime ),
        BLANK(),
        MIN( 1, DIVIDE( IdealTime, RunTime, 0 ) )
    )


-- B-07: OEE Composite
-- OEE = A x P x Q
-- Returns BLANK() if any factor is BLANK() - prevents false 0% OEE
-- when data is simply missing (e.g., no production_counts for a shift).
[OEE Composite] =
VAR A = [OEE Availability]
VAR P = [OEE Performance]
VAR Q = [OEE Quality]
RETURN
    IF(
        ISBLANK(A) || ISBLANK(P) || ISBLANK(Q),
        BLANK(),
        A * P * Q
    )


-- B-08: OEE Status Label
-- Day 2 locked status tier taxonomy:
-- >= 85% = WORLD CLASS, >= 75% = ACCEPTABLE, >= 65% = ALERT, < 65% = CRITICAL
[OEE Status] =
VAR OEEValue = [OEE Composite]
RETURN
    IF(
        ISBLANK( OEEValue ),
        BLANK(),
        SWITCH(
            TRUE(),
            OEEValue >= 0.85, "WORLD CLASS",
            OEEValue >= 0.75, "ACCEPTABLE",
            OEEValue >= 0.65, "ALERT",
            "CRITICAL"
        )
    )


-- B-09: Availability Loss (percentage points)
-- Additive decomposition for Six Big Losses waterfall chart.
-- NOTE: This measure decomposes fleet-average OEE, not the bottleneck value shown in KPI Card 1 (B-15). Semantic mismatch flagged and pending resolution — see STATE_SUMMARY.md Open Issues.
-- Note: A_loss + P_loss + Q_loss does NOT equal (1 - OEE) because OEE
-- is multiplicative, not additive. The individual loss columns are directionally
-- correct and useful for waterfall starting points but not exact waterfall steps.
[Availability Loss PP] =
IF(
    ISBLANK([OEE Availability]),
    BLANK(),
    ( 1 - [OEE Availability] ) * 100
)


-- B-10: Performance Loss (percentage points)
[Performance Loss PP] =
IF(
    ISBLANK([OEE Performance]),
    BLANK(),
    ( 1 - [OEE Performance] ) * 100
)


-- B-11: Quality Loss (percentage points)
[Quality Loss PP] =
IF(
    ISBLANK([OEE Quality]),
    BLANK(),
    ( 1 - [OEE Quality] ) * 100
)


-- B-11b: Selected Loss PP
-- Companion measure for Panel C Waterfall chart, switched by _Six_Big_Losses[Loss Type].
-- Ideal OEE starts at +100, while losses are negated so they step down in the visualization.
[Selected Loss PP] = 
SWITCH(
    SELECTEDVALUE('_Six_Big_Losses'[Loss Type]),
    "Ideal OEE", 100,
    "Availability Loss", -[Availability Loss PP],
    "Performance Loss", -[Performance Loss PP],
    "Quality Loss", -[Quality Loss PP],
    BLANK()
)


-- B-12: System OEE Availability (series-system MIN rule)
-- Evaluates OEE Availability for each component and returns the minimum.
-- Implements the series-system bottleneck rule: A_sys = MIN(A_i).
-- MINX() iterates over each component_id in the current context.
-- Meaningful only when multiple components are in context (no component slicer).
[System OEE Availability] =
MINX(
    VALUES( dim_components[component_id] ),
    CALCULATE( [OEE Availability] )
)


-- B-13: System OEE Performance (series-system MIN rule)
[System OEE Performance] =
MINX(
    VALUES( dim_components[component_id] ),
    CALCULATE( [OEE Performance] )
)


-- B-14: System OEE Quality (series-system PRODUCT rule)
-- PRODUCT(Q_i) implemented as EXP(SUM(LN(Q_i))) - the DAX equivalent of the
-- SQL EXP(SUM(LN())) pattern (DAX has no native PRODUCTX() function).
-- Zero-guard: if any component has Q = 0, return 0 directly to avoid
-- LN(0) = -Infinity error.
[System OEE Quality] =
VAR HasBlankQuality = 
    SUMX(
        VALUES( dim_components[component_id] ),
        IF(ISBLANK(CALCULATE([OEE Quality])), 1, 0)
    ) > 0
VAR HasZeroQuality = 
    COUNTROWS(
        FILTER(
            VALUES( dim_components[component_id] ),
            VAR Q = CALCULATE([OEE Quality])
            RETURN NOT ISBLANK(Q) && Q = 0
        )
    ) > 0
RETURN
    IF(
        HasBlankQuality, BLANK(),
        IF(
            HasZeroQuality, 0,
            EXP(
                SUMX(
                    VALUES( dim_components[component_id] ),
                    LN( CALCULATE( [OEE Quality] ) )
                )
            )
        )
    )


-- B-15: System OEE Composite
[System OEE Composite] =
[System OEE Availability] * [System OEE Performance] * [System OEE Quality]


-- B-16: Loss 1 - Unplanned Breakdown Minutes (Six Big Losses)
[Loss 1 Unplanned Breakdown Min] =
CALCULATE(
    SUM( fact_downtime_events[duration_min] ),
    fact_downtime_events[downtime_category] = "unplanned_failure"
)


-- B-17: Loss 2 - Setup & Changeover Minutes
[Loss 2 Changeover Min] =
CALCULATE(
    SUM( fact_downtime_events[duration_min] ),
    fact_downtime_events[downtime_category] = "changeover"
)


-- B-18: Loss 3 - Minor Stops & Idle Minutes
-- Includes both idle events and cascade-upstream events (minor system-level stops).
[Loss 3 Minor Stop Idle Min] =
CALCULATE(
    SUM( fact_downtime_events[duration_min] ),
    fact_downtime_events[downtime_category] IN { "idle", "cascade_upstream" }
)


-- B-18b: Selected Loss Min
-- Companion measure for Panel C Waterfall chart tooltip, switched by _Six_Big_Losses[Loss Type].
-- Maps the OEE Pillar loss category to the underlying raw downtime minutes.
[Selected Loss Min] = 
SWITCH(
    SELECTEDVALUE('_Six_Big_Losses'[Loss Type]),
    "Availability Loss", [Loss 1 Unplanned Breakdown Min] + [Loss 2 Changeover Min],
    "Performance Loss", [Loss 3 Minor Stop Idle Min],
    "Quality Loss", BLANK(),  -- Quality defect counts are typically used instead of minutes
    BLANK()
)


-- B-19: Dominant Loss Category (for waterfall annotation)
-- Returns the name of the largest loss in the current filter context.
[Dominant Loss Category] =
VAR L1 = [Loss 1 Unplanned Breakdown Min]
VAR L2 = [Loss 2 Changeover Min]
VAR L3 = [Loss 3 Minor Stop Idle Min]
VAR MaxLoss = MAX( MAX( L1, L2 ), L3 )
VAR MatchCount = INT(MaxLoss = L1) + INT(MaxLoss = L2) + INT(MaxLoss = L3)
RETURN
    IF(
        ISBLANK( MaxLoss ) || MaxLoss = 0,
        BLANK(),
        IF(
            MatchCount > 1,
            "Tied",
            SWITCH(
                TRUE(),
                MaxLoss = L1, "Loss 1: Breakdowns",
                MaxLoss = L2, "Loss 2: Changeover",
                MaxLoss = L3, "Loss 3: Minor Stops"
            )
        )
    )


-- B-BN-00: Bottleneck Component ID
-- Returns the component_id of the component with the minimum average health score
-- in the current filter context (= the constraining / weakest-link component).
-- Used by B-BN-01 through B-BN-04 to scope OEE decomposition to this component only.
[Bottleneck Component ID] =
VAR _HealthTable =
    ADDCOLUMNS(
        VALUES( dim_components[component_id] ),
        "@AvgHealth", CALCULATE( [Avg Health Score] )
    )
VAR _MinHealth =
    MINX( _HealthTable, IF( ISBLANK( [@AvgHealth] ), BLANK(), [@AvgHealth] ) )
VAR _BNID =
    MAXX(
        FILTER( _HealthTable, NOT ISBLANK( [@AvgHealth] ) && [@AvgHealth] = _MinHealth ),
        [component_id]
    )
RETURN _BNID


-- B-BN-01: Bottleneck OEE Availability
-- Scoped to bottleneck component only via CALCULATE + FILTER on component_id.
[Bottleneck OEE Availability] =
VAR _BNID = [Bottleneck Component ID]
RETURN
    IF(
        ISBLANK( _BNID ),
        BLANK(),
        CALCULATE(
            [OEE Availability],
            FILTER( dim_components, dim_components[component_id] = _BNID )
        )
    )


-- B-BN-02: Bottleneck OEE Performance
[Bottleneck OEE Performance] =
VAR _BNID = [Bottleneck Component ID]
RETURN
    IF(
        ISBLANK( _BNID ),
        BLANK(),
        CALCULATE(
            [OEE Performance],
            FILTER( dim_components, dim_components[component_id] = _BNID )
        )
    )


-- B-BN-03: Bottleneck OEE Quality
[Bottleneck OEE Quality] =
VAR _BNID = [Bottleneck Component ID]
RETURN
    IF(
        ISBLANK( _BNID ),
        BLANK(),
        CALCULATE(
            [OEE Quality],
            FILTER( dim_components, dim_components[component_id] = _BNID )
        )
    )


-- B-BN-04: Bottleneck Availability Loss PP
-- (1 - A_bottleneck) * 100 percentage-point loss for bottleneck component only.
[Bottleneck Availability Loss PP] =
IF(
    ISBLANK( [Bottleneck OEE Availability] ),
    BLANK(),
    ( 1 - [Bottleneck OEE Availability] ) * 100
)


-- B-BN-05: Bottleneck Performance Loss PP
-- Sequentially weighted by Availability.
[Bottleneck Performance Loss PP] =
IF(
    ISBLANK( [Bottleneck OEE Performance] ) || ISBLANK( [Bottleneck OEE Availability] ),
    BLANK(),
    [Bottleneck OEE Availability] * ( 1 - [Bottleneck OEE Performance] ) * 100
)


-- B-BN-06: Bottleneck Quality Loss PP
-- Sequentially weighted by Availability and Performance.
[Bottleneck Quality Loss PP] =
IF(
    ISBLANK( [Bottleneck OEE Quality] ) || ISBLANK( [Bottleneck OEE Performance] ) || ISBLANK( [Bottleneck OEE Availability] ),
    BLANK(),
    [Bottleneck OEE Availability] * [Bottleneck OEE Performance] * ( 1 - [Bottleneck OEE Quality] ) * 100
)


-- B-BN-07: Selected Loss PP (Bottleneck)
-- Companion measure for Panel C Waterfall chart.
-- Routes _Six_Big_Losses[Loss Type] to bottleneck-scoped OEE loss measures.
[Selected Loss PP (Bottleneck)] =
VAR _ALoss = [Bottleneck Availability Loss PP]
VAR _PLoss = [Bottleneck Performance Loss PP]
VAR _QLoss = [Bottleneck Quality Loss PP]
RETURN
SWITCH(
    SELECTEDVALUE( '_Six_Big_Losses'[Loss Type] ),
    "Ideal OEE",          100,
    "Availability Loss",  -_ALoss,
    "Performance Loss",   -_PLoss,
    "Quality Loss",       -_QLoss,
    BLANK()
)


-- B-BN-08: Bottleneck OEE Composite
-- Resolves the KPI Card 1 vs Panel C mismatch by explicitly calculating
-- the composite OEE (A * P * Q) of the bottleneck component alone.
-- Must be used in KPI Card 1 instead of [System OEE Composite] so that
-- the waterfall chart (Panel C) and KPI Card 1 describe the same physical subject.
[Bottleneck OEE Composite] =
VAR A = [Bottleneck OEE Availability]
VAR P = [Bottleneck OEE Performance]
VAR Q = [Bottleneck OEE Quality]
RETURN
    IF(
        A = 0, 0,
        IF(
            ISBLANK(A) || ISBLANK(P) || ISBLANK(Q),
            BLANK(),
            A * P * Q
        )
    )
```

---

## 4. DAX Measure Group C — MTBF / MTTR

**Source table:** `dim_failure_log`
**Measure home table:** `_Measures_C_MTBF`

> **Evaluation context note:** These measures evaluate within whatever filter context is applied — typically one component. `[MTBF Hours]` with no component filter returns the fleet-level aggregate MTBF (mean of ALL TTF values across all components), which is less analytically useful than per-component MTBF. Always pair with a component slicer or component-axis visual.

```dax
-- ============================================================
-- MEASURE GROUP C: MTBF / MTTR / Empirical Availability
-- Source: dim_failure_log
-- ============================================================


-- C-01: Failure Count
-- Count of discrete failure events in the current filter context.
[Failure Count] =
CALCULATE(
    COUNTROWS( dim_failure_log ),
    NOT ISBLANK( dim_failure_log[t_failure_abs] )
)


-- C-02: Mean Time Between Failures (MTBF) - hours
-- MTBF = SUM(ttf_hours) / Failure Count
-- Written as DIVIDE() explicitly to surface the formula for viva defence.
-- Returns BLANK() when Failure Count = 0 (no failures in context).
[MTBF Hours] =
DIVIDE(
    SUM( dim_failure_log[ttf_hours] ),
    [Failure Count],
    BLANK()
)


-- C-03: Mean Time To Repair (MTTR) - hours
-- Arithmetic mean of repair durations for all failure events in context.
-- AVERAGE() returns BLANK() when no rows exist - correct behaviour.
[MTTR Hours] =
AVERAGE( dim_failure_log[repair_duration_hours] )


-- C-04: Total Repair Hours
-- Total cumulative repair time in context. Useful for maintenance budget analysis.
[Total Repair Hours] =
SUM( dim_failure_log[repair_duration_hours] )


-- C-05: Total Operating Hours (sum of TTF)
-- Sum of all time-to-failure values in context = total observed operating time
-- across all failure cycles. NOT wall-clock time.
[Total Operating Hours] =
SUM( dim_failure_log[ttf_hours] )


-- C-06: Empirical Availability (from MTBF and MTTR)
-- A_empirical = MTBF / (MTBF + MTTR)
-- This is steady-state availability from renewal theory.
-- DISTINCT from OEE Availability (B-04): B-04 is shift-level production availability;
-- C-06 is component-level inherent availability from failure data.
-- Both are valid but measure different things - a likely viva question.
[Empirical Availability] =
DIVIDE(
    [MTBF Hours],
    [MTBF Hours] + [MTTR Hours],
    BLANK()
)


-- C-07: Maintenance Ratio
-- MTTR / MTBF - proportion of a failure cycle spent on repair (lower = better).
-- Ratio > 0.10 (10% repair overhead) indicates high maintenance burden.
[Maintenance Ratio] =
DIVIDE(
    [MTTR Hours],
    [MTBF Hours],
    BLANK()
)


-- C-08: MTBF vs Weibull MTBF Delta
-- Compares empirical MTBF from dim_failure_log vs theoretical Weibull MTBF
-- (= eta * Gamma(1 + 1/beta)) for the selected component.
-- Requires dim_criticality[weibull_mtbf_hours] column (see note below).
-- Positive = component lasting longer than Weibull model predicts (conservative model).
-- Negative = component failing earlier than model predicts (model is optimistic - ALERT).
[MTBF vs Weibull Delta] =
VAR EmpiricalMTBF = [MTBF Hours]
VAR WeibullMTBF   = SELECTEDVALUE( dim_criticality[weibull_mtbf_hours], BLANK() )
RETURN
    IF(
        ISBLANK( EmpiricalMTBF ) || ISBLANK( WeibullMTBF ),
        BLANK(),
        EmpiricalMTBF - WeibullMTBF
    )


-- C-09: MTBF Delta Color
-- Returns hex colour string for Panel D diverging bar conditional formatting.
-- Positive delta (observed MTBF >= model MTBF) = Teal; Negative = Red.
-- Handles BLANK explicitly to avoid painting blank months.
[MTBF Delta Color] =
IF(
    ISBLANK( [MTBF vs Weibull Delta] ),
    BLANK(),
    IF( [MTBF vs Weibull Delta] >= 0, "#00695C", "#B00020" )
)


-- C-10: Weibull MTBF Model
-- Returns the theoretical Weibull MTBF for the selected component.
-- Required for Panel A reference line via fx > Field value conditional formatting.
[Weibull MTBF Model] =
MAX( dim_criticality[weibull_mtbf_hours] )
```

> **Note on C-08:** `dim_criticality[weibull_mtbf_hours]` requires a column in `criticality_scores.csv`. If not present, add to `composite_criticality.py`:
> ```python
> from scipy.special import gamma as scipy_gamma
> df['weibull_mtbf_hours'] = df['eta_hours'] * scipy_gamma(1 + 1/df['beta_mid'])
> ```
> Then re-export `criticality_scores.csv` and reload in Power BI.

---

## 5. DAX Measure Group D — Criticality (with USERELATIONSHIP)

**Source tables:** `dim_criticality`, `dim_components`, `fact_downtime_events`, `dim_production_counts`
**Measure home table:** `_Measures_D_Criticality`

### Why USERELATIONSHIP() Is Required

The Power BI model has **two inactive relationships** both connecting `dim_components[component_id]` to different foreign-key columns:

| Inactive Relationship | Semantic Question Answered |
|---|---|
| `dim_components[component_id]` → `fact_downtime_events[root_cause_component_id]` | "How much downtime did this component **CAUSE** as a cascade trigger?" |
| `dim_components[component_id]` → `dim_production_counts[defect_source_component_id]` | "How many defects **originated FROM** this component upstream?" |

Power BI allows only **one active relationship** between any two tables. The active joins already use the standard `component_id → component_id` path ("who experienced it"). `USERELATIONSHIP()` activates the inactive path **only inside the specific CALCULATE() call**, routing the filter context through the specified inactive relationship without affecting any other measure or visual on the page.

```dax
-- ============================================================
-- MEASURE GROUP D: Criticality
-- Sources: dim_criticality (bridged via dim_components),
--          fact_downtime_events (USERELATIONSHIP for root-cause),
--          dim_production_counts (USERELATIONSHIP for defect source)
-- ============================================================


-- D-01: CCI Score
-- Composite Criticality Index: 0.40*SRS_norm + 0.35*Unreliability_norm + 0.25*TBR_norm
-- SELECTEDVALUE() returns the single CCI value when exactly ONE component is in filter context.
-- Returns BLANK() when multiple components are selected - correct; CCI is a rank, not an aggregate.
-- This prevents a nonsensical "average CCI" from appearing in a multi-component card visual.
[CCI Score] =
SELECTEDVALUE( dim_criticality[composite_criticality], BLANK() )


-- D-01b: Fleet Avg CCI Score
-- Fleet-average version for Panel B Radar Chart second polygon.
-- Removes the drill-through component filter to evaluate across all components.
[Fleet Avg CCI Score] =
CALCULATE(
    AVERAGE( dim_criticality[composite_criticality] ),
    REMOVEFILTERS( dim_components )
)


-- D-01c: CCI Score Fleet View
-- Removes the drill-through component filter so that all components 
-- can be rendered in Panel F (Criticality Ranking) during drill-through,
-- when used in combination with 'Show items with no data' on the Y-axis.
[CCI Score Fleet View] =
CALCULATE(
    [CCI Score],
    REMOVEFILTERS( dim_components )
)


-- D-02: CCI Rank
-- 1 = most critical component (Coupling expected from Phase 2.2 analysis).
[CCI Rank] =
SELECTEDVALUE( dim_criticality[cci_rank], BLANK() )


-- D-03: Structural Risk Score
-- Graph centrality-derived risk score from graph_centrality.py (Day 18).
-- Reflects cascade reach x failure impact position in the pipeline DAG.
[SRS Score] =
SELECTEDVALUE( dim_criticality[structural_risk_score], BLANK() )


-- D-03b: Fleet Avg SRS Score
-- Fleet-average version for Panel B Radar Chart second polygon.
[Fleet Avg SRS Score] =
CALCULATE(
    AVERAGE( dim_criticality[structural_risk_score] ),
    REMOVEFILTERS( dim_components )
)


-- D-04: Weibull Unreliability at 2920 hours
-- Unreliability = 1 - R(t=2920h) where 2920h = one-third of annual operating hours.
-- Higher value = more likely to have failed by this time horizon.
[Weibull Unreliability] =
SELECTEDVALUE( dim_criticality[weibull_unreliability], BLANK() )


-- D-04b: Fleet Avg Weibull Unreliability
-- Fleet-average version for Panel B Radar Chart second polygon.
[Fleet Avg Weibull Unreliability] =
CALCULATE(
    AVERAGE( dim_criticality[weibull_unreliability] ),
    REMOVEFILTERS( dim_components )
)


-- D-05: Threshold Breach Rate
-- TBR = fraction of sensor readings that breached ISO alarm threshold (from Day 17 EDA).
[Threshold Breach Rate] =
SELECTEDVALUE( dim_criticality[threshold_breach_rate], BLANK() )


-- D-05b: Fleet Avg TBR
-- Fleet-average version for Panel B Radar Chart second polygon.
[Fleet Avg TBR] =
CALCULATE(
    AVERAGE( dim_criticality[threshold_breach_rate] ),
    REMOVEFILTERS( dim_components )
)


-- D-06: CCI Tier Label
-- Returns the cci_tier Power Query derived column value for the selected component.
[CCI Tier] =
SELECTEDVALUE( dim_criticality[cci_tier], BLANK() )


-- D-06b: CCI Tier Worst
-- Evaluates the worst-case (maximum) CCI Score across all components in context
-- and assigns the corresponding risk tier label.
[CCI Tier Worst] = 
VAR WorstScore = 
    MAXX(
        ALLSELECTED(dim_components),
        [CCI Score]
    )
RETURN
    SWITCH(
        TRUE(),
        WorstScore >= 0.75, "Critical",
        WorstScore >= 0.50, "High",
        WorstScore >= 0.25, "Moderate",
        "Low"
    )


-- D-06c: CCI Tier Color
-- Hex string for Panel B conditional formatting.
[CCI Tier Color] =
SWITCH(
    [CCI Tier],
    "Critical", "#C62828",
    "High",     "#F57F17",
    "Moderate", "#FFC107",
    "Low",      "#2E7D32",
    "#FFFFFF"
)


-- D-06d: CCI Tier Worst Color
-- Companion color measure for KPI Card 6 background conditional formatting.
[CCI Tier Worst Color] =
SWITCH(
    [CCI Tier Worst],
    "Critical", "#C6282855",
    "High",     "#F57F1755",
    "Moderate", "#FFC10755",
    "Low",      "#2E7D3255",
    "#FFFFFF00"
)

-- D-07: Root Cause Downtime Minutes — USERELATIONSHIP() on root_cause_component_id
-- ===========================================================================
-- ACTIVE relationship: dim_components[component_id] -> fact_downtime_events[component_id]
-- Answers: "How much downtime did this component EXPERIENCE?"
--
-- INACTIVE relationship (activated here):
-- dim_components[component_id] -> fact_downtime_events[root_cause_component_id]
-- Answers: "How much total system downtime did this component CAUSE as cascade trigger?"
--
-- When dim_components filter = Bearing (component_id = 1):
-- The USERELATIONSHIP() routes the filter through root_cause_component_id = 1.
-- This captures ALL downtime events whose root cause was Bearing - including cascade
-- downtime rows tagged on Shaft (id=2), Motor Housing (3), Coupling (4), Gearbox (5).
-- The standard component_id = 1 path (active) is suppressed for this measure only.
-- ===========================================================================
[Root Cause Downtime Min] =
CALCULATE(
    SUM( fact_downtime_events[duration_min] ),
    USERELATIONSHIP(
        dim_components[component_id],
        fact_downtime_events[root_cause_component_id]
    ),
    CROSSFILTER(
        dim_components[component_id],
        dim_production_shifts[component_id],
        None
    )
)


-- D-07b: Cumulative Root Cause DT %
-- Companion measure for Panel A Pareto chart (Root Cause Downtime by Component)
[Cumulative Root Cause DT %] =
VAR _currentLabel = MAX(dim_components[pipeline_label])
VAR _currentDT = [Root Cause Downtime Min]
VAR _totalDT = CALCULATE([Root Cause Downtime Min], ALL(dim_components))
VAR _cumulativeDT =
    CALCULATE(
        [Root Cause Downtime Min],
        FILTER(
            ALL(dim_components),
            [Root Cause Downtime Min] > _currentDT ||
            ([Root Cause Downtime Min] = _currentDT && dim_components[pipeline_label] <= _currentLabel)
        )
    )
RETURN
    IF(
        ISINSCOPE( dim_components[pipeline_label] ),
        DIVIDE( _cumulativeDT, _totalDT, 0 ),
        1.0
    )


-- D-08: Upstream Defect Units — USERELATIONSHIP() on defect_source_component_id
-- ===========================================================================
-- ACTIVE filter path: dim_components[component_id] -> dim_production_shifts -> dim_production_counts
-- Answers: "How many defects were recorded AT this component's inspection point?"
--
-- INACTIVE relationship (activated here):
-- dim_components[component_id] -> dim_production_counts[defect_source_component_id]
-- Answers: "How many defects originated FROM this component upstream?"
--
-- Defects may be detected at the Gearbox inspection point but originate from Bearing
-- surface damage propagated through the pipeline. The active relationship assigns those
-- defects to Gearbox. This measure re-attributes them to Bearing (the upstream source)
-- for root-cause quality analysis.
--
-- NULL rows: defect_source_component_id = NULL means self-caused defect (no upstream origin).
-- USERELATIONSHIP() returns BLANK() for those rows - correct; we only want upstream defects.
-- ===========================================================================
[Upstream Defect Units] =
CALCULATE(
    SUM( dim_production_counts[defective_units] ),
    USERELATIONSHIP(
        dim_components[component_id],
        dim_production_counts[defect_source_component_id]
    ),
    CROSSFILTER(
        dim_components[component_id],
        dim_production_shifts[component_id],
        None
    )
)


-- D-08b: Cumulative Upstream Defect % 
-- Companion measure for Panel C Pareto chart (Upstream Defects by Component)
[Cumulative Upstream Defect %] =
VAR _currentLabel = MAX(dim_components[pipeline_label])
VAR _currentDefects = [Upstream Defect Units]
VAR _totalDefects = CALCULATE([Upstream Defect Units], ALL(dim_components))
VAR _cumulativeDefects =
    CALCULATE(
        [Upstream Defect Units],
        FILTER(
            ALL(dim_components),
            [Upstream Defect Units] > _currentDefects ||
            ([Upstream Defect Units] = _currentDefects && dim_components[pipeline_label] <= _currentLabel)
        )
    )
RETURN
    IF(
        ISINSCOPE( dim_components[pipeline_label] ),
        DIVIDE(_cumulativeDefects, _totalDefects, 0),
        1.0
    )


-- D-09: Root Cause vs Experienced Downtime Ratio
-- Ratio > 1.0 means a component causes more total system downtime than it directly experiences.
-- Bearing is expected to have the highest ratio due to its position-1 cascade reach
-- (a failure cascades through all 4 downstream components).
[Root Cause Downtime Ratio] =
VAR RootCauseMin    = [Root Cause Downtime Min]
VAR ExperiencedMin  =
    CALCULATE(
        SUM( fact_downtime_events[duration_min] ),
        fact_downtime_events[downtime_category] <> "planned_maintenance"
    )
RETURN
    DIVIDE( RootCauseMin, ExperiencedMin, BLANK() )


-- D-10: CCI-Weighted Health Score
-- Weights the current-context average health score by the component's CCI score.
-- Higher-criticality components' health degradation receives more weight.
-- Used in Fleet Overview composite health KPI card.
-- Returns BLANK() when CCI Score is BLANK() (multi-component context - by design).
[CCI Weighted Health Score] =
VAR HS  = [Avg Health Score]
VAR CCI = [CCI Score]
RETURN
    IF(
        ISBLANK( CCI ),
        BLANK(),
        HS * CCI
    )


-- D-11: Radar Component Value
-- Routes the selected radar axis metric to the corresponding component-level DAX measure.
-- Used as the "Values" (Polygon 1) in the Page 2 Panel B Radar Chart.
[Radar Component Value] =
SWITCH(
    SELECTEDVALUE('_Radar_Metrics'[Metric Name]),
    "CCI",          [CCI Score],
    "SRS",          [SRS Score],
    "TBR",          [Threshold Breach Rate],
    "Weibull F(t)", [Weibull Unreliability],
    BLANK()
)


-- D-12: Radar Fleet Avg Value
-- Routes the selected radar axis metric to the corresponding fleet-average DAX measure.
-- Used as the "Values" (Polygon 2) in the Page 2 Panel B Radar Chart.
[Radar Fleet Avg Value] =
SWITCH(
    SELECTEDVALUE('_Radar_Metrics'[Metric Name]),
    "CCI",          [Fleet Avg CCI Score],
    "SRS",          [Fleet Avg SRS Score],
    "TBR",          [Fleet Avg TBR],
    "Weibull F(t)", [Fleet Avg Weibull Unreliability],
    BLANK()
)


-- ============================================================
-- DAX MEASURE GROUP D (CONTINUED) -- Day 28 Additions
-- ============================================================

-- D-13: Criticality Rank
-- RANKX over all components. The entire RANKX function is wrapped in CALCULATE
-- with REMOVEFILTERS to evaluate the rank while ignoring any external page-level 
-- drill-through filters on component_id. This allows all 5 components 
-- to be ranked accurately even when only 1 is selected via drill-through.

-- Home table: _Measures_D_Criticality
[Criticality Rank] =
CALCULATE(
    RANKX(
        ALL( dim_components ),
        [CCI Score],
        ,
        DESC,
        DENSE
    ),
    REMOVEFILTERS( dim_components[component_id] )
)

-- D-14: Panel F Tooltip / Color Fleet View Measures
-- These wrappers are required for the Criticality Ranking visual (Panel F) tooltips
-- and conditional formatting. They remove the page-level drill-through filter on
-- component_id so that the visual's Y-axis (component_name) can render the correct
-- values for all 5 components, even when only 1 is selected via drill-through.
-- Home table: _Measures_D_Criticality
[SRS Score Fleet View] = CALCULATE( [SRS Score], REMOVEFILTERS( dim_components[component_id] ) )
[Weibull Unreliability Fleet View] = CALCULATE( [Weibull Unreliability], REMOVEFILTERS( dim_components[component_id] ) )
[Threshold Breach Rate Fleet View] = CALCULATE( [Threshold Breach Rate], REMOVEFILTERS( dim_components[component_id] ) )
[CCI Tier Fleet View] = CALCULATE( [CCI Tier], REMOVEFILTERS( dim_components[component_id] ) )
[CCI Tier Color Fleet View] = CALCULATE( [CCI Tier Color], REMOVEFILTERS( dim_components[component_id] ) )


-- D-15: Criticality Bar Colour
-- Alias of D-06c, row-level grain, used for Panel B Risk Prioritization Matrix bar CF.
[Criticality Bar Colour] = [CCI Tier Color]


-- D-16: Criticality Ranking Title (Dynamic -- ISFILTERED)
-- Context-aware title for the Criticality Ranking bar chart (Panel F, Page 2).
-- ISFILTERED(dim_components[component_id]) = TRUE when drill-through from
-- Page 1 Panel B has pushed a component_id filter into the evaluation context.
-- Note: In our single-direction Star Schema, dim_calendar filters fact tables 
-- but DOES NOT cross-filter dim_components. Therefore, date slicers will never 
-- filter out components, and SELECTEDVALUE safely resolves without needing 
-- REMOVEFILTERS(dim_calendar).
-- When no drill-through filter is active the generic title is returned.
-- Home table: _Measures_D_Criticality
[Criticality Ranking Title] =
IF(
    ISFILTERED( dim_components[component_id] ),
    "Criticality Ranking - " &
        SELECTEDVALUE(
            dim_components[component_name], "Selected Component"
        ) &
        " vs Fleet",
    "Criticality Ranking - All Components"
)


## 6. Relationship Reference

All 12 relationships in the Power BI model. Relationships 10 and 11 appear as **dashed lines** in Model View.

| # | From Table | From Column | To Table | To Column | Cardinality | Cross-Filter | Status |
|---|---|---|---|---|---|---|---|
| 1 | `dim_components` | `component_id` | `fact_sensor_readings` | `component_id` | 1:Many | Single | **Active** |
| 2 | `dim_sensors` | `sensor_id` | `fact_sensor_readings` | `sensor_id` | 1:Many | Single | **Active** |
| 3 | `dim_components` | `component_id` | `fact_downtime_events` | `component_id` | 1:Many | Single | **Inactive** |
| 4 | `dim_production_shifts` | `shift_id` | `fact_downtime_events` | `shift_id` | 1:Many | Single | **Active** |
| 5 | `dim_components` | `component_id` | `dim_production_shifts` | `component_id` | 1:Many | Single | **Active** |
| 6 | `dim_production_shifts` | `shift_id` | `dim_production_counts` | `shift_id` | **1:1** | **Both** | **Active** |
| 7 | `dim_components` | `component_id` | `dim_production_counts` | `component_id` | 1:Many | Single | **DROPPED** (redundant) |
| 8 | `dim_components` | `component_id` | `dim_failure_log` | `component_id` | 1:Many | Single | **Active** |
| 9 | `dim_criticality` | `component` | `dim_components` | `component_name` | **1:1** | **Both** | **Active** |
| 10 | `dim_components` | `component_id` | `fact_downtime_events` | `root_cause_component_id` | 1:Many | Single | **Inactive** — D-07 |
| 11 | `dim_components` | `component_id` | `dim_production_counts` | `defect_source_component_id` | 1:Many | Single | **Inactive** — D-08 |
| 12 | `dim_calendar` | `date` | `fact_sensor_readings` | `date_key` | 1:Many | Single | **Active** |
| 13 | `dim_calendar` | `date` | `dim_production_shifts` | `shift_date` | 1:Many | Single | **Active** |
| 14 | `dim_calendar` | `date` | `dim_failure_log` | `failure_date_key` | 1:Many | Single | **Active** |

---

## 7. USERELATIONSHIP() Logic Explained

### Step-by-Step Evaluation: `[Root Cause Downtime Min]` for Bearing

Suppose a visual has `dim_components[component_name]` on the axis, and the current row is **Bearing**.

**Step 1:** Power BI establishes filter context: `dim_components[component_id] = 1`.

**Step 2:** The measure body is entered: `CALCULATE( SUM(duration_min), USERELATIONSHIP(...) )`.

**Step 3:** `USERELATIONSHIP(dim_components[component_id], fact_downtime_events[root_cause_component_id])` is a **filter modifier**, not a table function. It does not add rows. It instructs CALCULATE() to propagate the current dimension filter (`component_id = 1`) through the **inactive** path (via `root_cause_component_id`) instead of the **active** path (via `component_id`).

**Step 4:** `fact_downtime_events` is now filtered to rows where `root_cause_component_id = 1` — i.e., all downtime events caused by Bearing, regardless of which component experienced them.

**Step 5:** `SUM(duration_min)` is evaluated over this filtered set, returning the total minutes of system downtime attributable to Bearing failures.

**Step 6:** The active `component_id → component_id` path is **fully suppressed** for this measure's execution. No double-counting occurs.

### Expected Pattern: Root Cause Downtime by Component

| Component | Expected [Root Cause Downtime Min] | Reason |
|---|---|---|
| Bearing | **Highest** | Position 1: cascades through all 4 downstream components |
| Shaft | High | Position 2: cascades through 3 downstream components |
| Motor Housing | Medium | Position 3: cascades through 2 downstream |
| Coupling | Low | Position 4: cascades through 1 downstream (Gearbox only) |
| Gearbox | Lowest | Position 5: terminal node, no downstream cascade |

This pattern directly mirrors the pipeline topology `[Bearing→Shaft→Motor Housing→Coupling→Gearbox]` and is a strong viva talking point about cascade failure modelling.

---

## 8. Validation Checklist

### Power Query Validation

- [ ] `fact_sensor_readings`: `health_score` column range is 0–100 (no negatives, no > 100)
- [ ] `fact_sensor_readings`: `date_key` column type is `Date` (not `DateTime`)
- [ ] `fact_sensor_readings`: `iso_zone` is null for non-vibration rows
- [ ] `dim_components`: `pipeline_label` values are "Pos 1: Bearing" through "Pos 5: Gearbox"
- [ ] `dim_components`: `component_name` Sort Column = `position` (set in Model View)
- [ ] `dim_production_shifts`: `shift_month_name` Sort Column = `shift_month` (set in Model View)
- [ ] `dim_criticality`: 5 rows loaded; `cci_rank` values are 1–5 with no duplicates
- [ ] `dim_criticality`: `component_id` lookup is 1–5 with no nulls

### Relationship Validation

- [ ] All 9 active relationships show solid lines in Model View (no red / broken indicators)
- [ ] Relationship 6 (`shifts ↔ counts`) shows 1:1 bidirectional arrow
- [ ] Relationship 9 (`criticality ↔ components`) shows 1:1 bidirectional arrow
- [ ] Relationships 10 and 11 appear as **dashed lines** (inactive) in Model View

### DAX Measure Validation

Run each in a blank Table visual:

| Measure | Expected Result | Visual Axis |
|---|---|---|
| `[Avg Health Score]` | 30–95% range per component | `dim_components[component_name]` |
| `[OEE Availability]` | 0.70–1.00 range | `dim_production_shifts[shift_date]` |
| `[OEE Composite]` | Always <= `[OEE Availability]` | `dim_production_shifts[shift_date]` |
| `[OEE Status]` | All 4 statuses appear; no nulls | `dim_production_shifts[shift_date]` |
| `[MTBF Hours]` | Positive; Bearing expected lowest | `dim_components[component_name]` |
| `[Empirical Availability]` | 0.80–0.99 range | `dim_components[component_name]` |
| `[CCI Score]` | 0.0–1.0; BLANK() with multi-component | Single component slicer |
| `[Root Cause Downtime Min]` | Bearing > Shaft > MH > Coupling > Gearbox | `dim_components[component_name]` |
| `[Upstream Defect Units]` | Non-zero for upstream components | `dim_components[component_name]` |
| `[System OEE Composite]` | < minimum individual `[OEE Composite]` | `dim_production_shifts[shift_date]` |

### Cross-Validation Against SQL

1. Run `sql/queries/oee_composite.sql` on `data/manufacturing.db`
2. Export result and import into Power BI as a temporary verification table
3. Place `[OEE Availability]` and the SQL `availability` column side-by-side, filtered to the same component + shift date
4. Values should match to 4+ decimal places. Any discrepancy indicates a CALCULATE() filter gap or a downtime category exclusion mismatch

---

*End of `docs/dax_and_m_scripts.md` — Day 22 DAX & Power Query deliverable.*
*Next: Day 23 — Fleet Overview page layout and component drill-through pages.*


## ============================================================
## DAX MEASURE GROUP E -- Alert & Risk Summary (Page 3)
## Day 29 -- August 14, 2026
## Home table for all E measures: _Measures_E_Alerts
## Star schema integration: fact_sensor_readings[is_anomaly],
##   fact_sensor_readings[iso_zone], dim_components,
##   dim_criticality (via R-09 1:1 link)
## Drill-through key: dim_components[component_id]
## ============================================================


-- E-01: Total Active Alerts
-- Fleet-wide count of sensor readings that breach the ISO alarm or danger
-- threshold. Uses the pre-computed is_anomaly flag set by etl.py at load
-- time (Day 9), ensuring DAX threshold logic exactly mirrors ETL logic.
-- Returns BLANK() when fact_sensor_readings has no rows in context.
-- Home table: _Measures_E_Alerts
[Total Active Alerts] =
CALCULATE(
    COUNTROWS( fact_sensor_readings ),
    fact_sensor_readings[is_anomaly] = 1
) + 0


-- E-02: Active Danger Zone Alerts
-- Count of sensor readings in ISO Zone D (value > iso_danger_threshold).
-- Subset of E-01. Used as KPI Card 2 and as bubble-size input in Panel B.
-- iso_zone column is NULL for non-vibration sensors (RPM has no ISO zone);
-- those rows are excluded automatically by the filter.
-- Home table: _Measures_E_Alerts
[Active Danger Zone Alerts] =
CALCULATE(
    COUNTROWS( fact_sensor_readings ),
    fact_sensor_readings[iso_zone] = "D - Danger"
) + 0


-- E-03: Alarm Zone Count
-- Count of sensor readings in ISO Zone C (alarm threshold <= value < danger).
-- Complements E-02. Together E-02 + E-03 = E-01 for vibration sensors.
-- For non-vibration sensors (temperature, oil_debris, load), is_anomaly=1
-- rows appear in E-01 but NOT in E-02 or E-03 (iso_zone is NULL for them).
-- This is correct and documented: E-01 is the primary fleet alert KPI.
-- Home table: _Measures_E_Alerts
[Alarm Zone Count] =
CALCULATE(
    COUNTROWS( fact_sensor_readings ),
    fact_sensor_readings[iso_zone] = "C - Alarm"
) + 0


-- E-04: Most Alerting Component
-- Returns the component_name of the component with the highest [Total Active Alerts]
-- count. Uses REMOVEFILTERS on component_id to evaluate across all components
-- even when a drill-through or slicer has filtered to a single component.
-- The TOPN+MAXX pattern returns the name of the top-1 component by alert count.
-- Returns BLANK() if no alerts exist (all E-01 = 0).
-- Home table: _Measures_E_Alerts
[Most Alerting Component] =
VAR _AlertTable =
    CALCULATETABLE(
        ADDCOLUMNS(
            VALUES( dim_components[component_name] ),
            "@Alerts", [Total Active Alerts]
        ),
        REMOVEFILTERS( dim_components )
    )
VAR _MaxAlerts =
    MAXX( _AlertTable, [@Alerts] )
VAR _TopComponent =
    MAXX(
        FILTER( _AlertTable, [@Alerts] = _MaxAlerts ),
        [component_name]
    )
RETURN
    IF( _MaxAlerts = 0 || ISBLANK( _MaxAlerts ), BLANK(), _TopComponent )


-- E-05: Critical Risk Component Count
-- Count of components where CCI >= 0.50 (High tier and above, mapping to Critical Priority quadrant) AND
-- current Avg Health Score < 75 (degraded health).
-- Both conditions must be true simultaneously -- a critically positioned
-- component that is still healthy is a monitoring case, not an action case.
-- Used as KPI Card 5 "Critical Risk Components".
-- Home table: _Measures_E_Alerts
[Critical Risk Component Count] =
VAR _CompTable =
    ADDCOLUMNS(
        VALUES( dim_components[component_id] ),
        "@CCI",    CALCULATE( [CCI Score] ),
        "@Health", CALCULATE( [Avg Health Score] )
    )
RETURN
    COUNTROWS(
        FILTER(
            _CompTable,
            NOT ISBLANK( [@CCI] )
                && NOT ISBLANK( [@Health] )
                && [@CCI] >= 0.50
                && [@Health] < 75
        )
    ) + 0


-- E-06: Alert Count by Sensor Type
-- Returns E-01 [Total Active Alerts] in the current sensor_type filter
-- context. When placed in a stacked bar chart with sensor_type as the
-- legend/series field, each series slice evaluates this measure within
-- its own sensor_type filter, producing the stacked count correctly.
-- Note: This measure is structurally identical to E-01. The separation
-- exists for semantic clarity (E-06 is documented as the Panel A series
-- measure; E-01 is the fleet-total KPI). Both evaluate the same COUNTROWS.
-- Home table: _Measures_E_Alerts
[Alert Count by Sensor Type] =
CALCULATE(
    COUNTROWS( fact_sensor_readings ),
    fact_sensor_readings[is_anomaly] = 1
) + 0


-- E-07: Violation Rate
-- Threshold breach rate: distinct operating days with an anomaly divided by the number
-- of distinct operating days in the current filter context.
-- Formula: DISTINCTCOUNT(date_key) where is_anomaly=1 / DISTINCTCOUNT(date_key)
-- Normalizes by operating days to produce a comparable rate across
-- components with different sensor counts (Gearbox has 3 sensors, others 2).
-- Returns BLANK() when no date context (no rows in fact_sensor_readings).
-- Used in Panel C Matrix visual as the cell value for heat-map colouring.
-- Home table: _Measures_E_Alerts
[Violation Rate] =
VAR _AlertDays =
    CALCULATE(
        DISTINCTCOUNT( fact_sensor_readings[date_key] ),
        fact_sensor_readings[is_anomaly] = 1
    )
VAR _OperatingDays =
    CALCULATE(
        DISTINCTCOUNT( fact_sensor_readings[date_key] )
    )
RETURN
    DIVIDE( _AlertDays, _OperatingDays, BLANK() )


-- E-08: Violation Rate Colour
-- Returns a hex colour string for Panel C (Threshold Violation Matrix)
-- cell background conditional formatting. Applied via Format > Cell elements
-- > Background colour > Field value > [Violation Rate Colour].
-- Colour bands match the locked Day 29 threshold design:
--   0.00       : #0D1117 (background -- invisible, no violation)
--   0.01-0.10  : #1E2D2F (dark teal -- very low)
--   0.11-0.30  : #F57F17 (amber -- moderate, CBM review recommended)
--   0.31-0.60  : #E65100 (orange -- high, escalate to condition monitoring)
--   above 0.60 : #B00020 (red -- severe, immediate inspection required)
-- Home table: _Measures_E_Alerts
[Violation Rate Colour] =
VAR _Rate = [Violation Rate]
RETURN
SWITCH(
    TRUE(),
    ISBLANK( _Rate ) || _Rate = 0,         "#0D1117",
    _Rate <= 0.10,                          "#1E2D2F",
    _Rate <= 0.30,                          "#F57F17",
    _Rate <= 0.60,                          "#E65100",
    "#B00020"
)


-- E-09: Page 3 Status Banner
-- Generates a plain-language risk statement for Panel E (full-width status bar).
-- Behaviour depends on filter context:
--   Single component active (ISFILTERED = TRUE via drill-through or slicer):
--     "[ComponentName] -- [Tier] | Health: [HS] | Danger Alerts: [N]"
--   Fleet view (no component filter):
--     "Highest Risk: [MostAlertingComp] -- [CCI Tier] | [N] Danger Zone Alerts Active"
-- SELECTEDVALUE default "Fleet" prevents BLANK() display when multi-component context.
-- Home table: _Measures_E_Alerts
[Page 3 Status Banner] =
VAR _IsSingleComp = HASONEVALUE( dim_components[component_name] )
VAR _CompName = SELECTEDVALUE( dim_components[component_name], "Fleet" )
VAR _Tier = SELECTEDVALUE( dim_criticality[cci_tier], "" )
VAR _Health = ROUND( [Avg Health Score], 1 )
VAR _Danger = [Active Danger Zone Alerts]
VAR _MostAlert = [Most Alerting Component]
VAR _MostAlertTier = 
    CALCULATE(
        SELECTEDVALUE( dim_criticality[cci_tier], "" ),
        REMOVEFILTERS( dim_components ),
        dim_components[component_name] = _MostAlert
    )
VAR _MostAlertDanger =
    CALCULATE(
        [Active Danger Zone Alerts],
        REMOVEFILTERS( dim_components ),
        dim_components[component_name] = _MostAlert
    )
VAR _TotalAlerts = [Total Active Alerts]
RETURN
IF(
    _IsSingleComp,
    _CompName & " -- " & _Tier & " | Health: " & _Health & " | Danger Alerts: " & _Danger,
    IF(
        _TotalAlerts = 0,
        "All Systems Normal | 0 Danger Zone Alerts Active",
        "Highest Risk: " & _MostAlert & " -- " & _MostAlertTier & " | " & _MostAlertDanger & " Danger Zone Alerts Active"
    )
)


-- E-10: Status Banner Colour
-- Returns background hex colour for Panel E (Dynamic Status Bar) card.
-- Priority: Danger active > Alarm active > Zero alerts.
-- The #AA prefix (55 hex = ~33% alpha) matches the card alpha convention
-- used in KPI Cards 2/3 for consistent visual language.
-- Home table: _Measures_E_Alerts
[Status Banner Colour] =
VAR _Danger = [Active Danger Zone Alerts]
VAR _Alarm = [Alarm Zone Count]
VAR _Total = [Total Active Alerts]
RETURN
SWITCH(
    TRUE(),
    NOT ISBLANK( _Danger ) && _Danger > 0, "#B00020",
    NOT ISBLANK( _Alarm )  && _Alarm  > 0, "#F57F17",
    NOT ISBLANK( _Total )  && _Total  > 0, "#F57F17",
    "#00695C"
)


-- ============================================================
-- END OF DAX MEASURE GROUP E
-- Running measure total after Day 29: 78
--   (68 through Day 28 + 10 new E-01 through E-10)
-- ============================================================
