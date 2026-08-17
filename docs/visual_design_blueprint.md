# Power BI Visual Design Blueprint
## Digital Twin Predictive Maintenance Dashboard -- Day 23

**Project:** Manufacturing Analytics -- Predictive Maintenance Digital Twin
**Phase:** 2.3 -- Power BI Dashboards
**Day:** 23 -- Visual Design Principles and Chart-Type Selection Logic
**Date:** 2026-08-08
**Status:** Specification -- For implementation in Power BI Desktop

---

## 0. Document Purpose

This document is the authoritative visual design specification for the Power BI dashboard.
Because `.pbix` is a binary format that cannot be diffed or version-controlled, this Markdown
file is the textual record of every layout decision, chart-type rationale, and measure-to-visual
assignment. It is the Day 23 equivalent of `docs/dax_and_m_scripts.md` -- the human-readable
source of truth before the binary file is built.

Three things are documented here:

1. **Chart-type selection logic** -- Why each metric group maps to a specific visual type,
   grounded in data visualization theory and the specific semantics of our reliability metrics.
2. **Page-by-page wireframe outlines** -- Spatial layout, visual slots, filter panels, and
   drill-through targets for each of the three dashboard pages.
3. **DAX measure-to-visual mapping** -- Every one of the 47 Day 22 DAX measures assigned to
   its designated visual type and page, with configuration details.

---

## 1. Chart-Type Selection Logic -- Metric Group Analysis

The selection logic follows a single governing principle: **match the data answer type to the
human perceptual task**. For each metric group: what question does this metric answer? -> what
perceptual task does the reader need to perform? -> which chart type best supports that task?

---

### 1.1 Health Score Metrics (Group A -- 10 Measures)

**Key measures:** `[Avg Health Score]`, `[Min Health Score]`, `[Avg R_Derated]`,
`[Health Score Period Delta]`, `[Alarm Breach Count]`, `[Danger Breach Count]`, `[Avg AF]`

**Answer type:** *How healthy is each component right now, and is it getting better or worse?*

| Metric | Question Answered | Perceptual Task | Selected Visual | Rationale |
|---|---|---|---|---|
| `[Avg Health Score]` per component | Point-in-time status comparison | Rank 5 entities | **Horizontal bar chart** | Bars support length-encoded magnitude comparison. Horizontal layout accommodates long pipeline_label names. Sorted descending by health score surfaces the worst component immediately. |
| `[Min Health Score]` (system worst) | Single critical threshold watch | Is value above/below limit? | **KPI card with conditional formatting** | KPI card with red/amber/green background. Minimum health = weakest-link system indicator. |
| `[Avg Health Score]` over time | Trend detection -- is degradation occurring? | Detect slope, inflection | **Line chart (trend)** | Lines encode continuous change over time. Continuous x-axis (date_key) preserves temporal spacing. Non-contiguous bars would obscure degradation slope. One series per component = 5 overlapping lines. |
| `[Health Score Period Delta]` | Month-over-month change direction | Positive vs negative change | **Diverging bar chart or conditional KPI card** | Delta can be positive (recovery) or negative (degradation). Diverging bars centered on zero encode direction unambiguously. |
| `[Alarm Breach Count]`, `[Danger Breach Count]` | Cumulative threshold exceedance count | Magnitude comparison by component | **Stacked bar (alarm + danger)** | Two-tier stacking separates severity levels while preserving total magnitude per component. Bars sorted by total count = automatic Pareto signal. |
| `[Avg AF]` (Arrhenius Factor) | Thermal acceleration of degradation | Rank components by thermal risk | **Horizontal bar chart** | AF is a pure magnitude comparison across 5 components. Logarithmic scale recommended if AF values span more than 1 order of magnitude. |

**Design rule for Group A:** Health Score is the dashboard headline metric. Every page shows at
least one health indicator. The line chart trend is the anchor visual for Page 1 (Fleet Overview).

---

### 1.2 OEE Metrics (Group B -- 19 Measures)

**Key measures:** `[OEE Availability]`, `[OEE Performance]`, `[OEE Quality]`,
`[OEE Composite]`, `[OEE Status]`, `[System OEE Composite]`, Six Big Losses, `[Dominant Loss Category]`

**Answer type:** *How efficient is production, and where are the losses?*

| Metric | Question Answered | Perceptual Task | Selected Visual | Rationale |
|---|---|---|---|---|
| `[OEE Composite]` (system) | Single-number production efficiency | Is it above/below 85%? | **KPI card** | Single-number metric with known target (85% = World Class). Conditional background: green >=85%, amber >=75%, red <65%. |
| `[OEE Availability]`, `[OEE Performance]`, `[OEE Quality]` (component-level) | A/P/Q decomposition per component | Compare three ratios across 5 components | **Clustered bar chart (3 series)** | A stacked bar is wrong here because A x P x Q is a product, not a sum -- stacking would imply summing. |
| `[OEE Composite]` trend over time | Is overall OEE recovering or declining? | Slope, seasonal pattern | **Line chart with 85% reference line** | Horizontal reference line at 0.85 provides immediate at-a-glance pass/fail framing. |
| Six Big Losses decomposition | OEE loss decomposition -- where does time go? | Understand loss hierarchy | **Waterfall chart** | Waterfall is the canonical OEE decomposition visual: starts at 100% planned time, subtracts each loss in sequence, ends at OEE%. Waterfall shows PATH from total potential to actual -- exactly the Six Big Losses model. |
| `[Dominant Loss Category]` | Which loss type is largest right now? | One-word classification | **Slicer / conditional card** | Text label with category-conditional color. |
| `[System OEE Composite]` vs component | Is system OEE dragged below best component? | Compare system to five components | **Bullet chart or reference-line bar** | System OEE placed as reference line on clustered bar chart. |

**Why a Waterfall for Six Big Losses, not a Pareto?**

A Pareto chart is appropriate for identifying the largest of several independent, separable categories
(the 80/20 rule). A waterfall is appropriate when categories are sequential subtractions from a starting
total -- which is the exact semantics of OEE loss decomposition (100% -> -Loss1 -> -Loss2 -> ... -> OEE%).
Both visuals are used: the waterfall shows the OEE decomposition flow on Page 1, and a Pareto-ordered
bar chart on Page 3 shows root cause downtime attribution for maintenance prioritization decisions.

---

### 1.3 MTBF/MTTR Metrics (Group C -- 8 Measures)

**Key measures:** `[MTBF Hours]`, `[MTTR Hours]`, `[Empirical Availability]`,
`[Maintenance Ratio]`, `[MTBF vs Weibull Delta]`, `[Failure Count]`

**Answer type:** *How reliable are components historically, and how does observed reliability
compare to theoretical predictions?*

| Metric | Question Answered | Perceptual Task | Selected Visual | Rationale |
|---|---|---|---|---|
| `[MTBF Hours]` by component | Which component fails most frequently? | Rank 5 by time-between-failures | **Horizontal bar chart** | Sort ascending (shortest MTBF first) = automatic risk prioritization. |
| `[MTTR Hours]` by component | Which component takes longest to repair? | Rank 5 by repair time | **Horizontal bar chart** | Sort descending (longest MTTR first) = highest maintenance burden first. |
| `[MTBF Hours]` over time (trend) | Is reliability improving under the maintenance program? | Detect increasing/decreasing MTBF slope | **Line chart** | Increasing MTBF slope = maintenance program working. Decreasing = accelerating failure rate. Critical for CBM validation. |
| `[Empirical Availability]` vs `[OEE Availability]` | Do inherent reliability and production availability agree? | Two-metric comparison per component | **Dual-axis bar or diverging bar** | Empirical Availability (MTBF/(MTBF+MTTR)) vs OEE Availability (production-schedule-based). Divergence signals data quality issues or schedule vs reliability mismatch. |
| `[MTBF vs Weibull Delta]` | Is observed MTBF tracking Weibull model prediction? | Positive vs negative deviation | **Diverging bar (delta chart)** | Diverging bars centered at 0 = over/under-performance vs Weibull prediction. Critical for model calibration monitoring. |
| `[Maintenance Ratio]` = MTTR/MTBF | How much repair time per operating hour? | Single ratio per component | **KPI card or dot plot** | Values >0.1 warrant attention. |

**Why a Line Chart for MTBF Trends?**

MTBF is a derived aggregate computed over a rolling date window. A line chart reveals whether the
maintenance program is extending inter-failure intervals over the 12-month simulation window
(2026-07-20 to 2027-07-20). A bar chart would obscure temporal ordering and make slope detection
impossible. A scatter plot would lose the continuous time flow. Additionally, a reference line
showing the Weibull-predicted MTBF (dim_criticality[weibull_mtbf_hours]) can be overlaid on a
line chart but would require a cluttered second axis on a bar chart.

---

### 1.4 Criticality Metrics (Group D -- 10 Measures)

**Key measures:** `[CCI Score]`, `[CCI Rank]`, `[SRS Score]`, `[Weibull Unreliability]`,
`[Threshold Breach Rate]`, `[CCI Tier]`, `[Root Cause Downtime Min]`, `[Upstream Defect Units]`,
`[Root Cause Downtime Ratio]`, `[CCI Weighted Health Score]`

**Answer type:** *Which components pose the greatest systemic risk, and which are causing
downstream failures?*

| Metric | Question Answered | Perceptual Task | Selected Visual | Rationale |
|---|---|---|---|---|
| `[CCI Score]`, `[SRS Score]`, `[Weibull Unreliability]`, `[Threshold Breach Rate]` | Multi-dimensional risk profile per component | Compare 4+ risk dimensions across 5 components | **Radar / spider chart** | Appropriate when comparing multiple commensurate dimensions for a small number of entities (<=7). Suitable only in single-component drill-through context. |
| `[CCI Rank]` | Ranked risk ordering | Rank 5 components by composite risk | **Ranked table (matrix visual)** | CCI Rank is ordinal. Table with conditional formatting data bars is more honest than a bar chart. A bar chart would suggest continuous magnitude; CCI is rank-ordered, not continuous. |
| `[Root Cause Downtime Min]` | How much system downtime did each component CAUSE? | Rank root causes by impact | **Pareto chart (sorted bar + cumulative %)** | Pareto identifies the 20% of root causes driving 80% of system downtime. Bearing expected #1 (cascade trigger). USERELATIONSHIP() in D-07 makes this semantically correct: causation, not coincidence. |
| `[Upstream Defect Units]` | How many defects originated from each component? | Rank defect sources | **Pareto chart** | USERELATIONSHIP() in D-08 re-attributes defects to origin component, not detection point. |
| `[CCI Weighted Health Score]` | What is risk-adjusted health? | Single composite score per component | **KPI card or ranked bar** | Product of CCI Score and Avg Health Score. High CCI + low health = doubly dangerous. |
| `[CCI Tier]` | Is this component Critical/High/Moderate/Low? | Categorical classification | **Matrix table with conditional color** | Tier is categorical. Color-coded cells (red/orange/amber/green) are more honest than a bar chart. |

---

## 2. Page-by-Page Wireframe Outlines

### Page 1: Fleet Overview

**Purpose:** Executive-level system health snapshot.
**Primary audience:** Maintenance manager, operations lead
**Slicer context:** Date range picker (defaults to fixed 30-day range), Component multi-select (defaults to ALL)

```
+================================================================================+
|  FLEET OVERVIEW -- Digital Twin Predictive Maintenance Dashboard               |
|  [Date Range Slicer: 2026-07-20 to 2027-07-20]  [Component Slicer: ALL]       |
+==============+==============+==============+==============+======================+
|  KPI CARD 1  |  KPI CARD 2  |  KPI CARD 3  |  KPI CARD 4  |  KPI CARD 5          |
|  System OEE  |  Min Health  |  MTBF Avg    |  Active      |  CCI Tier (worst)    |
|  [B-15]      |  Score [A-02]|  [C-02]      |  Alerts[A-06]|  component [D-06]    |
|  78.3% ACCEPT|  64.1% ALERT |  312 hrs     |  7 breaches  |  Bearing: CRITICAL   |
+==============+==============+==============+==============+======================+
|                                                                                 |
|  PANEL A (60% width, left):                                                    |
|  LINE CHART -- Health Score Trend (all 5 components, 12-month timeline)        |
|  x-axis: date_key (monthly)   y-axis: [Avg Health Score]                      |
|  Series: Bearing, Shaft, Motor Housing, Coupling, Gearbox (5 color lines)     |
|  Reference lines: 65 (ALERT threshold), 75 (ACCEPTABLE threshold)             |
|                                                                                 |
+================================================================================+
|                                                                                 |
|  PANEL B (40% width, right):          PANEL C (40% width, right):             |
|  HORIZONTAL BAR CHART                 OEE WATERFALL CHART                     |
|  [Avg Health Score] by component      Six Big Losses decomposition             |
|  Sort: ascending (worst first)      |  100% -> -L1 -> -L2 -> -L3 -> OEE%      |
|  Measures: B-09, B-10, B-11              |Measures: B-16, B-17, B-18              |
|                                                                                 |
+================================================================================+
|  STATUS BAR: [Root Cause Downtime Min] Pareto (compact) | [Dominant Loss Cat]  |
+================================================================================+
```

**Visual Inventory -- Page 1:**

| Slot | Visual Type | DAX Measures | Configuration |
|---|---|---|---|
| KPI Card 1 | KPI Card | `[System OEE Composite]` (B-15) | Conditional bg: >=0.85 green, >=0.75 amber, <0.65 red. Target = 0.85. |
| KPI Card 2 | KPI Card | `[Min Health Score]` (A-02) | Conditional bg: <65 red, <75 amber, else green. |
| KPI Card 3 | KPI Card | `[MTBF Hours]` (C-02) all components | System average. Reference = Weibull MTBF from dim_criticality. |
| KPI Card 4 | KPI Card | `[Alarm Breach Count]` (A-06) + `[Danger Breach Count]` (A-07) | Sum both. Red if >0 danger breaches. |
| KPI Card 5 | KPI Card (text) | `[CCI Tier]` (D-06) filtered to highest-risk component | Component name + tier label. Drill-through to Page 2 on click. |
| Panel A | Line Chart | `[Avg Health Score]` (A-01) by date_key x component_name | 5 series. Monthly granularity. Two horizontal reference lines (65, 75). |
| Panel B | Horizontal Bar | `[Avg Health Score]` (A-01) by pipeline_label | Sort ascending. CCI-tier conditional color (D-06 used for color axis). |
| Panel C | Waterfall | B-09, B-10, B-11 + implied losses 4-6 | Breakdown bars = red. Total bar = system OEE %. Subtotals per OEE pillar. |
| Status Bar | Compact Pareto | `[Root Cause Downtime Min]` (D-07) | 5 components, compact sparkline style. |

**Drill-through (Page 1 -> Page 2):**
Right-click any component bar in Panel B -> "Drill through to Component Health".
Passes `component_id` as drill-through filter. Back button auto-generated on Page 2.

---

### Page 2: Component Health (Drill-Through Target)

**Purpose:** Deep-dive into a single component health, reliability, and criticality profile.
**Primary audience:** Reliability engineer, maintenance planner
**Slicer context:** Component fixed to drill-through selection. Date range. Shift-period.

```
+================================================================================+
|  COMPONENT HEALTH -- [BEARING]   Back to Fleet Overview                       |
|  [Date Range Slicer]  [Shift Period: All]  [CCI Tier: All]                    |
+===============+===============+==============+==============+==================+
|  KPI Card     |  KPI Card     |  KPI Card    |  KPI Card    |  KPI Card         |
|  Avg Health   |  MTBF Hours   |  MTTR Hours  |  Empirical   |  MTBF vs Weibull  |
|  Score [A-01] |  [C-02]       |  [C-03]      |  Avail [C-06]|  Delta [C-08]     |
|  64.1% ALERT  |  287 hrs      |  12.3 hrs    |  95.9%       |  -24.5 hrs (down) |
+===============+===============+==============+==============+==================+
|                                                                                 |
|  PANEL A (50% width):                    PANEL B (50% width):                 |
|  LINE CHART -- MTBF Trend (monthly)      RADAR CHART -- Risk Profile          |
|  x: date_key (monthly)                   Axes: CCI, SRS, TBR, Weibull F(t)    |
|  y: [MTBF Hours] (C-02)                  Measures: D-01, D-03, D-05, D-04     |
|  Reference line: Weibull MTBF (from C-08)|Single component polygon            |
|  2nd line: [MTTR Hours] (C-03)           Reference polygon: fleet average     |
|                                                                                 |
+================================================================================+
|                                                                                 |
|  PANEL C (50% width):                    PANEL D (50% width):                 |
|  CLUSTERED BAR -- OEE A/P/Q Breakdown    DIVERGING BAR -- MTBF vs Weibull     |
|  Series: A (B-04), P (B-06), Q (B-05)   x: [MTBF vs Weibull Delta] (C-08)   |
|  By: shift_month (monthly comparison)   y: month                              |
|  Reference: 1.0 target line             Color: positive=teal, negative=red   |
|                                                                                 |
+================================================================================+
|  PANEL E (100% width):                                                         |
|  LINE CHART -- Sensor Health Score (daily granularity)                        |
|  x: date_key (daily)  y: [Avg Health Score] (A-01) + [Avg R_Derated] (A-03) |
|  Background band shading where [Alarm Breach Count] > 0                      |
|  Vertical markers at failure events from dim_failure_log                      |
+================================================================================+
```

**Visual Inventory -- Page 2:**

| Slot | Visual Type | DAX Measures | Configuration |
|---|---|---|---|
| KPI Card 1 | KPI Card | `[Avg Health Score]` (A-01) | Filtered to drill-through component. Conditional color. |
| KPI Card 2 | KPI Card | `[MTBF Hours]` (C-02) | Single component MTBF in filtered context. |
| KPI Card 3 | KPI Card | `[MTTR Hours]` (C-03) | Avg repair duration. Red if >8 hours (shift boundary). |
| KPI Card 4 | KPI Card | `[Empirical Availability]` (C-06) | Label: "Inherent Avail." to distinguish from OEE Avail. |
| KPI Card 5 | KPI Card | `[MTBF vs Weibull Delta]` (C-08) | Arrow icon up/down. Positive = observed > model (better). |
| Panel A | Line Chart | `[MTBF Hours]` (C-02), `[MTTR Hours]` (C-03) by date_key | Dual lines. Reference line from dim_criticality[weibull_mtbf_hours]. |
| Panel B | Radar Chart | D-01, D-03, D-05, D-04 | 4 axes normalized 0-1. Reference polygon = fleet average via ALL() companion measure. |
| Panel C | Clustered Bar | B-04, B-06, B-05 by shift_month_name | Three series per month. Reference line at 1.0. Sort by shift_month. |
| Panel D | Diverging Bar | `[MTBF vs Weibull Delta]` (C-08) by shift_month_name | Bars left of zero = worse than model. Zero line prominent. |
| Panel E | Line Chart | A-01, A-03 by date_key daily | Background shading on alarm breaches. Failure event markers. |

---

### Page 3: Alert / Risk Intelligence

**Purpose:** Actionable alert triage and root cause attribution.
**Primary audience:** On-shift maintenance technician, reliability analyst
**Slicer context:** Date range (defaults to fixed 7-day range). Severity. CCI Tier. Downtime category.

```
+================================================================================+
|  ALERT & RISK INTELLIGENCE -- Real-Time Maintenance Prioritization            |
|  [Date Range: Fixed 7 Days]  [Severity: All]  [CCI Tier: All]                 |
+==============+==============+==============+==============+======================+
|  KPI Card    |  KPI Card    |  KPI Card    |  KPI Card    |  KPI Card            |
|  Danger      |  Alarm       |  Root Cause  |  Total       |  Cascade Flag Rate   |
|  Breaches    |  Breaches    |  Downtime    |  Failures    |  [A-05]              |
|  [A-07]      |  [A-06]      |  [D-07]      |  [C-01]      |  34.2%               |
+==============+==============+==============+==============+======================+
|                                                                                 |
|  PANEL A (60% width):                    PANEL B (40% width):                 |
|  PARETO CHART -- Root Cause Downtime     RANKED MATRIX TABLE                  |
|  (sorted bars + cumulative % line)       Cols: Component | CCI Rank |         |
|  x: pipeline_label (5 components)        CCI Tier | SRS Score | TBR Rate      |
|  y1: [Root Cause Downtime Min] (D-07)    Measures: D-02, D-06, D-03, D-05    |
|  y2: cumulative % (companion measure)    Data bars on SRS Score column        |
|  USERELATIONSHIP activates root-cause    Sort by CCI Rank ascending           |
|  attribution (not experienced downtime)  Drill-through on row click           |
|                                                                                 |
+================================================================================+
|                                                                                 |
|  PANEL C (50% width):                    PANEL D (50% width):                 |
|  PARETO -- Upstream Defect Units         STACKED BAR -- Alarm + Danger         |
|  x: pipeline_label                       x: pipeline_label (5 components)     |
|  y: [Upstream Defect Units] (D-08)       y: Breach count                      |
|  Sorted descending + cumulative % line   Series: Alarm (amber) + Danger (red) |
|  USERELATIONSHIP re-attributes to source Sort by total descending             |
|                                                                                 |
+================================================================================+
|  PANEL E (100% width):                                                         |
|  MATRIX TABLE -- Alert Event Log                                               |
|  Rows: dim_failure_log (date, component, failure_mode, repair_duration_hours) |
|  Columns: [Failure Count] (C-01), [MTTR Hours] (C-03), [Total Repair Hours]  |
|  Conditional: repair_duration_hours > threshold -> red cell                   |
|  Sort: failure_date_key descending (most recent first)                        |
+================================================================================+
```

**Visual Inventory -- Page 3:**

| Slot | Visual Type | DAX Measures | Configuration |
|---|---|---|---|
| KPI Card 1 | KPI Card | `[Danger Breach Count]` (A-07) | Red background if > 0. Target = 0. |
| KPI Card 2 | KPI Card | `[Alarm Breach Count]` (A-06) | Amber if > 0. |
| KPI Card 3 | KPI Card | `[Root Cause Downtime Min]` (D-07) | Total system downtime caused by root causes in date context. |
| KPI Card 4 | KPI Card | `[Failure Count]` (C-01) | Excludes censored rows via ISBLANK guard. |
| KPI Card 5 | KPI Card | `[Cascade Flag Rate]` (A-05) | Amber if > 25%. |
| Panel A | Pareto (Bar + Line) | `[Root Cause Downtime Min]` (D-07) by pipeline_label | Sorted descending. Cumulative % on secondary y-axis. 80% reference line. |
| Panel B | Matrix Table | D-02, D-06, D-03, D-05 | Sorted by D-02 ascending. Cell color on D-06 (Critical=red, High=orange, Moderate=amber, Low=green). |
| Panel C | Pareto (Bar + Line) | `[Upstream Defect Units]` (D-08) by pipeline_label | USERELATIONSHIP re-attributes defects to source, not detection point. |
| Panel D | Stacked Bar | A-06, A-07 by pipeline_label | Two series stacked. Sort by total descending. Amber + red. |
| Panel E | Matrix Table | dim_failure_log rows with C-03, C-01 | Date descending. Conditional formatting on repair duration. |

---

## 3. DAX Measure-to-Visual Mapping (All 47 Measures)

### Group A -- Health & Reliability (10 Measures)

| ID | Measure | Primary Visual | Page | Role |
|---|---|---|---|---|
| A-01 | `[Avg Health Score]` | Line Chart + Horizontal Bar | P1 Panel A, P1 Panel B, P2 Panel E | Primary metric (y-axis) |
| A-02 | `[Min Health Score]` | KPI Card | P1 | Card value. Conditional color. |
| A-03 | `[Avg R_Derated]` | Line Chart (overlay) | P2 Panel E | Secondary line on health score trend |
| A-04 | `[Failure Event Count]` | Implicit in C-01 | P3 | Tooltip / annotation count |
| A-05 | `[Cascade Flag Rate]` | KPI Card | P3 | Alert dashboard cascade indicator |
| A-06 | `[Alarm Breach Count]` | KPI Card + Stacked Bar | P1 (card), P3 Panel D | Card headline + bar series |
| A-07 | `[Danger Breach Count]` | KPI Card + Stacked Bar | P1 (card), P3 Panel D | Card headline + bar series |
| A-08 | `[Avg AF]` | Tooltip / Ad-hoc | P2 | Secondary context metric |
| A-09 | `[Health Score StdDev]` | Error bar / tooltip | P1 Panel A | Error band on line chart (optional) |
| A-10 | `[Health Score Period Delta]` | Diverging KPI Card | P1 | Delta card. Arrow direction icon. |

### Group B -- OEE (19 Measures)

| ID | Measure | Primary Visual | Page | Role |
|---|---|---|---|---|
| B-01 | `[Planned Production Min]` | Tooltip | P2 Panel C | Tooltip on OEE bars |
| B-02 | `[Total Downtime Min]` | Tooltip / waterfall base | P1 Panel C | Input to waterfall subtotals |
| B-03 | `[Run Time Min]` | Tooltip | P2 Panel C | Tooltip on OEE Performance bar |
| B-04 | `[OEE Availability]` | Clustered Bar | P2 Panel C | Series 1 of 3 |
| B-05 | `[OEE Quality]` | Clustered Bar | P2 Panel C | Series 3 of 3 |
| B-06 | `[OEE Performance]` | Clustered Bar | P2 Panel C | Series 2 of 3 |
| B-07 | `[OEE Composite]` | Line Chart trend | P1 (implicit) | Component-level OEE trend |
| B-08 | `[OEE Status]` | Conditional formatting | P1 KPI bg | Color driver for System OEE card |
| B-09 | `[Loss 1 PP]` | Waterfall | P1 Panel C | Loss step 1 (Availability pillar) |
| B-10 | `[Loss 2 PP]` | Waterfall | P1 Panel C | Loss step 2 (Availability pillar) |
| B-11 | `[Loss 3 PP]` | Waterfall | P1 Panel C | Loss step 3 (Performance pillar) |
| B-12 | `[System OEE Availability]` | KPI Card tooltip | P1 | Tooltip on System OEE card |
| B-13 | `[System OEE Performance]` | KPI Card tooltip | P1 | Tooltip on System OEE card |
| B-14 | `[System OEE Quality]` | KPI Card tooltip | P1 | Tooltip on System OEE card |
| B-15 | `[System OEE Composite]` | KPI Card (primary) | P1 KPI Card 1 | Dashboard headline metric |
| B-16 | `[Loss 1 Unplanned Breakdown Min]` | Tooltip (Waterfall) | P1 Panel C | Raw minutes tooltip |
| B-17 | `[Loss 2 Changeover Min]` | Tooltip (Waterfall) | P1 Panel C | Raw minutes tooltip |
| B-18 | `[Loss 3 Minor Stop Idle Min]` | Tooltip (Waterfall) | P1 Panel C | Raw minutes tooltip |
| B-19 | `[Dominant Loss Category]` | Text Card | P1 status bar | Category label with conditional color |

### Group C -- MTBF/MTTR (8 Measures)

| ID | Measure | Primary Visual | Page | Role |
|---|---|---|---|---|
| C-01 | `[Failure Count]` | KPI Card | P3 KPI Card 4 | Raw failure count |
| C-02 | `[MTBF Hours]` | KPI Card + Line Chart | P1 KPI 3, P2 Panel A | Card + trend line |
| C-03 | `[MTTR Hours]` | KPI Card + Line Chart | P2 KPI 3, P2 Panel A | Secondary trend line |
| C-04 | `[Total Repair Hours]` | Matrix Table tooltip | P3 Panel E | Tooltip on failure log |
| C-05 | `[Total Operating Hours]` | Tooltip | P2 | Denominator transparency tooltip |
| C-06 | `[Empirical Availability]` | KPI Card | P2 KPI Card 4 | "Inherent Availability" card |
| C-07 | `[Maintenance Ratio]` | Dot Plot / KPI Cards row | P2 | 5-component dot plot or card row |
| C-08 | `[MTBF vs Weibull Delta]` | Diverging Bar + KPI Card | P2 Panel D, P2 KPI 5 | Card + monthly diverging bar |

### Group D -- Criticality (10 Measures)

| ID | Measure | Primary Visual | Page | Role |
|---|---|---|---|---|
| D-01 | `[CCI Score]` | Radar Chart | P2 Panel B | Radar axis 1 |
| D-02 | `[CCI Rank]` | Matrix Table | P3 Panel B | Sort column; data bar |
| D-03 | `[SRS Score]` | Radar Chart + Matrix Table | P2 Panel B, P3 Panel B | Radar axis 2 + table column |
| D-04 | `[Weibull Unreliability]` | Radar Chart | P2 Panel B | Radar axis 4 |
| D-05 | `[Threshold Breach Rate]` | Radar Chart + Matrix Table | P2 Panel B, P3 Panel B | Radar axis 3 + table column |
| D-06 | `[CCI Tier]` | Matrix Table (conditional) + KPI Card | P1 KPI 5, P3 Panel B | Color encoding + card label |
| D-07 | `[Root Cause Downtime Min]` | Pareto Chart + KPI Card | P1 status, P3 Panel A, P3 KPI 3 | Root cause attribution pareto |
| D-08 | `[Upstream Defect Units]` | Pareto Chart | P3 Panel C | Defect source attribution |
| D-09 | `[Root Cause Downtime Ratio]` | Pareto line (cumulative %) | P3 Panel A | Secondary y-axis cumulative % |
| D-10 | `[CCI Weighted Health Score]` | Horizontal Bar | P2 supporting | Risk-adjusted health score bar |

---

## 4. Cross-Cutting Design Decisions

### 4.1 Color Palette

| Color | Hex | Meaning | Applied To |
|---|---|---|---|
| Danger Red | #C62828 | Critical risk / danger threshold breach | Danger Breach Count cards, CCI Tier = Critical |
| Alert Amber | #F57F17 | Warning / alarm threshold breach | Alarm Breach Count cards, CCI Tier = High |
| Acceptable Green | #2E7D32 | Within healthy range | Health Score >= 75, OEE >= 85% |
| World Class Teal | #00695C | World class performance | OEE >= 85% card background |
| Neutral Slate | #37474F | Pipeline label background | pipeline_label bars |

**5-Component Series Colors (accessible, distinguishable):**

| Component | Color | Hex |
|---|---|---|
| Bearing (Pos 1) | Deep Blue | #1565C0 |
| Shaft (Pos 2) | Purple | #6A1B9A |
| Motor Housing (Pos 3) | Teal | #00695C |
| Coupling (Pos 4) | Orange | #E65100 |
| Gearbox (Pos 5) | Slate | #37474F |

Colors are distinguishable at 8-pt size (WCAG AA contrast). Red/green reserved exclusively for status
encoding, not series colors (colorblindness consideration -- avoid red/green pairing for series).

### 4.2 Slicers and Cross-Filter Behavior

| Slicer | Type | Pages Active | Cross-filter Behavior |
|---|---|---|---|
| Date Range | Date picker (between) | All 3 | Filters via dim_calendar[date] column |
| Component | Dropdown / multi-select | P1 (multi), P3 (multi) | Filters via component_id active relationship |
| CCI Tier | Checkbox list | P3 | Filters via cci_tier column |
| Shift Period | Dropdown | P2 | Filters via shift_period M-derived column |
| Severity | Radio (Alarm / Danger / All) | P3 | Filters Alarm/Danger Breach Count measures |

**USERELATIONSHIP() slicer note:** The component slicer on P3 drives `[Root Cause Downtime Min]`
(D-07) through the INACTIVE relationship (root_cause_component_id). Selecting "Bearing" in the slicer
shows all downtime events CAUSED BY Bearing as root cause -- including cascade events on all 4
downstream components. This is the intended semantics: the slicer selects the "blame" component,
not the "experience" component.

### 4.3 Tooltip Pages (Custom Canvas Tooltips)

1. **Health Score Trend tooltip:** Hover on line chart data point -> show A-06, A-07, A-08 for
   that component-month.
2. **Pareto Root Cause tooltip:** Hover on D-07 bar -> show C-02 (MTBF), C-03 (MTTR), D-06 (CCI Tier).
3. **Waterfall OEE tooltip:** Hover on loss step -> show component(s) driving that loss category.

### 4.4 Drill-Through Configuration

| Source Page | Source Visual | Target Page | Filter Passed |
|---|---|---|---|
| P1 Fleet Overview | Panel B (Health Score bar) | P2 Component Health | component_id = clicked component |
| P3 Alert/Risk | Panel B (CCI matrix, row click) | P2 Component Health | component_id = clicked row |
| P3 Alert/Risk | Panel A (Pareto bar) | P2 Component Health | component_id = clicked bar |

---

## 5. Viva Q&A -- Visual Design Principles

**Q65: Why do you use a waterfall chart for the Six Big Losses decomposition rather than a Pareto chart?**

A waterfall chart encodes sequential subtraction from a baseline: "we started with 100% available
time; here is where it was consumed step by step, arriving at OEE%." The Six Big Losses model is
intrinsically a decomposition flow, not a frequency-rank ordering. A Pareto chart (sorted bars +
cumulative line) is appropriate for identifying the largest of several independent, separable
categories -- which is the correct tool for root cause downtime attribution (Panel A on Page 3,
using [Root Cause Downtime Min]). Using a Pareto for the OEE decomposition waterfall would mislead:
sorting losses by magnitude destroys the logical OEE = A x P x Q pillar structure and obscures
which OEE pillar the losses belong to.

**Q66: Why do you use a line chart rather than a bar chart for MTBF trends?**

MTBF over time is a continuous measure of an underlying process parameter (mean failure interval)
that evolves as the system ages and as maintenance is applied. Line charts encode continuity -- the
reader perceives slope, acceleration, and inflection points. A bar chart encodes discrete magnitude
per category -- the reader cannot easily detect whether the value is increasing or decreasing. Since
the diagnostic question is "is MTBF improving month-over-month?" (a slope question), the line chart
is analytically superior. A reference line showing the Weibull-predicted MTBF
(dim_criticality[weibull_mtbf_hours]) can also be cleanly overlaid on a line chart.

**Q67: Why use SELECTEDVALUE() for CCI Score in the radar chart rather than AVERAGE()?**

[CCI Score] is defined as SELECTEDVALUE(dim_criticality[composite_criticality], BLANK()). CCI is
a rank-ordered composite index derived from multiple heterogeneous sub-scores (failure rate, cascade
exposure, structural risk, Weibull unreliability). Averaging CCI across components is analytically
incorrect -- CCI rank is ordinal, not cardinal; averaging ranks produces a meaningless number. The
radar chart on Page 2 is always filtered to a single component (via drill-through), which is exactly
the context where SELECTEDVALUE() returns the unique scalar correctly. In a multi-component context
(Page 1), CCI measures return BLANK() -- preventing misleading cross-component CCI aggregation.

**Q68: Explain the semantic difference between [Root Cause Downtime Min] (D-07) and [Total Downtime Min] (B-02).**

[Total Downtime Min] (B-02) = SUM(fact_downtime_events[duration_min]) -- total downtime EXPERIENCED
by the selected component. If Bearing fails and causes Shaft to stop for 2 hours, Shaft includes
those 2 hours in B-02. [Root Cause Downtime Min] (D-07) uses USERELATIONSHIP(dim_components[component_id],
fact_downtime_events[root_cause_component_id]) to sum all downtime events where root_cause_component_id
= the selected component. Selecting Bearing via D-07 sums all downtime across all 4 downstream
components triggered by a Bearing failure. This answers "how much total damage did Bearing CAUSE to
the system?" -- a fundamentally different question from "how long was Bearing itself down?" The Pareto
chart on Page 3 uses D-07 to rank components by causal impact, not personal downtime experience.

---

## 6. Implementation Sequence for Power BI Desktop

1. Load all 6 CSVs via M scripts from docs/dax_and_m_scripts.md (Sections 1-6)
2. Build Model View relationships (9 active + 2 inactive; Section 6 of dax_and_m_scripts.md)
3. Set Sort Columns (component_name by position; shift_month_name by shift_month)
4. Enter all 47 DAX measures into their _Measures_* home tables (Groups A-D)
5. Run validation checklist (Section 8 of dax_and_m_scripts.md); cross-validate OEE vs SQL
6. Build Page 1 (Fleet Overview) starting with KPI cards
7. Build Page 2 (Component Health) -- configure drill-through filter
8. Build Page 3 (Alert/Risk) -- Pareto charts require D-07/D-08 USERELATIONSHIP measures
9. Configure slicer cross-filter sync across pages
10. Add tooltip pages and conditional formatting rules

---

*End of Day 23 Visual Design Blueprint. This document supersedes any informal layout notes and serves
as the definitive specification for the Power BI dashboard implementation. All 47 DAX measures are
assigned. All three pages are wireframed. Chart-type selections are grounded in data visualization
theory and project-specific metric semantics.*
