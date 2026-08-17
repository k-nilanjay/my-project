# Day 25 Build Log -- Page 1 Fleet Overview (Power BI Desktop)

**Date:** 2026-08-08  
**Phase:** 2.3 Power BI Build -- Page 1  
**Status:** Page 1 locked in

---

## 1. Canvas & Theme Setup

### 1.1 Canvas Configuration

Open Power BI Desktop. Navigate to:

```
File > Page Setup
  Width:  1280
  Height: 720
  Units:  Pixels
```

Apply to Page 1 only. Repeat for Pages 2 and 3 when those pages are created.  
Background color `#F5F5F5` is applied automatically by the theme JSON; no manual canvas background step required.

### 1.2 JSON Theme Import

Navigate to:

```
View > Themes > Browse for themes
  Select: powerbi_theme.json  (root directory of project)
```

After import, Power BI Desktop confirms with a toast notification: "Theme applied."

**What the theme applies automatically:**
- `dataColors` array: 5-component series palette (Bearing `#1565C0`, Shaft `#6A1B9A`, Motor Housing `#00695C`, Coupling `#E65100`, Gearbox `#37474F`)
- `textClasses`: Segoe UI font hierarchy (callout 40pt bold to smallLabel 9pt)
- `visualStyles`: Default format settings for `card`, `lineChart`, `clusteredBarChart`, `waterfallChart`, `matrix`, `slicer` visual types
- `good/neutral/bad`: `#2E7D32` / `#F57F17` / `#C62828` for native KPI indicator color semantics

**What the theme does NOT apply (must be set manually):**
- Analytics pane reference lines (health score thresholds at 75 and 65)
- Conditional formatting rules for KPI card backgrounds
- Slicer sync settings (View > Sync Slicers)
- Drill-through field well assignments

---

## 2. Data Model Relationship Construction

### 2.1 Load Tables via Power Query M

Open Power Query Editor (Transform Data). For each of the 6 source tables, paste the corresponding M query from `docs/dax_and_m_scripts.md` (Section 1):

| Query Name | Source File | Key Columns |
|---|---|---|
| `fact_sensor_readings` | data/processed/sensor_readings_export.csv | `reading_id`, `component_id` (FK), `date_key` (FK) |
| `fact_downtime_events` | data/processed/downtime_events_export.csv | `downtime_id`, `component_id` (FK), `root_cause_component_id` (FK), `shift_id` (FK) |
| `dim_components` | data/processed/components_export.csv | `component_id` (PK), `component_name`, `pipeline_label`, `position` |
| `dim_calendar` | data/processed/ (generated) | `date` (PK), `year`, `month`, `month_name` |
| `dim_production_shifts` | data/processed/production_shifts_export.csv | `shift_id` (PK), `shift_period`, `shift_month`, `shift_month_name` |
| `dim_failure_log` | data/processed/failure_log_export.csv | `failure_id` (PK), `component_id` (FK), `failure_date_key` (FK), `failure_mode` |
| `dim_criticality` | data/processed/criticality_scores.csv | `component` (PK), `composite_criticality`, `cci_rank` |
| `dim_production_counts` | data/processed/production_counts_export.csv | `count_id` (PK), `shift_id` (FK), `good_units`, `total_units` |
| `dim_sensors` | data/processed/sensors_export.csv | `sensor_id` (PK), `component_id` (FK), `sensor_type` |

Close and Apply after all 9 queries are loaded.

### 2.2 Relationship Definitions

Navigate to Model view. Build all 13 relationships using Manage Relationships > New. Cardinality is Many-to-One (*:1) for all FK to PK joins unless noted.

#### Active Relationships (10 solid lines in Model view)

| # | From Table | From Column | To Table | To Column | Cross-filter |
|---|---|---|---|---|---|
| R-01 | `fact_sensor_readings` | `component_id` | `dim_components` | `component_id` | Single |
| R-02 | `fact_sensor_readings` | `date_key` | `dim_calendar` | `date` | Single |
| R-03 | `fact_downtime_events` | `shift_id` | `dim_production_shifts` | `shift_id` | Single |
| R-04 | `dim_production_shifts` | `component_id` | `dim_components` | `component_id` | Single |
| R-05 | `dim_production_shifts` | `shift_date` | `dim_calendar` | `date` | Single |
| R-06 | `dim_failure_log` | `component_id` | `dim_components` | `component_id` | Single |
| R-07 | `dim_failure_log` | `failure_date_key` | `dim_calendar` | `date` | Single |
| R-08 | `fact_sensor_readings` | `sensor_id` | `dim_sensors` | `sensor_id` | Single |
| R-09 | `dim_criticality` | `component` | `dim_components` | `component_name` | Both |
| R-10 | `dim_production_counts` | `shift_id` | `dim_production_shifts` | `shift_id` | Both |

#### Inactive Relationships (3 dashed lines -- USERELATIONSHIP targets and ambiguous paths)

| # | From Table | From Column | To Table | To Column | Notes |
|---|---|---|---|---|---|
| R-11 | `fact_downtime_events` | `root_cause_component_id` | `dim_components` | `component_id` | Activated by D-07 via USERELATIONSHIP() |
| R-12 | `fact_downtime_events` | `component_id` | `dim_components` | `component_id` | Inactive to prevent ambiguous filter path with shifts |
| R-13 | `dim_production_counts` | `defect_source_component_id` | `dim_components` | `component_id` | Activated by D-08 via USERELATIONSHIP() |

**Verification:** In Model view, confirm 10 solid lines, 3 dashed lines, no yellow warning triangles. If ambiguous relationship warnings appear, ensure Cross-filter Direction is Single where specified.

### 2.3 Sort Column Assignments

In Data view (select column header > Column Tools > Sort by Column):

| Table | Column to Sort | Sort By Column | Purpose |
|---|---|---|---|
| `dim_components` | `component_name` | `position` | Series order: 1=Bearing, 2=Shaft, 3=Motor Housing, 4=Coupling, 5=Gearbox |
| `dim_production_shifts` | `shift_month_name` | `shift_month` | Chronological month axis order instead of alphabetical |

---

## 3. DAX Measure Entry

Create 4 home tables (Enter Data, 1-row stub tables):

- `_Measures_A (Health)`
- `_Measures_B (OEE)`
- `_Measures_C (MTBF)`
- `_Measures_D (Criticality)`

Enter all 47 DAX measures from `docs/dax_and_m_scripts.md` (Sections 2-5).

**Page 1 critical measures:**

| Measure ID | Name | Home Table | Used In |
|---|---|---|---|
| A-01 | `[Avg Health Score]` | _Measures_A | Panel A line chart (5 series via Legend) |
| A-02 | `[Min Health Score]` | _Measures_A | KPI Card 2 |
| A-07 | `[Alarm Breach Count]` | _Measures_A | KPI Card 5 component |
| A-08 | `[Danger Zone Count]` | _Measures_A | KPI Card 5 component |
| B-04 | `[OEE Availability]` | _Measures_B | KPI Card 2 |
| B-09 | `[Availability Loss PP]` | _Measures_B | Panel C waterfall step 1 |
| B-10 | `[Performance Loss PP]` | _Measures_B | Panel C waterfall step 2 |
| B-11 | `[Quality Loss PP]` | _Measures_B | Panel C waterfall step 3 |
| B-15 | `[System OEE Composite]` | _Measures_B | KPI Card 1 |
| B-19 | `[Dominant Loss Category]` | _Measures_B | Status Bar text card |
| C-02 | `[MTBF Hours]` | _Measures_C | KPI Card 3 |
| D-06 | `[CCI Tier]` | _Measures_D | Panel B bar conditional color |
| D-07 | `[Root Cause Downtime Min]` | _Measures_D | Status Bar mini Pareto |
| A-12 | `[Combined Alert Count]` | _Measures_A | KPI Card 5 |
| CCI Worst | `[CCI Tier Worst]` | _Measures_D | KPI Card 6 |

> **Note:** `[Combined Alert Count]` already exists as measure A-12 in `docs/dax_and_m_scripts.md` (updated in prior fix pass to equal `[Alarm Breach Count]`) — bind directly to the existing measure, do not recreate.

---

## 4. KPI Card Row (Zone 1 -- Y=0)

All 6 cards placed at Y=0 via Format > General > Position & Size:

| Card # | Measure | X | Y | Width | Height | Display Format |
|---|---|---|---|---|---|---|
| KPI Card 1 | B-15 `[System OEE Composite]` | 0 | 0 | 200 | 100 | Percentage, 1 decimal |
| KPI Card 2 | B-04 `[OEE Availability]` | 205 | 0 | 200 | 100 | Percentage, 1 decimal |
| KPI Card 3 | A-02 `[Min Health Score]` | 410 | 0 | 200 | 100 | None (0-100 integer) |
| KPI Card 4 | C-02 `[MTBF Hours]` | 615 | 0 | 200 | 100 | None, 1 decimal |
| KPI Card 5 | `[Combined Alert Count]` | 820 | 0 | 200 | 100 | Whole number |
| KPI Card 6 | `[CCI Tier Worst]` | 1025 | 0 | 255 | 100 | Text (no format) |

**Card format (theme default; verify):** Callout 32pt Segoe UI Bold, category label 11pt, rounded border 1px `#E0E0E0`, background `#FFFFFF`.

---

## 5. Slicer Row (Y=105)

| Slicer | Field | X | Y | Width | Height | Style |
|---|---|---|---|---|---|---|
| Date Range Slicer | `dim_calendar[date]` | 0 | 105 | 640 | 55 | Between (date range picker) |
| Component Slicer | `dim_components[component_name]` | 645 | 105 | 625 | 55 | List (multi-select, Select All enabled) |

**Slicer sync (View > Sync Slicers):**

| Slicer | P1 Sync | P1 Visible | P2 Sync | P2 Visible | P3 Sync | P3 Visible |
|---|---|---|---|---|---|---|
| Date Range | TRUE | TRUE | TRUE | TRUE | TRUE | TRUE |
| Component | TRUE | TRUE | TRUE | FALSE | FALSE | FALSE |

Critical: Component slicer -- P2 Sync=TRUE, Visible=FALSE. Enforces SELECTEDVALUE() single-component contract; preserves P1 filter state on drill-through return.

---

## 6. Panel A -- Line Chart Anchor (Zone 2, Left 60%)

**Visual type:** Line Chart  
**Position:** X=0, Y=165, Width=768, Height=290

### Field Bindings

| Field Well | Field | Notes |
|---|---|---|
| X-axis | `dim_calendar[date]` | Set to Date (not Date Hierarchy) for continuous axis |
| Y-axis | `A-01 [Avg Health Score]` | 0-100 scale |
| Legend | `dim_components[component_name]` | 5 series; auto-colored from theme dataColors |

### Format Settings

| Setting | Value |
|---|---|
| Y-axis minimum | 0 |
| Y-axis maximum | 100 |
| Line stroke width | 2px (theme default) |
| Markers | On, size 4 |
| Data labels | Off |
| Gridlines | `#F0F0F0` horizontal only |
| Title | "Component Health Trend" |

### Analytics Pane Reference Lines

Add via Analytics pane (not theme JSON):

| Line | Value | Color | Style | Label |
|---|---|---|---|---|
| Health Danger Threshold | 65 | `#C62828` | Dashed | "Danger: 65" |
| Health Alarm Threshold | 75 | `#F57F17` | Dashed | "Alarm: 75" |

Steps:
1. Select Panel A > Analytics pane
2. Constant Line > Add > Value=65, Color=`#C62828`, Dashed, Label="Danger: 65"
3. Constant Line > Add > Value=75, Color=`#F57F17`, Dashed, Label="Alarm: 75"

---

## 7. Panel B -- Horizontal Bar Chart (Zone 2, Right 40%)

**Visual type:** Clustered Bar Chart  
**Position:** X=773, Y=165, Width=502, Height=290

### Field Bindings

| Field Well | Field | Notes |
|---|---|---|
| Y-axis | `dim_components[component_name]` | Component labels (horizontal bars) |
| X-axis | `A-02 [Min Health Score]` | 0-100 value axis |
| Legend | (none) | Conditional formatting encodes status |

### Format Settings

| Setting | Value |
|---|---|
| X-axis min | 0 |
| X-axis max | 100 |
| Data labels | On, inside end |
| Sort | Ascending by `[Min Health Score]` (worst at top) |
| Title | "Health by Component" |
| Tooltip hint | Text box: "Right-click a bar to drill through to Component Health" |

### Conditional Formatting -- Bar Color by CCI Tier

Because `[CCI Tier]` is a text measure, Power BI's "Field value" setting requires a hex string. Use the companion color measure `[CCI Tier Color]` (already imported with the Group D measures in Section 3):

Format pane > Data colors > fx (Conditional formatting):
- Format by: Field value
- Based on field: `[CCI Tier Color]`

Drill-through trigger: Right-click any bar > Drill through > Page 2. Passes `component_id` via Page 2 field well.

---

## 8. Panel C -- Waterfall Chart (Zone 3, Left 60%)

> **Open Issue:** Panel C decomposes fleet-average OEE, which creates a semantic mismatch with KPI Card 1's bottleneck OEE. This is a known, unresolved design decision. Do not modify Panel C or its DAX further until the resolution is logged in `STATE_SUMMARY.md`.

**Visual type:** Waterfall Chart  
**Position:** X=0, Y=460, Width=768, Height=255

### Field Bindings & Implementation

| Field Well | Field |
|---|---|
| Category | `_Six_Big_Losses[Loss Type]` (from Section 1.10 of `dax_and_m_scripts.md`) |
| Y-axis | `B-11b [Selected Loss PP]` (SWITCH measure from Section 3 of `dax_and_m_scripts.md`) |

Waterfall configuration:
- Use the disconnected 4-row stub table (`_Six_Big_Losses`) as the Category. (Set the "Sort Order" column as the Sort by column for "Loss Type" in Data View so "Ideal OEE" appears first).
- The `[Selected Loss PP]` measure starts with a +100 baseline for "Ideal OEE", then uses negative values to step down through Availability, Performance, and Quality losses.
- The chart visually steps down through the 3 loss categories to the final OEE total.

Known approximation: Waterfall uses additive PP losses as approximation of multiplicative OEE (A x P x Q). Final bar may not exactly equal `B-15`. Do not attempt to reconcile -- this is industry standard.

### Format Settings

| Setting | Value |
|---|---|
| Increase bar color | `#2E7D32` (Acceptable Green) |
| Decrease bar color | `#C62828` (Danger Red) |
| Total bar color | `#1565C0` (Deep Blue) |
| Data labels | On, percentage format |
| Title | "Six Big Losses -- OEE Decomposition" |

### Reference Lines (Analytics Pane)

| Line | Value | Color | Label |
|---|---|---|---|
| OEE Target | 0.75 | `#F57F17` Alert Amber | "OEE Target: 75%" |
| World Class | 0.85 | `#00695C` World Class Teal | "World Class: 85%" |

---

## 9. Status Bar (Zone 3, Right 40%)

### 9.1 Mini D-07 Pareto (X=773, Y=460, W=380, H=255)

**Visual type:** Clustered Bar Chart (horizontal)

| Field Well | Field |
|---|---|
| Y-axis | `dim_components[pipeline_label]` |
| X-axis | `D-07 [Root Cause Downtime Min]` |

Sort: Descending by D-07. Shows causal component driving most system downtime. D-07 activates R-11 (inactive `root_cause_component_id` path) via USERELATIONSHIP(). Bars represent causal component, not victim component.

### 9.2 Dominant Loss Text Card (X=1158, Y=460, W=117, H=255)

**Visual type:** Card  
**Field binding:** `B-19 [Dominant Loss Category]`  
Returns text: "Loss 1: Breakdowns" / "Loss 2: Changeover" / "Loss 3: Minor Stops" / "Tied". Quick-read summary of largest OEE loss category.

---

## 10. Conditional Formatting Applications

### 10.1 KPI Card 1 -- System OEE (B-15)

| Condition | Background Color |
|---|---|
| `[System OEE Composite]` < 0.65 | `#C62828` Danger Red (20% alpha) |
| 0.65 <= value < 0.75 | `#F57F17` Alert Amber (20% alpha) |
| 0.75 <= value < 0.85 | `#2E7D32` Acceptable Green (20% alpha) |
| value >= 0.85 | `#00695C` World Class Teal (20% alpha) |

Format pane > Card > Background > fx > Rules-based.

### 10.2 KPI Card 3 -- Min Health Score (A-02)

| Condition | Background Color |
|---|---|
| `[Min Health Score]` < 65 | `#C62828` Danger Red (20% alpha) |
| 65 <= value < 75 | `#F57F17` Alert Amber (20% alpha) |
| value >= 75 | `#FFFFFF` (no highlight) |

### 10.3 KPI Card 6 -- CCI Tier Worst (Background)

Because `[CCI Tier Worst]` is a text measure, use the companion color measure `[CCI Tier Worst Color]` (using 8-character hex format #RRGGBBAA, already imported with the Group D measures in Section 3).
Bind to Card 6 Background > Conditional formatting > Format by: Field value > field: `[CCI Tier Worst Color]`.

### 10.4 KPI Card 5 -- Alerts (Font Color)

Bind to Card 5 Callout value > Conditional formatting > Font color > Format by: Field value > field: `[Alert Count Color]`.

---

## 11. Cross-Filter Edit Interactions

Configure via Format > Edit Interactions (select source visual first):

| Source | Panel A | Panel B | Panel C | KPI Cards (all 6) |
|---|---|---|---|---|
| Panel A click | -- | Filter | Filter | No interaction |
| Panel B click | Filter | -- | Filter | No interaction |
| Panel C click | Filter | Filter | -- | No interaction |
| Date Slicer | Filter | Filter | Filter | Filter |
| Component Slicer | Filter | Filter | Filter | Filter |

KPI cards set to No Interaction from all panel sources. Reason: KPI cards display fleet-level totals. Collapsing them to a single-component value on panel click creates a false impression that the KPI represents one component.

Steps:
1. Click Panel A > Format > Edit Interactions
2. Click the No Interaction icon on each KPI card
3. Repeat from Panel B and Panel C

---

## 12. Page 1 Lock-In Checklist

- [ ] Canvas = 1280 x 720 px
- [ ] Theme JSON applied (Bearing series = `#1565C0` in Format pane)
- [ ] All 13 relationships built (10 solid, 3 dashed), no yellow warning triangles
- [ ] Sort columns: `component_name` by `position`; `shift_month_name` by `shift_month`
- [ ] All 47 DAX measures entered in correct home tables
- [ ] `[Combined Alert Count]`, `[Alert Count Color]`, `[CCI Tier Color]`, and `[CCI Tier Worst Color]` companion measures added
- [ ] 6 KPI cards at Y=0 with correct measures and display formats
- [ ] KPI Card 1 OEE: 4-tier conditional background (Danger / Amber / Green / World Class)
- [ ] KPI Card 3 Min Health: 2-tier conditional background (Danger / Amber)
- [ ] KPI Card 5 Alerts: select Card 5 → Format (Fx) pane → Callout value → Conditional formatting → Font color → Format by "Field value" → bind to [Alert Count Color].
- [ ] KPI Card 6 CCI Tier: 4-tier conditional background via [CCI Tier Worst Color] companion measure.
- [ ] Date Range Slicer: X=0, Y=105, W=640, H=55
- [ ] Component Slicer: X=645, Y=105, W=625, H=55
- [ ] Slicer sync: Component -- P2 Sync=TRUE, Visible=FALSE
- [ ] Panel A Line Chart: X=0, Y=165, W=768, H=290; 2 reference lines (65 red dashed, 75 amber dashed)
- [ ] Panel B Horizontal Bar: X=773, Y=165, W=502, H=290; bar color conditional by `[CCI Tier Color]`
- [ ] Panel C Waterfall: X=0, Y=460, W=768, H=255; OEE reference lines (75% amber, 85% teal)
- [ ] Status Bar Pareto (D-07): X=773, Y=460, W=380, H=255; sorted descending
- [ ] Status Bar Text Card (B-19): X=1158, Y=460, W=117, H=255
- [ ] Edit interactions: KPI cards = No Interaction from all 3 panel clicks
- [ ] Page tab renamed "Fleet Overview"

---

*End of Day 25 Page 1 build log. Day 26: Pareto refinement (Page 1 Panel D -- RANKX-based cumulative measure, 80% reference line, secondary Y-axis percentage format).*
