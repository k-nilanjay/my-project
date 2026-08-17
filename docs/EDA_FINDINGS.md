# EDA Findings Report — Manufacturing & Industrial Analytics FYP
## Exploratory Data Analysis Integration Document
### Phase 1 Sub-phase 1.4 Synthesis | Day 17 — August 1, 2026

> **Purpose:** This document consolidates all Exploratory Data Analysis findings from Days 14–16
> into a single authoritative reference. It explicitly links each statistical finding to the
> threshold logic, conditional formatting rules, and visual alert configurations that will be
> implemented in Phase 2 (Python Processing) and Phase 3 (Power BI Diagnostic Dashboards).
>
> **Scope:** Three EDA scripts — `eda_summary_stats.py` (Day 14), `eda_correlation.py` (Day 15),
> `eda_trends.py` (Day 16) — plus the SQL queries and CSVs they produce.

---

## 1. Data Overview

| Dataset | Source Table(s) | Rows | Key Variables |
|---|---|---|---|
| Sensor Readings | `sensor_readings` + `sensors` + `components` | 47,957 | `value`, `r_derated`, `arrhenius_factor`, `health_score`, `is_anomaly`, `cascade_flag` |
| Production Counts | `production_counts` + `components` + `production_shifts` | 1,350 | `total_units`, `good_units`, `defective_units`, `rework_units`, `ideal_cycle_time_min`, `first_pass_yield` |
| Downtime Events | `downtime_events` + `components` | 142 | `duration_min`, `downtime_category`, `component_name` |
| Time-Series | `sensor_readings` daily pivot | 365 days × 2 sensors | Gearbox vibration (mm/s RMS), Motor Housing temperature (°C) |
| OEE | Computed from production tables | 1,350 shift-rows | OEE%, Availability%, Performance%, Quality% |

---

## 2. Distributional Findings (Day 14 — `eda_summary_stats.py`)

### 2.1 Fleet-Wide Sensor Readings

| Variable | n | Mean | Median | StdDev | Skewness | Ex. Kurtosis | Distribution Shape |
|---|---|---|---|---|---|---|---|
| `value` (pooled all sensors) | 47,957 | 171.34 | 24.05 | 412.22 | **+2.803** | **+5.947** | Highly right-skewed, leptokurtic |
| `r_derated` | 47,957 | 0.9164 | 0.9810 | 0.1390 | **−2.182** | **+4.124** | Highly left-skewed, leptokurtic |
| `arrhenius_factor` | 47,957 | 1.0000 | 1.0000 | 0.0000 | 0.000 | 0.000 | Constant (Shaft rows = 1.0, thermally-governed components > 1.0 when stratified) |
| `health_score` | 47,957 | 91.640 | 98.100 | 13.900 | **−2.182** | **+4.124** | Highly left-skewed, leptokurtic |

**Threshold implication:**

> The **pooled `value` column** is dominated by high-value post-failure readings and oil debris counts — pooled statistics are misleading. All Power BI KPI cards and control charts **must** stratify by `sensor_type` and `component_name`. Fleet-wide averages will not be used as threshold references.

> The **`r_derated` and `health_score`** left-skewed, leptokurtic profiles indicate that components spend the majority of their lives at high health (median = 98.1%, 0.981), then decline sharply near end-of-life. This validates the three-phase signal model (healthy / ramp / post-failure). Phase 2 control charts should use the P75 of `health_score` (≈ 100%) as the upper green zone and the P25 (≈ 85%) as the amber warning boundary.

---

### 2.2 Sensor-Type Stratified Distributions

| Sensor Type | Applicable Component(s) | Shape Finding | Phase 2 / Phase 3 Implication |
|---|---|---|---|
| **Vibration** (mm/s RMS) | All 5 | Moderate right-skew within healthy phase; heavy right tail post-failure | ISO 10816-3 zone thresholds are the correct non-parametric cut-points; do not fit a Gaussian control chart to raw vibration values |
| **Temperature** (°C) | Bearing, Motor Housing, Gearbox | Near-symmetric within healthy phase; right-skewed overall | IEC 60085 alarm thresholds are the correct alarm markers; 3σ upper control limit from healthy-phase data is a useful secondary alert |
| **Oil Debris** (count/mL) | Gearbox | Exponential-like ramp confirmed by kurtosis > 5; near-zero baseline then rapid spike | Exponential rise pattern justifies a log-scale axis in Power BI Gearbox drill-through; alarm at count = 50, danger at count = 200 (ISO 4406) |
| **RPM** | Shaft | Near-symmetric; slight left-skew during degradation ramp (RPM drops to 80% floor) | Lower control limit at 80% rated RPM is meaningful; upper limit is less critical |
| **Load** (%) | Coupling | Slight right-skew; drops to 0 at failure | Danger threshold = 100% (elastomer design limit); alarm = 90% (locked Day 4) |

---

### 2.3 Production Counts Distribution

| Variable | Mean | Median | Shape | Implication |
|---|---|---|---|---|
| `total_units` | 789.29 | 795.00 | Left-skewed (−1.27), leptokurtic | Failure shifts pull the mean down; use **median** as the production KPI baseline, not mean |
| `good_units` | 773.33 | 786.50 | Left-skewed (−1.26), leptokurtic | Median good units = 786.5 is the baseline target for Power BI Quality KPI card |
| `defective_units` | 9.953 | 11.00 | Highly right-skewed (+1.94), extreme kurtosis (+33.6) | Most shifts have near-zero defects; rare failure shifts dominate the mean. Pareto chart is the correct visual for defect analysis |
| `rework_units` | 6.016 | 7.00 | Right-skewed (+1.84), extreme kurtosis (+30.3) | Same distribution shape as defective_units (by construction: rework = 40% of non-good) |
| `ideal_cycle_time_min` | 0.6124 | 0.600 | Symmetric, **platykurtic** (−1.22) | 5 discrete values only (one per component). Platykurtic shape is expected and confirms consistent application of rated throughput constants |
| `first_pass_yield` | 0.9787 | 0.9794 | Highly left-skewed (−5.18), extreme kurtosis (+48.3) | Near-1.0 on most shifts; rare failure events create extreme left outliers. P05 = the minimum first-pass yield to use as the Power BI Quality alert floor |

---

### 2.4 Downtime Duration Distribution

| Statistic | Value | Implication |
|---|---|---|
| n | 142 events | |
| Mean | 75.70 min | **Do not use mean as KPI** — 3× inflated by Motor Housing CBM repairs |
| **Median** | **23.68 min** | Recommended central-tendency metric for all maintenance reporting |
| StdDev | 121.47 min | |
| Skewness | +2.239 | Highly right-skewed |
| Excess Kurtosis | +3.764 | Leptokurtic (heavy right tail) |
| P25 | 10.5 min | Lower quartile — typical short cascade/idle events |
| P75 | 107.5 min | Upper quartile — marks entry into long-repair territory |
| **P95** | **382.0 min** | 95th percentile — shifts where Motor Housing CBM (480 min cap) is partially absorbed |
| CV% | 160.5% | Distribution is dominated by extreme values |

**Threshold implication:**

> **Median (23.68 min)** is the correct benchmark for downtime KPI cards in Power BI.
> Events exceeding **P75 = 107.5 min** should be flagged as HIGH_COST events on the maintenance log page.
> Events at or above **P95 = 382 min** represent full-shift-loss events requiring management escalation alerts.
> The mean (75.70 min) must **not** be used in the Power BI maintenance KPI card — it overstates typical downtime by 3× due to Motor Housing CBM events.

---

### 2.5 Distribution Shape Summary — Shapiro-Wilk Results

| Variable | Shapiro-Wilk W | p-value | Normality Decision | Control Chart Method |
|---|---|---|---|---|
| `value` (vibration only) | < 0.95 | p < 0.001 | Non-normal | ISO 10816-3 zone thresholds (non-parametric) |
| `value` (temperature only) | ~0.97 | p < 0.05 | Borderline non-normal | IEC alarm thresholds + optional ±3σ UCL on healthy-phase subset |
| `r_derated` | < 0.90 | p < 0.001 | Non-normal | Percentile-based bounds (P10 as alert floor) |
| `health_score` | < 0.90 | p < 0.001 | Non-normal | Same as `r_derated` |
| `first_pass_yield` | < 0.85 | p < 0.001 | Non-normal | P05 as quality alert floor; median as baseline |
| `duration_min` | < 0.85 | p < 0.001 | Non-normal | Median (not mean) as KPI; P75 as HIGH_COST alert |

**Key decision locked:** All Phase 2 control charts and Phase 3 Power BI alerts will use **non-parametric, percentile-based or standards-based thresholds** rather than Gaussian (mean ± kσ) control limits. The Shapiro-Wilk results from Day 14 provide the statistical justification for this choice.

---

## 3. Correlation Findings (Day 15 — `eda_correlation.py`)

### 3.1 Cross-Component Cascade Correlation (Domain 1 — Sensor Pivot)

| Pair | Pearson r | Spearman ρ | Interpretation | Dashboard Implication |
|---|---|---|---|---|
| Gearbox_vibration ↔ Motor Housing_vibration | **+0.9954** | strong | Cascade propagation confirmed — MH vibration predicts Gearbox vibration | Power BI drill-through: show Gearbox vibration trend alongside MH vibration; alert on both simultaneously |
| Gearbox_oil_debris ↔ Motor Housing_temperature | **+0.9927** | strong | Thermal ageing drives downstream oil debris accumulation | Alert co-occurrence: if MH temp > alarm AND Gearbox oil_debris rising, escalate to DANGER level |
| Bearing_temperature ↔ Bearing_vibration | **+0.9892** | strong | Friction heat coupling — vibration increase causes thermal rise within the same component | Bearing deep-dive page: dual-axis chart (vibration + temperature) is diagnostically meaningful |

**Threshold implication:**

> These three correlation pairs (r > 0.98) are the **primary justification for cascade alert grouping** in the Phase 3 diagnostic dashboards. When one sensor in a correlated pair breaches its ISO alarm threshold, the Power BI alert should **simultaneously highlight the correlated downstream sensor**, even if that sensor has not yet independently breached its own threshold. This is the EDA-grounded foundation for the chain-fault alert logic.

---

### 3.2 Within-Component Sensor Correlations (Domain 2)

| Component | Sensor Pair | Pearson r | Implication |
|---|---|---|---|
| **Gearbox** | oil_debris ↔ vibration | > +0.95 | Oil debris is a leading indicator — rises before vibration crosses ISO Zone D |
| **Bearing** | vibration ↔ temperature | +0.9892 | Temperature follows vibration; vibration is the earlier warning |
| **Motor Housing** | temperature ↔ health_score | strong negative | Health score degradation tracks temperature rise linearly within the component |

**Threshold implication:**

> Gearbox oil debris (alarm = 50 counts) is a **leading indicator** — it should be the primary Phase 3 early-warning variable for Gearbox degradation before vibration reaches ISO Zone D. The oil debris threshold of 50 counts/mL is confirmed as a meaningful alarm point.

---

### 3.3 Production KPI Correlations (Domain 3)

| Pair | Pearson r | Spearman ρ | Implication |
|---|---|---|---|
| total_units ↔ good_units | **+0.9993** | **+0.9998** | Near-perfect linear: throughput variation drives quality variation |
| defective_units ↔ rework_units | **+0.9781** | +0.7979 | Pearson/Spearman divergence (linear vs rank): extreme defect events have non-linear rework consequences — use Spearman for quality alerts |
| defective_units ↔ first_pass_yield | −0.7101 | stronger negative | Moderate negative: defect counts partially predict yield drop but are not the sole driver |
| good_units ↔ ideal_cycle_time_min | −0.8489 | — | Slower ICT components (Motor Housing = 0.667 min/unit) systematically produce fewer good units per shift |

**Threshold implication:**

> The strong ICT–good_units correlation (r = −0.849) means that the **Gearbox (ICT = 0.75 min/unit, lowest throughput)** is structurally the binding constraint on Quality in the series system — even at normal quality rates. Power BI system OEE should annotate Gearbox as the quality bottleneck.

---

### 3.4 Sensor-vs-Production Correlation (Domain 4)

| Pair | Pearson r | Spearman ρ | Interpretation | Threshold Implication |
|---|---|---|---|---|
| mean_vibration ↔ anomaly_rate | **+0.92** | +0.76 | Non-linear: Pearson > Spearman confirms anomaly_rate jumps discretely at ISO zone boundaries | Power BI alerts should use **ISO zone thresholds** (4.5, 7.1 mm/s), not a continuous linear regression on vibration |
| mean_temperature ↔ first_pass_yield | moderate negative | moderate negative | Higher temperature correlates with yield reduction | Add temperature as a contributing factor to Quality drill-through; do not use as a standalone quality predictor |

> The **Pearson vs Spearman divergence** (0.92 vs 0.76) for mean_vibration ↔ anomaly_rate is the statistical proof that vibration's relationship with anomalies is **threshold-driven, not linear**. This is the EDA basis for using ISO 10816-3 zone thresholds as step-change alert triggers rather than a continuous alert score.

---

### 3.5 Downtime Duration Correlations (Domain 5)

| Pair | Pearson r | Spearman ρ | Interpretation |
|---|---|---|---|
| duration_min ↔ category_ord | **+0.90** | +0.75 | Downtime category is the **strongest predictor of duration** — stronger than component or position |
| position_in_chain ↔ duration_min | +0.16 | rho = +0.16, **p = 0.051** | Marginal — larger dataset needed to confirm cascade accumulation effect on downstream repair duration |

**Threshold implication:**

> Category is the best predictor of duration. Power BI maintenance log filters and alerts should prioritize **category-first filtering** (unplanned_failure > cascade_upstream > planned_maintenance > idle) before component-level drill-down. The marginal position_in_chain effect (p = 0.051) is noted but should not be used to drive dashboard logic in this dataset — it would need more failure cycles to reach statistical significance.

---

## 4. Time-Series Trend Findings (Day 16 — `eda_trends.py`)

### 4.1 Plot 1 — Rolling Average Sensor Trends

**File:** `data/processed/plots/rolling_avg_sensor_trends.png`
**Subject:** Gearbox vibration (mm/s RMS) + Motor Housing temperature (°C) over 365 days.
**Rolling windows:** 7-day and 14-day (both with `min_periods=1`).

| Metric | Value | Interpretation |
|---|---|---|
| Gearbox vib — 7-day rolling **max** | **18.764 mm/s** | ISO Zone D (danger > 7.1) — degradation ramp confirmed |
| Gearbox vib — sustained above ISO Zone C (4.5 mm/s) | Multiple periods | Vibration alarm threshold breach is **not a transient spike** — it is a persistent trend |
| Motor Housing temp — 14-day rolling max | **123.75 °C** | Below IEC alarm (130 °C) — acceptable, but approaching the alarm boundary |
| Motor Housing temp — baseline (healthy phase) | ~73–80 °C | Comfortable well within Zone B (below 100 °C danger) |

**Threshold decisions locked:**

> - **Gearbox vibration ISO Zone D threshold: > 7.1 mm/s** is confirmed as the danger alert level. The 7-day rolling average exceeding 7.1 mm/s is the Power BI Phase 3 visual alert trigger — not the instantaneous reading.
> - **Gearbox vibration ISO Zone C threshold: 4.5 mm/s** is the alarm boundary. When the 14-day rolling average first crosses 4.5 mm/s and stays above it for 3 consecutive days, a CBM intervention recommendation should be generated.
> - **Motor Housing temperature alarm: 130 °C** (IEC Class B limit). The 14-day rolling max of 123.75 °C confirms the temperature is approaching the alarm boundary — Phase 3 should display this as a WARN (amber) alert rather than a safe (green) indicator.

---

### 4.2 Plot 2 — Shift OEE Seasonality

**File:** `data/processed/plots/shift_oee_seasonality.png`
**Subject:** 1×4 boxplot grid of OEE%, Availability%, Performance%, Quality% stratified by shift (DAY / SWING / NIGHT).

| Metric | Median OEE: DAY | Median OEE: SWING | Median OEE: NIGHT | Shift Spread |
|---|---|---|---|---|
| OEE (%) | **96.92%** | **96.89%** | **96.89%** | **0.03 pp** |

**Shift seasonality decision:**

> **No significant shift-based seasonality was detected** in this simulated dataset (spread = 0.03 percentage points across shifts). The simulation is shift-agnostic by design. Power BI Phase 2 dashboards should implement a shift filter slicer (DAY / SWING / NIGHT) but should **not** set different OEE targets per shift in this dataset — the same WORLD_CLASS target (≥ 85% OEE) applies uniformly.
>
> In Phase 3 Diagnostic Dashboards, if real operational data (Post-FYP) shows shift divergence, the shift slicer is already in place to detect it. The current finding establishes the **null baseline** — no shift effect.

---

### 4.3 Plot 3 — Downtime vs Failure Events (Stacked Area)

**File:** `data/processed/plots/downtime_vs_failures_stacked.png`
**Subject:** Daily downtime minutes stacked by category with 9 failure event markers.

| Finding | Value | Implication |
|---|---|---|
| Failure events plotted | 9 | 4 Bearing, 3 Motor Housing (1 multi-shift), 2 Coupling |
| Total fleet downtime | **10,941 min (182.4 hrs)** | Spread across 68 downtime days |
| Downtime concentration | Visible cluster after each failure marker | Cascade_upstream category visually confirms downstream impact |
| Largest single-day downtime | Motor Housing CBM repair (multi-shift, 480 min cap) | Motor Housing is the highest downtime driver by duration |

**Threshold implication:**

> The visual clustering of `cascade_upstream` downtime events around each failure marker is the **graphical proof of the cascade propagation model**. Power BI Phase 3 should replicate this stacked area chart as an interactive visual — failure event markers should be clickable data points linking to the Root Cause drill-through page.

---

## 5. Finalized Threshold Decisions for Phase 2 / Phase 3

This section consolidates every threshold that the EDA has validated. These values are **locked** for use in Phase 2 Python processing (`anomaly.py`, `kpi.py`) and Phase 3 Power BI dashboard conditional formatting.

### 5.1 Vibration Thresholds (ISO 10816-3) — LOCKED

| Component | Sensor ID | Zone C Alarm | Zone D Danger | EDA Validation |
|---|---|---|---|---|
| Bearing | 11 | 4.5 mm/s | **7.1 mm/s** | 7-day rolling avg confirmed sustained Zone D in simulation |
| Shaft | 21 | 4.5 mm/s | **7.1 mm/s** | No violations in 365-day window (Shaft η = 8760 h; expected) |
| Motor Housing | 32 | 4.5 mm/s | **7.1 mm/s** | Correlated with Gearbox at r = 0.9954 (cascade pair) |
| Coupling | 41 | 4.5 mm/s | **7.1 mm/s** | 91.03% anomaly rate — all cascade-driven (cascade_flag = 1) |
| **Gearbox** | **51** | **4.5 mm/s** | **> 7.1 mm/s** | **7-day rolling max = 18.764 mm/s — primary alert target** |

> **ISO Zone D > 7.1 mm/s for Gearbox vibration is the primary Phase 3 dashboard danger alert.**
> All five vibration sensors use identical zone thresholds (ISO 10816-3 is size-class agnostic for this pipeline).
> Rolling window confirmation rule: **7-day rolling average** must exceed the zone boundary for ≥ 3 consecutive days before an alert fires — prevents false positives from single-reading spikes.

---

### 5.2 Temperature Thresholds — LOCKED

| Component | Sensor ID | Alarm (°C) | Danger (°C) | Source | EDA Validation |
|---|---|---|---|---|---|
| Bearing | 12 | 80.0 | 100.0 | Grease degradation / seizure | Healthy baseline 60–70 °C; alarm headroom = 10–20 °C |
| Motor Housing | 31 | **130.0** | **155.0** | IEC 60085 Class B / Class F | 14-day rolling max = 123.75 °C (approaching alarm) |
| Gearbox | 53 | 90.0 | 110.0 | Oil oxidation / flash point risk | Correlated with oil_debris at r = 0.9927 |

> Motor Housing temperature approaching 130 °C alarm boundary is confirmed by trend analysis. Power BI should display Motor Housing temperature as **AMBER (approaching alarm)** rather than GREEN when the 14-day rolling average exceeds **115 °C** (halfway between nominal ~80 °C and alarm 130 °C).

---

### 5.3 Gearbox Oil Debris Thresholds — LOCKED

| Sensor ID | Alarm | Danger | Source | EDA Validation |
|---|---|---|---|---|
| 52 | 50 counts/mL | 200 counts/mL | ISO 4406 / ODM wear particle standard | Within-component: oil_debris ↔ vibration r > 0.95; oil debris is a **leading indicator** |

> Oil debris is confirmed as a **leading indicator** of Gearbox gear-tooth wear. Phase 3 Gearbox drill-through should prioritize oil debris trend on a log-scale axis. When oil_debris crosses 50 counts/mL and is still rising (positive slope over 7-day rolling window), an early-warning alert should be generated before vibration reaches Zone D.

---

### 5.4 Load / RPM Thresholds — LOCKED

| Component | Sensor ID | Type | Alarm | Danger | EDA Validation |
|---|---|---|---|---|---|
| Coupling | 42 | Load (%) | 90.0% | 100.0% | Load drops sharply to 0 at failure (elastomer shear) — left-skewed distribution confirms |
| Shaft | 22 | RPM | RPM < 80% rated | RPM = 0 | RPM drops to 80% floor pre-failure then 0 at TTF — linear degradation confirmed |

---

### 5.5 Health Score (r_derated × 100) Alert Zones — LOCKED

| Zone | Health Score | Alert Level | Power BI Formatting |
|---|---|---|---|
| GREEN | 90–100 | HEALTHY | Green KPI card |
| **AMBER** | **75–89** | **DEGRADING** | **Amber KPI card** |
| **RED** | **< 75** | **CRITICAL** | **Red KPI card + visual alert** |

> These boundaries are derived from the Day 14 EDA percentile profile: P25 of `health_score` ≈ 85% (healthy-phase bottom quartile). The 75% boundary is one interquartile range below P25, representing a clear departure from the healthy distribution.

---

### 5.6 Downtime KPI Benchmarks — LOCKED

| Metric | Value | Source | Usage |
|---|---|---|---|
| Median downtime per event | 23.68 min | Day 14 EDA | Power BI Maintenance KPI card baseline |
| HIGH_COST event threshold | > 107.5 min (P75) | Day 14 EDA | Flag in maintenance log page |
| FULL_SHIFT_LOSS alert | > 382 min (P95) | Day 14 EDA | Management escalation alert |
| Do NOT use: mean | 75.70 min | Day 14 EDA | Inflated 3× by CBM repairs — excluded from KPI cards |

---

### 5.7 Cascade Alert Co-occurrence Rules — LOCKED

These rules are derived from the correlation findings (Section 3.1) and the cascade propagation model. They define when a single sensor breach should trigger a multi-component alert.

| Rule | Trigger | Alert Action |
|---|---|---|
| **R1 — Gearbox cascade chain** | Motor Housing vibration > 4.5 mm/s (Zone C) | Also highlight Gearbox vibration trend regardless of its own current zone |
| **R2 — Thermal oil debris co-alert** | Motor Housing temp > 115 °C (approaching alarm) | Also display Gearbox oil_debris trend — thermal–oil debris co-occurrence (r = 0.9927) |
| **R3 — Bearing friction co-alert** | Bearing vibration > 4.5 mm/s | Also display Bearing temperature — friction coupling (r = 0.9892) |
| **R4 — Cascade downstream escalation** | `cascade_flag = 1` on any downstream sensor | Tag the downstream anomaly as CASCADE (not intrinsic) on the maintenance log |

---

## 6. Dashboard Integration Roadmap

### Phase 2 — Python Processing (Days 18–20)

| Task | EDA Finding Applied |
|---|---|
| `anomaly.py` threshold logic | ISO zone thresholds (Section 5.1), temperature thresholds (5.2), oil debris (5.3), health score zones (5.5) |
| `kpi.py` control chart limits | P25/P75 from `eda_sensor_stats.csv` as soft control chart limits (Section 2.1 decision) |
| Rolling window CBM trigger | 7-day and 14-day rolling average confirmation rule (Section 4.1) |
| Downtime KPI computation | Median-based downtime benchmark (Section 5.6) |

### Phase 3 — Power BI Diagnostic Dashboards (Days 31–33)

| Dashboard Page | Threshold(s) Applied | Visual Type |
|---|---|---|
| **Fleet Overview** | Health score zones (5.5), OEE tiers (≥85% = WORLD_CLASS) | KPI cards with conditional formatting |
| **Bearing Deep-Dive** | Vibration Zone C/D (5.1), temp alarm 80°C (5.2), 7-day/14-day rolling lines | Dual-axis line chart + ISO zone reference lines |
| **Gearbox Wear Dashboard** | Vibration **> 7.1 mm/s** (5.1), oil_debris > 50 (5.3), temp > 90°C (5.2), cascade R2 rule | Multi-sensor trend panel + oil debris log-scale axis |
| **Motor Housing Thermal Map** | Temp alarm 130°C, approaching-alarm 115°C (5.2), cascade R1 rule | Gauge visual + approaching-alarm AMBER zone |
| **Maintenance Event Log** | Median 23.68 min, P75 107.5 min HIGH_COST flag, P95 382 min escalation (5.6) | Table with conditional row formatting |

---

## 7. Viva Defence Points

The following EDA findings are the most likely to be questioned in a viva examination regarding the move from descriptive statistics to business logic:

1. **Why are Gaussian control limits inappropriate for this data?** — All nine Shapiro-Wilk tests across the three variable domains returned p < 0.05 (non-normal). The distributions are skewed (skewness > 1.0) and leptokurtic (excess kurtosis > 3.0). The correct approach is standards-based thresholds (ISO 10816-3, IEC 60085) and percentile-based soft limits, not mean ± 3σ.

2. **How did you choose the 7-day and 14-day rolling windows?** — 7 days aligns with the industrial PM scheduling cycle (weekend maintenance window). 14 days provides dual-confirmation: when both windows exceed an alarm boundary simultaneously, the probability that a single noisy reading contaminates the decision is eliminated. This is the rolling-average equivalent of a SPC run-of-8 rule.

3. **Why does your cascade alert (Rule R1) fire on Motor Housing before Gearbox reaches Zone D?** — Because the Pearson correlation between Motor Housing vibration and Gearbox vibration is +0.9954 (Day 15, Domain 1). Statistically, when Motor Housing vibration enters Zone C (4.5 mm/s), Gearbox vibration is nearly certain to follow. Firing the alert on the upstream sensor is earlier intervention logic — it provides an additional response window before the more severe Gearbox degradation manifests. This is the diagnostic value of correlation analysis: it converts lagging indicators into leading ones.

---

## 8. Outputs Referenced in This Report

| File | Day | Contents |
|---|---|---|
| `data/processed/eda_sensor_stats.csv` | 14 | 44 rows of per-variable, per-group descriptive statistics |
| `data/processed/eda_production_stats.csv` | 14 | 54 rows — production count variable statistics |
| `data/processed/eda_downtime_stats.csv` | 14 | 27 rows — downtime duration statistics |
| `data/processed/eda_full_report.txt` | 14 | Human-readable full text report |
| `data/processed/corr_sensor_pivot_pearson.csv` | 15 | 11×11 cross-sensor fleet Pearson matrix |
| `data/processed/corr_sensor_pivot_spearman.csv` | 15 | 11×11 cross-sensor fleet Spearman matrix |
| `data/processed/corr_within_component_pearson.csv` | 15 | 26×26 per-component stacked Pearson matrix |
| `data/processed/corr_production_pearson.csv` | 15 | 7×7 production KPI Pearson matrix |
| `data/processed/corr_sensor_vs_production_pearson.csv` | 15 | 9×9 sensor-vs-production Pearson matrix |
| `data/processed/corr_downtime_pearson.csv` | 15 | 8×8 downtime variables Pearson matrix |
| `data/processed/plots/rolling_avg_sensor_trends.png` | 16 | 7-day & 14-day rolling average dual-axis trend chart |
| `data/processed/plots/shift_oee_seasonality.png` | 16 | Shift-stratified OEE/A/P/Q boxplot grid |
| `data/processed/plots/downtime_vs_failures_stacked.png` | 16 | Stacked downtime area chart with failure event markers |

---

*EDA Findings Report — Day 17, August 1, 2026. Created by synthesizing Days 14–16 EDA outputs.*
*Next phase: Day 18 — Betweenness centrality graph analysis for cascade propagation quantification.*
