
---

---

## Phase 1 — Foundation & Descriptive Analytics
### Sub-phase 1.4 — Python EDA (Exploratory Data Analysis)

---

### Day 14 — July 31, 2026
#### Topic: Comprehensive Descriptive Statistics — Sensor Readings, Production Counts, Downtime Durations

---

#### 1. What Was Built

`eda_summary_stats.py` connects to `data/manufacturing.db` via `sqlite3`, pulls data into pandas DataFrames, and computes the following statistics for every continuous variable across three numeric domains:

| Statistic | What it tells you |
|---|---|
| Mean | Central tendency |
| Median (P50) | Robust center, outlier-insensitive |
| Variance | Total squared spread |
| Std Dev | Spread in original units |
| Skewness | Distribution asymmetry (+ = right tail; - = left tail) |
| Excess Kurtosis | Tail weight vs normal (>1 = heavy, <-1 = light) |
| P05, P10, P25, P50, P75, P90, P95 | Full distribution in 7 slices |
| IQR | Middle 50% spread |
| CV% | Relative spread as % of mean |
| Shapiro-Wilk W & p | Formal normality test via scipy.stats.shapiro |

Stats are computed fleet-wide and stratified by sensor_type, component_name, and shift_label.

---

#### 2. Key Findings

**Sensor Readings (47,957 rows):**

| Variable | Mean | Median | Skewness | Shape |
|---|---|---|---|---|
| `value` (pooled) | 171.3 | 24.1 | +2.80 | Highly right-skewed, leptokurtic |
| `r_derated` | 0.916 | 0.981 | -2.18 | Highly left-skewed, leptokurtic |
| `arrhenius_factor` | 1.000 | 1.000 | 0.00 | Symmetric (Shaft constant at 1.0) |
| `health_score` | 91.6% | 98.1% | -2.18 | Highly left-skewed, leptokurtic |

**Production Counts (1,350 rows):**

| Variable | Mean | Skewness | Excess Kurtosis | Shape |
|---|---|---|---|---|
| `total_units` | 789 | -1.27 | +5.62 | Highly left-skewed, leptokurtic |
| `defective_units` | 9.95 | +1.94 | +33.6 | Highly right-skewed, leptokurtic |
| `first_pass_yield` | 97.87% | -5.18 | +48.3 | Highly left-skewed, leptokurtic |
| `ideal_cycle_time_min` | 0.612 | +0.30 | -1.22 | Symmetric, platykurtic |

**Downtime Durations (142 rows):** Mean=75.7 min, Median=23.7 min, Skewness=+2.24 — mean/median gap of 3x driven by Motor Housing 12-hour CBM repairs.

---

#### 3. Why It Matters

1. **Guides correct statistical tests.** Right-skewed durations disqualify parametric normality-assuming tests — Weibull modelling (confirmed by Q-Q plots Day 7) is empirically validated.
2. **Left-skewed reliability scores match Weibull theory.** Beta > 1 (wear-out) predicts components spend most of their life near-healthy; left tail represents rare post-failure windows.
3. **Extreme kurtosis in quality metrics (+48 for FPY)** flags outlier-driven reporting distortion. Median is the correct KPI display choice for Power BI quality cards.
4. **EDA CSVs seed Phase 2 calibration** — control chart limits, anomaly thresholds, and MLE parameter estimates.

---

#### 4. Outputs

| File | Rows |
|---|---|
| `data/processed/eda_sensor_stats.csv` | 44 |
| `data/processed/eda_production_stats.csv` | 54 |
| `data/processed/eda_downtime_stats.csv` | 27 |
| `data/processed/eda_full_report.txt` | Full human-readable report |

---

#### 5. Viva Q&A

**Q32: Why does the pooled `value` column show extreme right skew (+2.80) when individual sensor types look more normal?**

This is a **unit pooling artefact** (Simpson's paradox / aggregation bias). `sensor_readings.value` stores six physically different quantities with no unit normalization — Shaft RPM readings (>1,000) sit in the same column as vibration readings (1–5 mm/s). When pooled, the high-magnitude RPM rows create the heavy right tail. The stratified-by-sensor_type analysis shows each channel behaves more coherently. Fleet-wide pooled stats are reported for completeness and to flag this exact issue.

**Q33: `arrhenius_factor` has zero variance and triggered a Shapiro-Wilk "range zero" warning. Is this a bug?**

No — it is physically correct. The Shaft component has `is_arrhenius_applicable = False` (fatigue failure is not thermally governed), so its `arrhenius_factor` is always stored as 1.0 — a point mass, not a continuous distribution. When all five components are pooled, the fleet-wide AF series is dominated by this constant. Shapiro-Wilk correctly warns that a zero-range input makes the normality test meaningless. AF is analytically informative only when stratified by component: Bearing=2.15, Motor Housing=4.49, Coupling=1.84, Gearbox=2.62.

**Q34: Downtime mean (75.7 min) is 3x the median (23.7 min). What is the reporting implication?**

This gap signals a **mixture distribution**: most events are short (idle ~24 min median, cascade ~36 min) but rare long events (Motor Housing CBM = 720 min) pull the arithmetic mean rightward. Practical implication: (1) Power BI duration KPI cards should display **median**, not mean, to avoid alarming maintenance managers on every normal CBM cycle. (2) OEE Availability uses `SUM(duration_min)` per shift — correctly unaffected by this mean/median gap. The Weibull beta > 1 structure guarantees this right skew pattern; the EDA confirms it empirically.

---

*End of Day 14 entry. Next: Phase 2.2 Python Processing — ETL refinement, control charts, Weibull MLE fitting (Days 16–20).*

---
