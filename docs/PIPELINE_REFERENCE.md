# docs/PIPELINE_REFERENCE.md
## Manufacturing & Industrial Analytics FYP — End-to-End Pipeline Reference
### Consolidated for Viva Presentation | Day 20 — August 7, 2026

---

## 1. Pipeline Architecture Overview

```
  [Stage 1]              [Stage 2]         [Stage 3]           [Stage 4]        [Stage 5]
  Data Generation  -->  SQL Ingestion  -->  EDA (x3)  -->  Graph Centrality --> CCI
  rebuild.py            ingest.py          eda_*.py      graph_centrality.py  composite_criticality.py
        |                    |                 |                 |                    |
  multi_failure_      manufacturing.db   eda_stats.csv    centrality_         criticality_
  telemetry.csv       sensor_readings    eda_plots/*.png  rankings.csv        scores.csv
  ttf_samples.csv     failure_log                                             criticality_
                                                                              index_plot.png
```

**Run command (full pipeline):**
```bash
# Activate virtual environment first
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux

# Full pipeline
python run_pipeline.py

# Skip data generation (use existing DB)
python run_pipeline.py --skip-generation

# Skip generation + ingestion (DB already populated)
python run_pipeline.py --skip-generation --skip-ingestion

# Dry-run (show what would execute)
python run_pipeline.py --dry-run

# Verbose (stream all subprocess output)
python run_pipeline.py --verbose
```

---

## 2. Stage-by-Stage Reference

### Stage 1: Data Generation

| Field | Value |
|---|---|
| Runner | `rebuild.py` |
| Core module | `python/data_generator.py` |
| OEE module | `python/data_generator_oee.py` |
| Physics model | Weibull TTF injection (inverse-CDF) + Arrhenius temperature modulation |
| Window | 365 simulated days (continuous operation) |
| Rows generated | ~47,957 sensor readings (5 components × ~9,592 readings/component) |
| DB action | Deletes + recreates `data/manufacturing.db`; runs `sql/schema.sql` + `sql/seed.sql` |

**Key outputs:**
- `data/processed/multi_failure_telemetry.csv` — ~48,000 rows, columns: component, sensor_type, value, timestamp, cycle_number, r_derated, arrhenius_factor, health_score
- `data/processed/ttf_samples.csv` — 19 TTF samples (Weibull-generated failure times)
- `data/manufacturing.db` — SQLite database (~7.4 MB after Stage 2 completion)

> **WARNING**: Stage 1 **deletes** the existing `data/manufacturing.db`. Do not run Stage 1 if you need to preserve current DB data. Use `--skip-generation` flag.

---

### Stage 2: SQL Ingestion

| Field | Value |
|---|---|
| Runner | `ingest.py` |
| Core module | `python/etl.py` |
| SQL files used | `sql/schema.sql`, `sql/seed.sql` |
| Insert pattern | `INSERT OR IGNORE` (idempotent — safe to re-run) |
| Validation | 9 schema rules in `etl.validate_sensor_readings()` |
| Timestamp normalisation | UTC |

**Tables loaded:**
- `sensor_readings` ← `multi_failure_telemetry.csv` (expect ~47,957 rows)
- `failure_log` ← `ttf_samples.csv` (expect 19 rows)

**Other tables** (populated by `rebuild.py` Stage 1 OEE generation):
- `production_shifts` — 1,350 rows
- `downtime_events` — 142 rows
- `production_counts` — 1,350 rows

---

### Stage 3: Exploratory Data Analysis (3 sub-scripts)

All 3 EDA scripts run **sequentially** (SQLite write-lock contention prevents parallelism).

#### Stage 3a: `eda_summary_stats.py` (Day 14)

| Output | Description |
|---|---|
| `data/processed/eda_sensor_stats.csv` | Mean, median, std, skewness, kurtosis, Shapiro-Wilk p-value per sensor type × component |
| `data/processed/eda_production_stats.csv` | Production KPI descriptive stats (total_units, FPY, downtime_min per shift) |
| `data/processed/eda_downtime_stats.csv` | Downtime duration stats stratified by category and component |
| `data/processed/eda_full_report.txt` | Human-readable mirror of all above (82 KB) |

#### Stage 3b: `eda_trends.py` (Day 16)

| Output | Description |
|---|---|
| `data/processed/plots/rolling_avg_sensor_trends.png` | 7-day and 14-day rolling averages: Gearbox vibration and Motor Housing temperature degradation ramps |
| `data/processed/plots/shift_oee_seasonality.png` | OEE and A/P/Q factors stratified by shift label (DAY/SWING/NIGHT) |
| `data/processed/plots/downtime_vs_failures_stacked.png` | Daily downtime stacked area chart overlaid with failure event markers |

#### Stage 3c: `eda_correlation.py` (Day 15)

| Output | Description |
|---|---|
| `data/processed/corr_sensor_pivot_pearson.csv` | Cross-component sensor pivot correlation (Pearson) |
| `data/processed/corr_sensor_pivot_spearman.csv` | Cross-component sensor pivot correlation (Spearman) |
| `data/processed/corr_within_component_pearson.csv` | Within-component sensor correlation (Pearson, 5 components) |
| `data/processed/corr_within_component_spearman.csv` | Within-component sensor correlation (Spearman, 5 components) |
| `data/processed/corr_production_pearson.csv` | Production KPI correlation (Pearson) |
| `data/processed/corr_production_spearman.csv` | Production KPI correlation (Spearman) |
| `data/processed/corr_downtime_pearson.csv` | Downtime duration correlation (Pearson) |
| `data/processed/corr_downtime_spearman.csv` | Downtime duration correlation (Spearman) |
| `data/processed/corr_sensor_vs_production_pearson.csv` | Sensor vs production KPI (Pearson) |
| `data/processed/corr_sensor_vs_production_spearman.csv` | Sensor vs production KPI (Spearman) |

**Key EDA finding (locked Day 15/17):** Three high-correlation cascade pairs:
- Gearbox_vibration vs Motor Housing_vibration: Pearson r = +0.9954
- Gearbox_oil_debris vs Motor Housing_temperature: Pearson r = +0.9927
- Bearing_temperature vs Bearing_vibration: Pearson r = +0.9892

---

### Stage 4: Graph Centrality (`graph_centrality.py`, Day 18)

**DAG topology:**
```
[Bearing] --> [Shaft] --> [Motor Housing] --> [Coupling] --> [Gearbox]
```

**Metrics computed:**

| Metric | Formula |
|---|---|
| Betweenness Centrality (BC) | BC(v) = SUM_{s!=v!=t} [sigma_st(v)/sigma_st] / [(N-1)(N-2)] |
| In-Degree Centrality | in_edges / (N-1) |
| Out-Degree Centrality | out_edges / (N-1) |
| Cascade Reach | transitive downstream descendants |
| Cascade Exposure | transitive upstream ancestors |
| Structural Risk Score (SRS) | 0.50*BC_norm + 0.30*Reach_norm + 0.20*Exposure_norm |

**SRS Rankings (locked Day 18):**

| Component | BC | Reach | Exposure | SRS |
|---|---|---|---|---|
| Motor Housing | 0.5833 | 0.5000 | 0.5000 | 0.7500 |
| Shaft | 0.4167 | 0.7500 | 0.2500 | 0.6500 |
| Coupling | 0.2500 | 0.2500 | 0.7500 | 0.6000 |
| Bearing | 0.0000 | 1.0000 | 0.0000 | 0.3000 |
| Gearbox | 0.0000 | 0.0000 | 1.0000 | 0.2000 |

**Key outputs:**
- `data/processed/graph_centrality_rankings.csv` — SRS per component
- `data/processed/graph_centrality_metrics.csv` — full metrics table
- `data/processed/plots/dag_centrality_plot.png` — DAG visualisation with node sizes proportional to SRS

---

### Stage 5: Composite Criticality Index (`composite_criticality.py`, Day 19)

**Formula (locked Day 19):**
```
CCI(c) = 0.40 * SRS_norm(c) + 0.35 * (1-R(t))_norm(c) + 0.25 * TBR_norm(c)

where:
  SRS_norm    = SRS(c) / max(SRS)         [graph bottleneck — structural risk]
  Unreliability_norm = (1-R(t))(c) / max(1-R(t))  [Weibull wear-out]
  TBR_norm    = TBR(c) / max(TBR)         [empirical alarm breach frequency]

  R(t) = exp( -(t/eta)^beta )  at t = 2920 h (mid-life evaluation)
  Normalisation: max-normalisation (preserves zero-contribution semantics)
```

**CCI Final Rankings (locked Day 19):**

| CCI Rank | Component | SRS_norm | Unrel_norm | TBR_norm | CCI |
|---|---|---|---|---|---|
| **1** | **Coupling** | 0.8000 | 0.9882 | 0.5531 | **0.8040** |
| 2 | Shaft | 0.8667 | 0.4473 | 1.0000 | 0.7531 |
| 3 | Motor Housing | 1.0000 | 0.5274 | 0.5033 | 0.7104 |
| 4 | Gearbox | 0.2667 | 1.0000 | 0.3680 | 0.5487 |
| 5 | Bearing | 0.4000 | 0.8426 | 0.0089 | 0.4571 |

**Key outputs:**
- `data/processed/criticality_scores.csv` — 5 rows × 16 columns (all sub-metrics + CCI)
- `data/processed/plots/criticality_index_plot.png` — stacked bar chart (dark theme, DPI=150)

---

## 3. Key Output Artefacts for Viva

### Primary Deliverable Files

| Artefact | Path | Status |
|---|---|---|
| Composite Criticality Scores | `data/processed/criticality_scores.csv` | ✅ Generated Day 19 |
| Criticality Index Plot | `data/processed/plots/criticality_index_plot.png` | ✅ Generated Day 19 |
| DAG Centrality Plot | `data/processed/plots/dag_centrality_plot.png` | ✅ Generated Day 18 |
| Rolling Sensor Trends | `data/processed/plots/rolling_avg_sensor_trends.png` | ✅ Generated Day 16 |
| OEE Seasonality | `data/processed/plots/shift_oee_seasonality.png` | ✅ Generated Day 16 |
| Downtime vs Failures | `data/processed/plots/downtime_vs_failures_stacked.png` | ✅ Generated Day 16 |
| EDA Full Report | `data/processed/eda_full_report.txt` | ✅ Generated Day 14 |
| SQLite Database | `data/manufacturing.db` | ✅ 7.4 MB, 47,957 readings |

### criticality_scores.csv — Column Schema (16 columns)

| Column | Description |
|---|---|
| `cci_rank` | Final ranking (1 = most critical) |
| `component` | Component name |
| `structural_risk_score` | Raw SRS from graph_centrality_rankings.csv |
| `weibull_unreliability` | 1-R(t) at t=2920 h using locked Weibull params |
| `threshold_breach_rate` | Fraction of sensor readings exceeding ISO/IEC alarm limits |
| `srs_norm` | Max-normalised SRS |
| `unreliability_norm` | Max-normalised unreliability |
| `tbr_norm` | Max-normalised TBR |
| `cci_srs_contrib` | 0.40 * srs_norm |
| `cci_unrel_contrib` | 0.35 * unreliability_norm |
| `cci_tbr_contrib` | 0.25 * tbr_norm |
| `composite_criticality` | Final CCI = sum of three contributions |
| `w_srs` | Weight applied to SRS (= 0.40) |
| `w_unreliability` | Weight applied to unreliability (= 0.35) |
| `w_tbr` | Weight applied to TBR (= 0.25) |
| `t_eval_hours` | Evaluation age in hours (= 2920) |

---

## 4. Environment & Dependency Notes

### Python Environment
```bash
Python >= 3.9
Virtual environment: .venv/
Activate: .venv\Scripts\activate     (Windows)
          source .venv/bin/activate  (Unix)
pip install -r requirements.txt
```

### Key Dependencies (from requirements.txt)
| Package | Used in |
|---|---|
| pandas >= 1.5 | All stages — data manipulation |
| numpy >= 1.23 | Weibull/Arrhenius math |
| scipy >= 1.9 | Shapiro-Wilk, gamma function (MTBF) |
| matplotlib >= 3.6 | All plot outputs (Agg backend for headless) |
| seaborn >= 0.12 | Heatmap and boxplot styling |
| networkx >= 3.0 | Graph centrality (Stage 4) |
| sqlalchemy >= 1.4 | ORM layer (etl.py) |
| sqlite3 | Built-in — no external DB install needed |

### Environment Variables
| Variable | Value | Purpose |
|---|---|---|
| `MPLBACKEND` | `Agg` | Run matplotlib without display (set automatically by run_pipeline.py) |
| `PYTHONPATH` | `<project_root>/python` | Make python/ sub-modules importable (set automatically) |

### SQLite Constraints
- `PRAGMA foreign_keys = ON` required at each connection — enforces FK cascade rules.
- No SQL Server required for dev; schema is SQLite-compatible.
- Production migration to SQL Server: replace `INTEGER PRIMARY KEY` with `INT IDENTITY(1,1)`.

---

## 5. Success Criteria (Day 20 Validation)

The pipeline is considered successfully validated when all of the following hold:

- [x] `run_pipeline.py --dry-run` prints all 7 stage entries without error
- [x] `run_pipeline.py --skip-generation --skip-ingestion` completes with exit code 0
- [x] `data/processed/criticality_scores.csv` exists, has exactly 5 rows and 16 columns
- [x] `data/processed/plots/criticality_index_plot.png` exists and is > 0 bytes
- [x] `data/processed/graph_centrality_rankings.csv` exists with SRS values matching Day 18 locked values
- [x] `data/manufacturing.db` exists and is > 7 MB
- [x] `data/processed/eda_full_report.txt` exists and is > 50 KB

---

## 6. Likely Viva Questions — Pipeline Integration

**Q: Walk me through how the pipeline stages connect to each other.**

Stage 1 (`rebuild.py`) generates physics-consistent sensor telemetry using Weibull TTF injection and Arrhenius temperature modulation, producing `multi_failure_telemetry.csv`. Stage 2 (`ingest.py`) validates and loads this CSV into `manufacturing.db` using `etl.py`. Stage 3 (three EDA scripts) reads from `manufacturing.db` to compute descriptive statistics and generate diagnostic plots. Stage 4 (`graph_centrality.py`) reads `multi_failure_telemetry.csv` directly to compute betweenness centrality and SRS for each pipeline node. Stage 5 (`composite_criticality.py`) combines Stage 4's SRS output with Weibull parameters (from `sql/seed.sql`) and TBR computed from `multi_failure_telemetry.csv` to produce the final CCI ranking and `criticality_scores.csv`.

**Q: Why does the EDA run after ingestion rather than directly from the CSV?**

The EDA scripts (`eda_summary_stats.py` and `eda_trends.py`) query `manufacturing.db` rather than reading CSV directly because they join multiple tables — `sensor_readings`, `production_shifts`, `downtime_events`, and `production_counts` — in a single analytical pass. These OEE and production tables are populated by Stage 1's OEE data generator, not by Stage 2's ingestion. A direct CSV approach would require manual merging of 4 data sources in pandas, losing the integrity constraints and indexing provided by SQL.

**Q: What happens if Stage 1 (data generation) is re-run?**

`rebuild.py` explicitly deletes `data/manufacturing.db` before regenerating data (`os.remove('data/manufacturing.db')`). This ensures a clean slate — no orphaned rows from a prior run. The `--skip-generation` flag in `run_pipeline.py` prevents this destructive step when the goal is only to re-run analytics on existing data.

**Q: Why are the EDA sub-scripts run sequentially rather than in parallel?**

All three EDA scripts read from the same `data/manufacturing.db` SQLite file. SQLite uses file-level write locking, meaning concurrent writers will produce "database is locked" errors. Even in read-only mode, concurrent readers can sometimes block if the WAL (Write-Ahead Log) is active. Sequential execution is the safe choice for a single-developer environment.

**Q: How does `run_pipeline.py` validate its own output?**

After all stages complete, `validate_pipeline_outputs()` checks every critical artefact: it verifies existence, checks file size (manufacturing.db >= 7 MB, multi_failure_telemetry.csv >= 40,000 rows), and validates `criticality_scores.csv` schema (exactly 5 rows × 16 columns using pandas `df.shape`). The function returns `True` only if all checks pass, which maps to exit code 0 — enabling CI/CD integration or pre-viva automated checks.

---

*PIPELINE_REFERENCE.md — generated Day 20 (Buffer Day). Last updated: August 7, 2026.*
