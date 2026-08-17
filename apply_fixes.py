import re
import sys

filepath = r'c:\Users\Hement Kitukale\Desktop\Resume project\docs\ux_implementation_guide.md'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Chunk 1: Replace Section 2.3 Grid and Drill-Through
pattern1 = r'#### Zone Layout Grid \(1280 × 720 canvas\).*?(?=---\n+## 3\. Slicer Sync Configuration)'
replacement1 = r'''#### Zone Layout Grid (1280 × 720 canvas)

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

'''

content = re.sub(pattern1, replacement1, content, flags=re.DOTALL)

# Chunk 2: Section 4.4 Drill-Through configuration
pattern2 = r'### 4\.4 Source Page Drill-Through Trigger Points.*?### 4\.5 Optional Enhancement -- Tooltip Drill-Through Hint'
replacement2 = r'''### 4.4 Source Page Drill-Through Trigger Points

| Source Page | Trigger Visual | Field in Context | Destination |
|---|---|---|---|
| P1 Panel B | Horizontal bar chart (Health by Component) | `dim_components[component_id]` via Y-axis or Legend well | Page 2 |
| P3 Panel A | Stacked Bar (Fleet Alert Inventory) | `dim_components[component_id]` via X-axis, Y-axis, or Legend well | Page 2 |
| P3 Panel B | Scatter Chart (Risk Prioritization Matrix) | `dim_components[component_id]` via Details well | Page 2 |
| P3 Panel C | Matrix (Threshold Violation Frequency) | `dim_components[component_id]` via Rows well | Page 2 |

> **Important:** Drill-through filter context in Power BI is ONLY populated by fields in live data roles (Axis, Legend, Details, Rows, Columns, Values). Placing a field in Tooltips does NOT pass it to the drill-through destination. You MUST add `dim_components[component_id]` explicitly to the correct well for the visual type (e.g., Rows for Matrix, Y-axis for Bar Chart) for every source visual listed above. It cannot be passed implicitly via `component_name` or `pipeline_label`.

### 4.5 Optional Enhancement -- Tooltip Drill-Through Hint'''

content = re.sub(pattern2, replacement2, content, flags=re.DOTALL)

# Chunk 3: Delete Section 6 deprecations (6.2, 6.3, 6.4) and replace old Section 5 references
pattern3 = r'### 6\.2 Matrix Cell Colors \(Page 3 Panel B -- CCI Risk Table\).*?### 6\.4 Matrix Cell Colors \(Page 3 Panel E -- MTTR Outliers\).*?(?=---\n+## 7\. Implementation Sequence)'
replacement3 = r'''### 6.2 (Deprecated)
*(Page 3 conditional formatting is now handled via Field Value measures E-08 and E-10. See Day 30 UI Guide for details).*

'''
content = re.sub(pattern3, replacement3, content, flags=re.DOTALL)

# Also fix the Edit interactions section which failed last time:
old_interactions = r'''\| Panel A Pareto \(P3 -- Root cause\) \| Panel B Matrix \(P3\) \| \*\*Filter\*\* \(highlight selected component in matrix\) \|
\| Panel B Matrix \(P3 -- CCI Tier\) \| Panel A Pareto \(P3\) \| \*\*Filter\*\* \(highlight in Pareto\) \|
\| Panel D Stacked Bar \(P3 -- Alarm/Danger\) \| All P3 panels \| \*\*Filter\*\* \|
\| Date Slicer \(any page\) \| All visuals on that page \| \*\*Filter\*\* \(default -- do not change\) \|'''

new_interactions = r'''| Panel A Stacked Bar (P3 -- Fleet Alert Inventory) | Panel C Matrix (P3), Panel D Line Chart (P3) | **Filter** (highlight selected component) |
| Panel B Scatter (P3 -- Risk Matrix) | Panel A Stacked Bar (P3) | **Filter** (highlight component in bar chart) |
| Sensor Type Slicer (P3) | Panel A, Panel C, Panel D | **Filter** |
| Date Slicer (any page) | All visuals on that page | **Filter** (default -- do not change) |'''

content = re.sub(old_interactions, new_interactions, content)

old_interactions_2 = r'''- \*\*Severity Slicer \(Page 3\)\*\*: Since this uses a fact table column \(`fact_sensor_readings\[iso_zone\]`\), it will not filter other fact tables\. You MUST set \*\*No interaction\*\* for Panel A, Panel B, Panel C, Panel E, and KPI cards C-01, D-07, and A-05\. It should only filter the Alarm/Danger KPI cards \(A-07, A-08\) and Panel D\.
- \*\*Shift Period Slicer \(Page 2\)\*\*: Since this uses `fact_sensor_readings\[shift_period\]`, it will not filter MTBF or OEE data\. You MUST set \*\*No interaction\*\* for Panel C \(OEE\), Panel D \(MTBF Delta\), and KPI cards C-02, C-03, C-06, C-08\. It should only filter KPI card A-01 and Panels A and E\.
- \*\*Downtime Category Slicer \(Page 3\)\*\*: Since this uses `fact_downtime_events\[downtime_category_label\]`, you MUST set \*\*No interaction\*\* for Panels B, C, D, E and KPI cards A-08, A-07, C-01, A-05\. It should only filter Panel A and KPI card D-07\.'''

new_interactions_2 = r'''- **Sensor Type Slicer (Page 3)**: Since this filters specific sensor modalities, it MUST NOT filter the composite fleet-level KPI cards. Set **No interaction** for all KPI cards (E-01 to E-05) and Panel B (Scatter Chart).
- **Shift Period Slicer (Page 2)**: Since this uses `fact_sensor_readings[shift_period]`, it will not filter MTBF or OEE data. You MUST set **No interaction** for Panel C (OEE), Panel D (MTBF Delta), and KPI cards C-02, C-03, C-06, C-08. It should only filter KPI card A-01 and Panels A and E.'''

content = re.sub(old_interactions_2, new_interactions_2, content)


with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updates completed successfully.")
