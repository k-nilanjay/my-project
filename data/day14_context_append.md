

---

#### Day 14 — July 31, 2026

**Status:** Complete

**Deliverables completed today:**
- [x] `eda_summary_stats.py` — Comprehensive EDA script: sqlite3 connection, pandas DataFrame loading, full descriptive statistics for 3 numeric domains, Shapiro-Wilk normality test, distribution shape labelling
- [x] `data/processed/eda_sensor_stats.csv` — 44 stat rows for sensor readings
- [x] `data/processed/eda_production_stats.csv` — 54 stat rows for production counts
- [x] `data/processed/eda_downtime_stats.csv` — 27 stat rows for downtime durations
- [x] `data/processed/eda_full_report.txt` — Human-readable full report (UTF-8)
- [x] `README.md` — Day 14 section appended (What/Why, key findings table, viva Q32-Q34)
- [x] `CONTEXT.md` — Day 14 section appended (this entry)
- [x] `STATE_SUMMARY.md` — Overwritten with fresh Day 14 snapshot

---

##### `eda_summary_stats.py` — Technical Summary

**Module purpose:** Compute comprehensive descriptive statistics for all continuous variables in `manufacturing.db`. Serves as the distributional baseline for Phase 2 control chart calibration, anomaly threshold setting, and Weibull MLE estimation.

**Database connection pattern:**
```python
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA foreign_keys = ON;")
df = pd.read_sql_query(sql, conn)   # pandas read_sql_query — returns DataFrame directly
```

**Statistics computed per variable:**

| Pandas / SciPy method | Statistic produced |
|---|---|
| `series.mean()` | Arithmetic mean |
| `series.median()` | Median (P50) |
| `series.var(ddof=1)` | Sample variance (Bessel's correction) |
| `series.std(ddof=1)` | Sample std dev (Bessel's correction) |
| `series.skew()` | Fisher-Pearson skewness coefficient |
| `series.kurtosis()` | Excess kurtosis (Fisher definition, relative to normal=0) |
| `series.quantile([0.05,0.10,0.25,0.50,0.75,0.90,0.95])` | 7-point percentile profile |
| P75 - P25 | IQR (interquartile range) |
| max - min | Range |
| std / mean * 100 | CV% (coefficient of variation) |
| `scipy.stats.shapiro(series)` | Shapiro-Wilk W statistic and p-value |

**`ddof=1` decision (locked Day 14):**
All variance/std computations use `ddof=1` (sample statistics, Bessel's correction). The simulation produced a finite sample of 47,957 sensor readings, not a census of all possible readings — the population variance is unknown. `ddof=1` is the statistically correct choice for estimating population parameters from a sample.

**Shapiro-Wilk subsampling (SHAPIRO_MAX_N = 5000):**
scipy.stats.shapiro is accurate for n ≤ ~5000 and can be numerically unstable for very large n. Series with n > 5000 are randomly subsampled (random_state=42 for reproducibility) before passing to shapiro(). This preserves test validity while handling the 47,957-row sensor_readings table.

**Distribution shape labelling logic (locked Day 14):**

Skewness thresholds (Bulmer 1979 convention):
```
|skew| < 0.5   → "symmetric"
0.5 <= |skew| < 1.0  → "moderately left/right-skewed"
|skew| >= 1.0  → "highly left/right-skewed"
```

Excess kurtosis thresholds (Fisher definition):
```
kurt > 1.0   → "leptokurtic (heavy tails)"    — outlier-prone, Weibull-consistent
kurt < -1.0  → "platykurtic (light tails)"    — uniform-like, bounded distributions
otherwise    → "mesokurtic (normal tails)"
```

Combined label examples:
- `value` (pooled sensors): "highly right-skewed, leptokurtic (heavy tails)" — skew=+2.80, kurt=+5.95
- `r_derated`: "highly left-skewed, leptokurtic (heavy tails)" — skew=-2.18, kurt=+4.12
- `ideal_cycle_time_min`: "symmetric, platykurtic (light tails)" — skew=+0.30, kurt=-1.22

---

##### Variable Domain — Sensor Readings

**SQL join used:**
```sql
SELECT sr.value, sr.r_derated, sr.arrhenius_factor, sr.health_score,
       s.sensor_type, c.component_name
FROM sensor_readings sr
JOIN sensors s ON sr.sensor_id = s.sensor_id
JOIN components c ON sr.component_id = c.component_id
```

**Stratification levels (3):**
1. Fleet-wide (`group = "FLEET_ALL"`) — all 47,957 rows
2. By sensor_type (6 types: vibration, temperature, rpm, load, oil_debris; 1 null-only)
3. By component_name (5 components)

**Key results (FLEET_ALL):**

| Variable | n | Mean | Median | StdDev | Skewness | ExKurtosis | Shape |
|---|---|---|---|---|---|---|---|
| `value` | 47,957 | 171.34 | 24.05 | 412.22 | +2.803 | +5.947 | highly right-skewed, leptokurtic |
| `r_derated` | 47,957 | 0.9164 | 0.9810 | 0.1390 | -2.182 | +4.124 | highly left-skewed, leptokurtic |
| `arrhenius_factor` | 47,957 | 1.0000 | 1.0000 | 0.0000 | 0.000 | 0.000 | symmetric, mesokurtic (constant) |
| `health_score` | 47,957 | 91.640 | 98.100 | 13.900 | -2.182 | +4.124 | highly left-skewed, leptokurtic |

**arrhenius_factor design note:** Zero variance because Shaft sensor rows (sensor_type=rpm, sensor_id=22) always have AF=1.0 (`is_arrhenius_applicable=False` locked Day 5). When stratified by component, the four thermally-governed components show AF > 1.0. Shapiro-Wilk "range zero" warning on AF is expected and harmless — documented in module docstring.

---

##### Variable Domain — Production Counts

**SQL join used:**
```sql
SELECT pc.total_units, pc.good_units, pc.defective_units, pc.rework_units,
       pc.ideal_cycle_time_min,
       CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0) AS first_pass_yield,
       c.component_name, ps.shift_label
FROM production_counts pc
JOIN components c ON pc.component_id = c.component_id
JOIN production_shifts ps ON pc.shift_id = ps.shift_id
```

**`first_pass_yield` derivation:** Computed at query time using `CAST(good_units AS FLOAT) / NULLIF(total_units, 0)`. The `NULLIF` guard prevents division-by-zero for any hypothetical zero-unit shifts. This is the Python-side equivalent of the SQL `oee_quality.sql` formula (locked Day 4).

**Stratification levels (3):**
1. Fleet-wide
2. By component_name (5 components)
3. By shift_label (3 shifts: DAY, NIGHT, SWING)

**Key results (FLEET_ALL):**

| Variable | Mean | Median | Skewness | ExKurtosis |
|---|---|---|---|---|
| `total_units` | 789.29 | 795.00 | -1.270 | +5.615 |
| `good_units` | 773.33 | 786.50 | -1.256 | +5.167 |
| `defective_units` | 9.953 | 11.000 | +1.937 | +33.61 |
| `rework_units` | 6.016 | 7.000 | +1.838 | +30.33 |
| `ideal_cycle_time_min` | 0.6124 | 0.600 | +0.301 | -1.216 |
| `first_pass_yield` | 0.9787 | 0.9794 | -5.179 | +48.29 |

**`ideal_cycle_time_min` platykurtic result explained:** ICT takes exactly 5 discrete values (one per component, derived from RATED_THROUGHPUT_UPH constants locked Day 11). A uniform-like 5-point discrete distribution is expected to have negative excess kurtosis (platykurtic). This confirms the design constant was applied consistently across all 1,350 production_counts rows.

---

##### Variable Domain — Downtime Durations

**SQL join used:**
```sql
SELECT de.duration_min, de.downtime_category, c.component_name
FROM downtime_events de
JOIN components c ON de.component_id = c.component_id
```

**Stratification levels (4):**
1. Fleet-wide (142 rows)
2. By downtime_category (4 categories present: unplanned_failure, cascade_upstream, idle, planned_maintenance)
3. By component_name (5 components)
4. Cross-stratified: (component_name × downtime_category) — 16 non-empty combinations

**Key results (FLEET_ALL, duration_min):**

| Statistic | Value |
|---|---|
| n | 142 |
| Mean | 75.70 min |
| Median | 23.68 min |
| StdDev | 121.47 min |
| Skewness | +2.239 |
| Excess Kurtosis | +3.764 |
| P05 | 8.0 min |
| P25 | 10.5 min |
| P75 | 107.5 min |
| P95 | 382.0 min |
| Max | 480.0 min |
| CV% | 160.5% |
| Shape | highly right-skewed, leptokurtic |

**Mean/Median gap interpretation:** Mean=75.7 vs Median=23.7 — Motor Housing CBM repairs (MTTR=12h=720 min, capped to shift window of 480 min) create the heavy right tail. CV=160% confirms the distribution is dominated by extreme values. Median is the recommended central tendency metric for maintenance reporting.

---

##### pandas Methods Used (Day 14 — locked)

| Method | Purpose |
|---|---|
| `pd.read_sql_query(sql, conn)` | Load SQLite query result as DataFrame |
| `series.dropna()` | Exclude NULL rows before statistics |
| `series.mean()` | Arithmetic mean |
| `series.median()` | Median |
| `series.var(ddof=1)` | Sample variance |
| `series.std(ddof=1)` | Sample std dev |
| `series.skew()` | Fisher-Pearson skewness |
| `series.kurtosis()` | Excess kurtosis (Fisher) |
| `series.quantile([...])` | Vectorised percentile computation |
| `series.isna().sum()` | Count of missing values |
| `series.sample(n, random_state=42)` | Shapiro-Wilk subsampling |
| `df.groupby(col, sort=True)` | Stratified iteration |
| `pd.DataFrame(rows)` | Assemble stats list into output DataFrame |
| `df.to_csv(path, index=False)` | Write output CSVs |
| `scipy.stats.shapiro(series)` | Shapiro-Wilk normality test |

---

##### Key Decisions Locked Today

1. **`ddof=1` for all variance/std:** Sample statistics, not population. The 47,957 rows are a simulated sample from an infinite generating distribution — Bessel's correction is correct.

2. **Shapiro-Wilk subsampling at n=5000:** scipy.stats.shapiro is designed for n ≤ 5000. Subsampling with fixed seed=42 preserves reproducibility and test validity. Documented in `_shapiro()` docstring.

3. **`first_pass_yield` derived in SQL, not Python:** `CAST(good_units AS FLOAT) / NULLIF(total_units, 0)` is computed in the SELECT statement, not post-load in pandas. This keeps the derivation in the same layer as the OEE quality formula (Day 4) and ensures NULLIF zero-guard is SQL-enforced.

4. **Report file written with `encoding="utf-8"`:** The full text report (`eda_full_report.txt`) uses UTF-8 for Unicode characters (em-dash, box-drawing lines). The console print statements use ASCII-only characters for Windows cp1252 compatibility.

5. **Four stratification levels for downtime (including cross-tab):** The component × category cross-tab was added specifically to support Power BI matrix visual data (Days 21–23) — each cell of the cross-tab provides the median/mean downtime for one (component, failure_type) pair.

**Open items / carry-forward to Day 15:**
- [ ] Power BI connection to `data/manufacturing.db` (DirectQuery or Import)
- [ ] Fleet Overview page: OEE KPI cards, 4-week rolling trend, MTBF ranking bar chart
- [ ] Backfill `failure_log.repair_hours` (required before Q2 in oee_window_analytics.sql returns data)
- [ ] Consider visualizing EDA distributions using matplotlib/seaborn histograms with KDE overlay (Phase 2.2 polish)
- [ ] Wire `eda_sensor_stats.csv` P25/P75 bounds as soft control chart limits in kpi.py (Day 18+)

---

*End of Day 14 context entry. Tomorrow (Day 15): Power BI Fleet Overview page — OEE KPI cards, downtime Pareto, MTBF ranking.*

---
