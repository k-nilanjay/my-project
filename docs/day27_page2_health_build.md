# Day 27 Build Log — Panel C DAX Rewrite (Option 2) + Page 2: Component Health / Degradation

**Date:** 2026-08-10
**Phase:** 2.3 Power BI — Day 27
**Status:** Panel C semantic issue resolved. Page 2 visual specification complete.

---

## Part 1: Panel C DAX Rewrite — Option 2 (Bottleneck Decomposition)

### Background

The Day 26 open issue: KPI Card 1 shows `[System OEE Composite]` = bottleneck (MIN rule across components). Panel C (Waterfall) previously used `[Selected Loss PP]` routing through `[Availability Loss PP]`, `[Performance Loss PP]`, `[Quality Loss PP]` — each of which averages or sums across **all** components. The two visuals described different subjects.

**Option 2 chosen:** Rewrite Panel C to decompose only the **bottleneck component's** OEE. New measures are scoped to the component holding `[Min Health Score]` — the same component whose constraining availability drives `[System OEE Composite]`.

---

### Step 1: Identify the Bottleneck Component

```dax
-- B-BN-00: Bottleneck Component ID
-- Returns the component_id of the component with the minimum average health score
-- in the current filter context (= the constraining / weakest-link component).
-- Used by B-BN-01 through B-BN-04 to scope OEE decomposition to this component only.
-- Home table: _Measures_B
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
```

**Why MAXX after MINX:** MINX on `[@AvgHealth]` returns the minimum health score value (a number), not the component_id. The second FILTER/MAXX step retrieves the component_id corresponding to that minimum. MAXX arbitrarily breaks ties; this is acceptable because the bottleneck is definitionally the worst-health component regardless of tie-breaking.

---

### Step 2: Bottleneck-Scoped OEE Sub-Factor Measures

```dax
-- B-BN-01: Bottleneck OEE Availability
-- Scoped to bottleneck component only via CALCULATE + FILTER on component_id.
-- Home table: _Measures_B
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
```

```dax
-- B-BN-02: Bottleneck OEE Performance
-- Home table: _Measures_B
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
```

```dax
-- B-BN-03: Bottleneck OEE Quality
-- Home table: _Measures_B
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
```

---

### Step 3: Bottleneck Loss PP Measures

```dax
-- B-BN-04: Bottleneck Availability Loss PP
-- (1 - A_bottleneck) * 100 percentage-point loss for bottleneck component only.
-- Home table: _Measures_B
[Bottleneck Availability Loss PP] =
IF(
    ISBLANK( [Bottleneck OEE Availability] ),
    BLANK(),
    ( 1 - [Bottleneck OEE Availability] ) * 100
)
```

```dax
-- B-BN-05: Bottleneck Performance Loss PP
-- Sequentially weighted by Availability.
[Bottleneck Performance Loss PP] =
IF(
    ISBLANK( [Bottleneck OEE Performance] ) || ISBLANK( [Bottleneck OEE Availability] ),
    BLANK(),
    [Bottleneck OEE Availability] * ( 1 - [Bottleneck OEE Performance] ) * 100
)
```

```dax
-- B-BN-06: Bottleneck Quality Loss PP
-- Sequentially weighted by Availability and Performance.
[Bottleneck Quality Loss PP] =
IF(
    ISBLANK( [Bottleneck OEE Quality] ) || ISBLANK( [Bottleneck OEE Performance] ) || ISBLANK( [Bottleneck OEE Availability] ),
    BLANK(),
    [Bottleneck OEE Availability] * [Bottleneck OEE Performance] * ( 1 - [Bottleneck OEE Quality] ) * 100
)
```

---

### Step 4: Rewrite `[Selected Loss PP]` — Panel C SWITCH Measure (B-BN-07)

Replaces original B-11b. `_Six_Big_Losses` disconnected stub table is unchanged.

```dax
-- B-BN-07: Selected Loss PP (Bottleneck) — REPLACES B-11b
-- Companion measure for Panel C Waterfall chart.
-- Routes _Six_Big_Losses[Loss Type] to bottleneck-scoped OEE loss measures.
-- "Ideal OEE" bar = 100.
-- Home table: _Measures_B
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
```

**Why "Ideal OEE" = 100:** Ideal OEE must always start at 100%. The losses are calculated sequentially (Availability Loss = `(1 - A)`, Performance Loss = `A * (1 - P)`, Quality Loss = `A * P * (1 - Q)`) so that the final composed bar perfectly matches the composed `A * P * Q` value of the bottleneck component.

---

### Step 5: Panel C Visual Re-Binding in Power BI Desktop

| Field well | Old binding | New binding |
|---|---|---|
| Category | `_Six_Big_Losses[Loss Type]` | `_Six_Big_Losses[Loss Type]` (unchanged) |
| Y Values | `[Selected Loss PP]` (B-11b) | `[Selected Loss PP (Bottleneck)]` (B-BN-07) |

**Title:** Change from `"OEE Loss Decomposition"` to `"Bottleneck OEE Decomposition"`.

**Semantic accuracy confirmation:** After re-binding Panel C to `[Selected Loss PP (Bottleneck)]`, **KPI Card 1 must also be re-bound** to `[Bottleneck OEE Composite]` (B-BN-08). Do not use `[System OEE Composite]` for KPI Card 1, as a series-system OEE mathematically diverges from a single bottleneck's OEE. After both are bound, verify:
1. "Ideal OEE" bar height matches KPI Card 1 (`[Bottleneck OEE Composite]`) + total loss PPs
2. Final composed bar = KPI Card 1 value
3. With no slicer, both visuals describe the lowest-health-score component (typically Bearing)

---

## Part 2: Page 2 — Component Health / Degradation Build Log

### Page Identity

| Property | Value |
|---|---|
| Page name | `Component Health` |
| Page type | Drill-through target |
| Drill-through field | `dim_components[component_id]` |
| Canvas size | 1280 x 720 px (16:9) |
| Back button | Auto-generated; top-left, 20px from canvas edge |
| Slicer scope | Date range only; component fixed by drill-through |

---

### Core Visual Layout

> **IMPORTANT: Page 2 Data Model Rules**
> All Page 2 time axes MUST use `dim_calendar[year_month]` or `dim_calendar[date]`. Never use `dim_production_shifts` for time-axis filtering — it cannot cross-filter `dim_failure_log` due to relationship direction, and will silently starve MTBF-dependent visuals (Panel D) of data.

```
+===================================================================================+
|  COMPONENT HEALTH — [BEARING]                       [< Back to Fleet Overview]    |
|  [Date Range Slicer: Last 90 days]                                                |
+==============+==============+==============+==============+=======================+
|  KPI Card 1  |  KPI Card 2  |  KPI Card 3  |  KPI Card 4  |  KPI Card 5           |
|  Avg Health  |  MTBF (hrs)  |  MTTR (hrs)  |  Empirical   |  MTBF vs Weibull      |
|  Score (A-01)|  (C-02)      |  (C-03)      |  Avail.(C-06)|  Delta hrs (C-08)     |
+=======================================+===========================================+
|  PANEL A (50% width)                  |  PANEL B (50% width)                      |
|  LINE CHART: MTBF + MTTR Trend        |  RADAR CHART: Risk Profile                |
|  x: dim_calendar[year_month]          |  Category: _Radar_Metrics[Metric Name]    |
|  y1: [MTBF Hours] (C-02)              |  Values: [Radar Component Value] (D-11),  |
|  y2: [MTTR Hours] (C-03)              |          [Radar Fleet Avg Value] (D-12)   |
|  Ref line: [Weibull MTBF Model]       |                                           |
|                                       |                                           |
|                                       |                                           |
+=======================================+===========================================+
|  PANEL C (50% width)                  |  PANEL D (50% width)                      |
|  CLUSTERED BAR: OEE A/P/Q by Month    |  DIVERGING BAR: MTBF vs Weibull Delta     |
|  y: dim_calendar[year_month]          |  y: dim_calendar[year_month]              |
|  x: B-04 (Avail), B-06 (Perf),        |  x: [MTBF vs Weibull Delta] (C-08)        |
|       B-05 (Qual)                     |  Colour: positive=teal / negative=red     |
|  Ref line at 1.0                      |  Zero baseline prominent                  |
+=======================================+===========================================+
|  PANEL E (100% width)                                                              |
|  PANEL E (100% width)                                                              |
|  LINE AND STACKED COLUMN CHART: Sensor Health Score - Daily Degradation Trend     |
|  x: dim_calendar[date] (daily)                                                    |
|  column-y: [Alarm Band Shade] at alarm breach timestamps (amber, 20% opacity)     |
|  line-y: [Avg Health Score] (A-01) - range 0-100                                  |
|  line-y: [Failure Marker Plot Y] (A-04b) as red circle markers                       |
|  Zoom slider: On                                                                   |
+===================================================================================+
```

---

### KPI Card Row — Field Bindings and Conditional Formatting

| Slot | Measure | Home Table | Format | CF Rule |
|---|---|---|---|---|
| KPI Card 1 | `[Avg Health Score]` (A-01) | `_Measures_A` | 1 dp, % symbol | Background: <60 Red #B00020; <75 Amber #F57F17; >=75 Teal #00695C |
| KPI Card 2 | `[MTBF Hours]` (C-02) | `_Measures_C_MTBF` | 1 dp, "hrs" | Font: Format by Field value -> bind to [MTBF Delta Color] |
| KPI Card 3 | `[MTTR Hours]` (C-03) | `_Measures_C_MTBF` | 1 dp, "hrs" | Font: >8 Red (shift-boundary breach); <=8 White |
| KPI Card 4 | `[Empirical Availability]` (C-06) | `_Measures_C_MTBF` | 2 dp, % | Label: "Inherent Avail." |
| KPI Card 5 | `[MTBF vs Weibull Delta]` (C-08) | `_Measures_C_MTBF` | +/- prefix, 1 dp, "hrs" | Positive -> up-arrow icon, Teal; Negative -> down-arrow, Red |

---

### Panel A — Degradation Trend Lines: Field Bindings

**Visual type:** Line Chart

| Field well | Binding | Notes |
|---|---|---|
| X-axis | `dim_calendar[year_month]` | Sort column: `dim_calendar[year_month_key]` (chronological, not alphabetical) |
| Values (y-primary) | `[MTBF Hours]` (C-02) | Left axis |
| Values (y-secondary) | `[MTTR Hours]` (C-03) | Enable Secondary Y-axis in Format pane; separate scale avoids MTTR values being dwarfed by MTBF range |
| Legend | Auto-populated | Rename series: "MTBF (hrs)" and "MTTR (hrs)" |

**Reference line — Weibull MTBF:**
- Analytics pane > Constant line > Value > click `fx` (Conditional formatting) > Field value > Select `[Weibull MTBF Model]`
- Color: `#9E9E9E` grey dashed; label: "Weibull MTBF Model"; position: Behind

| Format property | Value |
|---|---|
| Line style MTBF | Solid, 2.5px, Teal #00695C |
| Line style MTTR | Dashed, 1.5px, Amber #F57F17 |
| Markers | On, circle, size 5 |
| Y-axis start | 0 (both axes) |
| Data labels | Off |

---

### Panel E — Daily Health Score Trend: Field Bindings and Alarm Shading

**Visual type:** Line and Stacked Column Chart (workaround for lack of native Line + Area + Scatter visual)

| Field well | Binding | Notes |
|---|---|---|
| X-axis | `dim_calendar[date]` (daily) | Disable hierarchy - use Date level only |
| Column y-axis | `[Alarm Band Shade]` | Renders as background column spanning full height at alarm breach timestamps |
| Line y-axis | `[Avg Health Score]` (A-01) | Left axis 0-100 |
| Line y-axis | `[Failure Marker Plot Y]` (A-04b) | DECISION MADE - confirm with user: Rendered as a line with 0 stroke width and markers on, to simulate a scatter plot on the same axis. Note: This measure (which returns Health Score when failures > 0) must be used instead of raw [Failure Event Count] to anchor markers properly to the trendline. |
| Line y-axis | `[Avg R_Derated]` (A-03) | DECISION MADE - confirm with user: Removed from Panel E to accommodate the visual workaround (Line and Stacked Column chart only supports a single secondary axis which we cannot use effectively here). |

**Alarm band DAX:**
```dax
-- [Alarm Band Shade]
-- Returns 100 (full y-axis height) when is_anomaly readings exist in the daily context,
-- else BLANK. Used as an Area series on Panel E to shade alarm breach periods.
-- Home table: _Measures_A
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

| Format property | Value |
|---|---|
| Health Score line | Solid 2.5px Teal #00695C |
| Alarm band column | Amber #F57F17, 20% transparency |
| Failure markers line | 0px stroke width, Red circles #B00020 markers, size 8 |
| Primary Y-axis | 0-100, title: "Health Score (%)" |
| X-axis label rotation | 45 degrees |
| Zoom slider | On |

---

### Diverging Bar Colour Measure — Panel D

```dax
-- [MTBF Delta Color]
-- Returns hex colour string for Panel D diverging bar conditional formatting.
-- Positive delta (observed MTBF >= model MTBF) = Teal; Negative = Red.
-- Home table: _Measures_C_MTBF
[MTBF Delta Color] =
IF(
    ISBLANK( [MTBF vs Weibull Delta] ),
    BLANK(),
    IF( [MTBF vs Weibull Delta] >= 0, "#00695C", "#B00020" )
)
```

Apply via: Format pane > Data colors > Conditional formatting > Field value > `[MTBF Delta Color]`

---

### Drill-Through Setup

1. Navigate to Page 2 (Component Health) in Power BI Desktop.
2. Visualizations pane > Drill-through well: drag `dim_components[component_id]`.
3. Power BI auto-generates Back button — position: top-left, 20px inset.
4. Verify: Right-click component bar on Page 1 Panel B > Drill through > Component Health. All Page 2 KPI cards and panels must reflect the right-clicked component's data.

---

### Viva Prep — Day 27

**Q: Why decompose OEE at the bottleneck component rather than fleet average?**
A: System OEE is governed by the weakest-link (series reliability block). Decomposing fleet-average losses against a bottleneck KPI misleads: the waterfall would appear to explain a KPI it does not. Option 2 makes Panel C and KPI Card 1 describe the same subject (e.g., Bearing), making the diagnostic chain auditable.

**Q: How does `[Bottleneck Component ID]` behave under slicer context?**
A: If a component slicer is applied, `VALUES(dim_components[component_id])` reduces to one member, and the measure returns that component's ID. In the all-components context (no slicer), it returns the globally lowest-health-score component — the system bottleneck.

**Q: Why was the secondary axis (Avg R_Derated) removed from Panel E?**
A: To accommodate the Line and Stacked Column Chart workaround for plotting failure event markers and alarm bands on the same visual, which only supports a single line axis. Since `[Avg Health Score]` and `[Avg R_Derated]` are mathematically equivalent (Health Score = R_derated x 100), the loss of analytical precision is acceptable to maintain the visual alert context.

**Q: How are failure events marked on Panel E without native Power BI annotation?**
A: Using the Line and Stacked Column Chart workaround: `[Failure Marker Plot Y]` is plotted as a line series on the same y-axis, but formatted with 0px stroke width and markers enabled. By using this measure (which returns Health Score when failures occur) instead of raw `[Failure Event Count]`, the markers correctly anchor onto the trend line rather than flattening at the bottom of the 0-100 axis.

---

*End of Day 27 build log. Panel C bottleneck DAX complete (B-BN-00 to B-BN-07). Page 2 Component Health specification complete.*

---

## Part 3: Day 28 — Panel F: Criticality Ranking Visual (Page 2)

**Date:** 2026-08-10
**Status:** Panel F specified. D-13 [Criticality Rank] and D-16 [Criticality Ranking Title] appended to dax_and_m_scripts.md.

---

### Background and Scope

Panel F is a horizontal bar chart placed at the bottom of Page 2 (Component Health / Degradation).
It ranks all 5 pipeline components by their Composite Criticality Index (CCI Score, D-01) so that
when a user drills through from Page 1 Panel B to a specific component, they immediately see where
that component sits in the fleet-wide criticality order.

**CCI source:** composite_criticality.py (Day 19). Actual locked weights:
  - SRS (graph structural risk): 0.40
  - Weibull Unreliability (1 - R(t=2920h)): 0.35
  - Threshold Breach Rate (ISO alarm breach frequency): 0.25

**Coupling is the CCI rank 1 component** (composite_criticality = 0.804) per the actual
composite_criticality.py output. Coupling scores highest overall due to high normalized SRS
(srs_norm = 0.80), highest normalized Weibull unreliability (unreliability_norm = 0.988), and
moderate TBR (tbr_norm = 0.553). **Motor Housing** (position 3) is the true betweenness-central
intermediary (BC = 0.333, highest in the DAG) with SRS = 0.75. **Bearing** is CCI rank 5
(composite = 0.457): it is the most upstream source node (position 1, BC = 0.0 -- no shortest
paths pass *through* it as an intermediary) and has the lowest TBR in the fleet (TBR = 0.007).
Full CCI ranking: Coupling (0.804) > Shaft (0.753) > Motor Housing (0.710) > Gearbox (0.549) > Bearing (0.457).

---

### New DAX Measures (Day 28)

#### D-13: [Criticality Rank]

```dax
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
```

**Why ALL and REMOVEFILTERS:**
- Drill-through filters are applied as external page-level filters. `ALLSELECTED` would restore this filter, meaning if a single component was selected, it would rank only that 1 component against itself.
- `ALL(dim_components)` in the table argument ensures RANKX iterates over all 5 components.
- `REMOVEFILTERS(dim_components[component_id])` in the value expression ensures the score is computed for each component without the drill-through context suppressing the other 4 components. This produces a true relative ranking within the fleet.

**Why DENSE and not SKIP:**
- There are only 5 components. SKIP would produce gaps (e.g. 1, 3, 5) if two components tie on
  CCI Score (possible if both have near-identical normalised sub-metrics). DENSE produces 1, 2, 2, 3
  which is less confusing in a 5-row bar chart.

---

#### D-16: [Criticality Ranking Title] (Dynamic -- ISFILTERED)

```dax
-- D-16: Criticality Ranking Title (Dynamic -- ISFILTERED)
-- Context-aware visual title for Panel F.
-- ISFILTERED(dim_components[component_id]) = TRUE when drill-through from
-- Page 1 Panel B has pushed a component_id value filter into the Page 2
-- evaluation context.
-- Note: In our single-direction Star Schema, dim_calendar filters fact tables 
-- but DOES NOT cross-filter dim_components. Therefore, date slicers will never 
-- filter out components, and SELECTEDVALUE safely resolves without needing 
-- REMOVEFILTERS(dim_calendar).
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
```

**ISFILTERED() semantics:**
- Detects direct column filters only -- not filters propagated through relationships. The
  drill-through mechanism applies a direct value filter to `dim_components[component_id]`, so
  ISFILTERED correctly returns TRUE in the drill-through context.
- ISFILTERED does NOT return TRUE when a related table (e.g. dim_calendar) filters dim_components
  indirectly. This is the correct behaviour -- we only want the title to name a component when the
  user has explicitly navigated to that component via drill-through.


---

### Panel F: Power BI Desktop Field Bindings

**Visual type:** Clustered Bar Chart (horizontal orientation -- Y axis = categories, X axis = values)
**Canvas position:** Row 5 (below Panel E). X=0, Y=720, W=1275, H=220.
**Page:** Page 2 (Component Health / Degradation)

| Well | Field / Measure | Notes |
|---|---|---|
| Y axis | `dim_components[component_name]` | One bar per component. Must enable 'Show items with no data'. |
| X axis | `[CCI Score Fleet View]` (D-01c) | 0.0 to 1.0 range |
| Tooltips | `[Criticality Rank]` (D-13) | Rank number shown on hover |
| Tooltips | `[CCI Tier Fleet View]` (D-14) | Tier label (Critical/High/Moderate/Low) on hover |
| Tooltips | `[SRS Score Fleet View]` (D-14) | Sub-metric breakdown on hover |
| Tooltips | `[Weibull Unreliability Fleet View]` (D-14) | Sub-metric breakdown on hover |
| Tooltips | `[Threshold Breach Rate Fleet View]` (D-14) | Sub-metric breakdown on hover |
| Data colours | `[CCI Tier Color Fleet View]` (D-14) | Format > Data colours > fx > Field value |
| Visual title | `[Criticality Ranking Title]` (D-16) | Format > Title > Title text > fx > Field value |

**Why D-13 goes in Tooltips (not Legend or Data labels):**
The bar chart Y axis already sorts by component_name. To sort bars by rank (rank 1 = top), use the
visual sort control: click the Y axis sort icon > Sort by "Criticality Rank" > Ascending (rank 1
at top). D-13 must be in the visual's query (Tooltips well satisfies this) for the sort to work.

---

### Panel F: Format Settings

| Property | Value |
|---|---|
| X axis min | 0 (fixed) |
| X axis max | 1.0 (fixed) |
| X axis display units | None |
| X axis title | "Composite Criticality Index (CCI)" |
| Y axis title | OFF (component names self-describe) |
| Y axis font | Outfit 9px |
| Bar inner padding | 40% |
| Data labels | ON; Position = Outside End; Font = Outfit 9px |
| Background | #0D1117 |
| Border | None |
| Legend | OFF |
| Gridlines | Vertical only; colour #1E2D2F; 1px; dashed |
| Sort | Y axis by [Criticality Rank] Ascending (rank 1 = top) |

---

### Panel F: Conditional Formatting Steps (Power BI Desktop)

1. Select Panel F visual.
2. Format pane > Visual > Bars > Colours > click **fx** (conditional formatting icon).
3. In the dialog: Format style = **Field value**; Based on field = `[CCI Tier Color Fleet View]` (D-14).
4. Click OK. Each bar now renders in its tier colour (Critical = #C62828, High = #F57F17,
   Moderate = #FFC107, Low = #2E7D32).
5. Format pane > General > Title > Title text > click **fx**.
6. In the dialog: Format style = **Field value**; Based on field = `[Criticality Ranking Title]` (D-16).
7. Click OK. Title updates dynamically on drill-through.

**Note on D-06c hex values (from dax_and_m_scripts.md):**

| Tier | Hex | Label in dim_criticality[cci_tier] |
|---|---|---|
| Critical | #C62828 | "Critical" |
| High | #F57F17 | "High" |
| Moderate | #FFC107 | "Moderate" |
| Low | #2E7D32 | "Low" |

---

### Panel F: Drill-Through Behaviour

When accessed via drill-through from Page 1 Panel B (filter: `dim_components[component_id]` = e.g. 1 for Bearing):

- All 5 bars are rendered because D-13 wraps RANKX(ALL(dim_components)) in a CALCULATE with REMOVEFILTERS(dim_components[component_id]) (drill-through filter ignored for ranking scope).
- [CCI Score] (D-01) evaluates properly during RANKX context transition for each component row. The drill-through filter does NOT suppress the other bars.
- The dynamic title (D-16) detects ISFILTERED = TRUE and names the component:
  "Criticality Ranking - Bearing vs Fleet".
- To visually distinguish the drilled-through component's bar: add an Analytics pane Constant line
  bound to a fixed value representing that component's CCI. Because CCI is a stored column value
  (not computed at runtime by a measure that changes per bar), the correct approach is:
    -- Add a Reference line via Analytics pane > Constant line > Value = the numeric CCI of the
       selected component (e.g. 0.87 for Bearing). Enter this manually or use a card visual on
       the page that shows [CCI Score] for the drilled-through component.
    -- Line style: dashed, Teal #00695C, 1.5px. Label: "Selected CCI", font 9px, right position.

---

### Panel F: Tier Legend (Static Text Box)

Add a text box to the top-right corner of Panel F (X=1040, Y=655, W=235, H=90):

```
  Critical  >= 0.75
  High      >= 0.50
  Moderate  >= 0.25
  Low        < 0.25
```

Colour each line by applying the tier colour to the text character level in Power BI's text box
rich-text editor. Font: Outfit 8px. Background: #0D1117. No border.

---

### Viva Prep -- Day 28: Panel F

**Q: What is the final DAX for [Criticality Rank] (D-13) and why is it so complex?**
A: The final, correct DAX is:
```dax
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
```
**REJECTED APPROACH (Do not defend):** The original logic attempted to use `ALLSELECTED(dim_components[component_id])`. This was a major bug because a drill-through pushes a hard filter on `component_id`. `ALLSELECTED` merely restores that external page-level filter—it does not clear it. As a result, the visual would be suppressed to show only 1 bar (the drilled-through component). 
**THE FIX:** We must supply the entire table `ALL(dim_components)` to `RANKX` so it iterates all 5 components, and wrap the whole thing in `CALCULATE(..., REMOVEFILTERS(dim_components[component_id]))` to explicitly strip the drill-through filter. The omitted `<value>` argument in RANKX safely picks up the visual's internal row context (`component_name`), accurately comparing each bar against the full fleet.

**Q: How do page-level filters interact with the bar chart's axis?**
A: **REJECTED BELIEF (Do not defend):** We originally thought that a page-level filter on `component_id` does not suppress visual rows if the axis is mapped to `component_name`. This is completely false. 
**THE REALITY:** `component_id` and `component_name` are in the same table (`dim_components`). Filtering `component_id` directly filters the table. The visual engine plots the distinct `component_name` values remaining in `dim_components` in the current filter context. Therefore, a drill-through on `component_id = 1` absolutely suppresses the other 4 rows. To render all 5 bars, you MUST check "Show items with no data" on the Y-axis AND ensure every measure plotted in the visual uses `REMOVEFILTERS(dim_components[component_id])`. This is exactly why the D-14 Fleet View wrappers were created.

**Q: Why are the D-14 Fleet View wrappers required?**
A: The D-14 measures (e.g., `[SRS Score Fleet View] = CALCULATE( [SRS Score], REMOVEFILTERS( dim_components[component_id] ) )`) are required for the tooltips and conditional formatting on Panel F. Because a drill-through suppresses the other 4 components, any standard measure (like `[SRS Score]`) would evaluate to BLANK for those 4 bars. The Fleet View wrappers strip the `component_id` drill-through filter, allowing the visual's internal row context (`component_name`) to correctly pull the metrics for all 5 bars.

**Q: Why doesn't D-16 [Criticality Ranking Title] use REMOVEFILTERS(dim_calendar)?**
A: The final D-16 DAX is:
```dax
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
```
**REJECTED APPROACH (Do not defend):** The original logic wrapped `SELECTEDVALUE` in `REMOVEFILTERS(dim_calendar)` to protect it from date slicers. This guard was removed as functionally useless. In our single-direction star schema, `dim_calendar` filters fact tables, but it DOES NOT cross-filter upstream to `dim_components`. Therefore, a date slicer can never filter out a component name, and `SELECTEDVALUE` resolves perfectly without the `REMOVEFILTERS(dim_calendar)` guard. ISFILTERED is correctly used because it detects the direct `component_id` filter pushed by the drill-through, distinguishing it from an unfiltered page view.

---

*End of Day 28 additions to build log. Panel F Criticality Ranking visual fully specified.*
