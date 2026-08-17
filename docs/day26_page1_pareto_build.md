# Day 26 — Page 1 Refinement: Panel D Status Bar Pareto Build

**Date:** 2026-08-10
**Phase:** 2.3 Power BI — Day 26
**Scope:** Panel D (Status Bar Pareto) — D-07 Root Cause Downtime by `pipeline_label`
**Page:** Page 1 — Fleet Overview (1280 × 720 px)

> [!IMPORTANT]
> Panel C (Waterfall Chart) is **out of scope for Day 26**. An unresolved semantic mismatch exists between the bottleneck OEE metric shown on KPI Card 1 (`[System OEE Composite]`) and the fleet-average OEE decomposition shown on Panel C. **Do not build, modify, or add reference lines to Panel C until this design decision is resolved.**

---

## 1. Pre-Flight Checklist

Before touching any visual, confirm the following in the saved Day 25 `.pbix`:

- [ ] Canvas is **1280 × 720 px** (File > Page Setup)
- [ ] Theme `powerbi_theme.json` is applied (View > Themes)
- [ ] You are on **Page 1 — Fleet Overview** (not Page 2 or Page 3)
- [ ] Inactive relationship **R-10** (`fact_downtime_events[root_cause_component_id]` → `dim_components[component_id]`) is confirmed **inactive** (dashed line in Model view)
- [ ] Measure `[Root Cause Downtime Min]` (D-07) is present in `_Measures_D` home table and uses `USERELATIONSHIP()`
- [ ] The existing Panel D visual is a **Clustered Bar chart** at position X=773, Y=460, W=380, H=255

If any pre-flight item fails, resolve it before proceeding. Do not continue with a broken model state.

---

## 2. Step D-01 — Change Visual Type to Line and Clustered Column Chart

The existing Panel D visual is a Clustered Bar chart (horizontal bars). Day 26 requires converting it to a **Line and Clustered Column chart** (vertical columns + line overlay).

**UI Steps:**

1. Click on the Panel D visual to select it.
2. In the **Visualizations pane**, click **"..."** (three dots) at the top-right of the visual type gallery, or scroll to find the **Line and clustered column chart** icon.
   - Icon description: vertical columns with a line overlay on top; it sits in the "Combo" chart group.
3. Click the **Line and clustered column chart** icon.
4. Power BI will retain existing field bindings where field-well names match. Verify the following field well mappings after the conversion:

| Field Well (new name) | Should contain |
|---|---|
| **Shared axis** (X-axis) | `dim_components[pipeline_label]` |
| **Column values** | `[Root Cause Downtime Min]` (D-07) |
| **Line values** | *(empty — to be filled in Step D-05)* |
| **Column series** | *(empty)* |

> [!NOTE]
> If the old Clustered Bar had `pipeline_label` on the Y-axis (horizontal) and D-07 on the X-axis (horizontal), Power BI may place them incorrectly after conversion. Manually drag fields into the correct wells as listed above.

5. Resize/reposition the visual to maintain the locked coordinates: **X=773, Y=460, W=380, H=255**.
   - Use Format > Position and Size (right-click menu) to set these precisely.

---

## 3. Step D-02 — Bind `pipeline_label` to Shared Axis (X-Axis)

`pipeline_label` is a column in `dim_components` that provides the human-readable root-cause component name (e.g., "Bearing", "Shaft", "Motor Housing", "Coupling", "Gearbox"). It is displayed on the Pareto X-axis.

**Important — Relationship Path:**

`pipeline_label` comes from `dim_components`. The D-07 measure activates R-10 via `USERELATIONSHIP()`, which links `fact_downtime_events[root_cause_component_id]` → `dim_components[component_id]`. This means the X-axis field (`pipeline_label`) and the measure (D-07) share the same relationship path when USERELATIONSHIP is active inside the measure — **no additional configuration is needed on the axis field itself**.

**UI Steps:**

1. In the **Visualizations pane > Fields** section, expand `dim_components`.
2. Drag `dim_components[pipeline_label]` into the **Shared axis** field well.
3. Confirm: the X-axis should show 5 labels — Bearing, Shaft, Motor Housing, Coupling, Gearbox (order will be corrected in Step D-03).

---

## 4. Step D-03 — Sort Descending by D-07 Value

The Pareto principle requires bars sorted largest-to-smallest (left-to-right). Power BI's default sort on a category axis is alphabetical — override this.

**UI Steps:**

1. Click on the Panel D visual to select it.
2. Click the **"..."** (More options) button at the top-right corner of the visual (not the Visualizations pane — the one on the visual itself when hovered).
3. In the dropdown, click **"Sort axis"** > **"Root Cause Downtime Min"** (the D-07 measure name as it appears in the visual).
4. Click **"..."** again > **"Sort axis"** > confirm **"Sort descending"** is checked (a checkmark appears next to it).

**Verification:**
- The component with the highest total root-cause downtime minutes should appear as the **leftmost column**.
- Visually, the bar heights should decrease monotonically left-to-right (a classic Pareto column shape).
- If ties exist at any position, the tie-breaking order is alphabetical by `pipeline_label` — this is acceptable.

---

## 5. Step D-04 — Define DAX Measure: `[Cumulative Root Cause DT %]`

This measure computes the running cumulative proportion of root-cause downtime, sorted descending. It produces the Pareto cumulative line (S-curve / convex-decreasing curve).

**DAX Pattern — Value-based Cumulative Proportion with Tie-Breaker:**

```dax
[Cumulative Root Cause DT %] =
VAR _CurrentLabel = MAX( dim_components[pipeline_label] )
VAR _CurrentDT = [Root Cause Downtime Min]
VAR _TotalDT = CALCULATE( [Root Cause Downtime Min], ALL( dim_components ) )
VAR _CumulativeDT =
    CALCULATE(
        [Root Cause Downtime Min],
        FILTER(
            ALL( dim_components ),
            [Root Cause Downtime Min] > _CurrentDT ||
            ([Root Cause Downtime Min] = _CurrentDT && dim_components[pipeline_label] <= _CurrentLabel)
        )
    )
RETURN
    IF(
        ISINSCOPE( dim_components[pipeline_label] ),
        DIVIDE( _CumulativeDT, _TotalDT, 0 ),
        1.0
    )
```

**Where to enter this measure:**

1. In the **Data pane**, expand the `_Measures_D` home table (or the dedicated downtime measures table).
2. Right-click `_Measures_D` > **"New measure"**.
3. Paste the DAX above into the formula bar.
4. Press **Enter** to commit.
5. In **Measure Tools** ribbon: set **Format** = **Percentage**, **Decimal places** = 1.
6. Rename the measure to `Cumulative Root Cause DT %` (Power BI will prefix with the home table name — ensure the final display name shown in the formula bar matches exactly).

**DAX Pattern Explanation (for viva clarity):**

| Variable | Purpose |
|---|---|
| `_CurrentLabel` | Captures the pipeline_label of the current row context in the visual (tie-breaker) |
| `_CurrentDT` | Captures the D-07 downtime minute total of the current row context |
| `_TotalDT` | Grand total of D-07 across all components (ALL() removes any axis filter) |
| `_CumulativeDT` | Sum of D-07 for all labels with greater DT, plus tied labels that sort alphabetically before or equal to this label |
| `DIVIDE(...)` | Returns the fraction as a decimal (0.0 to 1.0) — formatted as % at display |

**Why tie-breaking value logic rather than RANKX?**

`RANKX` with `Dense` rank mode fails when two components have equal downtime. If both get Rank 1, a `RANKX <= _CurrentRank` filter includes both simultaneously, causing the cumulative line to instantly jump to the combined total on the first bar. The value-based filter `[Root Cause Downtime Min] > _CurrentDT || ([Root Cause Downtime Min] = _CurrentDT && dim_components[pipeline_label] <= _CurrentLabel)` correctly handles ties by using alphabetical order (`<= _CurrentLabel`) as a tie-breaker, ensuring exactly one component is added per step. Additionally, `ISINSCOPE` ensures the grand total row evaluates to 100%.

---

## 6. Step D-05 — Add Cumulative Measure as Line Series on Secondary Y-Axis

**UI Steps:**

1. With Panel D selected, go to **Visualizations pane > Fields**.
2. Drag `[Cumulative Root Cause DT %]` from the `_Measures_D` table into the **Line values** field well.
3. Confirm: the visual now shows two series — the column bars (D-07) and a line overlay (`[Cumulative Root Cause DT %]`).
4. The line should automatically bind to the **secondary Y-axis** (right axis) in the Line and Clustered Column chart. If it does not:
   - Click on the line series in the visual legend.
   - In the **Visualizations pane > Format > Secondary y-axis**, toggle the secondary y-axis **On**.

**Visual Confirmation:**
- Two y-axes should now appear: left axis (downtime minutes, auto-scaled) and right axis (percentage, to be formatted in Step D-06).
- The line should overlay the columns and rise from the first bar onward.

---

## 7. Step D-06 — Format Secondary Y-Axis as Percentage (min=0, max=1.0)

The secondary Y-axis must display values as a percentage from 0% to 100%.

**UI Steps:**

1. With Panel D selected, go to **Visualizations pane > Format** (paint roller icon).
2. Expand **"Secondary y-axis"**.
3. Set the following properties:

| Property | Value |
|---|---|
| **On/Off toggle** | **On** |
| **Start** (minimum) | `0` |
| **End** (maximum) | `1` |
| **Display units** | **None** (the measure is already formatted as %, so the axis label will show "0%, 20%, 40%...") |
| **Decimal places** | `0` |
| **Title** | `Cumulative %` |
| **Title font** | Match body font from theme (Segoe UI, 10pt) |
| **Grid lines** | Off (primary Y-axis grid lines are sufficient; secondary grid lines add visual noise) |

> [!IMPORTANT]
> Set **End = 1** (not 100). Power BI reads the DAX measure value as a decimal (0.0–1.0) and applies the % format at display time. If you set End = 100, the axis will scale to 10000% (100 × 100) — wrong. The measure returns 1.0 for "100%", so the axis maximum must be 1.0.

4. Confirm: the right axis now shows tick marks at 0%, 20%, 40%, 60%, 80%, 100%.

---

## 8. Step D-07 — Add 80% Constant Reference Line on Secondary Axis

The 80% reference line is the Pareto threshold — the vertical position at which ~80% of cumulative downtime has been explained by the subset of components to the left of it.

**UI Steps:**

1. With Panel D selected, go to **Visualizations pane > Analytics** (magnifying glass / line icon).
2. Click **"+ Add"** next to **"Constant line"** (or "Y-Axis Constant Line" — the label varies by Power BI version).

> [!NOTE]
> In some Power BI Desktop versions, reference lines on combo charts offer separate options for the primary vs secondary axis. If prompted, select **Secondary axis** for this constant line.

3. Set the following properties on the constant line:

| Property | Value |
|---|---|
| **Value** | `0.8` (= 80%) |
| **Color** | `#F57F17` (Amber — consistent with alert-level threshold color in theme) |
| **Style** | Dashed |
| **Position** | Behind (line sits behind bars, not on top) |
| **Data label** | On |
| **Label** | `80% Threshold` |
| **Label horizontal position** | Right |
| **Label vertical position** | Above |
| **Label font** | Segoe UI, 9pt, `#F57F17` |

> [!NOTE]
> The value `0.8` must match the decimal scale of the secondary axis (max=1). If you mistakenly enter `80`, the reference line will appear at 80 × 100% = 8000% — completely off-axis and invisible.

---

## 9. Verification Steps — Pareto Curve Correctness

After completing Steps D-01 through D-07, perform the following verification checks before locking in Panel D.

### 9.1 Cumulative Line Reaches 100%

| Check | How to verify | Pass condition |
|---|---|---|
| Rightmost bar cumulative value | Hover the mouse over the **last** (rightmost, lowest-DT) column's line data point | Tooltip shows `Cumulative Root Cause DT % = 100.00%` |
| First bar cumulative value | Hover over the **first** (leftmost, highest-DT) column's line data point | Tooltip shows the single-component % of total — typically 30–50% for a realistic 5-component fleet |
| Grand total check | Add a Card visual off-canvas, bind `[Cumulative Root Cause DT %]` with no filter context | Card should show `100.00%` (grand total = 100% of all downtime) — delete this Card after verification |

### 9.2 Convex-Decreasing Curve Shape

The cumulative line should increase at a **decreasing rate** (convex shape):
- The step from bar 1 to bar 2 should be the **largest vertical jump**.
- Each subsequent step should be **smaller** than the previous step.
- The line should approach 100% asymptotically (last few bars add very small increments).

If the line is **concave** (increasing rate — getting steeper as it goes right), the sort order is wrong — bars are ascending instead of descending. Return to Step D-03 and confirm "Sort descending" is checked.

If the line is **flat then sudden jump at end**, a single component dominates all downtime — this is valid analytically (extreme Pareto concentration), not a bug.

### 9.3 Sort Alignment Check

| Check | Pass condition |
|---|---|
| Column heights | Strictly non-increasing left-to-right |
| Axis labels | Component names visible, not truncated |
| Sort indicator | Visual header shows sort icon on D-07 measure name, pointing downward |

### 9.4 Secondary Axis Scale Check

| Check | Pass condition |
|---|---|
| Axis minimum | 0% (line starts at or near 0% for the leftmost bar's baseline — the line point itself will not be at 0% since the first bar is already the highest-DT component) |
| Axis maximum | 100% (last tick mark at 100%) |
| 80% reference line | Horizontal dashed amber line visible at the 80% tick on the right axis |
| Line data points | All 5 data points visible and between 0%–100% |

### 9.5 USERELATIONSHIP Integrity Check

Confirm that the X-axis labels reflect **root-cause** responsibility, not victim component:

1. In a separate temporary Card visual (off-canvas), place `[Root Cause Downtime Min]` with `pipeline_label` from `dim_components` as a filter context.
2. Compare totals: the component with the highest D-07 value should be the one you'd expect to cause the most downstream failures (e.g., a Bearing with low health score is a plausible root cause of most downtime events).
3. Cross-check against `fact_downtime_events[root_cause_component_id]` in the data — the RANKX ranking should match a manual sort of root-cause counts.

If the ranking is dominated by unexpected components, verify that R-10 is inactive in Model view and that D-07's USERELATIONSHIP() references the correct relationship.

---

## 10. Final Panel D Lock-In Checklist

| Item | Status |
|---|---|
| Visual type: Line and Clustered Column chart | ☐ |
| Shared axis: `dim_components[pipeline_label]` | ☐ |
| Column values: `[Root Cause Downtime Min]` (D-07) | ☐ |
| Line values: `[Cumulative Root Cause DT %]` (new measure) | ☐ |
| Sort: descending by D-07 | ☐ |
| Secondary Y-axis: On, min=0, max=1, display as % | ☐ |
| 80% constant reference line: value=0.8, dashed amber, label "80% Threshold" | ☐ |
| Cumulative line reaches 100% at rightmost bar | ☐ |
| Curve shape: convex-decreasing (largest step first) | ☐ |
| Visual position: X=773, Y=460, W=380, H=255 | ☐ |
| Panel C: **NOT modified** (open semantic issue — deferred) | ☐ |

When all checkboxes are ticked, save the `.pbix`. Day 26 is complete.

---

## 11. Out of Scope (Day 26)

The following items are **explicitly excluded** from today's build:

| Item | Reason excluded |
|---|---|
| Panel C (Waterfall Chart) modifications | Unresolved semantic mismatch: KPI Card 1 shows bottleneck OEE; Panel C decomposes fleet-average OEE. These are different denominators and different analytical subjects. Modifying Panel C without resolving this contradiction risks cementing the misleading narrative. Deferred pending design decision. |
| Page 3 Pareto charts | Out of scope for Page 1 Day 26 refinement. Panel C on Page 3 (D-08 Upstream Defect Units) may be addressed in a future day once the Page 1 Panel C issue is resolved and the Pareto pattern is confirmed correct on Panel D. |
| New DAX measures beyond `[Cumulative Root Cause DT %]` | No new measures needed for Day 26 scope. |

---

*Document complete. Day 26 scope: Panel D Pareto locked in. Panel C explicitly deferred.*
