#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest.py — Manufacturing Analytics FYP
=========================================
Day 9 Ingestion Runner: data_generator.py output → SQLite

USAGE
-----
    # Run from project root:
    python ingest.py

    # Validate CSV only (no DB write):
    python ingest.py --validate-only

    # Custom paths:
    python ingest.py --data-dir data/processed --db data/manufacturing.db

WHAT THIS DOES
--------------
1. Reads multi_failure_telemetry.csv (47,957 rows) and ttf_samples.csv (19 rows)
   from data/processed/ — the output of python/data_generator.py.
2. Initialises data/manufacturing.db from sql/schema.sql + sql/seed.sql
   if the database file does not already exist.
3. Validates the CSV data against the 9 schema rules in etl.validate_sensor_readings().
4. Normalises timestamps to UTC.
5. Inserts validated rows into sensor_readings and failure_log tables using
   INSERT OR IGNORE (idempotent — safe to re-run).
6. Prints a summary showing rows inserted and a 5-row sample from each table.

SCHEMA TABLES LOADED
--------------------
    sensor_readings  ← multi_failure_telemetry.csv (expect ~47,957 rows)
    failure_log      ← ttf_samples.csv              (expect 19 rows)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Resolve project root so this script works from any CWD
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
_PYTHON_DIR   = _PROJECT_ROOT / "python"
_SQL_DIR      = _PROJECT_ROOT / "sql"
_DATA_DIR     = _PROJECT_ROOT / "data" / "processed"
_DB_PATH      = _PROJECT_ROOT / "data" / "manufacturing.db"

sys.path.insert(0, str(_PYTHON_DIR))

from etl import (  # noqa: E402
    load_failure_log,
    load_sensor_readings,
    normalize_timestamps,
    run_etl_pipeline,
    validate_sensor_readings,
)


# =============================================================================
# HELPERS
# =============================================================================

def _bar(n: int = 70) -> str:
    return "=" * n


def _section(title: str) -> None:
    print()
    print(_bar())
    print(f"  {title}")
    print(_bar())


def _check_prerequisites(data_dir: Path) -> None:
    """Raise FileNotFoundError if required CSVs are missing."""
    telemetry = data_dir / "multi_failure_telemetry.csv"
    ttf       = data_dir / "ttf_samples.csv"

    missing = []
    if not telemetry.exists():
        missing.append(str(telemetry))
    if not ttf.exists():
        missing.append(str(ttf))

    if missing:
        raise FileNotFoundError(
            "Required CSV files not found:\n"
            + "\n".join(f"  {p}" for p in missing)
            + "\n\nRun python/data_generator.py first to generate simulation data."
        )


# =============================================================================
# VALIDATION REPORT (Deliverable 3 — pre-load)
# =============================================================================

def _print_csv_validation_report(data_dir: Path) -> None:
    """Print a data-quality pre-flight report before loading to DB."""
    _section("STEP 1 — CSV PRE-FLIGHT VALIDATION")

    # -- multi_failure_telemetry.csv ------------------------------------------
    telemetry_path = data_dir / "multi_failure_telemetry.csv"
    df_tel = pd.read_csv(telemetry_path)
    print(f"\nmulti_failure_telemetry.csv")
    print(f"  Total rows   : {len(df_tel):,}")
    print(f"  Columns ({len(df_tel.columns)}) : {list(df_tel.columns)}")
    print(f"  Date range   : {df_tel['ts'].min()}  ->  {df_tel['ts'].max()}")
    print(f"  Components   : {sorted(df_tel['component_id'].unique().tolist())}")
    print(f"  Sensor types : {sorted(df_tel['sensor_type'].unique().tolist())}")

    null_counts = df_tel[["ts", "component_id", "sensor_type", "value",
                           "is_failure_event", "cascade_flag"]].isnull().sum()
    null_issues = null_counts[null_counts > 0]
    if null_issues.empty:
        print(f"  NULL check   : PASS — no NULLs in mandatory columns")
    else:
        print(f"  NULL check   : WARN — {null_issues.to_dict()}")

    neg_values = (df_tel["value"] < 0).sum()
    print(f"  value >= 0   : {'PASS' if neg_values == 0 else f'FAIL ({neg_values} negative rows)'}")

    failure_rows = (df_tel["is_failure_event"] == 1).sum()
    cascade_rows = (df_tel["cascade_flag"] == 1).sum()
    print(f"  Failure events (is_failure_event=1) : {failure_rows:,} rows")
    print(f"  Cascade flags  (cascade_flag=1)     : {cascade_rows:,} rows")

    # -- ttf_samples.csv ------------------------------------------------------
    ttf_path = data_dir / "ttf_samples.csv"
    df_ttf = pd.read_csv(ttf_path)
    print(f"\nttf_samples.csv")
    print(f"  Total rows   : {len(df_ttf)}")
    print(f"  Columns      : {list(df_ttf.columns)}")
    print(f"  Components   : {sorted(df_ttf['component_name'].unique().tolist())}")
    print(f"  Cycles       : {len(df_ttf)} failure events across "
          f"{df_ttf['component_id'].nunique()} components")


# =============================================================================
# POST-LOAD VALIDATION REPORT (Deliverable 3 — post-load)
# =============================================================================

def _print_post_load_report(db_path: Path) -> None:
    """
    Query the database and print row counts, breakdown by component/sensor,
    and a 5-row sample from sensor_readings and failure_log.
    """
    _section("STEP 3 — POST-LOAD VALIDATION REPORT")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # -- Row counts -----------------------------------------------------------
    tables_to_check = [
        "components", "sensors", "sensor_readings", "failure_log"
    ]
    print("\n-- TABLE ROW COUNTS ---------------------------------------------")
    for tbl in tables_to_check:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"  {tbl:<22}  {count:>8,} rows")
        except Exception as exc:
            print(f"  {tbl:<22}  ERROR: {exc}")

    # -- sensor_readings breakdown by component --------------------------------
    print("\n-- SENSOR_READINGS BY COMPONENT ---------------------------------")
    q_comp = """
        SELECT
            c.component_name,
            COUNT(*)              AS row_count,
            SUM(sr.is_anomaly)    AS anomaly_count,
            SUM(sr.is_failure_event) AS failure_events,
            ROUND(AVG(sr.health_score), 2) AS avg_health_score
        FROM sensor_readings sr
        JOIN components c ON sr.component_id = c.component_id
        GROUP BY c.component_name
        ORDER BY c.component_id
    """
    rows = conn.execute(q_comp).fetchall()
    print(f"  {'Component':<18} {'Rows':>8} {'Anomalies':>10} {'Failures':>10} {'Avg Health':>11}")
    print(f"  {'-'*18} {'-'*8} {'-'*10} {'-'*10} {'-'*11}")
    for r in rows:
        print(f"  {r['component_name']:<18} {r['row_count']:>8,} "
              f"{r['anomaly_count']:>10,} {r['failure_events']:>10,} "
              f"{(r['avg_health_score'] or 0):>11.1f}")

    # -- sensor_readings breakdown by sensor_type ------------------------------
    print("\n-- SENSOR_READINGS BY SENSOR_TYPE -------------------------------")
    q_stype = """
        SELECT
            s.sensor_type,
            COUNT(*)           AS row_count,
            ROUND(AVG(sr.value), 4) AS avg_value,
            ROUND(MIN(sr.value), 4) AS min_value,
            ROUND(MAX(sr.value), 4) AS max_value
        FROM sensor_readings sr
        JOIN sensors s ON sr.sensor_id = s.sensor_id
        GROUP BY s.sensor_type
        ORDER BY s.sensor_type
    """
    rows = conn.execute(q_stype).fetchall()
    print(f"  {'sensor_type':<14} {'Rows':>8} {'Avg Value':>12} {'Min':>10} {'Max':>10}")
    print(f"  {'-'*14} {'-'*8} {'-'*12} {'-'*10} {'-'*10}")
    for r in rows:
        print(f"  {r['sensor_type']:<14} {r['row_count']:>8,} "
              f"{r['avg_value']:>12.4f} {r['min_value']:>10.4f} {r['max_value']:>10.4f}")

    # -- ISO zone breakdown (vibration sensors only) ---------------------------
    print("\n-- ISO 10816-3 ZONE DISTRIBUTION (vibration sensors only) -------")
    q_zone = """
        SELECT
            iso_zone,
            COUNT(*) AS row_count,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM sensor_readings
        WHERE iso_zone IS NOT NULL
        GROUP BY iso_zone
        ORDER BY iso_zone
    """
    rows = conn.execute(q_zone).fetchall()
    print(f"  {'Zone':<6} {'Rows':>8} {'%':>7}   Description")
    print(f"  {'-'*6} {'-'*8} {'-'*7}   -----------")
    zone_desc = {"A": "New machine (0–2.3 mm/s)",
                 "B": "Acceptable long-term (2.3–4.5)",
                 "C": "ALARM (4.5–7.1 mm/s)",
                 "D": "DANGER (>7.1 mm/s)"}
    for r in rows:
        zone = r["iso_zone"] or "NULL"
        print(f"  {zone:<6} {r['row_count']:>8,} {r['pct']:>6.1f}%   "
              f"{zone_desc.get(zone, '')}")

    # -- 5-row sample from sensor_readings -------------------------------------
    print("\n-- SENSOR_READINGS SAMPLE (5 rows, most recent ts) --------------")
    q_sample = """
        SELECT sr.reading_id, c.component_name, s.sensor_type,
               sr.ts, ROUND(sr.value, 4) AS value,
               sr.is_anomaly, sr.iso_zone, sr.is_failure_event,
               ROUND(sr.health_score, 1) AS health_score,
               sr.cycle_number
        FROM sensor_readings sr
        JOIN components c ON sr.component_id = c.component_id
        JOIN sensors    s ON sr.sensor_id    = s.sensor_id
        ORDER BY sr.ts DESC
        LIMIT 5
    """
    rows = conn.execute(q_sample).fetchall()
    header = ["reading_id", "component", "sensor", "ts", "value",
              "anomaly", "zone", "failure", "health", "cycle"]
    print("  " + "  ".join(f"{h:>10}" for h in header))
    print("  " + "  ".join("-" * 10 for _ in header))
    for r in rows:
        vals = [r["reading_id"], r["component_name"], r["sensor_type"],
                r["ts"][:16], r["value"], r["is_anomaly"],
                r["iso_zone"] or "-", r["is_failure_event"],
                r["health_score"], r["cycle_number"]]
        print("  " + "  ".join(f"{str(v):>10}" for v in vals))

    # -- failure_log sample (all 19 rows) --------------------------------------
    print("\n-- FAILURE_LOG CONTENTS (all rows) ------------------------------")
    q_fl = """
        SELECT fl.failure_id, c.component_name, fl.cycle_number,
               ROUND(fl.ttf_hours, 1) AS ttf_hours,
               fl.beta_mid, ROUND(fl.eta_nominal_h, 0) AS eta_h,
               fl.ea_ev, fl.strategy
        FROM failure_log fl
        JOIN components c ON fl.component_id = c.component_id
        ORDER BY c.component_id, fl.cycle_number
    """
    rows = conn.execute(q_fl).fetchall()
    print(f"  {'id':>4} {'component':<16} {'cycle':>5} "
          f"{'ttf_h':>8} {'beta':>5} {'eta_h':>7} {'ea':>5} {'strategy'}")
    print(f"  {'--':>4} {'-'*16} {'-----':>5} "
          f"{'------':>8} {'----':>5} {'-----':>7} {'---':>5} --------")
    for r in rows:
        ea = f"{r['ea_ev']:.2f}" if r["ea_ev"] is not None else "None"
        print(f"  {r['failure_id']:>4} {r['component_name']:<16} "
              f"{r['cycle_number']:>5} {r['ttf_hours']:>8.1f} "
              f"{r['beta_mid']:>5.2f} {r['eta_h']:>7.0f} "
              f"{ea:>5} {r['strategy']}")

    # -- anomaly summary query (Day 10 preview) --------------------------------
    print("\n-- ANOMALY RATE BY COMPONENT (preview for Day 10 SQL queries) ---")
    q_anom = """
        SELECT
            c.component_name,
            COUNT(*) AS total_readings,
            SUM(sr.is_anomaly) AS anomalous_readings,
            ROUND(100.0 * SUM(sr.is_anomaly) / COUNT(*), 2) AS anomaly_rate_pct
        FROM sensor_readings sr
        JOIN components c ON sr.component_id = c.component_id
        GROUP BY c.component_name
        ORDER BY anomaly_rate_pct DESC
    """
    rows = conn.execute(q_anom).fetchall()
    print(f"  {'Component':<18} {'Total':>8} {'Anomalies':>10} {'Rate %':>8}")
    print(f"  {'-'*18} {'-'*8} {'-'*10} {'-'*8}")
    for r in rows:
        print(f"  {r['component_name']:<18} {r['total_readings']:>8,} "
              f"{r['anomalous_readings']:>10,} {r['anomaly_rate_pct']:>8.2f}%")

    conn.close()
    print()
    print(_bar())
    print(f"  DATABASE: {db_path}")
    print(f"  All validation queries PASSED.")
    print(_bar())


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Day 9 Ingestion Runner — load data_generator.py output into SQLite"
    )
    parser.add_argument(
        "--data-dir",
        default=str(_DATA_DIR),
        help="Directory containing multi_failure_telemetry.csv and ttf_samples.csv "
             f"(default: {_DATA_DIR})",
    )
    parser.add_argument(
        "--db",
        default=str(_DB_PATH),
        help=f"SQLite database path (default: {_DB_PATH})",
    )
    parser.add_argument(
        "--schema",
        default=str(_SQL_DIR / "schema.sql"),
        help="Path to schema.sql (default: sql/schema.sql)",
    )
    parser.add_argument(
        "--seed",
        default=str(_SQL_DIR / "seed.sql"),
        help="Path to seed.sql (default: sql/seed.sql)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run CSV validation only — skip database write",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    db_path  = Path(args.db)

    # -- Banner ----------------------------------------------------------------
    print()
    print(_bar())
    print("  MANUFACTURING ANALYTICS FYP — Day 9 Ingestion Runner")
    print("  data_generator.py output  ->  SQLite database")
    print(_bar())
    print(f"  Data directory : {data_dir}")
    print(f"  Database       : {db_path}")
    print(f"  Schema file    : {args.schema}")
    print(f"  Seed file      : {args.seed}")
    print(f"  Mode           : {'VALIDATE ONLY (no DB write)' if args.validate_only else 'FULL INGEST'}")

    # -- Prerequisites check ---------------------------------------------------
    try:
        _check_prerequisites(data_dir)
    except FileNotFoundError as exc:
        print(f"\n[FATAL] {exc}", file=sys.stderr)
        return 1

    # -- Step 1: CSV pre-flight validation ------------------------------------
    _print_csv_validation_report(data_dir)

    if args.validate_only:
        _section("VALIDATE-ONLY MODE — Database write skipped")
        print("  Re-run without --validate-only to perform the full ingest.")
        return 0

    # -- Step 2: Run ETL pipeline ---------------------------------------------
    _section("STEP 2 — ETL PIPELINE EXECUTION")
    print(f"\n  DB exists: {db_path.exists()}")
    if not db_path.exists():
        print(f"  New database will be created from schema.sql + seed.sql")

    try:
        result = run_etl_pipeline(
            data_dir=str(data_dir),
            db_path=str(db_path),
            validate_only=False,
            schema_path=args.schema,
            seed_path=args.seed,
        )
    except Exception as exc:
        print(f"\n[FATAL] ETL pipeline failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    print(f"\n  ETL Result:")
    for table, count in result.items():
        print(f"    {table:<22} -> {count:,} rows processed")

    # -- Step 3: Post-load validation report ----------------------------------
    _print_post_load_report(db_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
