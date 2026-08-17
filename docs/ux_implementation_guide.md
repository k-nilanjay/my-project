# UX Implementation Guide -- Manufacturing Digital Twin Dashboard
**Project:** Manufacturing Analytics Digital Twin  
**Phase:** 2.3 Power BI Build  
**Day:** 24  
**Date:** 2026-08-08  
**Status:** Implementation Reference -- for use in Power BI Desktop  
**Companion files:** `docs/visual_design_blueprint.md` | `powerbi_theme.json` | `docs/dax_and_m_scripts.md`

---

## 0. Purpose

This guide translates the Day 23 visual design specification into exact, step-by-step Power BI Desktop layout instructions. Where `docs/visual_design_blueprint.md` explains *what* to build and *why*, this guide specifies *exactly how* to build it: pixel dimensions, Z-pattern placement sequences, slicer sync mechanics, and drill-through button configuration.

Three things are documented here:

1. **Multi-page layout mechanics** -- Z-pattern visual placement grids for all 3 pages, with canvas coordinates and panel proportions.
2. **Slicer sync configuration** -- Exact steps for View > Sync Slicers across the 3 pages, including hidden-but-synced mechanics for the drill-through page.
3. **Drill-through button placement** -- Where, how, and when to place drill-through triggers and the Back button.

---

## 1. Canvas Setup

### 1.1 Page Canvas Size (All 3 Pages)

In Power BI Desktop: **File > Page Setup**

| Setting | Value | Rationale |
|---|---|---|
| Page size | Custom | 16:9 widescreen for monitor display |
| Width | 1280 px | Standard 1280 fits most 1366+ screens without horizontal scroll |
| Height | 720 px | 16:9 ratio; matches most presentation and monitor contexts |
| Canvas background | `#F5F5F5` (Light Grey) | From `powerbi_theme.json`. White on white loses panel separation. |

> **Apply canvas settings before placing any visual.** Resizing canvas after placing visuals misaligns all padding-relative positions.

---

## 2. Z-Pattern Layout Mechanics

The Z-pattern reading order is the UX foundation of all 3 pages. The human eye traces:

```
1. Top-left → Top-right   (Zone 1: KPI cards -- primary status bar)
2. Diagonal ↘             (Zone 2: Primary chart -- the analytical anchor)
3. Bottom-left → Bottom-right (Zone 3: Supporting detail panels)
```

This mirrors standard dashboard reading behavior: users check "is anything on fire?" (Zone 1), then read the main trend (Zone 2), then investigate detail (Zone 3).

---

### 2.1 Page 1 -- Fleet Overview Layout

**Audience:** Maintenance manager, operations lead  
**Primary question:** "Is the fleet healthy? Which component needs attention today?"

#### Zone Layout Grid (1280 × 720 canvas)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ZONE 1: KPI Card Row  (y: 0–100)                                             │
│ [E-01 Total Alerts] [E-02 Danger Zone] [E-03 Alarm Zone] [E-04 Most Alert.] [E-05 Critical Count] │
├─────────────────────────────────────────────────────────────────────────────┤
│ FILTER PANEL (y: 100–160)                                                    │
│ [Date Slicer] [Sensor Type Slicer]                                          │
├──────────────────────────────────────┬──────────────────────────────────────┤
│ ZONE 2 (PRIMARY ANCHOR)              │ PANEL B (40%)                        │
│ PANEL A: Stacked Bar -- Fleet Alert  │ Scatter Chart -- Risk Prioritization │
│ Inventory by Component + Sensor Type │ Matrix (CCI vs Health)              │
│ Width: 768 px (60%)                  │ Width: 502 px (40%)                 │
│ y: 165–435 (270 px)                  │ y: 165–435 (270 px)                 │
├──────────────────────────────────────┴──────────────────────────────────────┤
│ ZONE 3: Detail Panels                                                        │
│ PANEL C (50%): Matrix -- Threshold    │ PANEL D (50%): Line Chart --        │
│ Violation Frequency (Comp x Sensor)  │ Alert Trend Over Time                │
│ Width: 640 px  y: 440–670            │ Width: 635 px  y: 440–670           │
├──────────────────────────────────────────────────────────────────────────────┤
│ PANEL E (100%): Card -- Dynamic Status Banner (y: 675–720)                   │
│ Text: "Highest Risk: [COMPONENT] -- [TIER] | [N] Danger Zone Alerts Active"  │
│ Full width: 1280 px                                                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### Exact Visual Coordinates

| Panel | Visual Type | X | Y | Width | Height |
|---|---|---|---|---|---|
| KPI Card 1 (E-01 Total Alerts) | Card | 0 | 0 | 230 | 100 |
| KPI Card 2 (E-02 Danger Zone) | Card | 235 | 0 | 230 | 100 |
| KPI Card 3 (E-03 Alarm Zone) | Card | 470 | 0 | 230 | 100 |
| KPI Card 4 (E-04 Most Alerting) | Card | 705 | 0 | 230 | 100 |
| KPI Card 5 (E-05 Critical Count) | Card | 940 | 0 | 330 | 100 |
| Date Range Slicer | Slicer | 0 | 105 | 640 | 55 |
| Sensor Type Slicer | Slicer | 645 | 105 | 625 | 55 |
| Panel A -- Fleet Alert Inventory (ANCHOR) | Stacked Bar | 0 | 165 | 768 | 270 |
| Panel B -- Risk Prioritization Matrix | Scatter Chart | 773 | 165 | 502 | 270 |
| Panel C -- Threshold Violation Matrix | Matrix | 0 | 440 | 640 | 230 |
| Panel D -- Alert Trend Line | Line Chart | 645 | 440 | 635 | 230 |
| Panel E -- Status Banner | Card | 0 | 675 | 1280 | 45 |

---

## 3. Slicer Sync Configuration

### 3.1 Why Slicer Sync Matters

Without slicer sync, a user who selects "2027-07-13 to 2027-07-20" on Page 3, then navigates to Page 1, finds Page 1 still showing the 30-day view. The date context appears inconsistent. Sync Slicers solves this by making the date filter a global session state rather than per-page state.

### 3.2 Step-by-Step Slicer Sync Setup

In Power BI Desktop: **View > Sync Slicers**

This opens a panel showing all slicers and all pages in a matrix.

---

#### Slicer 1: Date Range (Between style)

**Present on:** Page 1 (top left), Page 2 (top center), Page 3 (top left)

**Sync configuration:**

| | Sync | Visible |
|---|---|---|
| Page 1 Fleet Overview | ✓ | ✓ |
| Page 2 Component Health | ✓ | ✓ |
| Page 3 Alert Risk Intelligence | ✓ | ✓ |

**Steps:**
1. Click the Date Range slicer on Page 1
2. Open **View > Sync Slicers**
3. Check **Sync** for Pages 1, 2, and 3
4. Check **Visible** for Pages 1, 2, and 3
5. Repeat click on Page 2 Date slicer → confirm same sync group appears (same slicer name)
6. Set global default: set filter to fixed date range (e.g. "2027-06-20 to 2027-07-20") to cover the final 30 days of the static simulation. Do NOT use relative time filtering as it will show a blank dashboard outside the simulation epoch.
7. Navigate to Page 3 and confirm the slicer correctly mirrors the 30-day range.

> **Technical note:** Synced slicers in Power BI share a single, global filter state. It is not possible to have a 30-day default on Page 1 and a 7-day default on Page 3 if the slicers are synced. We prioritize cross-page consistency, so the 30-day default will apply globally to all pages in this sync group.

---

#### Slicer 2: Component (Dropdown style)

**Present on:** Page 1 (visible)

**Sync configuration:**

| | Sync | Visible |
|---|---|---|
| Page 1 Fleet Overview | ✓ | ✓ |
| Page 2 Component Health | ✓ | ✗ |
| Page 3 Alert Risk Intelligence | ✓ | ✓ |

**Steps:**
1. Click the Component slicer on Page 1
2. Open **View > Sync Slicers**
3. Check **Sync** for Pages 1, 2, and 3
4. Check **Visible** for Pages 1 and 3 (leave Page 2 unchecked)
5. Set default = "All" on Page 1

**Why Sync=ON / Visible=OFF on Page 2?**  
Page 2 is a drill-through target. The `SELECTEDVALUE()` pattern used by Group D criticality measures relies on single-component filter context and returns BLANK() if multiple components are selected. Hiding the slicer while keeping Sync=ON preserves the drill-through filter state across a Page 2 -> Page 1 -> Page 2 round-trip while preventing any user action that would violate the single-component invariant.

---

#### Slicer 3: Sensor Type (List, multi-select -- Page 3 only)

| | Sync | Visible |
|---|---|---|
| Page 1 Fleet Overview | ✗ | ✗ |
| Page 2 Component Health | ✗ | ✗ |
| Page 3 Alert Risk Intelligence | local only | ✓ |

**Steps:**
1. Click Sensor Type slicer on Page 3
2. Open **View > Sync Slicers**
3. Leave all pages unchecked for both Sync and Visible except Page 3 (local only)
4. Source field: `dim_sensors[sensor_type]`

> **Sensor Type slicer rationale:** Page 3-specific. Filters Panels A, C, D to a single sensor modality. NOT synced to Pages 1/2 because those show composite fleet metrics, not sensor-type-specific alert counts.

---

#### Slicer 4: Severity (Dropdown style -- Optional / Deprecated)

| | Sync | Visible |
|---|---|---|
| Page 1 Fleet Overview | ✗ | ✗ |
| Page 2 Component Health | ✗ | ✗ |
| Page 3 Alert Risk Intelligence | ✗ | ✗ |

**Steps:**
1. If used (as an optional extension), source field: `fact_sensor_readings[iso_zone]`
2. Note: The M-script explicitly renames `iso_zone_label` to `iso_zone` (dropping the raw A/B/C/D codes entirely and storing the display labels directly in the `iso_zone` column). Therefore, bind directly to `iso_zone`.

---

#### Slicer 5: Shift Period (Dropdown: Night (00-08) / Day (08-16) / Evening (16-24) -- Page 2 only)

| | Sync | Visible |
|---|---|---|
| Page 1 Fleet Overview | ✗ | ✗ |
| Page 2 Component Health | local only | ✓ |
| Page 3 Alert Risk Intelligence | ✗ | ✗ |

**Steps:**
1. Click Shift Period slicer on Page 2
2. Open **View > Sync Slicers**
3. Leave all pages unchecked -- local only
4. Source field: `fact_sensor_readings[shift_period]` (values: Night (00-08), Day (08-16), Evening (16-24))

---

### 3.3 Slicer Sync Summary Table

| Slicer | P1 Sync | P1 Visible | P2 Sync | P2 Visible | P3 Sync | P3 Visible |
|---|---|---|---|---|---|---|
| Date Range | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Component | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ |
| Shift Period | ✗ | ✗ | local | ✓ | ✗ | ✗ |
| Sensor Type | ✗ | ✗ | ✗ | ✗ | local | ✓ |

---

## 4. Drill-Through Button Placement

### 4.1 Drill-Through Mechanism

Power BI drill-through works by:
1. Adding a field to the **Drill through field well** on the *destination* page (Page 2)
2. Power BI auto-enables right-click drill-through from any visual on any *source* page that has that field in context
3. Power BI auto-generates a **Back button** on the destination page

### 4.2 Page 2 Drill-Through Configuration

**Step-by-step:**
1. Navigate to **Page 2 Component Health** in Power BI Desktop
2. Click anywhere on the blank canvas (deselect all visuals)
3. In the **Visualizations pane**, find the **Drill through** section (below the Filters pane)
4. Drag `dim_components[component_id]` into the **Drill through** field well
5. Power BI automatically creates a **Back button** in the top-left of Page 2
6. The Back button is pre-wired to return the user to the page they drilled from (P1 or P3)

### 4.3 Back Button Positioning and Styling

| Property | Value |
|---|---|
| Position (X, Y) | 0, 105 (below KPI row, above slicers) |
| Width | 140 px |
| Height | 45 px |
| Action | Back (auto-configured by Power BI) |
| Fill color | `#1565C0` (Deep Blue from theme) |
| Text color | `#FFFFFF` |
| Text content | `← Fleet Overview` |
| Font | Segoe UI, 11pt, Bold |
| Border radius | 4 px |

**To customize the Back button:**
1. Click the auto-generated Back button
2. Format pane → **Button text** → change text to `← Fleet Overview`
3. Format pane → **Fill** → set color to `#1565C0`
4. Format pane → **Font** → Segoe UI, 11pt, white

### 4.4 Source Page Drill-Through Trigger Points

| Source Page | Trigger Visual | Field in Context | Destination |
|---|---|---|---|
| P1 Panel B | Horizontal bar chart (Health by Component) | `dim_components[component_id]` via Y-axis or Legend well | Page 2 |
| P3 Panel A | Stacked Bar (Fleet Alert Inventory) | `dim_components[component_id]` via X-axis, Y-axis, or Legend well | Page 2 |
| P3 Panel B | Scatter Chart (Risk Prioritization Matrix) | `dim_components[component_id]` via Details well | Page 2 |
| P3 Panel C | Matrix (Threshold Violation Frequency) | `dim_components[component_id]` via Rows well | Page 2 |

> **Important:** Drill-through filter context in Power BI is ONLY populated by fields in live data roles (Axis, Legend, Details, Rows, Columns, Values). Placing a field in Tooltips does NOT pass it to the drill-through destination. You MUST add `dim_components[component_id]` explicitly to the correct well for the visual type (e.g., Rows for Matrix, Y-axis for Bar Chart) for every source visual listed above. It cannot be passed implicitly via `component_name` or `pipeline_label`.

### 4.5 Optional Enhancement -- Tooltip Drill-Through Hint

To guide non-expert users, add a tooltip hint near each drill-through trigger visual:

1. Insert a **Text box** near the top-right corner of Panel B (P1) and Panel A/B (P3)
2. Text: *"💡 Right-click any bar / row → Drill Through → Component Health"*
3. Font size: 9pt, color: `#616161`, no background, no border
4. Group this text box with its parent visual (Ctrl+G) so it moves together

---

## 5. Cross-Filter Interaction Configuration

### 5.1 Default Cross-Filter Behavior

By default, clicking a bar in one chart filters all other visuals on the page. This is desirable in most cases but must be managed carefully.

**Edit Interactions** configuration (Format > Edit Interactions):

| Source Visual | Target Visual | Interaction |
|---|---|---|
| Panel B Bar (P1 -- Health by component) | Panel A Line Chart (P1) | **Filter** (highlight selected component series) |
| Panel B Bar (P1) | Panel C Waterfall (P1) | **Filter** (show OEE losses for selected component) |
| Panel A Stacked Bar (P3 -- Fleet Alert Inventory) | Panel C Matrix (P3), Panel D Line Chart (P3) | **Filter** (highlight selected component) |
| Panel B Scatter (P3 -- Risk Matrix) | Panel A Stacked Bar (P3) | **Filter** (highlight component in bar chart) |
| Sensor Type Slicer (P3) | Panel A, Panel C, Panel D | **Filter** |
| Date Slicer (any page) | All visuals on that page | **Filter** (default -- do not change) |

### 5.2 Disabling Unwanted Cross-Filter

1. Click the **Format** tab → **Edit Interactions**
2. Grey filter/highlight icons appear on all other visuals
3. Click the **No interaction** icon (circle with line) on visuals where cross-filtering is not desired

**Recommended "no interaction" settings (CRITICAL FOR FACT TABLE SLICERS):**
- **Sensor Type Slicer (Page 3)**: Since this filters specific sensor modalities, it MUST NOT filter the composite fleet-level KPI cards. Set **No interaction** for all KPI cards (E-01 to E-05) and Panel B (Scatter Chart).
- **Shift Period Slicer (Page 2)**: Since this uses `fact_sensor_readings[shift_period]`, it will not filter MTBF or OEE data. You MUST set **No interaction** for Panel C (OEE), Panel D (MTBF Delta), and KPI cards C-02, C-03, C-06, C-08. It should only filter KPI card A-01 and Panels A and E.
- **KPI Cards**: Set all KPI cards to **No interaction** when clicking chart panels (cards are headline metrics -- filtering them produces confusing KPI value changes)
- **Status bar text card (B-19 Dominant Loss on P1)**: **No interaction** from all charts

---

## 6. Conditional Formatting Application Checklist

These rules cannot be embedded in the theme JSON and must be applied manually in Power BI Desktop.

### 6.1 KPI Card Backgrounds

Navigate to each card → **Format > Callout value > Background color > Conditional formatting > Rules**

| Card | Measure | Rule Thresholds | Colors |
|---|---|---|---|
| B-15 System OEE | [System OEE Composite] | ≥0.85 / ≥0.75 / ≥0.65 / <0.65 | Teal / Green / Amber / Red |
| A-02 Min Health Score | [Min Health Score] | ≥75 / ≥65 / <65 | Green / Amber / Red |
| D-06 CCI Tier (worst) | [CCI Tier Worst] | Critical/High/Moderate/Low | Red/Amber/Yellow/Green |
| Combined Alerts | [Combined Alerts] | Critical / Warning / Caution / Normal | Red / Amber / Yellow / Green |
| A-08 Danger Zone Count | [Danger Zone Count] | >0 / =0 | Red / Green |
| A-07 Alarm Breach Count | [Alarm Breach Count] | >5 / >0 / =0 | Amber / Yellow / Green |

### 6.2 (Deprecated)
*(Page 3 conditional formatting is now handled via Field Value measures E-08 and E-10. See Day 30 UI Guide for details).*

---

## 7. Implementation Sequence (Day 25 Priority Order)

When building Page 1 in Power BI Desktop, follow this sequence to avoid layout thrash:

```
1. Open Power BI Desktop; File > Page Setup: 1280 × 720 px
2. View > Themes > Browse > select `powerbi_theme.json` (applies industrial palette instantly)
3. Paste all M queries from `docs/dax_and_m_scripts.md` into Power Query Editor
4. Build all 11 model relationships (9 active solid lines, 2 inactive dashed)
5. Set sort columns: component_name by position; shift_month_name by shift_month
6. Enter all 47 DAX measures (Groups A–D) into _Measures_* home tables
7. Run Section 8 validation checklist from `docs/dax_and_m_scripts.md`
8. Place KPI card row (5 cards at y=0) per guide Section 2.1 coordinates
9. Place Date + Component slicers (y=105)
10. Add Panel A line chart anchor (x=0, y=165, 768×290)
11. Add Panel B horizontal bar (x=773, y=165, 502×290); add drill-through tooltip hint
12. Add Panel C waterfall + Status bar (y=460); configure cross-filter edit interactions
13. Apply conditional formatting to KPI cards (OEE, Min Health, CCI Tier)
14. Add reference lines (75 + 65 health score thresholds) to Panel A
```

---


---

## 8. Day 28 Additions -- Panel F: Criticality Ranking (Page 2)

**Date:** 2026-08-10

---

### 8.1 Panel F -- Zone Layout Update

Panel F is appended as **Row 5** on Page 2, directly below Panel E (which was the previous bottom panel).
The canvas height is extended from 715px to 940px to accommodate Panel F.

Updated Page 2 zone summary:

| Row | Zone | Y start | Height | Panels |
|---|---|---|---|---|
| 1 | KPI Card Row | 0 | 100 | Cards 1-5 |
| 1b | Filter / Back Button | 105 | 55 | Slicers, Back button |
| 2 | Primary Analysis | 165 | 230 | Panel A (MTBF/MTTR), Panel B (Radar) |
| 3 | Detail Panels | 400 | 170 | Panel C (OEE bars), Panel D (Diverging bar) |
| 4 | Degradation Trend | 575 | 140 | Panel E (Daily health + alarm shading) |
| 5 | Criticality Ranking | 720 | 220 | Panel F (Horizontal bar -- all 5 components) |

---

### 8.2 Panel F -- Field Bindings

**Visual type:** Clustered Bar Chart (horizontal orientation)
**Canvas coordinates:** X=0, Y=720, W=1275, H=220

| Well | Field / Measure | Source | Notes |
|---|---|---|---|
| Y axis | `dim_components[component_name]` | dim_components | One bar per component. Enable 'Show items with no data' |
| X axis | `[CCI Score Fleet View]` (D-01c) | _Measures_D_Criticality | Fixed range 0.0-1.0 |
| Tooltips | `[Criticality Rank]` (D-13) | _Measures_D_Criticality | Rank shown on hover |
| Tooltips | `[CCI Tier Fleet View]` (D-14) | _Measures_D_Criticality | Tier string on hover |
| Tooltips | `[SRS Score Fleet View]` (D-14) | _Measures_D_Criticality | Sub-metric on hover |
| Tooltips | `[Weibull Unreliability Fleet View]` (D-14) | _Measures_D_Criticality | Sub-metric on hover |
| Tooltips | `[Threshold Breach Rate Fleet View]` (D-14) | _Measures_D_Criticality | Sub-metric on hover |
| Data colours | `[CCI Tier Color Fleet View]` (D-14) | _Measures_D_Criticality | Format > Data colours > fx > Field value |
| Visual title | `[Criticality Ranking Title]` (D-16) | _Measures_D_Criticality | Format > Title > Title text > fx > Field value |

**Why D-13 is in Tooltips and not Data labels or Legend:**
D-13 must be part of the visual's query for the sort-by-rank feature to work. Adding it to Tooltips
achieves this without cluttering the bar faces. Sort: click Y axis sort icon > Sort by
"Criticality Rank" > Ascending (rank 1 = most critical at top).

---

### 8.3 Panel F -- Step-by-Step Build Sequence

1. Navigate to Page 2 (Component Health) in Power BI Desktop.
2. Click on blank canvas area below Panel E (below y=715).
3. Insert > Clustered Bar Chart (horizontal orientation -- select from Visualizations pane).
4. Resize to X=0, Y=720, W=1275, H=220 (use Format > General > Position and Size fields).
5. Field bindings:
   - Drag `dim_components[component_name]` to the Y axis well. Right-click and check 'Show items with no data'.
   - Drag `[CCI Score Fleet View]` (D-01c) to the X axis well.
   - Drag `[Criticality Rank]` (D-13), `[CCI Tier Fleet View]` (D-14), `[SRS Score Fleet View]` (D-14),
     `[Weibull Unreliability Fleet View]` (D-14), `[Threshold Breach Rate Fleet View]` (D-14) to Tooltips well.
6. Sort: Click the Y axis sort icon (three horizontal lines icon in visual header) >
   Sort by > "Criticality Rank" > Ascending.
7. X axis: Format > Visual > X axis > set Min=0, Max=1, Title="Composite Criticality Index (CCI)".
8. Y axis: Format > Visual > Y axis > Title OFF.
9. Data labels: Format > Visual > Data labels > ON; Position=Outside End; Font=Outfit 9px.
10. Background: Format > General > Background > colour #0D1117.
11. Conditional formatting -- bar colours:
    a. Format > Visual > Bars > Colours > click fx icon.
    b. Dialog: Format style = Field value; Based on field = [CCI Tier Color Fleet View] (D-14). OK.
12. Dynamic title:
    a. Format > General > Title > Title text > click fx icon.
    b. Dialog: Format style = Field value; Based on field = [Criticality Ranking Title] (D-16). OK.
13. Add tier legend text box (optional but recommended for viva):
    - Insert > Text box; position X=1010, Y=725, W=260, H=85.
    - Text: "Critical >= 0.75 / High >= 0.50 / Moderate >= 0.25 / Low < 0.25"
    - Apply per-line colours using the rich-text editor (Critical=red, High=orange, etc.).

---

### 8.4 Panel F -- Conditional Formatting Detail

This supplements Section 6 of this guide.

#### 8.4.1 Bar Colours via D-14 [CCI Tier Color Fleet View]

| Tier label (dim_criticality[cci_tier]) | Hex returned by D-14 | Visual result |
|---|---|---|
| "Critical" | #C62828 | Dark red bar (Coupling expected) |
| "High" | #F57F17 | Amber bar |
| "Moderate" | #FFC107 | Yellow bar (Bearing expected) |
| "Low" | #2E7D32 | Green bar (Gearbox expected) |

**Configuration path:** Format pane > Visual > Bars > Colours > fx > Field value > [CCI Tier Color Fleet View]

#### 8.4.2 Dynamic Title via D-16 [Criticality Ranking Title]

| Drill-through context | ISFILTERED result | Title returned |
|---|---|---|
| No drill-through (standalone / Page 1 use) | FALSE | "Criticality Ranking - All Components" |
| Drill-through: Bearing (component_id = 1) | TRUE | "Criticality Ranking - Bearing vs Fleet" |
| Drill-through: Shaft (component_id = 2) | TRUE | "Criticality Ranking - Shaft vs Fleet" |

**Configuration path:** Format pane > General > Title > Title text > fx > Field value > [Criticality Ranking Title]

---

### 8.5 Panel F -- Cross-Filter Interaction Rules

Panel F (Criticality Ranking) renders all components regardless of drill-through context by using
D-01c and 'Show items with no data'. To act as a read-only reference visual without creating
loop-backs, Panel F cross-filter interactions are set to **None** for all other Page 2 visuals.

**Required interaction override:**
- Select Panel F > Format > Edit Interactions.
- Set Panel F > Panel E (Daily Health Trend): **None** (clicking a Panel F bar should NOT
  re-filter Panel E to a different component -- Panel E must remain scoped to the drilled-through
  component for diagnostic coherence).
- Set Panel F > Panel A, B, C, D: **None** for the same reason.
- Panel F is a READ-ONLY reference visual on Page 2; it should not trigger additional filtering.

---

### 8.6 Canvas Size Update

Page 2 canvas height was 720px (Day 27 spec). Panel F extends this to **940px**.

**Update path:** Page 2 > Format > Page information > Canvas settings > Height: 940.

Note: this makes Page 2 vertically scrollable in the Power BI web service. In Power BI Desktop
the canvas auto-scrolls. If vertical scroll is undesirable, Panel F can be placed on a separate
third panel at Y=0 within the same 720px canvas by using a bookmarked toggle button -- but
this is optional complexity and not required for the FYP submission.

---

*End of Day 28 addendum. Panel F fully specified in this guide. See docs/day27_page2_health_build.md Part 3 for DAX detail.*

*End of UX Implementation Guide. Day 24 deliverable. For Power BI Desktop implementation of Page 1, follow Section 7 sequence above.*
