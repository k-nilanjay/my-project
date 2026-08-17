"""
eda_correlation.py — Day 15: Correlation Analysis
===================================================
Phase 2.1 — SQL Analytics | Sub-phase: EDA Correlation

PURPOSE
-------
Connect to data/manufacturing.db, use Pandas groupby and pivot_table to
structure sensor readings, production counts, and downtime variables into
wide/pivoted formats, then compute Pearson and Spearman correlation matrices
for each analytical domain.

ANALYTICAL DOMAINS (5 correlation matrices produced)
------------------------------------------------------
  1. Sensor-pivot by component — wide DataFrame where each column is a
     (component_name, sensor_type) pair; correlates cross-sensor readings
     for the same timestamp/cycle (Pearson + Spearman).

  2. Within-component sensor correlations — per-component: correlate all
     sensor channels for that component (vibration, temperature, etc.)
     using pivot_table to align by cycle number.

  3. Production KPI correlations — correlate total_units, good_units,
     defective_units, rework_units, ideal_cycle_time_min, and
     first_pass_yield per component × shift (Pearson + Spearman).

  4. Sensor readings vs production KPIs — join sensor-level aggregates
     (mean vibration, mean temperature) to production KPIs per component
     per shift day; correlate health against quality outcomes.

  5. Downtime variables — correlate duration_min with component_id,
     downtime_category (encoded), cascade_flag, and cycle-level
     health score; Pearson + Spearman.

OUTPUTS (all exported to data/processed/)
------------------------------------------
  corr_sensor_pivot_pearson.csv
  corr_sensor_pivot_spearman.csv
  corr_within_component_pearson.csv    (one block per component, stacked)
  corr_within_component_spearman.csv
  corr_production_pearson.csv
  corr_production_spearman.csv
  corr_sensor_vs_production_pearson.csv
  corr_sensor_vs_production_spearman.csv
  corr_downtime_pearson.csv
  corr_downtime_spearman.csv

LOCKED DECISIONS
----------------
- Pearson: assumes linear relationship; suitable for vibration/temperature
  continuous channels with Gaussian noise.
- Spearman: rank-based, appropriate for skewed distributions (downtime,
  oil_debris, defect counts confirmed heavily skewed in Day 14 EDA).
- Both methods computed for every domain — report includes both so the viva
  can discuss where they diverge (oil_debris: Spearman >> Pearson due to
  exponential ramp distribution).
- groupby().mean() used to aggregate per-component per-cycle before pivoting.
- pivot_table(aggfunc='mean') used where multiple readings exist per
  (index, column) combination.
- min_periods=5 enforced on all corr() calls to suppress spurious
  correlations from components with few data points.
- NaN cells in correlation matrix left as NaN (not zero-filled) so that
  Power BI conditional formatting can distinguish from true-zero correlation.

PANDAS API CHOICES (locked Day 15)
-----------------------------------
  pd.read_sql_query()       — load from SQLite without SQLAlchemy overhead
  df.pivot_table()          — structured wide reshaping; handles duplicates via aggfunc
  df.groupby()              — stratified aggregation before correlation
  df.corr(method='pearson') — pairwise Pearson r matrix
  df.corr(method='spearman')— pairwise Spearman ρ matrix
  df.to_csv()               — export matrices

REFERENCES
----------
  Day 14 CONTEXT.md — EDA summary stats (skewness confirmed for all 3 domains)
  Day 9  CONTEXT.md — sensor_readings schema (component_id, sensor_type, value, ...)
  Day 11 CONTEXT.md — production_counts schema (total_units, good_units, ...)
  ISO 10816-3        — vibration zones (WHY vibration-temperature correlation matters)
  scipy.stats.spearmanr — alternative rank-correlation; cross-checked against df.corr
"""

import sqlite3
import os
import warnings

import pandas as pd
import numpy as np
from scipy import stats

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PATH = os.path.join("data", "manufacturing.db")
OUTPUT_DIR = os.path.join("data", "processed")
MIN_PERIODS = 5           # minimum non-NaN pairs to compute a correlation cell
RANDOM_STATE = 42         # reproducibility for any sampling steps

# Component names (PIPELINE_ORDER from topology.py, locked Day 5)
COMPONENT_ORDER = ["Bearing", "Shaft", "Motor Housing", "Coupling", "Gearbox"]

# Sensor types present in the DB (from Day 9 inspection)
SENSOR_TYPES = ["vibration", "temperature", "rpm", "load", "oil_debris"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Open a read-only SQLite connection with FK enforcement."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _save_matrix(df: pd.DataFrame, filename: str) -> None:
    """Export a correlation matrix DataFrame to data/processed/ as CSV."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, filename)
    df.to_csv(out_path)
    print(f"  [SAVED] {out_path}  shape={df.shape}")


def _corr_both_methods(df: pd.DataFrame, label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute Pearson and Spearman correlation matrices.

    Parameters
    ----------
    df : DataFrame — wide-format numeric data (rows = observations, cols = variables)
    label : str — descriptive label for console output

    Returns
    -------
    pearson_corr, spearman_corr : (pd.DataFrame, pd.DataFrame)
    """
    numeric_df = df.select_dtypes(include=[np.number])
    pearson = numeric_df.corr(method="pearson", min_periods=MIN_PERIODS)
    spearman = numeric_df.corr(method="spearman", min_periods=MIN_PERIODS)
    n_vars = numeric_df.shape[1]
    print(f"\n  {label}: {n_vars} variables, {len(numeric_df)} observations")
    print(f"    Pearson  matrix : {pearson.shape[0]}×{pearson.shape[1]}")
    print(f"    Spearman matrix : {spearman.shape[0]}×{spearman.shape[1]}")
    return pearson, spearman


# ---------------------------------------------------------------------------
# Domain 1 — Sensor Pivot: cross-sensor correlations (all components)
# ---------------------------------------------------------------------------

def domain1_sensor_pivot_correlations(conn: sqlite3.Connection) -> None:
    """
    Build a wide pivot where columns = (component_name, sensor_type) pairs
    and rows = cycle_number × hour-level readings (aligned by component_id + cycle_number).

    groupby(component_id, sensor_type, cycle_number).mean() collapses multiple
    readings in the same cycle to a single mean value per channel per cycle.
    pivot_table() then reshapes to wide format.

    Purpose: identify cross-sensor, cross-component linear relationships —
    e.g., Bearing vibration ↔ Motor Housing temperature (cascade symptom).
    """
    print("\n" + "=" * 60)
    print("DOMAIN 1 — Sensor Pivot Correlation (All Components)")
    print("=" * 60)

    sql = """
        SELECT
            c.component_name,
            s.sensor_type,
            sr.cycle_number,
            sr.value,
            sr.r_derated,
            sr.health_score
        FROM sensor_readings sr
        JOIN sensors        s  ON sr.sensor_id    = s.sensor_id
        JOIN components     c  ON sr.component_id = c.component_id
        WHERE sr.value IS NOT NULL
    """
    df = pd.read_sql_query(sql, conn)
    print(f"  Loaded {len(df):,} sensor reading rows")

    # --- groupby: mean per (component_name, sensor_type, cycle_number) ---
    grouped = (
        df.groupby(["component_name", "sensor_type", "cycle_number"], sort=True)
        ["value"]
        .mean()
        .reset_index()
    )
    print(f"  After groupby mean: {len(grouped):,} rows")

    # --- pivot_table: rows=cycle_number, columns=(component_name, sensor_type) ---
    pivot = df.pivot_table(
        index="cycle_number",
        columns=["component_name", "sensor_type"],
        values="value",
        aggfunc="mean"
    )
    # Flatten MultiIndex columns to "ComponentName_SensorType"
    pivot.columns = [f"{comp}_{stype}" for comp, stype in pivot.columns]
    pivot = pivot.reset_index(drop=True)
    print(f"  Pivot shape: {pivot.shape}  (rows=cycles, cols=component×sensor)")

    # --- correlations ---
    pearson, spearman = _corr_both_methods(pivot, "Sensor Pivot")
    _save_matrix(pearson,  "corr_sensor_pivot_pearson.csv")
    _save_matrix(spearman, "corr_sensor_pivot_spearman.csv")

    # Console highlight: top 5 off-diagonal Pearson pairs
    _print_top_correlations(pearson, label="Sensor Pivot (Pearson)", top_n=5)


# ---------------------------------------------------------------------------
# Domain 2 — Within-Component Sensor Correlations
# ---------------------------------------------------------------------------

def domain2_within_component_correlations(conn: sqlite3.Connection) -> None:
    """
    For each component independently, pivot its own sensor types into columns
    and compute Pearson + Spearman.

    Use pivot_table(aggfunc='mean') per component — aligns vibration,
    temperature (and component-specific channels: rpm for Shaft, load for
    Coupling, oil_debris for Gearbox) on cycle_number.

    Produces one stacked CSV with a 'component' index block per component.
    """
    print("\n" + "=" * 60)
    print("DOMAIN 2 — Within-Component Sensor Correlations")
    print("=" * 60)

    sql = """
        SELECT
            c.component_name,
            sr.component_id,
            s.sensor_type,
            sr.cycle_number,
            sr.value,
            sr.r_derated,
            sr.health_score,
            sr.is_anomaly
        FROM sensor_readings sr
        JOIN sensors        s  ON sr.sensor_id    = s.sensor_id
        JOIN components     c  ON sr.component_id = c.component_id
        WHERE sr.value IS NOT NULL
    """
    df = pd.read_sql_query(sql, conn)

    all_pearson_blocks = []
    all_spearman_blocks = []

    for comp_name in COMPONENT_ORDER:
        comp_df = df[df["component_name"] == comp_name].copy()
        if comp_df.empty:
            print(f"  [{comp_name}] No data — skipping")
            continue

        # pivot_table: rows = cycle_number, columns = sensor_type
        pivot = comp_df.pivot_table(
            index="cycle_number",
            columns="sensor_type",
            values="value",
            aggfunc="mean"
        )
        # Also add r_derated and health_score as additional columns
        meta = (
            comp_df.groupby("cycle_number")[["r_derated", "health_score", "is_anomaly"]]
            .mean()
        )
        pivot = pivot.join(meta, how="left")
        pivot = pivot.reset_index(drop=True)

        pearson, spearman = _corr_both_methods(pivot, comp_name)

        # Tag with component name for stacking
        pearson.index  = [f"{comp_name}|{c}" for c in pearson.index]
        pearson.columns = [f"{comp_name}|{c}" for c in pearson.columns]
        spearman.index  = [f"{comp_name}|{c}" for c in spearman.index]
        spearman.columns = [f"{comp_name}|{c}" for c in spearman.columns]

        all_pearson_blocks.append(pearson)
        all_spearman_blocks.append(spearman)
        _print_top_correlations(pearson, label=f"  {comp_name} (Pearson)", top_n=3)

    # Stack all component blocks vertically (different column sets — pad with NaN)
    pearson_stacked  = pd.concat(all_pearson_blocks,  axis=0, sort=False)
    spearman_stacked = pd.concat(all_spearman_blocks, axis=0, sort=False)

    _save_matrix(pearson_stacked,  "corr_within_component_pearson.csv")
    _save_matrix(spearman_stacked, "corr_within_component_spearman.csv")


# ---------------------------------------------------------------------------
# Domain 3 — Production KPI Correlations
# ---------------------------------------------------------------------------

def domain3_production_correlations(conn: sqlite3.Connection) -> None:
    """
    Load production_counts joined to components and production_shifts.
    Compute first_pass_yield in SQL (matches Day 4 oee_quality.sql formula).
    groupby component_name to confirm stratification, then run corr() on
    the full joined DataFrame (pooled fleet-wide).

    Variables: total_units, good_units, defective_units, rework_units,
               ideal_cycle_time_min, first_pass_yield.
    """
    print("\n" + "=" * 60)
    print("DOMAIN 3 — Production KPI Correlations")
    print("=" * 60)

    sql = """
        SELECT
            c.component_name,
            ps.shift_label,
            pc.total_units,
            pc.good_units,
            pc.defective_units,
            pc.rework_units,
            pc.ideal_cycle_time_min,
            CAST(pc.good_units AS REAL) / NULLIF(pc.total_units, 0) AS first_pass_yield
        FROM production_counts  pc
        JOIN components         c  ON pc.component_id = c.component_id
        JOIN production_shifts  ps ON pc.shift_id     = ps.shift_id
    """
    df = pd.read_sql_query(sql, conn)
    print(f"  Loaded {len(df):,} production count rows")

    # --- groupby: report row counts per component for context ---
    counts_by_comp = df.groupby("component_name").size()
    print("  Rows per component:")
    for comp, n in counts_by_comp.items():
        print(f"    {comp}: {n}")

    # Encode shift_label as ordinal for correlation (DAY=0, SWING=1, NIGHT=2)
    shift_map = {"DAY": 0, "SWING": 1, "NIGHT": 2}
    df["shift_ord"] = df["shift_label"].map(shift_map)

    # Numeric columns for fleet-wide correlation
    numeric_cols = [
        "total_units", "good_units", "defective_units", "rework_units",
        "ideal_cycle_time_min", "first_pass_yield", "shift_ord"
    ]
    fleet_df = df[numeric_cols].dropna()
    print(f"  Fleet-wide numeric rows after dropna: {len(fleet_df):,}")

    pearson, spearman = _corr_both_methods(fleet_df, "Production KPIs (fleet-wide)")
    _save_matrix(pearson,  "corr_production_pearson.csv")
    _save_matrix(spearman, "corr_production_spearman.csv")
    _print_top_correlations(pearson, label="Production (Pearson)", top_n=5)

    # --- per-component stratified correlation (append to report separately) ---
    print("\n  Per-component Pearson highlights:")
    for comp_name in COMPONENT_ORDER:
        comp_df = df[df["component_name"] == comp_name][numeric_cols].dropna()
        if len(comp_df) < MIN_PERIODS:
            print(f"    [{comp_name}] insufficient data ({len(comp_df)} rows)")
            continue
        r = comp_df.corr(method="pearson", min_periods=MIN_PERIODS)
        fpy_corrs = r["first_pass_yield"].drop("first_pass_yield").sort_values(key=abs, ascending=False)
        top = fpy_corrs.iloc[0]
        print(f"    [{comp_name}] first_pass_yield ~ {fpy_corrs.index[0]}: r={top:.4f}")


# ---------------------------------------------------------------------------
# Domain 4 — Sensor Readings vs Production KPIs
# ---------------------------------------------------------------------------

def domain4_sensor_vs_production(conn: sqlite3.Connection) -> None:
    """
    Aggregate sensor readings to daily means per component (groupby on
    date portion of ts + component_name), then join to production_counts
    aggregated to the same day-level.

    Resulting wide DataFrame columns:
      mean_vibration, mean_temperature, mean_health_score,
      anomaly_rate, total_units, good_units, first_pass_yield

    Purpose: test whether elevated sensor readings (degradation) correlate
    with reduced production quality in the same operational window.
    """
    print("\n" + "=" * 60)
    print("DOMAIN 4 — Sensor Readings vs Production KPIs")
    print("=" * 60)

    # Sensor daily means per component
    sql_sensors = """
        SELECT
            c.component_id,
            c.component_name,
            DATE(sr.ts) AS reading_date,
            s.sensor_type,
            AVG(sr.value)        AS mean_value,
            AVG(sr.health_score) AS mean_health_score,
            AVG(CAST(sr.is_anomaly AS REAL)) AS anomaly_rate
        FROM sensor_readings sr
        JOIN sensors          s  ON sr.sensor_id    = s.sensor_id
        JOIN components       c  ON sr.component_id = c.component_id
        WHERE s.sensor_type IN ('vibration', 'temperature')
        GROUP BY c.component_id, c.component_name, DATE(sr.ts), s.sensor_type
    """
    sensor_daily = pd.read_sql_query(sql_sensors, conn)
    print(f"  Loaded {len(sensor_daily):,} sensor-daily aggregate rows")

    # Pivot sensor_type into columns: mean_vibration, mean_temperature
    sensor_pivot = sensor_daily.pivot_table(
        index=["component_id", "component_name", "reading_date"],
        columns="sensor_type",
        values="mean_value",
        aggfunc="mean"
    ).reset_index()
    sensor_pivot.columns.name = None
    sensor_pivot = sensor_pivot.rename(columns={
        "vibration":   "mean_vibration",
        "temperature": "mean_temperature"
    })

    # Health score and anomaly rate by day (averaged across sensor types)
    health_daily = (
        sensor_daily.groupby(["component_id", "reading_date"])[["mean_health_score", "anomaly_rate"]]
        .mean()
        .reset_index()
    )
    sensor_pivot = sensor_pivot.merge(health_daily, on=["component_id", "reading_date"], how="left")

    # Production counts: aggregate to daily level (sum across shifts per day)
    sql_prod = """
        SELECT
            pc.component_id,
            DATE(ps.planned_start_ts) AS shift_date,
            SUM(pc.total_units)     AS total_units,
            SUM(pc.good_units)      AS good_units,
            SUM(pc.defective_units) AS defective_units,
            SUM(pc.rework_units)    AS rework_units,
            AVG(CAST(pc.good_units AS REAL) / NULLIF(pc.total_units, 0)) AS first_pass_yield
        FROM production_counts  pc
        JOIN production_shifts  ps ON pc.shift_id = ps.shift_id
        GROUP BY pc.component_id, DATE(ps.planned_start_ts)
    """
    prod_daily = pd.read_sql_query(sql_prod, conn)
    print(f"  Loaded {len(prod_daily):,} production-daily aggregate rows")

    # Join sensor and production daily frames on (component_id, date)
    merged = sensor_pivot.merge(
        prod_daily,
        left_on=["component_id", "reading_date"],
        right_on=["component_id", "shift_date"],
        how="inner"
    )
    print(f"  Merged rows (inner join sensor×production): {len(merged):,}")

    if len(merged) < MIN_PERIODS:
        print("  WARNING: Insufficient overlapping rows — skipping Domain 4 correlation.")
        return

    # groupby component_name to report per-component row counts
    print("  Merged rows per component:")
    for comp, grp in merged.groupby("component_name"):
        print(f"    {comp}: {len(grp)}")

    numeric_cols = [
        "mean_vibration", "mean_temperature", "mean_health_score",
        "anomaly_rate", "total_units", "good_units",
        "defective_units", "rework_units", "first_pass_yield"
    ]
    analysis_df = merged[numeric_cols].dropna()
    print(f"  Analysis rows (dropna): {len(analysis_df):,}")

    pearson, spearman = _corr_both_methods(analysis_df, "Sensor vs Production")
    _save_matrix(pearson,  "corr_sensor_vs_production_pearson.csv")
    _save_matrix(spearman, "corr_sensor_vs_production_spearman.csv")
    _print_top_correlations(pearson,  label="Sensor vs Production (Pearson)",  top_n=5)
    _print_top_correlations(spearman, label="Sensor vs Production (Spearman)", top_n=5)


# ---------------------------------------------------------------------------
# Domain 5 — Downtime Variable Correlations
# ---------------------------------------------------------------------------

def domain5_downtime_correlations(conn: sqlite3.Connection) -> None:
    """
    Join downtime_events with components and production_shifts to obtain:
      - duration_min      (dependent variable — Day 14: CV=160%, highly right-skewed)
      - component_id      (categorical, numeric ID)
      - downtime_category (label-encoded: 0=idle, 1=planned_maintenance,
                           2=cascade_upstream, 3=unplanned_failure)
      - pipeline_position (component position 1–5 in the series chain)
      - is_cascade        (binary: 1 if downtime_category='cascade_upstream')
      - shift_label_ord   (DAY=0, SWING=1, NIGHT=2)

    Then join failure_log mean health_score at failure time for context.

    Spearman is primary here: duration_min confirmed highly right-skewed in
    Day 14 EDA (skew=+2.239, ExKurt=+3.764); rank-based correlation more robust.
    """
    print("\n" + "=" * 60)
    print("DOMAIN 5 — Downtime Variable Correlations")
    print("=" * 60)

    sql = """
        SELECT
            de.downtime_id,
            de.component_id,
            c.position_in_chain,
            de.duration_min,
            de.downtime_category,
            de.shift_id,
            ps.shift_label,
            CASE WHEN de.downtime_category = 'cascade_upstream'   THEN 1 ELSE 0 END AS is_cascade,
            CASE WHEN de.downtime_category = 'unplanned_failure'  THEN 1 ELSE 0 END AS is_unplanned,
            CASE WHEN de.downtime_category = 'planned_maintenance' THEN 1 ELSE 0 END AS is_planned,
            de.root_cause_component_id
        FROM downtime_events     de
        JOIN components          c  ON de.component_id = c.component_id
        JOIN production_shifts   ps ON de.shift_id     = ps.shift_id
    """
    df = pd.read_sql_query(sql, conn)
    print(f"  Loaded {len(df):,} downtime event rows")

    # Ordinal-encode downtime_category (for Pearson; rank-invariant for Spearman)
    cat_map = {
        "idle": 0,
        "planned_maintenance": 1,
        "cascade_upstream": 2,
        "unplanned_failure": 3,
        "changeover": 4
    }
    df["category_ord"] = df["downtime_category"].map(cat_map)

    shift_map = {"DAY": 0, "SWING": 1, "NIGHT": 2}
    df["shift_ord"] = df["shift_label"].map(shift_map)

    # groupby component to report row counts
    print("  Rows per component:")
    for comp_id, grp in df.groupby("component_id"):
        print(f"    component_id={comp_id}: {len(grp)} events")

    numeric_cols = [
        "component_id", "position_in_chain", "duration_min",
        "category_ord", "is_cascade", "is_unplanned", "is_planned",
        "shift_ord"
    ]
    analysis_df = df[numeric_cols].dropna()
    print(f"  Numeric rows (after dropna): {len(analysis_df):,}")

    pearson, spearman = _corr_both_methods(analysis_df, "Downtime Variables")
    _save_matrix(pearson,  "corr_downtime_pearson.csv")
    _save_matrix(spearman, "corr_downtime_spearman.csv")
    _print_top_correlations(pearson,  label="Downtime (Pearson)",  top_n=5)
    _print_top_correlations(spearman, label="Downtime (Spearman)", top_n=5)

    # --- Additional: per-category duration summary via groupby ---
    print("\n  Duration_min summary by downtime_category (groupby):")
    cat_summary = df.groupby("downtime_category")["duration_min"].agg(
        n="count", mean="mean", median="median", std="std", max="max"
    ).round(2)
    print(cat_summary.to_string())

    # --- Spearman r for duration_min ~ pipeline_position ---
    rho, pval = stats.spearmanr(
        analysis_df["position_in_chain"].dropna(),
        analysis_df["duration_min"].dropna()
    )
    print(f"\n  Spearman r (duration_min ~ pipeline_position): rho={rho:.4f}, p={pval:.4f}")
    direction = "downstream components tend to have LONGER downtimes" if rho > 0 else \
                "downstream components tend to have SHORTER downtimes"
    print(f"  Interpretation: {direction} (cascade propagation expected)")


# ---------------------------------------------------------------------------
# Utility — Print top N correlations (off-diagonal)
# ---------------------------------------------------------------------------

def _print_top_correlations(
    corr_matrix: pd.DataFrame,
    label: str = "",
    top_n: int = 5
) -> None:
    """
    Extract the upper triangle of a correlation matrix, exclude diagonal (r=1),
    sort by absolute value, and print the top N pairs.

    Uses numpy triu mask to avoid reporting each pair twice.
    """
    mat = corr_matrix.copy()
    mat_np = mat.values.astype(float)
    mask = np.triu(np.ones(mat_np.shape, dtype=bool), k=1)
    rows, cols = np.where(mask)

    pairs = []
    for r, c in zip(rows, cols):
        val = mat_np[r, c]
        if not np.isnan(val):
            pairs.append((mat.index[r], mat.columns[c], val))

    pairs.sort(key=lambda x: abs(x[2]), reverse=True)

    print(f"\n  Top {min(top_n, len(pairs))} correlations — {label}:")
    for a, b, r_val in pairs[:top_n]:
        bar = "|" * int(abs(r_val) * 20)
        direction = "+" if r_val >= 0 else "-"
        print(f"    {direction}{abs(r_val):.4f}  {bar:<20}  {a}  <->  {b}")


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def _print_summary() -> None:
    """Print a final summary of all exported CSVs."""
    print("\n" + "=" * 60)
    print("DAY 15 SUMMARY — Exported Correlation Matrices")
    print("=" * 60)
    files = [
        ("corr_sensor_pivot_pearson.csv",           "Domain 1 — Sensor Pivot (Pearson)"),
        ("corr_sensor_pivot_spearman.csv",           "Domain 1 — Sensor Pivot (Spearman)"),
        ("corr_within_component_pearson.csv",        "Domain 2 — Within-Component (Pearson)"),
        ("corr_within_component_spearman.csv",       "Domain 2 — Within-Component (Spearman)"),
        ("corr_production_pearson.csv",              "Domain 3 — Production KPIs (Pearson)"),
        ("corr_production_spearman.csv",             "Domain 3 — Production KPIs (Spearman)"),
        ("corr_sensor_vs_production_pearson.csv",    "Domain 4 — Sensor vs Production (Pearson)"),
        ("corr_sensor_vs_production_spearman.csv",   "Domain 4 — Sensor vs Production (Spearman)"),
        ("corr_downtime_pearson.csv",                "Domain 5 — Downtime Variables (Pearson)"),
        ("corr_downtime_spearman.csv",               "Domain 5 — Downtime Variables (Spearman)"),
    ]
    for fname, desc in files:
        fpath = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(fpath):
            size_kb = os.path.getsize(fpath) / 1024
            print(f"  [OK]  {fname:<50}  {size_kb:.1f} KB  — {desc}")
        else:
            print(f"  [MISSING]  {fname}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("eda_correlation.py — Day 15 Correlation Analysis")
    print(f"Database : {os.path.abspath(DB_PATH)}")
    print(f"Output   : {os.path.abspath(OUTPUT_DIR)}")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}\n"
            "Run run_etl_pipeline() from etl.py to populate the database first."
        )

    conn = _connect(DB_PATH)

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            domain1_sensor_pivot_correlations(conn)
            domain2_within_component_correlations(conn)
            domain3_production_correlations(conn)
            domain4_sensor_vs_production(conn)
            domain5_downtime_correlations(conn)
    finally:
        conn.close()

    _print_summary()
    print("\nDay 15 correlation analysis complete.")


if __name__ == "__main__":
    main()
