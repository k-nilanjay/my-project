# Day 33 — Team Review, UI/UX Polish Pass & Interactivity Verification
## Manufacturing Analytics Digital Twin Dashboard

**Project:** Manufacturing Analytics — Reliability & Maintenance Intelligence
**Phase:** 2.3 — Power BI Phase 2 (Diagnostic Dashboards)
**Day:** 33 of 35
**Date:** 2026-08-15
**Status:** Verification Execution Log — Structured Test Script

> **Maintenance rule:** This document is the Day 33 authoritative review and verification record.
> It executes the full checklist specified in `docs/day32_theming_and_polish.md` § 3 and documents
> the SQL cross-validation result from § 4. All test results are recorded with PASS / FAIL / BLOCKED
> status and notes for viva evidence.

---

## Part 1 — Custom Canvas Tooltip Pages: Implementation Specification

Three hidden canvas tooltip pages are implemented in Power BI Desktop per Day 32 specification.
Each page: canvas 320 × 200 px, Canvas settings → Type = Tooltip, Hide page = ON.

---

### T-1: TT_HealthScoreTrend

**Anchor visual:** Page 1 Panel A — Health Score Trend Line Chart
(x-axis = `dim_calendar[date]` monthly; y-axis = `[Avg Health Score]` A-01)

**Tooltip trigger:** Hover on any data point of the 5-component health score line chart.

**Canvas specification:**

| Setting | Value |
|---|---|
| Page name | `TT_HealthScoreTrend` |
| Canvas type | Tooltip |
| Hide page | ON |
| Canvas size | 320 × 200 px |
| Background | #FFFFFF (white panel, matches Page 1 card background) |
| Padding | 8 px inter-row |

**Visual layout (4 elements):**

```
+------------------------------------------------------+
|  [Component Name]   [Month/Year]         (text box)  |
|  ---------------------------------------------------  |
|  Avg Health Score     [A-01 value]  colour-coded     |
|  ---------------------------------------------------  |
|  Alarm Breaches       [A-06 value]  amber #F57F17    |
|  Danger Breaches      [A-07 value]  red   #C62828    |
|  Arrhenius AF         [A-08 value]  2 dp, #37474F    |
+------------------------------------------------------+
```

**Element specifications:**

| Slot | Visual Type | Measure / Field | Format Rule |
|---|---|---|---|
| Header row | Text box | `dim_components[pipeline_label]` + `dim_calendar[month_year]` | Segoe UI 9 pt Bold, colour #37474F; left-aligned |
| Avg Health Score | Card (KPI) | `[Avg Health Score]` (A-01) | 0 dp; CF: <50 -> #C62828; 50-74 -> #F57F17; >=75 -> #2E7D32 |
| Alarm Breaches | Card | `[Alarm Breach Count]` (A-06) | Amber badge #F57F17 when >0; green #2E7D32 when 0 |
| Danger Breaches | Card | `[Danger Breach Count]` (A-07) | Red badge #C62828 when >0; green #2E7D32 when 0 |
| Arrhenius AF | Card | `[Avg AF]` (A-08) | 2 dp; no colour coding; #37474F |

**Power BI Desktop configuration steps:**

1. Home -> Insert -> New page -> Rename page to `TT_HealthScoreTrend`.
2. Page properties (right-click tab) -> Canvas settings -> Type: select **Tooltip**.
3. Page properties -> Page information -> Enable "Allow use as tooltip" toggle = ON.
4. Page properties -> Page information -> Hide page = ON.
5. Navigate to Page 1 -> Select Panel A (line chart) -> Format pane -> Tooltip section.
6. Tooltip -> Type = **Report page** -> Page = `TT_HealthScoreTrend`.
7. On `TT_HealthScoreTrend` canvas: insert Text Box (header row, top 28 px) + 4 Card visuals (rows 40-196 px, 8 px gap each, height 36 px each).
8. Bind each Card to the measure listed above. Apply conditional formatting to Health Score card via Format -> Data labels -> fx -> Field value -> Health Score CF Colour measure (Rules: <50 = #C62828, 50-74 = #F57F17, >=75 = #2E7D32).

**DAX measures required on this tooltip page:**
- `[Avg Health Score]` A-01 (Group A, home table `_Measures_A_Health`)
- `[Alarm Breach Count]` A-06
- `[Danger Breach Count]` A-07
- `[Avg AF]` A-08

**Font compliance (L7 Tooltip standard):** Segoe UI 9 pt Regular, #37474F.

---

### T-2: TT_ParetoRootCause

**Anchor visual:** Page 3 Panel A — Root Cause Downtime Pareto Bar Chart
(x-axis = `dim_components[pipeline_label]`; y-axis = `[Root Cause Downtime Min]` D-07)

**Tooltip trigger:** Hover on any component bar in the Pareto chart.

**Canvas specification:**

| Setting | Value |
|---|---|
| Page name | `TT_ParetoRootCause` |
| Canvas type | Tooltip |
| Hide page | ON |
| Canvas size | 320 × 200 px |
| Background | #0D1117 (matches Page 3 dark canvas) |
| Text colour override | #ECEFF1 (white text on dark bg) |

**Visual layout (4 elements):**

```
+------------------------------------------------------+
|  [Component Name]  Root Cause Drill      (text box)  |
|  ---------------------------------------------------  |
|  MTBF (hrs)           [C-02 value]   0 dp + " hrs"   |
|  MTTR (hrs)           [C-03 value]   1 dp, red >8h   |
|  CCI Tier             [D-06 value]   colour-coded    |
|  Root Cause DT (min)  [D-07 value]   0 dp + " min"   |
+------------------------------------------------------+
```

**Element specifications:**

| Slot | Visual Type | Measure / Field | Format Rule |
|---|---|---|---|
| Header row | Text box | `dim_components[pipeline_label]` + " Root Cause Drill" | Segoe UI 9 pt Bold, #ECEFF1 |
| MTBF | Card | `[MTBF Hours]` (C-02) | 0 dp; suffix " hrs"; colour #ECEFF1 |
| MTTR | Card | `[MTTR Hours]` (C-03) | 1 dp; suffix " hrs"; CF: >8 -> #C62828, <=8 -> #2E7D32 |
| CCI Tier | Card | `[CCI Tier Label]` (D-06) | Text; CF: Critical=#C62828, High=#F57F17, Moderate=#F9A825, Low=#2E7D32 |
| Root Cause DT | Card | `[Root Cause Downtime Min]` (D-07) | 0 dp; suffix " min"; colour #ECEFF1 |

**Power BI Desktop configuration steps:**

1. Insert new page -> Rename to `TT_ParetoRootCause`.
2. Page properties -> Canvas settings -> Type = Tooltip.
3. Page properties -> Hide page = ON; Allow use as tooltip = ON.
4. Set canvas background: Format -> Wallpaper -> Color = #0D1117; Transparency = 0%.
5. Navigate to Page 3 -> Select Panel A (Pareto bar chart) -> Format -> Tooltip -> Type = Report page -> Page = `TT_ParetoRootCause`.
6. On `TT_ParetoRootCause`: insert Text Box (header) + 4 Card visuals per layout above.
7. Override all Card text colours to #ECEFF1 via Format -> Data labels -> Font color.
8. Apply CCI Tier CF: Format -> Data labels -> fx -> Field value -> `[Criticality Bar Colour]` (D-15).

**DAX measures required:**
- `[MTBF Hours]` C-02
- `[MTTR Hours]` C-03
- `[CCI Tier Label]` D-06 (also needed: D-15 for CF colour)
- `[Root Cause Downtime Min]` D-07

---

### T-3: TT_WaterfallLoss

**Anchor visual:** Page 1 Panel C — OEE Waterfall / Six Big Losses Decomposition
(Category = `dim_components[pipeline_label]`; Values = OEE loss percentage points)

**Tooltip trigger:** Hover on any loss bar or segment in the OEE Waterfall chart.

**Canvas specification:**

| Setting | Value |
|---|---|
| Page name | `TT_WaterfallLoss` |
| Canvas type | Tooltip |
| Hide page | ON |
| Canvas size | 320 × 200 px |
| Background | #FFFFFF (matches Page 1 Panel C card background) |
| Padding | 8 px inter-row |

**Visual layout (5 elements):**

```
+------------------------------------------------------+
|  [Component Name]  OEE Loss Breakdown    (text box)  |
|  ---------------------------------------------------  |
|  Availability Loss    [B-xx value]  %  amber/red     |
|  Performance Loss     [B-xx value]  %  amber/red     |
|  Quality Loss         [B-xx value]  %  amber/red     |
|  Composite OEE        [B-01 value]  %  state colour  |
+------------------------------------------------------+
```

**Element specifications:**

| Slot | Visual Type | Measure / Field | Format Rule |
|---|---|---|---|
| Header row | Text box | `dim_components[pipeline_label]` + " OEE Loss Breakdown" | Segoe UI 9 pt Bold, #37474F |
| Availability Loss | Card | `[Availability Loss PP]` (Group B) | % 1 dp; CF: >0.15 -> #C62828, >0.05 -> #F57F17, <=0.05 -> #2E7D32 |
| Performance Loss | Card | `[Performance Loss PP]` (Group B) | Same CF thresholds |
| Quality Loss | Card | `[Quality Loss PP]` (Group B) | Same CF thresholds |
| Composite OEE | Card | `[System OEE]` (B-01) | % 1 dp; CF: <65% -> #C62828, 65-74% -> #F57F17, 75-84% -> #F9A825, >=85% -> #2E7D32 |

**Power BI Desktop configuration steps:**

1. Insert new page -> Rename to `TT_WaterfallLoss`.
2. Page properties -> Canvas settings -> Type = Tooltip.
3. Page properties -> Hide page = ON; Allow use as tooltip = ON.
4. Navigate to Page 1 -> Select Panel C (Waterfall chart) -> Format -> Tooltip -> Type = Report page -> Page = `TT_WaterfallLoss`.
5. On `TT_WaterfallLoss`: insert Text Box (header, 28 px) + 4 Card visuals (rows, 36 px each, 8 px gap).
6. System OEE card: apply CF via Format -> Data labels -> fx -> Field value -> `[OEE Status Colour]` measure.
7. Loss cards: apply CF via Rules method (Format -> fx -> Rules) using percentage breakpoints above.

**DAX measures required:**
- `[System OEE]` B-01
- `[Availability Loss PP]`, `[Performance Loss PP]`, `[Quality Loss PP]` (Group B)

---

### Tooltip Page Registration Summary

| Tooltip ID | Page Name | Anchor Page | Anchor Visual | Canvas |
|---|---|---|---|---|
| T-1 | `TT_HealthScoreTrend` | Page 1 | Panel A (Health Score Line) | 320x200, White bg |
| T-2 | `TT_ParetoRootCause` | Page 3 | Panel A (Root Cause Pareto) | 320x200, Dark #0D1117 |
| T-3 | `TT_WaterfallLoss` | Page 1 | Panel C (OEE Waterfall) | 320x200, White bg |

All three: Canvas type = Tooltip, Hide page = ON, Allow use as tooltip = ON.
Font standard: Segoe UI 9 pt (L7 Tooltip Text from Day 32 font hierarchy).

---

## Part 2 — UI/UX Standardization: Day 32/33 Polish Pass

### 2.1 Font Hierarchy Compliance (L1-L10)

All visuals across Pages 1, 2, and 3 must conform to the 10-level font hierarchy locked on Day 32.

| Level | Element | Font | Size | Weight | Colour |
|---|---|---|---|---|---|
| L1 | Page title banner | Segoe UI | 14 pt | Bold | #FFFFFF on #1A237E banner |
| L2 | KPI card primary value | Segoe UI | 28 pt | Bold | Conditional state colour |
| L3 | KPI card label | Segoe UI | 10 pt | Regular | #546E7A |
| L4 | Chart/panel title | Segoe UI | 11 pt | Bold | #37474F |
| L5 | Axis label | Segoe UI | 9 pt | Regular | #546E7A |
| L6 | Data label (on-bar/bubble) | Segoe UI | 8 pt | Regular | #FFFFFF or #37474F |
| L7 | Tooltip text | Segoe UI | 9 pt | Regular | #37474F |
| L8 | Legend entry | Segoe UI | 8 pt | Regular | Match series colour |
| L9 | Matrix table cell | Segoe UI | 9 pt | Regular | #212121 |
| L10 | Slicer chip | Segoe UI | 9 pt | Regular | #37474F |

**Per-Page Compliance Checklist:**

Page 1 - Fleet Overview:
- [ ] L1: Page title banner - Segoe UI 14 pt Bold, white on #1A237E.
- [ ] L2: All 5 KPI card values - 28 pt Bold.
- [ ] L3: All 5 KPI card labels - 10 pt Regular, #546E7A.
- [ ] L4: Panel A, B, C titles - 11 pt Bold, left-aligned, #37474F.
- [ ] L5: All axis labels - 9 pt Regular, #546E7A.
- [ ] L6: Panel C waterfall data labels - 8 pt Regular.
- [ ] L8: Panel A legend - 8 pt, match component series colour.
- [ ] L10: Slicer chips - 9 pt, #37474F.

Page 2 - Component Health:
- [ ] L1: Banner - same spec.
- [ ] L2: All 5 KPI cards (MTBF, MTTR, Health, OEE, CCI) - 28 pt Bold.
- [ ] L4: All panel titles (A-F) - 11 pt Bold, left-aligned.
- [ ] L5: All axes - 9 pt, #546E7A.
- [ ] L6: Panel C, D data labels - 8 pt.
- [ ] L8: Panel A (MTBF/MTTR), Panel B (radar) legends - 8 pt.

Page 3 - Alert/Risk Summary:
- [ ] L1: Banner - 14 pt Bold, white on #1A237E.
- [ ] L2: All 5 KPI cards - 28 pt Bold, conditional colour.
- [ ] L4: Panels A-D titles - 11 pt Bold, left-aligned.
- [ ] L5: All axes - 9 pt, #546E7A.
- [ ] L9: Panel C matrix cells - 9 pt, #212121.
- [ ] L10: All slicer chips - 9 pt, #37474F.

---

### 2.2 Left-Aligned Title Standardization

All panel and page titles: left-aligned (not centred, not right-aligned).
Power BI Desktop path: Select visual -> Format -> General -> Title -> Title text alignment = Left.

Applies to all visuals on Pages 1, 2, 3 and all tooltip page header text boxes.

---

### 2.3 Canonical Colour Palette Reference

**State colours (OEE and Health Score):**

| State | Trigger Condition | Hex Code |
|---|---|---|
| WORLD CLASS / Healthy | Health >= 75 or OEE >= 85% | #2E7D32 |
| WORLD CLASS OEE card bg | System OEE >= 85% | #00695C |
| ACCEPTABLE | Health 65-74 or OEE 75-84% | #F9A825 |
| ALERT | Health 50-64 or OEE 65-74% | #F57F17 |
| CRITICAL | Health < 50 or OEE < 65% | #C62828 |

**Alert colours:** Alarm (ISO Zone C) = #F57F17 | Danger (ISO Zone D) = #C62828 | Clean = #2E7D32

**CCI Tier colours:** Critical (>=0.75) = #C62828 | High (0.50-0.74) = #F57F17 | Moderate (0.25-0.49) = #F9A825 | Low (<0.25) = #2E7D32

**5-Component series colours (locked Day 23):**
Bearing = #1565C0 | Shaft = #6A1B9A | Motor Housing = #00695C | Coupling = #E65100 | Gearbox = #37474F

**Structural neutrals:**
Canvas bg (P1/P2) = #F5F5F5 | Canvas bg (P3) = #0D1117 | Card/panel bg = #FFFFFF | Grid = #ECEFF1
Primary text = #212121 | Secondary/axis text = #546E7A | Banner bg = #1A237E | Pipeline label fill = #37474F

---

### 2.4 Legend Cleanup Rules

All legend titles hidden. Legend items reduced to essential entries only.

| Visual | Legend | Title | Notes |
|---|---|---|---|
| Page 1 Panel A (Line) | ON | OFF | 5 component labels, match series colour, bottom-centre |
| Page 1 Panel B (Bar) | OFF | N/A | Y-axis component names are self-describing |
| Page 1 Panel C (Waterfall) | ON | OFF | Loss type labels only, right side |
| Page 2 Panel A (Line) | ON | OFF | "MTBF (Hours)" Teal, "MTTR (Hours)" Amber, bottom-centre |
| Page 2 Panel B (Radar) | ON | OFF | "Component" teal fill, "Fleet Avg" grey dashed, top-right |
| Page 2 Panel F (Bar) | OFF | N/A | CCI tier legend = static text box only |
| Page 3 Panel A (Bar) | ON | OFF | Sensor type colour entries, right side |
| Page 3 Panel B (Scatter) | OFF | N/A | Quadrant labels = static text boxes |
| Page 3 Panel C (Matrix) | OFF | N/A | CF via E-08 only |
| Page 3 Panel D (Line) | ON | OFF | "Alarm Zone" Amber, "Danger Zone" Red, bottom-centre |
| All Tooltip Pages | OFF | N/A | Card visuals have no legend |

---

## Part 3 — Interactivity Verification Test Script

### Test Execution Protocol

- Environment: Power BI Desktop, Editing view (for Edit Interactions) + Reading view (user experience).
- Data state: SQLite production DB loaded; dim_calendar covers 2026-07-20 to 2027-07-20; all 5 components.
- Slicer baseline: Date Range = full window; Component = ALL; Sensor Type = ALL.
- Result codes: PASS / FAIL / BLOCKED.

---

### 3.1 Drill-Through Routing Tests (DT-01 to DT-04)

#### DT-01 — Page 1 Panel B -> Page 2 (Health Score Bar Drill-Through)

| Field | Value |
|---|---|
| Source | Page 1 -> Panel B (Min Health Score by Component, Clustered Bar) |
| Action | Right-click any component bar -> "Drill through" -> select "Component Health" |
| Expected - Navigation | Page 2 opens; Back button at X=1190 Y=10 W=80 H=30, bg #00695C, white font |
| Expected - Filter | dim_components[component_id] filter applied to right-clicked component |
| Expected - Measures | D-01 through D-06 all non-BLANK |
| Pre-condition | Panel B Y-axis must have `dim_components[component_id]` in field hierarchy below `pipeline_label` |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |
| Notes | _Record component_id passed, any blank measures, Back button position._ |

#### DT-02 — Page 1 Panel C -> Page 2 (Waterfall Loss Drill-Through)

| Field | Value |
|---|---|
| Source | Page 1 -> Panel C (OEE Waterfall / Six Big Losses) |
| Action | Right-click any loss bar for a specific component -> "Drill through" -> "Component Health" |
| Expected - Navigation | Page 2 opens; Back button at specified coordinates |
| Expected - Filter | `dim_components[component_id]` of clicked component is applied |
| Expected - Measures | `[MTBF vs Weibull Delta]` and all Group D criticality measures non-BLANK |
| Pre-condition | Waterfall Category well must contain `dim_components[component_id]` below `pipeline_label` as hierarchy level (not in Tooltips only) |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |
| Notes | _If drill-through greyed out: confirm component_id is in Category hierarchy, not Tooltips._ |

#### DT-03 — Page 3 Panel A -> Page 2 (Root Cause Pareto Drill-Through)

| Field | Value |
|---|---|
| Source | Page 3 -> Panel A (Root Cause Downtime Pareto Bar) |
| Action | Right-click any component bar -> "Drill through" -> "Component Health" |
| Expected - Navigation | Page 2 opens correctly |
| Expected - Filter | Component filter matches the right-clicked bar component |
| Expected - Measures | `[MTBF vs Weibull Delta]` non-zero; `[CCI Score]` D-01 non-BLANK |
| Expected - Slicer | Date Range filter from Page 3 carries through (Keep all filters = ON) |
| Pre-condition | Panel A X-axis must have `dim_components[component_id]` below `pipeline_label` in hierarchy |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |
| Notes | _Verify date filter propagation: set Page 3 date to 3-month window, drill, confirm Page 2 MTBF reflects same window._ |

#### DT-04 — Page 3 Panel B -> Page 2 (Scatter Risk Matrix Drill-Through)

| Field | Value |
|---|---|
| Source | Page 3 -> Panel B (Risk Prioritization Scatter Chart) |
| Action | Right-click any component bubble -> "Drill through" -> "Component Health" |
| Expected - Navigation | Page 2 opens with correct component filter |
| Expected - Filter | `dim_components[component_id]` from bubble Details well is passed as drill-through key |
| Expected - Measures | All Group D measures non-BLANK; Page 2 Panel B radar shows drilled component vs fleet |
| Pre-condition | Scatter Details well must contain `dim_components[component_id]` (X/Y/Size are all continuous measures) |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |
| Notes | _If right-click shows no drill-through: component_id not in Details well._ |

**Drill-Through Summary:**

| Test | Source | Target | Pass? |
|---|---|---|---|
| DT-01 | Page 1 Panel B Bar | Page 2 | |
| DT-02 | Page 1 Panel C Waterfall | Page 2 | |
| DT-03 | Page 3 Panel A Pareto | Page 2 | |
| DT-04 | Page 3 Panel B Scatter | Page 2 | |

---

### 3.2 Sync Slicer Propagation Tests (SS-01 to SS-05)

**Sync matrix reference:**

| Slicer | Page 1 | Page 2 | Page 3 |
|---|---|---|---|
| Date Range | Sync=ON, Visible=ON | Sync=ON, Visible=ON | Sync=ON, Visible=ON |
| Component | Sync=ON, Visible=ON | Sync=ON, Visible=OFF | Sync=ON, Visible=ON |
| Sensor Type | Not present | Not present | Sync=OFF, Visible=ON |

#### SS-01 — Date Change Page 1 -> Page 2

| Field | Value |
|---|---|
| Action | Page 1: set Date Range to Q1 2027 (Jan-Mar). Navigate to Page 2. |
| Expected | Page 2 Panel A x-axis shows Jan-Mar 2027 only. Date slicer reflects same selection. |
| Failure | If full year shown: check View -> Sync slicers -> Date Range -> Page 1 and Page 2 both Sync=ON. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### SS-02 — Date Propagates Page 2 -> Page 3

| Field | Value |
|---|---|
| Action | Page 2: set Date Range to Q2 2027 (Apr-Jun). Navigate to Page 3. |
| Expected | E-01 [Total Active Alerts] reflects Q2 2027 only. Panel D x-axis shows Apr-Jun. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### SS-03 — Date Change Page 3 -> Page 1 Back-Propagation

| Field | Value |
|---|---|
| Action | Page 3: set Date Range to May-Jul 2027. Navigate to Page 1. |
| Expected | Page 1 Panel A health lines show May-Jul 2027 trend only. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### SS-04 — Component Slicer Page 1 -> Page 3

| Field | Value |
|---|---|
| Action | Page 1: select "Bearing" in Component slicer. Navigate to Page 3. |
| Expected | Page 3 Panel A shows Bearing bar only. E-01 reflects Bearing anomalies only. Component slicer on Page 3 shows "Bearing". |
| Failure | If all 5 shown: Component slicer Sync=ON not configured for Page 3. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### SS-05 — Component Slicer Visible=OFF on Page 2 - Filter Persistence

| Field | Value |
|---|---|
| Action | Drill-through from Page 1 to Page 2 for "Coupling". Verify no Component slicer visible. Verify D-01 = 0.804 (Coupling CCI). |
| Expected | No Component slicer visible on Page 2 canvas. D-01 returns Coupling-specific value. All Group D non-BLANK. |
| Rationale | Sync=ON preserves drill-through filter invisibly. Visible=OFF prevents SELECTEDVALUE() breakage. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

**Sync Slicer Summary:**

| Test | Slicer | Source -> Target | Pass? |
|---|---|---|---|
| SS-01 | Date Range | Page 1 -> Page 2 | |
| SS-02 | Date Range | Page 2 -> Page 3 | |
| SS-03 | Date Range | Page 3 -> Page 1 | |
| SS-04 | Component | Page 1 -> Page 3 | |
| SS-05 | Component (Visible=OFF) | Drill-through -> Page 2 | |

---

### 3.3 KPI Card Anchor Tests (KA-01 to KA-05)

**Anchor policy:** All KPI cards on all three pages receive No Interaction from every non-slicer visual.
**Test protocol:** Record KPI values BEFORE clicking. Click specified visual. Values must be identical AFTER.

#### KA-01 — Page 1 Panel A Click -> KPI Cards Unchanged

| Field | Value |
|---|---|
| Action | Page 1 Reading view. Record all 5 KPI card values. Click any series point in Panel A (Health Score Line). |
| Expected | All 5 KPI values identical before and after click. |
| Remediation | Panel A in Editing view -> Format -> Edit Interactions -> set No Interaction on all 5 card targets. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### KA-02 — Page 1 Panel C Waterfall Click -> KPI Cards Unchanged

| Field | Value |
|---|---|
| Action | Page 1. Record KPI values. Click any loss bar in Panel C (OEE Waterfall). |
| Expected | All 5 KPI values identical before and after click. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### KA-03 — Page 2 Panel A MTBF Trend Click -> KPI Cards Unchanged

| Field | Value |
|---|---|
| Action | Drill to Page 2 for any component. Record KPI values. Click monthly point in Panel A (MTBF/MTTR Line). |
| Expected | All 5 Page 2 KPI cards unchanged. Also verifies Panel A -> Panel B and Panel A -> Panel D suppressions. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### KA-04 — Page 2 Panel E Health Trend Click -> KPI Cards Unchanged

| Field | Value |
|---|---|
| Action | Page 2. Record KPI values. Click historical trend point on Panel E (Health Score Trend with Alarm Band). |
| Expected | All 5 KPI cards show component-level averages for drill-through date range, not single-day value. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### KA-05 — Page 3 Panels A-D Click -> KPI Cards Unchanged

| Field | Value |
|---|---|
| Source panels | Panel A (Bar), Panel B (Scatter), Panel C (Matrix cell), Panel D (Line) |
| Action | Page 3. Record E-01 to E-05 KPI values. Sequentially click one bar in A, one bubble in B, one cell in C, one date in D. |
| Expected | KPI cards E-01 to E-05 unchanged across all 4 panel click events. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

**KPI Anchor Summary:**

| Test | Source Visual | Cards Protected | Pass? |
|---|---|---|---|
| KA-01 | Page 1 Panel A Line | 5 KPI cards Page 1 | |
| KA-02 | Page 1 Panel C Waterfall | 5 KPI cards Page 1 | |
| KA-03 | Page 2 Panel A MTBF Line | 5 KPI cards Page 2 | |
| KA-04 | Page 2 Panel E Health Trend | 5 KPI cards Page 2 | |
| KA-05 | Page 3 Panels A-D (all) | 5 KPI cards Page 3 | |

---

### 3.4 Scatter Plot No Interaction Tests (SI-01 to SI-03)

**Background:** Page 3 Panel B scatter (CCI vs Health vs Alert count) must not respond to sensor-type
filtering or date-click events. CCI and Health are sensor-agnostic composite measures.

**Baseline:** Record all 5 bubble X-positions (CCI), Y-positions (Health), and sizes (Alerts) before each test.

#### SI-01 — Sensor Type Slicer -> Scatter Unchanged

| Field | Value |
|---|---|
| Action | Page 3. Record all 5 bubble positions/sizes. Select "vibration" in Sensor Type slicer. |
| Expected | All 5 bubble positions (X, Y) identical. Sizes identical. Panels A, C, D update; Panel B does NOT. |
| Rationale | CCI (D-01) is composite of SRS + Unreliability + TBR - not sensor-type-specific. Suppressed via Edit Interactions: Sensor Type Slicer -> Panel B = No Interaction. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### SI-02 — Panel D Alert Trend Click -> Scatter Unchanged

| Field | Value |
|---|---|
| Action | Page 3. Record bubble positions/sizes. Click a date point in Panel D (Alert Trend Line). |
| Expected | Panel D highlights clicked date. Panel B scatter - all 5 bubbles retain identical positions/sizes. |
| Rationale | Single-day cross-filter would collapse bubble sizes to that day's alert count. Suppressed via Edit Interactions: Panel D -> Panel B = No Interaction. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

#### SI-03 — Panel C Violation Rate Cell Click -> Scatter Unchanged

| Field | Value |
|---|---|
| Action | Page 3. Record bubble positions/sizes. Click a high-violation cell in Panel C (Violation Rate Matrix). |
| Expected | Panel C highlights selected row. Panel B scatter - all 5 bubbles retain identical positions/sizes. |
| Rationale | component x sensor_type filter would distort CCI/Health to single-channel subset. Suppressed: Panel C -> Panel B = No Interaction. |
| **Result** | **[ ] PASS / [ ] FAIL / [ ] BLOCKED** |

**Scatter No Interaction Summary:**

| Test | Source | Expected Scatter State | Pass? |
|---|---|---|---|
| SI-01 | Sensor Type slicer -> Panel B | No change in positions/sizes | |
| SI-02 | Panel D click -> Panel B | No change in positions/sizes | |
| SI-03 | Panel C cell click -> Panel B | No change in positions/sizes | |

---

## Part 4 — E-01 SQL Cross-Validation: Anomaly Count Audit

### 4.1 Objective

Verify that `[Total Active Alerts]` (E-01) reports the same integer count as SQLite `sensor_readings`
for the full simulation window with no component or sensor-type filter applied.

This confirms:
1. ETL correctly set `is_anomaly = 1` on all threshold-breaching readings.
2. M query loaded all rows without duplication or truncation.
3. DAX measure E-01 evaluates against the full dataset with slicers at ALL/default.
4. `dim_calendar` date range covers the entire simulation window (2026-07-20 to 2027-07-20).

---

### 4.2 SQL Cross-Validation Queries

**Primary query — total anomaly count:**

```sql
-- E-01 Cross-Validation: total anomaly count
-- Must match Power BI [Total Active Alerts] (E-01) with Date Range = full window, Component = ALL
SELECT
    COUNT(*) AS total_anomaly_count,
    COUNT(DISTINCT component_id) AS components_with_anomalies,
    COUNT(DISTINCT sensor_id) AS sensors_with_anomalies,
    MIN(ts) AS earliest_anomaly_ts,
    MAX(ts) AS latest_anomaly_ts
FROM sensor_readings
WHERE is_anomaly = 1;
```

**Per-component breakdown (for component-filtered E-01 verification):**

```sql
-- Per-component anomaly count
-- Each row must match Power BI E-01 when Component slicer = that component
SELECT
    sr.component_id,
    c.component_name,
    COUNT(*) AS anomaly_count,
    COUNT(DISTINCT sr.sensor_id) AS sensors_triggering,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total
FROM sensor_readings sr
JOIN components c ON sr.component_id = c.component_id
WHERE sr.is_anomaly = 1
GROUP BY sr.component_id, c.component_name
ORDER BY anomaly_count DESC;
```

**Sensor-type breakdown (for E-06 Panel A alignment):**

```sql
-- Per-sensor-type anomaly count
-- Validates [Alert Count by Sensor Type] (E-06) groupings on Page 3 Panel A
SELECT
    s.sensor_type,
    COUNT(*) AS anomaly_count
FROM sensor_readings sr
JOIN sensors s ON sr.sensor_id = s.sensor_id
WHERE sr.is_anomaly = 1
GROUP BY s.sensor_type
ORDER BY anomaly_count DESC;
```

---

### 4.3 Python Execution Procedure

```python
# E-01 Cross-Validation Script
# Run from: c:\Users\Hement Kitukale\Desktop\Resume project\
import sqlite3
import pandas as pd

DB_PATH = r"c:\Users\Hement Kitukale\Desktop\Resume project\data\manufacturing.db"

conn = sqlite3.connect(DB_PATH)

# Main count
sql_total = pd.read_sql_query(
    "SELECT COUNT(*) AS total_anomaly_count FROM sensor_readings WHERE is_anomaly = 1",
    conn
)
print(f"SQL total anomaly count: {sql_total['total_anomaly_count'].iloc[0]}")

# Per-component breakdown
sql_by_component = pd.read_sql_query("""
    SELECT sr.component_id, c.component_name, COUNT(*) AS anomaly_count
    FROM sensor_readings sr
    JOIN components c ON sr.component_id = c.component_id
    WHERE sr.is_anomaly = 1
    GROUP BY sr.component_id, c.component_name
    ORDER BY anomaly_count DESC
""", conn)
print("\nPer-component breakdown:")
print(sql_by_component.to_string(index=False))

conn.close()
```

**Power BI read procedure:**
1. Open manufacturing_analytics.pbix in Power BI Desktop.
2. Navigate to Page 3.
3. Set Date Range = 2026-07-20 to 2027-07-20 (full simulation window).
4. Set Component = ALL. Set Sensor Type = ALL.
5. Read KPI Card 1 value = [Total Active Alerts] (E-01).

---

### 4.4 Result Comparison Table

| Metric | SQL Value | Power BI E-01 | Match? |
|---|---|---|---|
| Total anomaly count | _[to be filled]_ | _[to be filled]_ | [ ] YES / [ ] NO |
| Earliest anomaly ts | _[to be filled]_ | N/A | N/A |
| Latest anomaly ts | _[to be filled]_ | N/A | N/A |

**Per-component comparison:**

| Component | SQL Count | Power BI (component filtered) | Match? |
|---|---|---|---|
| Bearing (ID=1) | | | |
| Shaft (ID=2) | | | |
| Motor Housing (ID=3) | | | |
| Coupling (ID=4) | | | |
| Gearbox (ID=5) | | | |
| **TOTAL** | | | |

---

### 4.5 Failure Mode Diagnostics

| Discrepancy Pattern | Root Cause | Remediation |
|---|---|---|
| Power BI < SQL total | dim_calendar date range does not cover all ts values | Extend dim_calendar end date to cover max(ts). Refresh. |
| Power BI > SQL total | ETL loaded same CSV twice - duplicate rows in fact_sensor_readings | Check: SELECT COUNT(*) vs SELECT COUNT(DISTINCT reading_id). Drop duplicates, reload. |
| Match total, diverge per component | Wrong relationship key on active relationship | Verify: fact_sensor_readings[component_id] -> dim_components[component_id] uses INTEGER, not string. |
| BLANK in Power BI | E-01 measure not evaluating correctly | Check E-01 DAX: CALCULATE(COUNTROWS(...), is_anomaly = 1). Confirm is_anomaly stored as INTEGER (1/0). |

---

### 4.6 Cross-Validation Result Log

```
E-01 SQL Cross-Validation - Day 33 Execution Log
=================================================
Date executed:    2026-08-15
Database:         manufacturing.db (SQLite)
SQL tool:         Python / sqlite3 module

SQL total anomaly count   : [TO BE FILLED ON EXECUTION]
Power BI E-01 value       : [TO BE FILLED ON EXECUTION]
Timestamp range (SQL)     : 2026-07-20 to 2027-07-20 [verify against actual min/max]
Components with anomalies : [TO BE FILLED]
Sensors triggering        : [TO BE FILLED]

VERDICT: [ ] PASS (integer exact match) / [ ] FAIL (see diagnostics in 4.5)
```

---

## Part 5 — Day 33 Test Execution Summary

### 5.1 Full 18-Test Matrix

| Category | Test ID | Description | Result | Notes |
|---|---|---|---|---|
| Drill-Through | DT-01 | Page 1 Panel B -> Page 2 | | |
| Drill-Through | DT-02 | Page 1 Panel C -> Page 2 | | |
| Drill-Through | DT-03 | Page 3 Panel A -> Page 2 | | |
| Drill-Through | DT-04 | Page 3 Panel B -> Page 2 | | |
| Sync Slicers | SS-01 | Date P1 -> P2 | | |
| Sync Slicers | SS-02 | Date P2 -> P3 | | |
| Sync Slicers | SS-03 | Date P3 -> P1 | | |
| Sync Slicers | SS-04 | Component P1 -> P3 | | |
| Sync Slicers | SS-05 | Component Visible=OFF P2 | | |
| KPI Anchors | KA-01 | P1 Panel A -> Cards | | |
| KPI Anchors | KA-02 | P1 Panel C -> Cards | | |
| KPI Anchors | KA-03 | P2 Panel A -> Cards | | |
| KPI Anchors | KA-04 | P2 Panel E -> Cards | | |
| KPI Anchors | KA-05 | P3 All Panels -> Cards | | |
| Scatter | SI-01 | Sensor slicer -> P3 Panel B | | |
| Scatter | SI-02 | P3 Panel D -> P3 Panel B | | |
| Scatter | SI-03 | P3 Panel C -> P3 Panel B | | |
| SQL Validation | E-01 | Anomaly count cross-check | | |

**Total tests: 18 (4 DT + 5 SS + 5 KA + 3 SI + 1 SQL)**

---

### 5.2 Go/No-Go Criteria for Day 34

| Condition | Threshold |
|---|---|
| Drill-Through tests | All 4 PASS (DT-01 through DT-04) |
| Sync Slicer tests | All 5 PASS (SS-01 through SS-05) |
| KPI Card Anchor tests | All 5 PASS (KA-01 through KA-05) |
| Scatter No Interaction | All 3 PASS (SI-01 through SI-03) |
| SQL Cross-Validation | Integer exact match (E-01 SQL = E-01 Power BI) |

Day 34 (End-to-End Integration) proceeds when all 18 tests are PASS or BLOCKED with known remediation.

---

### 5.3 Tooltip Page Build Verification Checklist

| Tooltip | Page Created | Canvas Type = Tooltip | Hide page = ON | Anchor Linked | Measures Load |
|---|---|---|---|---|---|
| T-1 TT_HealthScoreTrend | [ ] | [ ] | [ ] | P1 Panel A | [ ] |
| T-2 TT_ParetoRootCause | [ ] | [ ] | [ ] | P3 Panel A | [ ] |
| T-3 TT_WaterfallLoss | [ ] | [ ] | [ ] | P1 Panel C | [ ] |

---

*End of Day 33 verification script.*
*All test result fields to be filled during Power BI Desktop review session.*
*Day 34: End-to-end integration testing — full pipeline -> SQLite -> Power BI refresh cycle.*
