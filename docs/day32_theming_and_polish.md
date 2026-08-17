# Day 32 — Power BI Theming & Polish Specification
## Manufacturing Analytics Digital Twin Dashboard

**Project:** Manufacturing Analytics — Reliability & Maintenance Intelligence
**Phase:** 2.3 — Power BI Phase 2 (Diagnostic Dashboards)
**Day:** 32 of 35
**Date:** 2026-08-15
**Status:** Specification — Drafted, Not Yet Built in Power BI Desktop

> **Maintenance rule:** This document is the authoritative Day 32 theming and polish record.
> It extends `docs/visual_design_blueprint.md` (Section 4.3 Tooltip Pages).
> Nothing here supersedes the locked DAX measures (87 total, Groups A–E) or the
> interactivity architecture finalized on Day 31.

---

## 1. Custom Tooltip Page Layouts
### Per visual_design_blueprint.md Section 4.3

Three dedicated canvas tooltip pages are specified below. Each is a separate hidden report
page in Power BI Desktop (Page properties → Hide page = ON, Allow use as tooltip = ON,
canvas type = Tooltip). Tooltip pages are triggered by hover on the host visual — not by
click, and not via the standard auto-generated tooltip.

---

### Tooltip Page T-1 — Health Score Trend (Line Chart, Page 1 Panel A)

**Trigger:** Hover on any data point of the 5-component health score line chart
(Page 1, Panel A, x-axis = date_key monthly, y-axis = [Avg Health Score]).

**Canvas size:** 320 × 200 px (Power BI Tooltip preset)

**Layout:**

```
┌──────────────────────────────────────────────────────┐
│  [Component Name]   [Month/Year]                     │
│  ─────────────────────────────────────────────────── │
│  Avg Health Score     [A-01 value]  ● colour-coded   │
│  ─────────────────────────────────────────────────── │
│  Alarm Breaches       [A-06 value]  amber badge      │
│  Danger Breaches      [A-07 value]  red badge        │
│  Arrhenius AF         [A-08 value]  (2 dp)           │
└──────────────────────────────────────────────────────┘
```

**Visual elements:**
| Slot | Visual Type | Measure | Format |
|---|---|---|---|
| Header row | Text box | dim_components[pipeline_label] + dim_calendar[month_year] | Font: Segoe UI 9 pt bold, colour #37474F |
| Health Score row | Card | `[Avg Health Score]` (A-01) | Colour-coded: <65 → #C62828, <75 → #F57F17, ≥75 → #2E7D32. 0 dp. |
| Alarm Breaches | Card | `[Alarm Breach Count]` (A-06) | Amber badge #F57F17 if > 0. |
| Danger Breaches | Card | `[Danger Breach Count]` (A-07) | Red badge #C62828 if > 0. 0 if clean. |
| Arrhenius AF | Card | `[Avg AF]` (A-08) | 2 dp. No colour coding — contextual numeric. |

**Configuration steps in Power BI Desktop:**
1. Insert new page → Rename to `TT_HealthScoreTrend`.
2. Page properties → Canvas settings → Type = Tooltip.
3. Page properties → Hide page = ON.
4. On Page 1 Panel A (line chart) → Format → Tooltip → Type = Report page → Page = `TT_HealthScoreTrend`.
5. Add above visuals with padding 8 px between rows.

---

### Tooltip Page T-2 — Pareto Root Cause (Bar Chart, Page 3 Panel A)

**Trigger:** Hover on any component bar in the Root Cause Downtime Pareto chart
(Page 3, Panel A, x-axis = dim_components[pipeline_label], y-axis = [Root Cause Downtime Min] D-07).

**Canvas size:** 320 × 200 px

**Layout:**

```
┌──────────────────────────────────────────────────────┐
│  [Component Name]  Root Cause Drill                  │
│  ─────────────────────────────────────────────────── │
│  MTBF (hrs)           [C-02 value]                   │
│  MTTR (hrs)           [C-03 value]                   │
│  CCI Tier             [D-06 value]  colour-coded     │
│  Root Cause DT (min)  [D-07 value]                   │
└──────────────────────────────────────────────────────┘
```

**Visual elements:**
| Slot | Visual Type | Measure | Format |
|---|---|---|---|
| Header row | Text box | dim_components[pipeline_label] + label "Root Cause Drill" | Font: Segoe UI 9 pt bold, colour #37474F |
| MTBF | Card | `[MTBF Hours]` (C-02) | 0 dp, suffix " hrs". |
| MTTR | Card | `[MTTR Hours]` (C-03) | 1 dp, suffix " hrs". Red text if > 8 hrs. |
| CCI Tier | Card | `[CCI Tier]` (D-06) | Text label. Critical=#C62828, High=#F57F17, Moderate=#F9A825, Low=#2E7D32. |
| Root Cause DT | Card | `[Root Cause Downtime Min]` (D-07) | 0 dp, suffix " min". |

**Configuration steps:**
1. Insert new page → Rename to `TT_ParetoRootCause`.
2. Page properties → Canvas settings → Type = Tooltip.
3. Page properties → Hide page = ON.
4. On Page 3 Panel A (Pareto bar) → Format → Tooltip → Type = Report page → Page = `TT_ParetoRootCause`.

---

### Tooltip Page T-3 — OEE Waterfall Loss Step (Waterfall Chart, Page 1 Panel C)

**Trigger:** Hover on any loss step bar in the Six Big Losses waterfall chart
(Page 1, Panel C, y-axis = loss percentage points, x-axis = loss category labels).

**Canvas size:** 320 × 200 px

**Layout:**

```
┌──────────────────────────────────────────────────────┐
│  Loss Category: [Loss Name]                          │
│  ─────────────────────────────────────────────────── │
│  Loss (pp)            [B-11b value]                  │
│  Raw Duration (min)   [B-18b value]                  │
│  Component(s)         [pipeline_label context]       │
│  OEE Pillar           [Availability / Performance /  │
│                         Quality — text box]          │
└──────────────────────────────────────────────────────┘
```

**Visual elements:**
| Slot | Visual Type | Measure | Format |
|---|---|---|---|
| Header | Text box | Loss category label from waterfall context | Font: Segoe UI 9 pt bold, colour #C62828 (loss bars are negative). |
| Loss PP | Card | `[Selected Loss PP]` (B-11b) | 1 dp, suffix " pp". |
| Raw Duration | Card | `[Selected Loss Min]` (B-18b) | 0 dp, suffix " min". |
| Component(s) | Card / slicer echo | dim_components[pipeline_label] in current filter context | Lists affected components in that loss category. |
| OEE Pillar | Static text box | Hard-coded per loss category (L1/L2 = Availability, L3/L4 = Performance, L5/L6 = Quality) | Font: Segoe UI 8 pt italic, colour #37474F. |

**Configuration steps:**
1. Insert new page → Rename to `TT_WaterfallLoss`.
2. Page properties → Canvas settings → Type = Tooltip.
3. Page properties → Hide page = ON.
4. On Page 1 Panel C (waterfall) → Format → Tooltip → Type = Report page → Page = `TT_WaterfallLoss`.

> **Power BI tooltip scoping note:** Waterfall chart tooltip pages receive the category-level
> filter context of the hovered bar (the loss-category label, not a component_id). To show
> component attribution within that loss category, the tooltip visuals must rely on cross-filter
> propagation from the active date-range and component slicer context, combined with the
> loss-category bar context. This is sufficient for T-3 because the waterfall already operates
> in the fleet-aggregate context on Page 1.

---

## 2. Cross-Page UX Standards

These rules apply uniformly to all three dashboard pages and all visuals.
They are finalized as of Day 32 and are not visual-specific — they are system-wide standards.

---

### 2.1 Visual Title Alignment

| Rule | Standard | Rationale |
|---|---|---|
| Title horizontal alignment | **Left-aligned** (not centred) | Left-aligned titles are faster to scan in a grid layout; centred titles misalign when card widths vary. |
| Title vertical position | Top of visual container, **8 px padding** from top edge | Consistent breathing room; prevents titles from abutting the visual border. |
| Title case | **Title Case** for panel labels (e.g., "Health Score Trend"), **ALL CAPS** for KPI card labels (e.g., "SYSTEM OEE") | Mirrors Power BI default KPI card conventions; distinguishes card headlines from panel axis labels. |
| Title font | **Segoe UI, 11 pt, bold** for panel/chart titles | Segoe UI is the Power BI native font; 11 pt bold is readable at standard 1280 × 800 report canvas. |
| Sub-label / axis label font | **Segoe UI, 9 pt, regular** | One size step below title; retains hierarchy without competing for attention. |

**Implementation path in Power BI Desktop:**
Format pane → General → Title → Text = [set per visual], Font = Segoe UI 11 pt Bold,
Horizontal Alignment = Left. Apply to every visual on all three pages before final export.

---

### 2.2 Legend Cleanup Rules

| Rule | Standard |
|---|---|
| Legend position | **Right** for all multi-series line charts (Page 1 Panel A, Page 2 Panel A). **None** for all single-series visuals and KPI cards. |
| Legend font | Segoe UI 8 pt regular. Match series colour exactly (no default grey). |
| Legend title | **Hidden** (no legend title text). The page-level slicer context is the implicit legend title. |
| Legend entries | Match exactly to `dim_components[pipeline_label]` values; no abbreviations. |
| Scatter chart legend | **None** — bubble label (pipeline_label) is displayed directly on each bubble as a data label. |
| Radar chart legend | **None** — the single-component drill-through context makes the legend redundant. |
| Waterfall chart legend | **None** — increase/decrease/total are visually encoded by bar colour (teal/red/grey); a redundant legend adds noise. |
| Stacked bar chart legend | **Bottom** for Page 3 Panel D (Alarm + Danger stacked bar). Two entries: Alarm Breach (amber) and Danger Breach (red). |

---

### 2.3 Font Size Hierarchy

The complete font size hierarchy for this dashboard:

| Level | Element | Font | Size | Weight | Colour |
|---|---|---|---|---|---|
| L1 | Page title (banner row) | Segoe UI | 14 pt | Bold | #FFFFFF on dark banner background #1A237E |
| L2 | KPI card value (primary number) | Segoe UI | 28 pt | Bold | Conditional (state colour — see §2.4) |
| L3 | KPI card label (description) | Segoe UI | 10 pt | Regular | #546E7A |
| L4 | Chart / panel title | Segoe UI | 11 pt | Bold | #37474F |
| L5 | Axis label (x and y) | Segoe UI | 9 pt | Regular | #546E7A |
| L6 | Data label (on-bar, on-bubble) | Segoe UI | 8 pt | Regular | #FFFFFF (dark bars) or #37474F (light bars) |
| L7 | Tooltip text | Segoe UI | 9 pt | Regular | #37474F |
| L8 | Legend entry | Segoe UI | 8 pt | Regular | Match series colour |
| L9 | Matrix / table cell | Segoe UI | 9 pt | Regular | #212121 |
| L10 | Slicer chip / dropdown | Segoe UI | 9 pt | Regular | #37474F |

**Enforcement note:** These sizes are set via Format pane for each visual.
Power BI does not have a single global font token; each visual type exposes its own font
settings under Title, Data labels, Axis, Legend, and Tooltip sub-sections.

---

### 2.4 Standardized Colour Codes — States and Alerts

These are the canonical state/alert colours for this project. They are already encoded in
`powerbi_theme.json` and in `docs/visual_design_blueprint.md` Section 4.1. This section
consolidates them as the single reference for theming and conditional formatting configuration.

#### State Colours (Health Score, OEE Status, CCI Tier)

| State Label | Trigger Condition | Hex Code | Usage |
|---|---|---|---|
| WORLD CLASS / Healthy | Health ≥ 75 **or** OEE ≥ 85% | `#2E7D32` | KPI card background (light), bar fill, data label |
| WORLD CLASS (alt) | OEE ≥ 85% card background | `#00695C` | KPI card primary bg for System OEE card |
| ACCEPTABLE | Health 65–74 **or** OEE 75–84% | `#F9A825` | KPI card background (amber-gold) |
| ALERT | Health 50–64 **or** OEE 65–74% | `#F57F17` | KPI card background (deep amber) |
| CRITICAL | Health < 50 **or** OEE < 65% | `#C62828` | KPI card background (danger red) |

#### Alert / Breach Colours

| Alert Type | Hex Code | Applied To |
|---|---|---|
| Alarm threshold breach | `#F57F17` | Alarm Breach Count badge, stacked bar Alarm series, Alarm marker on trend line |
| Danger threshold breach | `#C62828` | Danger Breach Count badge, stacked bar Danger series, Danger marker on trend line |
| No breach (clean) | `#2E7D32` | Zero-breach KPI card background |

#### CCI Tier Colours

| Tier | Hex Code |
|---|---|
| Critical | `#C62828` |
| High | `#F57F17` |
| Moderate | `#F9A825` |
| Low | `#2E7D32` |

#### Neutral / Structural Colours

| Purpose | Hex Code |
|---|---|
| Pipeline label bar fill (neutral) | `#37474F` |
| Page banner / dark header | `#1A237E` |
| Background canvas | `#F5F5F5` |
| Card / panel background | `#FFFFFF` |
| Grid line / separator | `#ECEFF1` |
| Text — primary | `#212121` |
| Text — secondary / axis | `#546E7A` |

#### 5-Component Series Colours (locked Day 23)

| Component | Hex Code |
|---|---|
| Bearing (Position 1) | `#1565C0` |
| Shaft (Position 2) | `#6A1B9A` |
| Motor Housing (Position 3) | `#00695C` |
| Coupling (Position 4) | `#E65100` |
| Gearbox (Position 5) | `#37474F` |

---

## 3. Interactivity Verification Checklist

This checklist covers the four verification domains specified for Day 32.
Each item must be confirmed in Power BI Desktop (Editing view + Reading view)
before the report is published or submitted.

> **Pre-condition:** All data must be loaded (all 6 CSVs via M scripts), the star-schema
> relationships must be active (9 active + 2 inactive), and all 87 DAX measures must be
> entered. The Date Range slicer must be set to a date range within the simulation window
> (2026-07-20 to 2027-07-20) that includes at least one anomaly event.

---

### 3.1 Drill-Through Routing Checks

Four source visuals must be verified end-to-end.

| # | Source Page | Source Visual | Action | Expected Result | Pass Criteria |
|---|---|---|---|---|---|
| DT-01 | Page 1 (Fleet Overview) | Panel B — Horizontal Bar (Health Score by component) | Right-click any component bar → "Drill through" → "Component Health" | Page 2 loads, filtered to clicked component. All 5 KPI cards show that component's values. Back button visible top-right. | D-01..D-06 measures return non-BLANK values. KPI Card 1 (Avg Health Score) matches Panel B clicked bar value. |
| DT-02 | Page 1 (Fleet Overview) | Panel C — OEE Waterfall (Bottleneck Decomposition) | Drill down to a component sub-bar within a loss category, THEN right-click that component bar → "Drill through" → "Component Health" | Page 2 loads filtered to the specific component. | The Category well must have component_id (or pipeline_label) below Loss Category. Drill-through directly from an aggregate loss category bar will pass the loss type instead of component_id. |
| DT-03 | Page 3 (Alert / Risk) | Panel A — Pareto (Root Cause Downtime) | Right-click any component bar → "Drill through" → "Component Health" | Page 2 loads filtered to the right-clicked component. MTBF trend (Panel A), radar (Panel B), and OEE bars (Panel C) all show single-component context. | `[MTBF vs Weibull Delta]` (C-08) KPI card shows a non-zero delta, confirming the filter resolved to one component. |
| DT-04 | Page 3 (Alert / Risk) | Panel B — Scatter (Risk Prioritization Matrix) | Right-click any component bubble → "Drill through" → "Component Health" | Page 2 loads filtered to the bubble's component. The Details well must contain dim_components[component_id] for this to work. | If right-click does not show "Drill through", verify component_id is in the Details well (not Tooltips). [CCI Score] (D-01) on radar chart returns a non-BLANK value. |

**Back-navigation check (all four):** After each successful drill-through, click the auto-generated
Back button (positioned X=1190, Y=10, W=80, H=30, teal #00695C background, white font) and confirm
return to the correct source page with all prior filter context restored.

---

### 3.2 Sync Slicer Propagation Checks

| # | Action | Expected Propagation | Pass Criteria |
|---|---|---|---|
| SS-01 | On Page 1: set Date Range slicer to a specific 30-day window (e.g., 2026-09-01 to 2026-09-30). Navigate to Page 2. | Page 2 Date Range slicer must show the same 30-day window. All KPI cards and trend charts must be filtered to that window. | Panel A (MTBF Trend) x-axis shows only September 2026 data points. KPI Card 2 (MTBF Hours) shows September-only MTBF. |
| SS-02 | Continue on Page 2: navigate to Page 3 without changing the slicer. | Page 3 Date Range slicer must show the same 30-day window. Alert counts and pareto bars must reflect only that window. | KPI Card 1 (Danger Breaches) count matches `SELECT COUNT(*) FROM sensor_readings WHERE is_anomaly=1 AND ts BETWEEN '2026-09-01' AND '2026-09-30'` (approx). |
| SS-03 | On Page 3: set Date Range to a 7-day window. Navigate back to Page 1. | Page 1 Date Range slicer must show the 7-day window. Health Score Trend (Panel A) must show only 7 days of data. | Panel A x-axis shows 7 data points at daily granularity (or 1 at monthly if granularity exceeds window). |
| SS-04 | On Page 1: select a single component from the Component slicer (e.g., Bearing). Navigate to Page 3. | Page 3 Component slicer must show Bearing selected. Pareto bars and scatter must reflect Bearing-only data. | Panel B scatter shows only one bubble (Bearing). Alert counts in KPI Cards reflect Bearing-only readings. |
| SS-05 | Component slicer on Page 2 — verify Visible=OFF. | The component slicer is not visible anywhere on the Page 2 canvas. Sync=ON must still be active (filter context persists from drill-through). | After drilling through to Page 2 from Bearing's bar on Page 1, all Page 2 visuals show Bearing-only data despite no visible slicer. Navigating back to Page 1 still shows Bearing selected in Page 1 Component slicer. |

---

### 3.3 KPI Card Anchor Tests

The universal anchor pattern: KPI cards on all three pages must return No Interaction from
all non-slicer visuals. These tests confirm that anchor behaviour is active.

| # | Trigger Action | Target | Expected Behaviour | Pass Criteria |
|---|---|---|---|---|
| KA-01 | Page 1: Click a component series point on Panel A (Health Score Line Chart). | KPI Cards 1–5 on Page 1. | KPI card values do not change. All five cards continue to show fleet-level aggregates (all-component context). | KPI Card 2 (Min Health Score) still shows the global minimum across all 5 components — not just the clicked component's health score. |
| KA-02 | Page 1: Click any loss bar on Panel C (OEE Waterfall). | KPI Cards 1–5 on Page 1. | KPI card values do not change. System OEE card (KPI 1) continues to show fleet system OEE. | KPI Card 1 value is identical before and after clicking the waterfall bar. |
| KA-03 | Page 2: Click a monthly data point on Panel A (MTBF/MTTR Line Chart). | KPI Cards 1–5 on Page 2. | KPI card values do not change. All cards continue to show averages over the full drill-through context date window. | KPI Card 1 (Avg Health Score) value is identical before and after clicking the MTBF trend line. |
| KA-04 | Page 2: Click a data point on Panel E (Health Score Trend, daily). | KPI Cards 1–5 on Page 2. | KPI card values do not change. | Same as KA-03. |
| KA-05 | Page 3: Click any panel (A, B, C, or D). | KPI Cards 1–5 on Page 3. | KPI card values do not change. Fleet-level danger breach count and alert counts remain stable. | KPI Card 1 (Danger Breaches) shows the same count before and after clicking any non-slicer element on Page 3. |

---

### 3.4 Scatter Plot No Interaction Test (Page 3 Panel B)

Three specific No Interaction suppressions protect the Risk Prioritization Matrix scatter.

| # | Trigger | Target | Expected Behaviour | Pass Criteria |
|---|---|---|---|---|
| SI-01 | Page 3: Select a Sensor Type in the Sensor Type slicer (e.g., "vibration"). | Panel B Scatter (Risk Prioritization Matrix). | The scatter chart layout does NOT change. All 5 component bubbles remain at the same positions (X = CCI Score, Y = Avg Health Score, Size = Total Active Alerts). Bubble sizes remain proportional to the unfiltered alert counts. | Before slicer selection: note X/Y positions and bubble sizes of all 5 bubbles. After selecting "vibration": positions and sizes are identical. CCI and health score are sensor-agnostic composites — they must not respond to sensor type filter. |
| SI-02 | Page 3: Click a date point on Panel D (Alert Trend Line). | Panel B Scatter (Risk Prioritization Matrix). | The scatter chart layout does NOT change. Bubble positions and sizes remain as in unfiltered state. | Note bubble layout before Panel D click. After click: layout is identical. |
| SI-03 | Page 3: Click a cell in Panel C (Violation Rate Matrix). | Panel B Scatter (Risk Prioritization Matrix). | The scatter chart layout does NOT change. | Same test protocol as SI-01 and SI-02. |

**If any SI test fails:** Navigate to Page 3 in Editing view → Click Panel B scatter to select it →
Format tab → Edit Interactions → find the failing source visual (sensor type slicer, Panel D, or
Panel C) → click the No Interaction icon (⊘) on Panel B's interaction control. Re-test in Reading view.

---

## 4. E-01 SQL Cross-Validation Query

**Measure being validated:** `[Total Active Alerts]` (E-01) — used as bubble size in Page 3
Panel B scatter chart.

**Power BI measure definition (DAX):**
```dax
[Total Active Alerts] =
CALCULATE(
    COUNTROWS(fact_sensor_readings),
    fact_sensor_readings[is_anomaly] = 1
)
```

**SQL cross-validation query (SQLite, production table name):**
```sql
SELECT COUNT(*) FROM sensor_readings WHERE is_anomaly = 1;
```

**Expected behaviour:**
- With Date Range slicer set to ALL / maximum date range, the Power BI card showing
  `[Total Active Alerts]` (fleet total, no component filter) must match the SQL COUNT(*) result.
- With Date Range slicer set to a specific window, the Power BI value must match:

```sql
SELECT COUNT(*)
FROM sensor_readings
WHERE is_anomaly = 1
  AND ts >= '[slicer_start_date]'
  AND ts <  '[slicer_end_date + 1 day]';
```

**Cross-validation procedure:**
1. Run the SQL query in SQLite (or SQL Server equivalent) against the production database:
   ```sql
   SELECT COUNT(*) AS total_active_alerts
   FROM sensor_readings
   WHERE is_anomaly = 1;
   ```
2. Note the returned integer value.
3. In Power BI: set Date Range slicer to the full simulation window (2026-07-20 to 2027-07-20).
   Remove all component filters (Component slicer = ALL).
4. Read the `[Total Active Alerts]` value from Page 3 KPI Card 4 (or Page 1 KPI Card 4,
   `[Alarm Breach Count]` + `[Danger Breach Count]` combined if E-01 is the sum of A-06 + A-07).
5. The Power BI value must equal the SQL COUNT(*) within ±0 (integer exact match).
   Any discrepancy indicates a data load error (ETL missed rows), a DAX filter leak,
   or a date-table boundary mismatch.

**Known failure modes to check if values diverge:**
| Failure Mode | Diagnostic |
|---|---|
| Power BI < SQL count | Check if dim_calendar date range covers all ts values. Run `SELECT MIN(ts), MAX(ts) FROM sensor_readings WHERE is_anomaly=1` and compare to dim_calendar bounds. |
| Power BI > SQL count | Check for duplicate rows in fact_sensor_readings (ETL loaded the same CSV twice). Run `SELECT COUNT(*), COUNT(DISTINCT reading_id) FROM sensor_readings WHERE is_anomaly=1` — if they differ, duplicates exist. |
| Values match at fleet level but diverge per component | Check that the active relationship between fact_sensor_readings and dim_components is on component_id (not component_name). A wrong relationship key would produce incorrect per-component filter propagation. |

---

## 5. Day 32 Decisions Locked

1. **Tooltip page canvas type must be set to Tooltip (not Tooltip page).** In Power BI Desktop,
   the correct setting is Page properties → Canvas settings → Type = Tooltip (not the
   deprecated "Set as tooltip" toggle in older builds). This enables both hover delivery and
   correct canvas sizing.

2. **All legend titles are hidden.** The slicer context on each page provides the implicit legend
   title. Adding redundant legend title text ("Component Name") clutters the canvas and repeats
   information already surfaced by the page-level slicer chip.

3. **L2 KPI card value size is 28 pt.** This is a deliberate increase from Power BI default (20 pt).
   At 28 pt, KPI card primary values are readable at arm's length on a 24" monitor — the target
   display environment for a manufacturing control room presentation.

4. **No Interaction is used exclusively (not Highlight) for all Edit Interaction suppressions.**
   Highlight mode in Power BI dims non-selected data but still modifies the displayed value on
   target visuals (KPI cards would show the highlighted subset). No Interaction completely decouples
   the target visual from the interaction event, which is the required behaviour for all anchor KPI
   cards and sensor-agnostic scatter/radar visuals.

5. **E-01 SQL query uses the raw SQLite table name `sensor_readings`** (not the Power BI alias
   `fact_sensor_readings`). The SQL is run against the source database, not the Power BI data model.
   The M query renames the table during load to `fact_sensor_readings` in the Power BI model, but the
   underlying SQLite table retains its original schema name.

---

## 6. Open Items — Carry-Forward to Day 33

- [ ] Build the three tooltip pages (T-1, T-2, T-3) in Power BI Desktop per the specifications above.
- [ ] Apply all font, legend, and colour-code standards from §2 to all visuals across Pages 1, 2, and 3.
- [ ] Run the full interactivity verification checklist (§3) in both Editing and Reading views.
- [ ] Execute the E-01 SQL cross-validation (§4) and record the result in the Day 33 CONTEXT.md entry.
- [ ] Day 33 target: Begin integration testing (end-to-end pipeline → SQL → Power BI refresh cycle).

---

*End of Day 32 specification. Phase 2.3 Power BI theming and polish. Status: drafted, not yet built in Power BI Desktop.*
