"""
eda_summary_stats.py
====================
Day 14 — Phase 1.4 Python EDA
Manufacturing & Industrial Analytics FYP

Purpose
-------
Connect to manufacturing.db via sqlite3, load the three key numeric
domains into pandas DataFrames, and compute comprehensive descriptive
statistics (mean, median, variance, std dev, skewness, kurtosis,
percentiles, IQR) for every continuous variable.  Distribution shape
is assessed via the skewness / kurtosis interpretation table and a
Shapiro-Wilk normality test (scipy.stats.shapiro).

Variable domains covered
------------------------
  1. Sensor Readings   — value, r_derated, arrhenius_factor, health_score
                         (stratified by sensor_type and component)
  2. Production Counts — total_units, good_units, defective_units,
                         rework_units, ideal_cycle_time_min, derived FPY
  3. Downtime Durations — duration_min
                          (stratified by downtime_category and component)

Outputs
-------
  data/processed/eda_sensor_stats.csv
  data/processed/eda_production_stats.csv
  data/processed/eda_downtime_stats.csv
  data/processed/eda_full_report.txt      ← human-readable console mirror

Usage
-----
  python eda_summary_stats.py

Dependencies: pandas, scipy (both in requirements.txt)
"""

import sqlite3
import os
import textwrap
from pathlib import Path

import pandas as pd
import numpy as np
from scipy import stats as sp_stats


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = Path("data/manufacturing.db")
OUT_DIR = Path("data/processed")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PERCENTILES = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
SHAPIRO_MAX_N = 5000   # scipy shapiro accurate up to ~5000; subsample above


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a read-only SQLite connection with FK enforcement."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _shapiro(series: pd.Series) -> tuple[float, float, str]:
    """
    Run Shapiro-Wilk normality test.

    Returns (W statistic, p-value, interpretation string).
    Subsamples to SHAPIRO_MAX_N rows if larger (random seed=42).
    Returns (NaN, NaN, 'INSUFFICIENT_DATA') if n < 3.
    """
    clean = series.dropna()
    n = len(clean)
    if n < 3:
        return (float("nan"), float("nan"), "INSUFFICIENT_DATA")
    if n > SHAPIRO_MAX_N:
        clean = clean.sample(SHAPIRO_MAX_N, random_state=42)
    w, p = sp_stats.shapiro(clean)
    if p > 0.05:
        interpretation = "NORMAL (p>0.05)"
    elif p > 0.01:
        interpretation = "BORDERLINE (0.01<p<=0.05)"
    else:
        interpretation = "NON-NORMAL (p<=0.01)"
    return (float(w), float(p), interpretation)


def _shape_label(skew: float, kurt: float) -> str:
    """
    Translate skewness & excess kurtosis into a plain-language label.

    Skewness interpretation (Bulmer 1979 convention):
      |skew| < 0.5   → Approximately symmetric
      0.5 ≤ |skew| < 1.0 → Moderately skewed
      |skew| ≥ 1.0   → Highly skewed

    Excess kurtosis (Fisher definition, scipy default):
      kurt ≈ 0  → Mesokurtic  (normal-like tails)
      kurt > 1  → Leptokurtic (heavy tails, outlier-prone)
      kurt < -1 → Platykurtic (light tails, uniform-like)
    """
    if np.isnan(skew) or np.isnan(kurt):
        return "UNKNOWN"

    # Skewness label
    abs_skew = abs(skew)
    if abs_skew < 0.5:
        sk_label = "symmetric"
    elif abs_skew < 1.0:
        direction = "right" if skew > 0 else "left"
        sk_label = f"moderately {direction}-skewed"
    else:
        direction = "right" if skew > 0 else "left"
        sk_label = f"highly {direction}-skewed"

    # Kurtosis label
    if kurt > 1.0:
        kt_label = "leptokurtic (heavy tails)"
    elif kurt < -1.0:
        kt_label = "platykurtic (light tails)"
    else:
        kt_label = "mesokurtic (normal tails)"

    return f"{sk_label}, {kt_label}"


def _compute_stats(series: pd.Series, col_name: str, group_label: str = "") -> dict:
    """
    Compute the full descriptive statistics dictionary for a numeric Series.

    Returns a flat dict ready to be appended to a list for pd.DataFrame().
    """
    clean = series.dropna()
    n = len(clean)

    if n == 0:
        return {
            "group": group_label,
            "variable": col_name,
            "n": 0,
            "n_missing": len(series),
            "mean": np.nan, "median": np.nan,
            "variance": np.nan, "std_dev": np.nan,
            "skewness": np.nan, "kurtosis_excess": np.nan,
            "min": np.nan, "max": np.nan, "range": np.nan,
            "iqr": np.nan,
            "p05": np.nan, "p10": np.nan, "p25": np.nan,
            "p50": np.nan, "p75": np.nan, "p90": np.nan, "p95": np.nan,
            "cv_pct": np.nan,
            "shapiro_W": np.nan, "shapiro_p": np.nan,
            "shapiro_result": "INSUFFICIENT_DATA",
            "distribution_shape": "UNKNOWN",
        }

    q = clean.quantile(PERCENTILES).values  # [p05, p10, p25, p50, p75, p90, p95]
    mean_val = float(clean.mean())
    std_val = float(clean.std(ddof=1))      # sample std dev (ddof=1)
    var_val = float(clean.var(ddof=1))      # sample variance (ddof=1)
    skew_val = float(clean.skew())          # Fisher-Pearson skewness (pandas default)
    kurt_val = float(clean.kurtosis())      # Excess kurtosis, Fisher def (pandas default)
    iqr_val = float(q[4] - q[2])           # p75 - p25
    cv_pct = (std_val / mean_val * 100) if mean_val != 0 else np.nan

    sw_w, sw_p, sw_result = _shapiro(clean)

    return {
        "group": group_label,
        "variable": col_name,
        "n": n,
        "n_missing": int(series.isna().sum()),
        "mean": round(mean_val, 6),
        "median": round(float(clean.median()), 6),
        "variance": round(var_val, 6),
        "std_dev": round(std_val, 6),
        "skewness": round(skew_val, 6),
        "kurtosis_excess": round(kurt_val, 6),
        "min": round(float(clean.min()), 6),
        "max": round(float(clean.max()), 6),
        "range": round(float(clean.max() - clean.min()), 6),
        "iqr": round(iqr_val, 6),
        "p05": round(float(q[0]), 6),
        "p10": round(float(q[1]), 6),
        "p25": round(float(q[2]), 6),
        "p50": round(float(q[3]), 6),
        "p75": round(float(q[4]), 6),
        "p90": round(float(q[5]), 6),
        "p95": round(float(q[6]), 6),
        "cv_pct": round(cv_pct, 4) if not np.isnan(cv_pct) else np.nan,
        "shapiro_W": round(sw_w, 6) if not np.isnan(sw_w) else np.nan,
        "shapiro_p": round(sw_p, 8) if not np.isnan(sw_p) else np.nan,
        "shapiro_result": sw_result,
        "distribution_shape": _shape_label(skew_val, kurt_val),
    }


# ---------------------------------------------------------------------------
# Domain 1 — Sensor Readings
# ---------------------------------------------------------------------------

SENSOR_NUMERIC_COLS = ["value", "r_derated", "arrhenius_factor", "health_score"]

def analyse_sensor_readings(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Load sensor_readings joined to sensors and components.
    Compute stats for each numeric column:
      (a) fleet-wide (all components, all types)
      (b) stratified by sensor_type
      (c) stratified by component_name
    Returns a DataFrame with one row per (group, variable) combination.
    """
    print("\n[1/3] Loading sensor_readings ...")
    query = """
        SELECT
            sr.value,
            sr.r_derated,
            sr.arrhenius_factor,
            sr.health_score,
            s.sensor_type,
            c.component_name
        FROM sensor_readings sr
        JOIN sensors        s  ON sr.sensor_id    = s.sensor_id
        JOIN components     c  ON sr.component_id = c.component_id
    """
    df = pd.read_sql_query(query, conn)
    print(f"    Loaded {len(df):,} rows, columns: {list(df.columns)}")

    rows = []

    # (a) Fleet-wide stats
    for col in SENSOR_NUMERIC_COLS:
        rows.append(_compute_stats(df[col], col, group_label="FLEET_ALL"))

    # (b) Stratified by sensor_type
    for stype, grp in df.groupby("sensor_type", sort=True):
        for col in SENSOR_NUMERIC_COLS:
            rows.append(_compute_stats(grp[col], col, group_label=f"sensor_type={stype}"))

    # (c) Stratified by component_name
    for comp, grp in df.groupby("component_name", sort=True):
        for col in SENSOR_NUMERIC_COLS:
            rows.append(_compute_stats(grp[col], col, group_label=f"component={comp}"))

    result = pd.DataFrame(rows)
    print(f"    -> {len(result)} stat rows produced")
    return result


# ---------------------------------------------------------------------------
# Domain 2 — Production Counts
# ---------------------------------------------------------------------------

PRODUCTION_NUMERIC_COLS = [
    "total_units", "good_units", "defective_units", "rework_units",
    "ideal_cycle_time_min", "first_pass_yield"
]

def analyse_production_counts(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Load production_counts joined to components and production_shifts.
    Derives first_pass_yield = good_units / total_units (Quality factor).
    Computes stats:
      (a) fleet-wide
      (b) stratified by component_name
      (c) stratified by shift_label
    Returns a DataFrame with one row per (group, variable) combination.
    """
    print("\n[2/3] Loading production_counts ...")
    query = """
        SELECT
            pc.total_units,
            pc.good_units,
            pc.defective_units,
            pc.rework_units,
            pc.ideal_cycle_time_min,
            CAST(pc.good_units AS FLOAT) / NULLIF(pc.total_units, 0) AS first_pass_yield,
            c.component_name,
            ps.shift_label
        FROM production_counts pc
        JOIN components        c  ON pc.component_id = c.component_id
        JOIN production_shifts ps ON pc.shift_id     = ps.shift_id
    """
    df = pd.read_sql_query(query, conn)
    print(f"    Loaded {len(df):,} rows, columns: {list(df.columns)}")

    rows = []

    # (a) Fleet-wide
    for col in PRODUCTION_NUMERIC_COLS:
        rows.append(_compute_stats(df[col], col, group_label="FLEET_ALL"))

    # (b) Stratified by component_name
    for comp, grp in df.groupby("component_name", sort=True):
        for col in PRODUCTION_NUMERIC_COLS:
            rows.append(_compute_stats(grp[col], col, group_label=f"component={comp}"))

    # (c) Stratified by shift_label
    for slabel, grp in df.groupby("shift_label", sort=True):
        for col in PRODUCTION_NUMERIC_COLS:
            rows.append(_compute_stats(grp[col], col, group_label=f"shift={slabel}"))

    result = pd.DataFrame(rows)
    print(f"    -> {len(result)} stat rows produced")
    return result


# ---------------------------------------------------------------------------
# Domain 3 — Downtime Durations
# ---------------------------------------------------------------------------

def analyse_downtime_durations(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Load downtime_events joined to components.
    Computes stats for duration_min:
      (a) fleet-wide (all categories)
      (b) stratified by downtime_category
      (c) stratified by component_name
      (d) cross-stratified by (component_name, downtime_category)
    Returns a DataFrame with one row per (group, variable) combination.
    """
    print("\n[3/3] Loading downtime_events ...")
    query = """
        SELECT
            de.duration_min,
            de.downtime_category,
            c.component_name
        FROM downtime_events de
        JOIN components      c  ON de.component_id = c.component_id
    """
    df = pd.read_sql_query(query, conn)
    print(f"    Loaded {len(df):,} rows, columns: {list(df.columns)}")

    rows = []

    # (a) Fleet-wide
    rows.append(_compute_stats(df["duration_min"], "duration_min", group_label="FLEET_ALL"))

    # (b) Stratified by downtime_category
    for cat, grp in df.groupby("downtime_category", sort=True):
        rows.append(_compute_stats(grp["duration_min"], "duration_min",
                                   group_label=f"category={cat}"))

    # (c) Stratified by component_name
    for comp, grp in df.groupby("component_name", sort=True):
        rows.append(_compute_stats(grp["duration_min"], "duration_min",
                                   group_label=f"component={comp}"))

    # (d) Cross-stratified (component × category)
    for (comp, cat), grp in df.groupby(["component_name", "downtime_category"], sort=True):
        rows.append(_compute_stats(grp["duration_min"], "duration_min",
                                   group_label=f"component={comp}|category={cat}"))

    result = pd.DataFrame(rows)
    print(f"    -> {len(result)} stat rows produced")
    return result


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def _fmt_row(row: pd.Series, width: int = 72) -> str:
    """Format a single stats row as a readable block."""
    lines = [
        f"  Group    : {row['group']}",
        f"  Variable : {row['variable']}",
        f"  n={row['n']:,}  missing={row['n_missing']}",
        (f"  Mean={row['mean']:.4f}  Median={row['median']:.4f}  "
         f"StdDev={row['std_dev']:.4f}  Variance={row['variance']:.4f}"),
        (f"  Skewness={row['skewness']:.4f}  "
         f"ExKurtosis={row['kurtosis_excess']:.4f}  "
         f"CV%={row['cv_pct']:.2f}"),
        (f"  Min={row['min']:.4f}  P05={row['p05']:.4f}  "
         f"P25={row['p25']:.4f}  P50={row['p50']:.4f}  "
         f"P75={row['p75']:.4f}  P95={row['p95']:.4f}  Max={row['max']:.4f}"),
        f"  IQR={row['iqr']:.4f}  Range={row['range']:.4f}",
        (f"  Shapiro-Wilk: W={row['shapiro_W']:.4f}  "
         f"p={row['shapiro_p']:.6f}  → {row['shapiro_result']}"),
        f"  Shape: {row['distribution_shape']}",
    ]
    return "\n".join(lines)


def write_full_report(
    sensor_df: pd.DataFrame,
    production_df: pd.DataFrame,
    downtime_df: pd.DataFrame,
    out_path: Path,
) -> None:
    """Write a human-readable text mirror of all three stat DataFrames."""
    sections = [
        ("SENSOR READINGS — Descriptive Statistics", sensor_df),
        ("PRODUCTION COUNTS — Descriptive Statistics", production_df),
        ("DOWNTIME DURATIONS — Descriptive Statistics", downtime_df),
    ]
    sep = "=" * 72

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(f"EDA FULL REPORT — Manufacturing & Industrial Analytics FYP\n")
        fh.write(f"Day 14 — Phase 1.4 Python EDA\n")
        fh.write(f"Database: {DB_PATH}\n")
        fh.write(f"Percentiles computed: {[int(p*100) for p in PERCENTILES]}\n\n")

        for title, df in sections:
            fh.write(f"\n{sep}\n{title}\n{sep}\n")
            for _, row in df.iterrows():
                fh.write(f"\n{'─'*72}\n")
                fh.write(_fmt_row(row) + "\n")

    print(f"\n  [DONE] Full report written -> {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("EDA Summary Statistics — Day 14, Phase 1.4")
    print(f"Database : {DB_PATH.resolve()}")
    print(f"Output   : {OUT_DIR.resolve()}")
    print("=" * 72)

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. "
            "Run run_etl_pipeline() first (see python/etl.py)."
        )

    conn = _connect(DB_PATH)

    try:
        # --- Domain 1: Sensor Readings ---
        sensor_stats = analyse_sensor_readings(conn)
        sensor_csv = OUT_DIR / "eda_sensor_stats.csv"
        sensor_stats.to_csv(sensor_csv, index=False)
        print(f"  [OK] Saved -> {sensor_csv}")

        # --- Domain 2: Production Counts ---
        production_stats = analyse_production_counts(conn)
        production_csv = OUT_DIR / "eda_production_stats.csv"
        production_stats.to_csv(production_csv, index=False)
        print(f"  [OK] Saved -> {production_csv}")

        # --- Domain 3: Downtime Durations ---
        downtime_stats = analyse_downtime_durations(conn)
        downtime_csv = OUT_DIR / "eda_downtime_stats.csv"
        downtime_stats.to_csv(downtime_csv, index=False)
        print(f"  [OK] Saved -> {downtime_csv}")

        # --- Full text report ---
        report_path = OUT_DIR / "eda_full_report.txt"
        write_full_report(sensor_stats, production_stats, downtime_stats, report_path)

        # --- Print top-level summary to console ---
        print("\n" + "=" * 72)
        print("FLEET-LEVEL HIGHLIGHTS")
        print("=" * 72)

        def _highlights(df: pd.DataFrame, domain: str) -> None:
            fleet = df[df["group"] == "FLEET_ALL"].copy()
            if fleet.empty:
                return
            print(f"\n  [{domain}]")
            for _, row in fleet.iterrows():
                print(
                    f"    {row['variable']:30s}"
                    f"  mean={row['mean']:>10.4f}"
                    f"  median={row['median']:>10.4f}"
                    f"  std={row['std_dev']:>10.4f}"
                    f"  skew={row['skewness']:>7.3f}"
                    f"  kurt={row['kurtosis_excess']:>7.3f}"
                    f"  -> {row['distribution_shape']}"
                )

        _highlights(sensor_stats,     "Sensor Readings")
        _highlights(production_stats,  "Production Counts")
        _highlights(downtime_stats,    "Downtime Durations")

        print("\n" + "=" * 72)
        print("EDA COMPLETE — all outputs written to data/processed/")
        print("=" * 72)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
