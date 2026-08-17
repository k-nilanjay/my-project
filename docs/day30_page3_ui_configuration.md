# Day 30 — Power BI UI Configuration Guide
## Page 3: Alert / Risk Summary — Final Configuration Steps

**Purpose:** Exact step-by-step UI instructions for completing Page 3 in Power BI Desktop.
All measure logic is documented in `docs/dax_and_m_scripts.md`.
This file covers *where to click* and *what to type* in the Power BI Desktop interface.

---

## Section 1 — Entering DAX Measures E-01 through E-10

All 10 Group E measures belong to the home table `_Measures_E_Alerts`.

### 1.1 Create the Home Table (if not yet present)

1. In Power BI Desktop, go to **Modeling** tab → **New table**.
2. In the formula bar enter:
   `_Measures_E_Alerts = DATATABLE("Placeholder", STRING, {{""}})`
3. Press Enter. The table appears in the Fields pane.

### 1.2 Entering Each Measure

1. In the Fields pane, select `_Measures_E_Alerts`.
2. Go to **Modeling** tab → **New measure**.
3. In the formula bar, paste the measure DAX from `docs/dax_and_m_scripts.md` (Group E section).
4. Press Enter to commit.
5. In the **Measure tools** ribbon that appears, confirm **Home table** = `_Measures_E_Alerts`.
6. Set **Format** per the table below.

### 1.3 Format Strings for Group E

| Measure | Format | Decimal Places |
|---|---|---|
| E-01 `[Total Active Alerts]` | Whole number | 0 |
| E-02 `[Danger Zone Count]` | Whole number | 0 |
| E-03 `[Alarm Zone Count]` | Whole number | 0 |
| E-04 `[Most Alerting Component]` | Text | — |
| E-05 `[Critical Risk Component Count]` | Whole number | 0 |
| E-06 `[Alert Count by Sensor Type]` | Whole number | 0 |
| E-07 `[Violation Rate]` | Decimal number | 2 |
| E-08 `[Violation Rate Colour]` | Text | — |
| E-09 `[Page 3 Status Banner]` | Text | — |
| E-10 `[Status Banner Colour]` | Text | — |

**Verification:** Expand `_Measures_E_Alerts` in the Fields pane — confirm 10 calculator-icon entries.

---

## Section 2 — Panel B: Quadrant Reference Lines (X = 0.50, Y = 75)

Panel B is the Risk Prioritization Matrix (Scatter chart at X=773, Y=165, W=502, H=270).

### 2.1 Add the Vertical Reference Line (X = 0.50 — CCI boundary)

1. Click Panel B to select it.
2. In the Visualizations pane, click the **Analytics** icon (magnifying glass / ruler icon — third icon in pane header).
3. Expand **X-Axis Constant Line** → click **+ Add**.
4. A new row appears. Set:

| Property | Value |
|---|---|
| Value | `0.5` |
| Line color | `#757575` (medium grey) |
| Line style | Solid |
| Line width | 1 px |
| Position | **Behind** |
| Data label | Off |

> **Critical:** The X-axis is bound to `[CCI Score]` (D-01) which returns values 0.0–1.0.
> Enter `0.5` (not `50`). Entering `50` would push the line off-screen to the right.

### 2.2 Add the Horizontal Reference Line (Y = 75 — Health boundary)

1. With Panel B still selected, in the **Analytics** pane:
2. Expand **Y-Axis Constant Line** → click **+ Add**.
3. Set:

| Property | Value |
|---|---|
| Value | `75` |
| Line color | `#757575` (medium grey) |
| Line style | Solid |
| Line width | 1 px |
| Position | **Behind** |
| Data label | Off |

> **Note:** The Y-axis is bound to `[Avg Health Score]` (A-01), range 0–100.
> `75` matches the ALERT tier boundary locked in Day 17 EDA_FINDINGS.md Section 5.

### 2.3 Add Quadrant Text-Box Annotations

Go to **Insert** → **Text box** for each of the four quadrant labels.

| Quadrant | Label Text | Approx. X/Y on canvas | Font Color |
|---|---|---|---|
| Top-left (low CCI, high health) | `LOW RISK` | X=790, Y=185 | `#2E7D32` green |
| Top-right (high CCI, high health) | `MONITOR` | X=1000, Y=185 | `#F57F17` amber |
| Bottom-left (low CCI, low health) | `INVESTIGATE` | X=790, Y=380 | `#E65100` orange |
| Bottom-right (high CCI, low health) | `CRITICAL PRIORITY` | X=985, Y=380 | `#B00020` red |

Formatting for all four boxes: Outfit 8px Bold. Background fill: None (transparent). Border: None.

**Verification:** In Report View, confirm Coupling (CCI≈0.804) renders in the right half
(CCI > 0.50) and Bearing (CCI≈0.457) renders in the left half.

---

## Section 3 — Panel C: Field Value Conditional Formatting via E-08

Panel C is the Threshold Violation Frequency Matrix (Matrix visual at X=0, Y=440, W=630, H=230).

### 3.1 Confirm Field Bindings

Before applying CF, verify:

| Well | Field |
|---|---|
| Rows | `dim_components[component_name]` |
| Columns | `dim_sensors[sensor_type]` |
| Values | `[Violation Rate]` (E-07) |

### 3.2 Apply Cell Background CF — Field Value Method

1. Click Panel C (Matrix visual) to select it.
2. In the Visualizations pane → click **Format** (paint roller icon).
3. Scroll to **Cell elements** (some Power BI versions label this section **Conditional formatting**).
4. Find **Background color** under the Values section.
5. Click the **fx** button next to Background color.
6. The Conditional Formatting dialog opens. Set:

| Setting | Value |
|---|---|
| Format style | **Field value** |
| What field should we base this on? | `[Violation Rate Colour]` (E-08) |
| Summarization | First |

7. Click **OK**.

**How it works:** E-08 is a DAX measure that evaluates E-07 in each cell's filter context
and returns one of five hex strings. Power BI's "Field value" mode passes the returned string
directly as the cell background colour with no further threshold configuration needed in the UI.

**Colour mapping (for reference — defined in E-08 DAX, not in UI):**

| Violation Rate | Background Colour | Meaning |
|---|---|---|
| 0.00 | `#0D1117` | No violations — blends into canvas |
| 0.01–0.10 | `#1E2D2F` | Very low — informational |
| 0.11–0.30 | `#F57F17` | Moderate — CBM review recommended |
| 0.31–0.60 | `#E65100` | High — escalate to reliability engineer |
| > 0.60 | `#B00020` | Severe — immediate inspection required |

### 3.3 Additional Matrix Formatting

- Row subtotals: **Off** (Format → Row subtotals → Off)
- Column subtotals: **Off** (Format → Column subtotals → Off)
- Grid lines: Horizontal only, colour `#1E2D2F`, 1px
- Values font: Outfit 9px, White `#FFFFFF`

**Verification:**
- Cells with violation rate > 0.60 should show red `#B00020` background.
- Cells where a sensor type is not applicable for a component (e.g., Shaft/rpm — no ISO alarm)
  should show `#0D1117`, visually invisible against the page canvas.
- Shaft/rpm violation rate should be 0 (no alarm threshold defined for RPM per Day 4 seed data).

---

## Section 4 — Panel E: Field Value Conditional Formatting via E-10

Panel E is the Dynamic Status Banner (Card visual at X=0, Y=675, W=1280, H=45).

### 4.1 Confirm Field Binding

| Well | Field |
|---|---|
| Fields | `[Page 3 Status Banner]` (E-09) |

### 4.2 Apply Background CF — Field Value Method

1. Click Panel E (Card visual) to select it.
2. In the Visualizations pane → **Format** (paint roller).
3. Scroll to **Card** → **Background**.
4. Toggle Background **On** if not already enabled.
5. Click the **fx** button next to the background color swatch.
6. In the Conditional Formatting dialog:

| Setting | Value |
|---|---|
| Format style | **Field value** |
| What field should we base this on? | `[Status Banner Colour]` (E-10) |
| Summarization | First |

7. Click **OK**.

**Colour mapping (defined in E-10 DAX):**

| Condition | Banner Background | Meaning |
|---|---|---|
| E-02 (Danger Zone Count) > 0 | `#B00020` Red | Danger zone breach active — immediate action |
| E-02 = 0 AND (E-03 > 0 OR E-01 > 0) | `#F57F17` Amber | Alarm or non-vibration alert active — schedule inspection |
| E-01 = 0 | `#00695C` Teal | No active alerts — fleet healthy |

### 4.3 Card Font and Layout Settings

| Setting | Value |
|---|---|
| Callout value font | Outfit 12px, Bold, White `#FFFFFF` |
| Card title | Off |
| Border | None |
| Padding | 5px all sides |
| Callout value display | Fit to width |

**Verification:**
- With no date filter: if any Danger Zone readings exist, banner background = red.
- Narrow the date slicer to a date range with no alarm breaches: banner should turn teal.
- The banner text from E-09 (e.g., "Highest Risk: Coupling — Critical | 3 Danger Zone Alerts Active")
  should be visible in white font on the coloured background.

---

## Section 5 — Locked Thresholds Reference (Do Not Modify)

These values are permanently locked. They appear in the reference lines, CF conditions, and
quadrant annotations set above and must not be changed.

| Threshold | Value | Locked By |
|---|---|---|
| Panel B: CCI quadrant X-boundary | **0.50** | Day 19 CCI tier (High >= 0.50); Day 23 blueprint |
| Panel B: Health score Y-boundary | **75** | Day 17 EDA_FINDINGS.md §5; Day 23 ALERT tier |
| Panel C / E-08: Severe threshold | **> 0.60** violation rate | Day 29 design decision |
| Panel C / E-08: High threshold | **0.31–0.60** | Day 29 design decision |
| Panel C / E-08: Moderate threshold | **0.11–0.30** | Day 29 design decision |
| Panel C / E-08: Low threshold | **0.01–0.10** | Day 29 design decision |
| Panel E / E-10: Danger colour | `#B00020` | Day 24 palette; Day 17 Danger Red |
| Panel E / E-10: Alarm colour | `#F57F17` | Day 24 palette; Day 17 Alert Amber |
| Panel E / E-10: Healthy colour | `#00695C` | Day 24 World Class Teal |

---

## Section 6 — Final Verification Checklist

Run through this checklist after completing all sections above:

**Measures**
- [ ] 10 E-series measures present in `_Measures_E_Alerts` in the Fields pane
- [ ] E-01 through E-03 KPI cards show non-blank integers (0 is valid; "(Blank)" is a bug)
- [ ] E-04 KPI card shows a component name string
- [ ] E-05 KPI card shows an integer 0–5
- [ ] E-07 visible in Panel C matrix with values in 0.00–1.00+ range

**Panel B**
- [ ] Vertical reference line visible at X = 0.50 (grey, behind data points)
- [ ] Horizontal reference line visible at Y = 75 (grey, behind data points)
- [ ] Four quadrant text boxes present and legible against dark canvas
- [ ] Coupling bubble in the right half of scatter (CCI > 0.50)
- [ ] Bearing bubble in the left half (CCI < 0.50)

**Panel C**
- [ ] Cells with violation rate > 0.60 have red `#B00020` background
- [ ] Cells with violation rate = 0 are dark `#0D1117` (effectively invisible)
- [ ] Row and column subtotals are Off

**Panel E**
- [ ] Status banner text is white and readable
- [ ] Banner background changes colour when date slicer is adjusted
- [ ] Danger-period date selection produces red banner

**Slicer Sync**
- [ ] View → Sync slicers: Sensor Type slicer has Sync = OFF (Page 3 only, not propagated)
- [ ] Date Range slicer: Sync = ON for Pages 1, 2, 3
- [ ] Component slicer: Sync = ON; Visible = ON on Page 3

**SQL Cross-Validation**
- [ ] E-01 value matches: `SELECT COUNT(*) FROM sensor_readings WHERE is_anomaly = 1`
  *(Note: `sensor_readings` is the raw SQL table name. `fact_sensor_readings` is the Power Query/DAX-layer alias)*

---

*End of Day 30 UI Configuration Guide.*
*Page 3 is complete when all verification checklist items are checked.*