import os

filepath = r'c:\Users\Hement Kitukale\Desktop\Resume project\docs\ux_implementation_guide.md'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

target = """| Source Visual | Target Visual | Interaction |
|---|---|---|
| Panel B Bar (P1 -- Health by component) | Panel A Line Chart (P1) | **Filter** (highlight selected component series) |
| Panel B Bar (P1) | Panel C Waterfall (P1) | **Filter** (show OEE losses for selected component) |
|

### 5.2 Disabling Unwanted Cross-Filter

1. Click the **Format** tab → **Edit Interactions**
2. Grey filter/highlight icons appear on all other visuals
3. Click the **No interaction** icon (circle with line) on visuals where cross-filtering is not desired

**Recommended "no interaction" settings (CRITICAL FOR FACT TABLE SLICERS):**
- **Severity Slicer (Page 3)**: Since this uses a fact table column (`fact_sensor_readings[iso_zone]`), it will not filter other fact tables. You MUST set **No interaction** for Panel A, Panel B, Panel C, Panel E, and KPI cards C-01, D-07, and A-05. It should only filter the Alarm/Danger KPI cards (A-07, A-08) and Panel D.
- **Shift Period Slicer (Page 2)**: Since this uses `fact_sensor_readings[shift_period]`, it will not filter MTBF or OEE data. You MUST set **No interaction** for Panel C (OEE), Panel D (MTBF Delta), and KPI cards C-02, C-03, C-06, C-08. It should only filter KPI card A-01 and Panels A and E.
- **Downtime Category Slicer (Page 3)**: Since this uses `fact_downtime_events[downtime_category_label]`, you MUST set **No interaction** for Panels B, C, D, E and KPI cards A-08, A-07, C-01, A-05. It should only filter Panel A and KPI card D-07.
- **KPI Cards**: Set all KPI cards to **No interaction** when clicking chart panels (cards are headline metrics -- filtering them produces confusing KPI value changes)
- **Status bar text card (B-19 Dominant Loss on P1)**: **No interaction** from all charts"""

replacement = """| Source Visual | Target Visual | Interaction |
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
- **Status bar text card (B-19 Dominant Loss on P1)**: **No interaction** from all charts"""

text_fixed = text.replace(target, replacement)
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text_fixed)
print('Done. Replaced:', text_fixed != text)
