# Page 3 - Alert / Risk Summary: Build Specification
## Day 29 - August 14, 2026
**Project:** Manufacturing Analytics Digital Twin
**Phase:** 2.3 Power BI Build - Day 29
**Page:** Page 3 - Alert / Risk Summary
**Status:** Core visual layout defined and locked
**Companion files:** `docs/dax_and_m_scripts.md` | `docs/ux_implementation_guide.md` | `docs/visual_design_blueprint.md`

---

## 0. Purpose of Page 3

Page 3 is the **operational alert centre** of the dashboard. While Page 1 gives the fleet overview and Page 2 gives per-component deep-dive, Page 3 answers:

> "What is actively wrong right now, and which component needs my immediate attention?"

Page 3 surfaces three core analytical constructs:

1. **Fleet-wide Active Alert Inventory** - a count and breakdown of all active alarm/danger-zone sensor readings across the fleet, segmented by sensor type and component.
2. **Risk Prioritization Matrix** - a two-axis scatterplot placing each component by Criticality (CCI, X-axis) versus current Health Score (Y-axis), with quadrant classification driving maintenance action.
3. **Threshold Violation Frequency Panel** - a heat-map-style matrix showing how often each component-sensor combination breaches ISO/operational thresholds, enabling pattern detection beyond single-point alerts.

All three panels share the drill-through key `dim_components[component_id]`. Right-clicking any element on Page 3 routes to Page 2 for the selected component's full health degradation profile.

---

## 1. Canvas Setup

| Setting | Value |
|---|---|
| Page name | `Alert / Risk Summary` |
| Width | 1280 px |
| Height | 720 px |
| Background | `#0D1117` (dark industrial - matches Page 2 dark theme) |
| Theme file | `powerbi_theme.json` (already applied project-wide) |

> **Note on dark canvas:** Page 3 uses `#0D1117` because alert/risk data is most readable with high-contrast coloured status indicators on a dark neutral background. This creates a deliberate visual mode-shift from Page 1 light canvas (`#F5F5F5`).

---

## 2. Zone Layout Grid

```
+------------------------------------------------------------------------------+
| ZONE 1: KPI Card Row                                  (y: 0-100, 1280px)    |
| [E-01 Total Alerts] [E-02 Danger Zone] [E-03 Alarm Zone] [E-04 Most Alert.] [E-05 Critical Count] |
+------------------------------------------------------------------------------+
| FILTER PANEL                                          (y: 100-160)           |
| [Date Range Slicer (0-640)]   [Sensor Type Slicer (645-1275)]               |
+---------------------------------------+--------------------------------------+
| PANEL A (left 60%) W:768 H:270 Y:165  | PANEL B (right 40%) W:502 H:270 Y:165|
| Fleet Alert Inventory                 | Risk Prioritization Matrix           |
| Stacked Bar: Alert Count by           | Scatter: CCI (X) vs Health (Y)       |
| Component + Sensor Type               | Quadrant overlay, 5 component dots  |
+---------------------------------------+--------------------------------------+
| PANEL C (left ~50%) W:630 H:230 Y:440 | PANEL D (right ~50%) W:635 H:230 Y:440|
| Threshold Violation Frequency Matrix  | Alert Trend Over Time               |
| Matrix: Component x Sensor Type       | Line Chart: Daily Alarm+Danger Count |
| Value: E-07 [Violation Rate]          | Alarm vs Danger overlaid bands      |
+------------------------------------------------------------------------------+
| PANEL E - Full Width Status Bar       W:1280 H:45 X:0 Y:675                 |
| "Highest Risk: [COMPONENT] -- [TIER] | [N] Danger Zone Alerts Active"       |
+------------------------------------------------------------------------------+
```

---

## 3. Exact Visual Coordinates

| Panel | Visual Type | X | Y | W | H |
|---|---|---|---|---|---|
| KPI Card 1 - Total Active Alerts | Card | 0 | 0 | 230 | 100 |
| KPI Card 2 - Danger Zone Count | Card | 235 | 0 | 230 | 100 |
| KPI Card 3 - Alarm Zone Count | Card | 470 | 0 | 230 | 100 |
| KPI Card 4 - Most Alerting Component | Card | 705 | 0 | 230 | 100 |
| KPI Card 5 - Critical Risk Count | Card | 940 | 0 | 330 | 100 |
| Date Range Slicer | Slicer | 0 | 105 | 640 | 55 |
| Sensor Type Slicer | Slicer | 645 | 105 | 625 | 55 |
| Panel A - Fleet Alert Inventory | Stacked Bar Chart | 0 | 165 | 768 | 270 |
| Panel B - Risk Prioritization Matrix | Scatter Chart | 773 | 165 | 502 | 270 |
| Panel C - Threshold Violation Matrix | Matrix Visual | 0 | 440 | 630 | 230 |
| Panel D - Alert Trend Line | Line Chart | 645 | 440 | 635 | 230 |
| Panel E - Status Bar | Card | 0 | 675 | 1280 | 45 |

---

## 4. Panel-by-Panel Visual Specifications

---

### 4.1 KPI Card Row (Zone 1)

Five cards spanning the full top row. Dark background, white value text, status-colour conditional formatting.

| Card # | Measure | ID | CF Rule | Display Label |
|---|---|---|---|---|
| 1 | `[Total Active Alerts]` | E-01 | Red if >10, Amber if >0, Teal if 0 | "Active Alerts" |
| 2 | `[Active Danger Zone Alerts]` | E-02 | Background always `#55B00020` | "Danger Zone" |
| 3 | `[Alarm Zone Count]` | E-03 | Background always `#55F57F17` | "Alarm Zone" |
| 4 | `[Most Alerting Component]` (text) | E-04 | No CF - text card | "Highest Alert Source" |
| 5 | `[Critical Risk Component Count]` | E-05 | Red if >=2, Amber if =1, Teal if 0 | "Critical Risk Components" |

**Card formatting (uniform):**
- Background: `#0D1117`; Title font: Outfit 10px `#9E9E9E`; Value font: Outfit 28px Bold White; Border: 1px `#1E2D2F`

---

### 4.2 Filter Panel (Slicer Row)

| Slicer | Field | Style | Slicer Sync |
|---|---|---|---|
| Date Range | `dim_calendar[date]` | Between (date range picker) | Sync ON, Visible ON - all 3 pages |
| Sensor Type | `dim_sensors[sensor_type]` | List, multi-select | Sync OFF (Page 3 only) |

> **Sensor Type slicer rationale:** Page 3-specific. Filters Panels A, C, D to a single sensor modality. NOT synced to Pages 1/2 because those show composite fleet metrics, not sensor-type-specific alert counts.

---

### 4.3 Panel A - Fleet Alert Inventory (Stacked Bar Chart)

**Purpose:** Show total active alert count per component, stacked by sensor type. Immediately reveals which component has the most alerts and which sensor type is driving them.

**Field Bindings:**

| Well | Field / Measure |
|---|---|
| Y-axis (categories) | `dim_components[component_name]` (sorted by `position` ASC) |
| X-axis (values) | `[Alert Count by Sensor Type]` (E-06) |
| Legend (series) | `dim_sensors[sensor_type]` |
| Tooltips | `[Total Active Alerts]` (E-01), `[Active Danger Zone Alerts]` (E-02) |

**Format:**
- Title: "Fleet Active Alert Inventory - By Component & Sensor Type"
- Background: `#0D1117`; X-axis fixed min=0; Y-axis title OFF
- Stacked bar colours by sensor type: vibration=`#1565C0`, temperature=`#E65100`, oil_debris=`#6A1B9A`, load=`#558B2F`, rpm=`#37474F`
- Reference line X=5: `#F57F17` dashed, label "Alert Threshold"
- Reference line X=10: `#B00020` dashed, label "Critical Level"

**Drill-Through:** Bind `dim_components[component_id]` to Details well. Right-click -> Page 2.

**Edit Interactions:** Cross-filters Panels C and D. No interaction on KPI cards.

---

### 4.4 Panel B - Risk Prioritization Matrix (Scatter Chart)

**Purpose:** 2x2 risk matrix implemented as scatter plot. X=CCI (criticality), Y=Health Score. Quadrant classification drives maintenance action.

**Quadrant Classification (locked thresholds):**

```
                     |  CCI < 0.50           |  CCI >= 0.50          |
Health >= 75         |  LOW RISK             |  MONITOR              |
                     |  No action needed     |  Watch for decline    |
--Health=75 boundary-+-----------------------+-----------------------+
Health < 75          |  INVESTIGATE          |  CRITICAL PRIORITY    |
                     |  Declining, not crit. |  URGENT intervention  |
```

**Field Bindings:**

| Well | Field / Measure |
|---|---|
| X-axis | `[CCI Score]` (D-01) - 0.0 to 1.0 |
| Y-axis | `[Avg Health Score]` (A-01) - 0 to 100 |
| Size | `[Total Active Alerts]` (E-01) - bubble size scales with alert count |
| Legend / Details | `dim_components[component_name]` + `component_id` |
| Tooltips | `[CCI Tier]` (D-06), `[Criticality Rank]` (D-13), `[MTBF Hours]` (C-02) |

**Format:**
- Title: "Risk Prioritization Matrix - Criticality vs. Current Health"
- X-axis: Fixed 0-1.0; Y-axis: Fixed 0-100; Background: `#0D1117`
- Data colours: `[Criticality Bar Colour]` (D-15) via Field value CF
- Bubble size: 5px (0 alerts) to 25px (max alerts)
- Quadrant reference lines (Analytics pane): X=0.50 grey solid; Y=75 grey solid (both Behind)
- Quadrant text boxes: "LOW RISK" (#2E7D32), "MONITOR" (#F57F17), "INVESTIGATE" (#E65100), "CRITICAL PRIORITY" (#B00020)

**Expected component positions (Phase 2.1 scores):**
- Coupling: CCI=0.804 (CRITICAL PRIORITY quadrant - rank 1, highest priority)
- Shaft: CCI=0.753 (CRITICAL PRIORITY)
- Motor Housing: CCI=0.710 (CRITICAL/MONITOR boundary)
- Gearbox: CCI=0.549 (MONITOR)
- Bearing: CCI=0.457 (LOW RISK - BC=0.0 as source node)

---

### 4.5 Panel C - Threshold Violation Frequency Matrix

**Purpose:** Heat-map matrix. Rows=components, columns=sensor types, cell values=violation rate (breaches/day). Enables pattern detection - a component with 0.8 vibration violations/day has a systematic fault.

**Visual Type:** Power BI Matrix visual

**Field Bindings:**

| Well | Field |
|---|---|
| Rows | `dim_components[component_name]` (sort by `position` ASC) |
| Columns | `dim_sensors[sensor_type]` |
| Values | `[Violation Rate]` (E-07) - breaches per day |

**Format:**
- Title: "Threshold Violation Frequency (Breaches / Day)"
- Cell background CF via `[Violation Rate Colour]` (E-08):
  - 0.00: `#0D1117` (no violation)
  - 0.01-0.10: `#1E2D2F` (very low - dark teal)
  - 0.11-0.30: `#F57F17` (moderate - amber)
  - 0.31-0.60: `#E65100` (high - orange)
  - above 0.60: `#B00020` (severe - red)
- Row/column subtotals: OFF; Cell font: White 9px Bold; Gridlines: `#1E2D2F`

> **Heat map interpretation (viva):** 0.60 = threshold breached on 60% of operating days. Above 0.30 = systematic degradation requiring CBM intervention. Above 0.60 = imminent failure risk requiring immediate inspection.

---

### 4.6 Panel D - Alert Trend Over Time (Line Chart)

**Purpose:** Time series of alert counts separated by level (alarm vs danger). Distinguishes sudden spikes from rising trends.

**Field Bindings:**

| Well | Field / Measure |
|---|---|
| X-axis | `dim_calendar[date]` (daily, hierarchy disabled) |
| Y-axis Line 1 | `[Alarm Zone Count]` (E-03) - `#F57F17` Amber, solid 2px |
| Y-axis Line 2 | `[Active Danger Zone Alerts]` (E-02) - `#B00020` Red, solid 2px |
| Tooltips | `[Total Active Alerts]` (E-01) |

**Format:**
- Title: "Alert Trend - Alarm vs. Danger Zone Frequency"
- X-axis: Continuous; hierarchy disabled; 45deg labels; Y-axis fixed min=0; Zoom slider ON
- Shaded area ON for both series (20% opacity); Markers ON (3px circle)
- Reference line Y=10: `#B00020` dashed, label "Critical Alert Volume"

---

### 4.7 Panel E - Dynamic Status Bar (Full Width)

**Purpose:** Plain-language risk statement that updates dynamically.

**Measure:** `[Page 3 Status Banner]` (E-09)

**Examples:**
- Fleet view: `"Highest Risk Component: Coupling -- Critical | 3 Danger Zone Alerts Active"`
- Drill-through: `"Bearing -- Alarm Zone: 2 Vibration Breaches | Health Score: 61.3"`

**Format:**
- Card visual; Value font Outfit 16px Bold White
- Background via `[Status Banner Colour]` (E-10): Danger active=`#B00020`; Alarm only=`#F57F17`; Zero alerts=`#00695C`

---

## 5. Filter Interaction Matrix

| Source | Panel A | Panel B | Panel C | Panel D | KPI Cards |
|---|---|---|---|---|---|
| Date Slicer | Filter | Filter | Filter | Filter | Filter |
| Sensor Type Slicer | Filter | None | Filter | Filter | None |
| Panel A click | -- | Cross-filter | Cross-filter | Cross-filter | None |
| Panel B click | Cross-filter | -- | Cross-filter | Cross-filter | None |
| Panel C click | Cross-filter | None | -- | Cross-filter | None |
| Panel D click | Cross-filter | None | Cross-filter | -- | None |

KPI cards = "No Interaction" from all panels (fleet-level aggregates only).

---

## 6. Drill-Through Configuration (Page 3 to Page 2)

1. Page 3 is a **source** page - no drill-through field well on Page 3 itself.
2. Ensure `dim_components[component_id]` is in the Details well of Panels A, B, C.
3. Right-click any component element -> "Drill through" -> "Component Health" (Page 2).
4. Page 2 Back button auto-navigates to Page 3 (source tracking automatic).
5. D-16 `ISFILTERED()` logic on Page 2 Panel F title activates correctly for Page 3 drill-through.

---

## 7. Slicer Sync Configuration

| Slicer | Page 1 | Page 2 | Page 3 |
|---|---|---|---|
| Date Range | Sync ON, Visible ON | Sync ON, Visible ON | Sync ON, Visible ON |
| Component | Sync ON, Visible ON | Sync ON, Visible OFF | Sync ON, Visible ON |
| Sensor Type | Not present | Not present | Sync OFF, Visible ON |

Component slicer Visible ON on Page 3 (unlike Page 2 hidden). Allows non-drill-through component scoping.

---

## 8. Conditional Formatting Rule Reference

| Measure | Visual | CF Type | Rule |
|---|---|---|---|
| E-01 `[Total Active Alerts]` | KPI Card 1 | Background | >10=Red; 1-10=Amber; =0=Teal |
| E-02 `[Active Danger Zone Alerts]` | KPI Card 2 | Background | Always `#55B00020` |
| E-03 `[Alarm Zone Count]` | KPI Card 3 | Background | Always `#55F57F17` |
| E-05 `[Critical Risk Component Count]` | KPI Card 5 | Background | >=2=Red; =1=Amber; =0=Teal |
| E-08 `[Violation Rate Colour]` | Panel C cells | Background | Field value hex |
| D-15 `[Criticality Bar Colour]` | Panel B bubbles | Data colour | Field value |
| E-10 `[Status Banner Colour]` | Panel E | Background | Field value |

---

## 9. New DAX Measures Required (Day 29)

All full DAX written to `docs/dax_and_m_scripts.md`. Summary:

| ID | Name | Home Table | Purpose |
|---|---|---|---|
| E-01 | `[Total Active Alerts]` | _Measures_E_Alerts | Fleet-wide count: is_anomaly=1 OR iso_zone IN ('C','D') |
| E-02 | `[Active Danger Zone Alerts]` | _Measures_E_Alerts | iso_zone='D' readings count |
| E-03 | `[Alarm Zone Count]` | _Measures_E_Alerts | iso_zone='C' readings count |
| E-04 | `[Most Alerting Component]` | _Measures_E_Alerts | Component name with max E-01 (REMOVEFILTERS guarded) |
| E-05 | `[Critical Risk Component Count]` | _Measures_E_Alerts | Count: CCI>=0.75 AND health<75 |
| E-06 | `[Alert Count by Sensor Type]` | _Measures_E_Alerts | E-01 in current sensor_type filter context (Panel A series) |
| E-07 | `[Violation Rate]` | _Measures_E_Alerts | is_anomaly=1 count / DISTINCTCOUNT(operating days) |
| E-08 | `[Violation Rate Colour]` | _Measures_E_Alerts | SWITCH(TRUE(), E-07>0.60,"#B00020",...) hex string |
| E-09 | `[Page 3 Status Banner]` | _Measures_E_Alerts | Concatenated text: component + tier + alert count |
| E-10 | `[Status Banner Colour]` | _Measures_E_Alerts | "#B00020"/"#F57F17"/"#00695C" based on E-02/E-03 |

---

## 10. Design Decisions Locked (Day 29)

1. **Dark canvas (`#0D1117`) on Page 3:** Alert/risk context warrants a visual mode-shift. Red/amber/teal indicators maximally contrast against dark neutral.
2. **Scatter plot for risk matrix:** No native 2x2 visual in Power BI. Scatter + static quadrant reference lines achieves equivalent analytical output with zero AppSource dependencies.
3. **Matrix visual for threshold violations:** 5x5 heat-map grid = 25 simultaneous cells vs one-at-a-time bar reading. Appropriate information density for diagnostic tier.
4. **Violation Rate = breaches/day (not % of readings):** Gearbox has 3 sensor channels vs 2 for others. Normalizing by days makes cross-component comparison valid.
5. **Sensor Type slicer Page 3 only:** Vibration-only filter on Page 1/2 would suppress temperature-based health KPIs. Scoped to Page 3 where sensor-type granularity is analytically correct.
6. **`is_anomaly` flag from ETL (not recomputed in DAX):** ETL computed at load time (Day 9 `etl.py`) against `SENSOR_THRESHOLDS`. Single source of threshold truth - no DAX threshold duplication.

---

## 11. Verification Plan

| Check | Expected Result |
|---|---|
| KPI Card 1 with no slicer | Matches SQL: `SELECT COUNT(*) FROM fact_sensor_readings WHERE is_anomaly=1` |
| KPI Card 2 with no slicer | Matches SQL: `SELECT COUNT(*) FROM fact_sensor_readings WHERE iso_zone='D'` |
| Panel A total per component | Equals KPI Card 1 when component slicer filters to that component |
| Panel B - Coupling dot | Rightmost on X (CCI~=0.804); bubble size largest if most alerts |
| Panel B - Bearing dot | Leftmost on X (CCI~=0.457); likely LOW RISK quadrant |
| Panel C - Gearbox vibration cell | Highest violation rate (gear pitting = primary failure mode) |
| Panel D - alarm trend | Rising trend for Motor Housing thermal alerts as health degrades |
| Panel E banner | Updates correctly when Component slicer changed |
| Drill-through from Panel A | Passes component_id to Page 2; Back button returns to Page 3 |

---

*End of Day 29 Page 3 build specification.*
*Next: Page 3 visual assembly in Power BI Desktop. Day 30: Correlation analysis and root cause panels.*
