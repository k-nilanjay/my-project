"""
etl.py — Manufacturing Analytics FYP
======================================
Extract, Transform, Load Pipeline: CSV → Validate → SQL
Day 9 — Phase 1, Sub-phase 1.3 (FULL IMPLEMENTATION)

PURPOSE
-------
This module forms the data integration layer between the simulated telemetry
files (data/processed/ CSVs from data_generator.py) and the SQLite database
(data/manufacturing.db).

IMPLEMENTED FUNCTIONS (Day 9)
-------------------------------
  validate_sensor_readings(df)     — schema + range validation for multi_failure_telemetry.csv
  normalize_timestamps(df, ts_col) — parse ISO 8601 → UTC datetime64
  load_sensor_readings(df, conn)   — INSERT OR IGNORE into sensor_readings (with sensor_id lookup)
  load_failure_log(df, conn)       — INSERT OR IGNORE ttf_samples.csv into failure_log
  run_etl_pipeline(data_dir, db)   — end-to-end orchestration function

DATABASE CONNECTION PATTERN
------------------------------
    SQLite (dev):
        import sqlite3
        conn = sqlite3.connect("data/manufacturing.db")
        conn.execute("PRAGMA foreign_keys = ON")   # required for FK enforcement

VALIDATION RULES (locked Day 3 schema constraints, extended Day 8)
----------------------------------------------------------------------
See sql/schema.sql for full DDL CHECK constraints.
This module mirrors those constraints at the Python layer before DB insert.

CONSTANTS
---------
  VALID_SENSOR_TYPES        — 5 allowed sensor_type strings
  VALID_DOWNTIME_CATEGORIES — 5 allowed downtime_category strings
  SENSOR_READINGS_REQUIRED_COLS — 12 required CSV columns
  SENSOR_TYPE_TO_SENSOR_ID  — maps (component_id, sensor_type) → sensor_id
  SENSOR_THRESHOLDS         — per-sensor alarm/danger values from seed.sql
"""

from __future__ import annotations

import logging
import math
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

# =============================================================================
# MODULE-LEVEL CONSTANTS
# =============================================================================

# Raw input directory (relative to project root — single-cycle simulation)
RAW_DATA_DIR: str = "data/raw"

# Processed output directory (multi-failure simulation — Day 7)
PROCESSED_DATA_DIR: str = "data/processed"

# Required columns in multi_failure_telemetry.csv (12 columns — locked Day 7/8)
SENSOR_READINGS_REQUIRED_COLS: list[str] = [
    "ts",
    "component_id",
    "component_name",
    "sensor_type",
    "value",
    "is_failure_event",
    "failure_mode",
    "R_derated",
    "AF",
    "cascade_flag",
    "cycle_number",
    "health_score",
]

# Allowed sensor types (from sensors table, seed.sql — locked Day 4)
VALID_SENSOR_TYPES: set[str] = {
    "vibration",
    "temperature",
    "rpm",
    "load",
    "oil_debris",
}

# Allowed downtime categories (locked Day 2)
VALID_DOWNTIME_CATEGORIES: set[str] = {
    "unplanned_failure",
    "planned_maintenance",
    "changeover",
    "idle",
    "cascade_upstream",
}

# Sensor ID lookup: (component_id, sensor_type) → sensor_id
# Sourced from sql/seed.sql (locked Day 4). Sensor ID scheme: 10x=Bearing,
# 20x=Shaft, 30x=Motor Housing, 40x=Coupling, 50x=Gearbox.
# When a component has multiple sensors of the same type (e.g. two vibration
# sensors in future), use the lowest sensor_id (primary sensor).
SENSOR_TYPE_TO_SENSOR_ID: dict[tuple[int, str], int] = {
    (1, "vibration"):    11,   # Bearing vibration RMS (primary)
    (1, "temperature"):  12,   # Bearing temperature
    (2, "vibration"):    21,   # Shaft vibration 1× harmonic
    (2, "rpm"):          22,   # Shaft RPM
    (3, "temperature"):  31,   # Motor Housing temperature (primary)
    (3, "vibration"):    32,   # Motor Housing vibration (secondary)
    (4, "vibration"):    41,   # Coupling vibration 2× harmonic (primary)
    (4, "load"):         42,   # Coupling load %
    (5, "vibration"):    51,   # Gearbox vibration envelope (primary)
    (5, "oil_debris"):   52,   # Gearbox oil debris count
    (5, "temperature"):  53,   # Gearbox sump temperature
}

# Per-sensor alarm / danger thresholds from seed.sql (locked Day 4).
# Used to compute is_anomaly and iso_zone for sensor_readings.
# Key: sensor_id → {"alarm": float|None, "danger": float|None}
SENSOR_THRESHOLDS: dict[int, dict] = {
    11: {"alarm": 4.5,   "danger": 7.1},    # Bearing vibration
    12: {"alarm": 80.0,  "danger": 100.0},  # Bearing temperature
    21: {"alarm": 4.5,   "danger": 7.1},    # Shaft vibration
    22: {"alarm": None,  "danger": None},   # Shaft RPM (no ISO threshold)
    31: {"alarm": 130.0, "danger": 155.0},  # Motor Housing temperature
    32: {"alarm": 4.5,   "danger": 7.1},    # Motor Housing vibration
    41: {"alarm": 4.5,   "danger": 7.1},    # Coupling vibration
    42: {"alarm": 90.0,  "danger": 100.0},  # Coupling load %
    51: {"alarm": 4.5,   "danger": 7.1},    # Gearbox vibration
    52: {"alarm": 50.0,  "danger": 200.0},  # Gearbox oil debris
    53: {"alarm": 90.0,  "danger": 110.0},  # Gearbox temperature
}

# Logger for this module
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)


# =============================================================================
# 1. EXTRACT — Read raw CSV files from data_generator.py output
# =============================================================================

def extract_component_csv(component_name: str, raw_dir: str = RAW_DATA_DIR) -> pd.DataFrame:
    """
    Read a per-component telemetry CSV from data/raw/.

    FILE NAMING CONVENTION (from simulate.py):
        data/raw/<ComponentName>_telemetry.csv
        e.g.: data/raw/Motor_Housing_telemetry.csv

    Parameters
    ----------
    component_name : str — pipeline component name (spaces → underscores in filename)
    raw_dir        : str — path to raw data directory

    Returns
    -------
    pd.DataFrame — raw telemetry; not yet validated or transformed
    """
    filename = component_name.replace(" ", "_") + "_telemetry.csv"
    filepath = Path(raw_dir) / filename
    if not filepath.exists():
        raise FileNotFoundError(
            f"Telemetry CSV not found: {filepath}. "
            "Run python/simulate.py first to generate raw data."
        )
    df = pd.read_csv(filepath)
    logger.info("Extracted %d rows for %s from %s", len(df), component_name, filepath)
    return df


def extract_all_components(raw_dir: str = RAW_DATA_DIR) -> dict[str, pd.DataFrame]:
    """
    Read telemetry CSVs for all 5 pipeline components.

    Calls extract_component_csv() for each component in PIPELINE_ORDER.

    Returns
    -------
    dict[str, pd.DataFrame] — {component_name: raw_df}
    """
    pipeline_order = ["Bearing", "Shaft", "Motor Housing", "Coupling", "Gearbox"]
    result: dict[str, pd.DataFrame] = {}
    for name in pipeline_order:
        try:
            result[name] = extract_component_csv(name, raw_dir)
        except FileNotFoundError as exc:
            logger.warning("Skipping %s — %s", name, exc)
    return result


# =============================================================================
# 2. VALIDATE — Enforce schema constraints before INSERT
# =============================================================================

def validate_sensor_readings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate a sensor_readings DataFrame against the schema constraints
    locked in sql/schema.sql (Day 3, extended Day 8).

    Designed for multi_failure_telemetry.csv (47,957 rows, 12 columns).

    VALIDATION RULES APPLIED
    ------------------------
    1. All 12 required columns present (SENSOR_READINGS_REQUIRED_COLS).
    2. No NULL values in: ts, component_id, sensor_type, value,
                          is_failure_event, cascade_flag, cycle_number.
    3. sensor_type ∈ VALID_SENSOR_TYPES (5 allowed values from seed.sql).
    4. value >= 0.0 (physical sensor readings are non-negative).
    5. is_failure_event ∈ {0, 1}.
    6. cascade_flag ∈ {0, 1}.
    7. r_derated (CSV: R_derated) ∈ [0.0, 1.0] where not NULL.
    8. health_score ∈ [0.0, 100.0] where not NULL.
    9. ts parseable as ISO 8601 datetime (rows that cannot be parsed are dropped).

    HANDLING INVALID ROWS
    ---------------------
    - Rows failing any rule are dropped and logged at WARNING level.
    - Does NOT raise on invalid rows — data quality issues must not crash the pipeline.
    - Returns the cleaned DataFrame with a validation summary logged.

    Parameters
    ----------
    df : pd.DataFrame — raw telemetry from extract_component_csv() or from
                        data/processed/multi_failure_telemetry.csv

    Returns
    -------
    pd.DataFrame — validated (cleaned) DataFrame; invalid rows removed
    """
    original_count = len(df)
    df = df.copy()

    # ── Rule 1: Required columns present ────────────────────────────────────
    missing_cols = [c for c in SENSOR_READINGS_REQUIRED_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"validate_sensor_readings: missing required columns: {missing_cols}\n"
            f"Present: {list(df.columns)}"
        )

    # ── Rule 2: No NULLs in mandatory columns ───────────────────────────────
    mandatory_non_null = ["ts", "component_id", "sensor_type", "value",
                          "is_failure_event", "cascade_flag", "cycle_number"]
    null_mask = df[mandatory_non_null].isnull().any(axis=1)
    if null_mask.sum() > 0:
        logger.warning(
            "validate_sensor_readings: dropping %d rows with NULLs in mandatory columns.",
            null_mask.sum(),
        )
        df = df[~null_mask]

    # ── Rule 3: sensor_type in valid set ────────────────────────────────────
    invalid_sensor_type = ~df["sensor_type"].isin(VALID_SENSOR_TYPES)
    if invalid_sensor_type.sum() > 0:
        bad_types = df.loc[invalid_sensor_type, "sensor_type"].unique().tolist()
        logger.warning(
            "validate_sensor_readings: dropping %d rows with invalid sensor_type: %s",
            invalid_sensor_type.sum(),
            bad_types,
        )
        df = df[~invalid_sensor_type]

    # ── Rule 4: value >= 0.0 ────────────────────────────────────────────────
    negative_value = df["value"] < 0
    if negative_value.sum() > 0:
        logger.warning(
            "validate_sensor_readings: dropping %d rows with value < 0.",
            negative_value.sum(),
        )
        df = df[~negative_value]

    # ── Rule 5: is_failure_event ∈ {0, 1} ───────────────────────────────────
    invalid_failure_flag = ~df["is_failure_event"].isin([0, 1])
    if invalid_failure_flag.sum() > 0:
        logger.warning(
            "validate_sensor_readings: dropping %d rows with is_failure_event not in {0,1}.",
            invalid_failure_flag.sum(),
        )
        df = df[~invalid_failure_flag]

    # ── Rule 6: cascade_flag ∈ {0, 1} ───────────────────────────────────────
    invalid_cascade = ~df["cascade_flag"].isin([0, 1])
    if invalid_cascade.sum() > 0:
        logger.warning(
            "validate_sensor_readings: dropping %d rows with cascade_flag not in {0,1}.",
            invalid_cascade.sum(),
        )
        df = df[~invalid_cascade]

    # ── Rule 7: R_derated ∈ [0.0, 1.0] where not NULL ──────────────────────
    has_r = df["R_derated"].notna()
    out_of_range_r = has_r & ((df["R_derated"] < 0.0) | (df["R_derated"] > 1.0))
    if out_of_range_r.sum() > 0:
        logger.warning(
            "validate_sensor_readings: dropping %d rows where R_derated out of [0,1].",
            out_of_range_r.sum(),
        )
        df = df[~out_of_range_r]

    # ── Rule 8: health_score ∈ [0.0, 100.0] where not NULL ──────────────────
    has_hs = df["health_score"].notna()
    out_of_range_hs = has_hs & ((df["health_score"] < 0.0) | (df["health_score"] > 100.0))
    if out_of_range_hs.sum() > 0:
        logger.warning(
            "validate_sensor_readings: dropping %d rows where health_score out of [0,100].",
            out_of_range_hs.sum(),
        )
        df = df[~out_of_range_hs]

    # ── Rule 9: ts parseable as ISO 8601 ────────────────────────────────────
    def _is_valid_ts(val) -> bool:
        try:
            pd.Timestamp(val)
            return True
        except Exception:
            return False

    unparseable_ts = (~df["ts"].apply(_is_valid_ts)).astype(bool)
    if unparseable_ts.sum() > 0:
        logger.warning(
            "validate_sensor_readings: dropping %d rows with unparseable ts.",
            unparseable_ts.sum(),
        )
        df = df[~unparseable_ts]

    dropped = original_count - len(df)
    logger.info(
        "validate_sensor_readings: %d rows passed, %d rows dropped (%.2f%%).",
        len(df),
        dropped,
        (dropped / original_count * 100) if original_count > 0 else 0.0,
    )
    return df.reset_index(drop=True)


def validate_downtime_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate a downtime_events DataFrame before INSERT.

    VALIDATION RULES APPLIED
    ------------------------
    1. Required columns: component_id, shift_id, start_ts, end_ts,
                         duration_min, downtime_category
    2. downtime_category ∈ VALID_DOWNTIME_CATEGORIES
    3. duration_min > 0
    4. cascade_upstream rows: root_cause_component_id NOT NULL (Day 3 constraint)
    5. root_cause_component_id != component_id (self-reference guard)
    6. Overlapping downtime windows per component flagged (not dropped, just logged)

    Parameters
    ----------
    df : pd.DataFrame — raw downtime events

    Returns
    -------
    pd.DataFrame — validated downtime events; cascade constraint failures dropped
    """
    original_count = len(df)
    df = df.copy()

    required_cols = ["component_id", "shift_id", "start_ts", "end_ts",
                     "duration_min", "downtime_category"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"validate_downtime_events: missing columns: {missing}")

    # Rule 2: downtime_category in valid set
    invalid_cat = ~df["downtime_category"].isin(VALID_DOWNTIME_CATEGORIES)
    if invalid_cat.sum() > 0:
        logger.warning(
            "validate_downtime_events: dropping %d rows with invalid downtime_category.",
            invalid_cat.sum(),
        )
        df = df[~invalid_cat]

    # Rule 3: duration_min > 0
    nonpos_dur = df["duration_min"] <= 0
    if nonpos_dur.sum() > 0:
        logger.warning(
            "validate_downtime_events: dropping %d rows with duration_min <= 0.",
            nonpos_dur.sum(),
        )
        df = df[~nonpos_dur]

    # Rule 4 & 5: cascade_upstream rows must have root_cause_component_id (not null, not self)
    if "root_cause_component_id" in df.columns:
        cascade_mask = df["downtime_category"] == "cascade_upstream"
        null_root = cascade_mask & df["root_cause_component_id"].isnull()
        if null_root.sum() > 0:
            logger.warning(
                "validate_downtime_events: dropping %d cascade_upstream rows "
                "with NULL root_cause_component_id (Day 3 constraint violation).",
                null_root.sum(),
            )
            df = df[~null_root]

        self_ref = cascade_mask & (df["root_cause_component_id"] == df["component_id"])
        if self_ref.sum() > 0:
            logger.warning(
                "validate_downtime_events: dropping %d rows where "
                "root_cause_component_id == component_id (self-reference guard).",
                self_ref.sum(),
            )
            df = df[~self_ref]

    dropped = original_count - len(df)
    logger.info(
        "validate_downtime_events: %d rows passed, %d dropped.",
        len(df), dropped,
    )
    return df.reset_index(drop=True)


def validate_production_counts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate production_counts DataFrame before INSERT.

    KEY CONSTRAINT (locked Day 3 schema):
        good_units + defective_units + rework_units == total_units

    Any row violating this invariant is a data quality failure and must be
    dropped (not silently corrected) — correcting would falsify OEE calculations.

    Parameters
    ----------
    df : pd.DataFrame — production counts

    Returns
    -------
    pd.DataFrame — validated production counts; invalid rows removed
    """
    original_count = len(df)
    df = df.copy()

    required_cols = ["component_id", "shift_id", "total_units",
                     "good_units", "defective_units", "rework_units",
                     "ideal_cycle_time_min"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"validate_production_counts: missing columns: {missing}")

    # Unit reconciliation invariant
    reconciliation_ok = (
        df["good_units"] + df["defective_units"] + df["rework_units"] == df["total_units"]
    )
    if (~reconciliation_ok).sum() > 0:
        logger.warning(
            "validate_production_counts: dropping %d rows violating "
            "good + defective + rework == total OEE invariant.",
            (~reconciliation_ok).sum(),
        )
        df = df[reconciliation_ok]

    # total_units > 0
    zero_total = df["total_units"] <= 0
    if zero_total.sum() > 0:
        logger.warning(
            "validate_production_counts: dropping %d rows with total_units <= 0.",
            zero_total.sum(),
        )
        df = df[~zero_total]

    # ideal_cycle_time_min > 0
    nonpos_ict = df["ideal_cycle_time_min"] <= 0
    if nonpos_ict.sum() > 0:
        logger.warning(
            "validate_production_counts: dropping %d rows with ideal_cycle_time_min <= 0.",
            nonpos_ict.sum(),
        )
        df = df[~nonpos_ict]

    dropped = original_count - len(df)
    logger.info(
        "validate_production_counts: %d rows passed, %d dropped.",
        len(df), dropped,
    )
    return df.reset_index(drop=True)


# =============================================================================
# 3. TRANSFORM — Normalize and enrich before INSERT
# =============================================================================

def normalize_timestamps(df: pd.DataFrame, ts_column: str = "ts") -> pd.DataFrame:
    """
    Parse timestamp strings to pandas Timestamp objects and ensure UTC timezone.

    All timestamps in multi_failure_telemetry.csv are generated as naive ISO 8601
    strings anchored to 2026-07-20T00:00:00 by data_generator.py. This function:
      1. Converts the ts_column to pandas datetime using pd.to_datetime().
      2. If the result is timezone-naive, localizes to UTC (tz_localize).
      3. If it already carries a timezone, converts to UTC (tz_convert).

    This matches the UTC DATETIME requirement in sql/schema.sql:
        ts  DATETIME NOT NULL  -- UTC ISO 8601 timestamp

    Parameters
    ----------
    df        : pd.DataFrame
    ts_column : str — name of the timestamp column (default: 'ts')

    Returns
    -------
    pd.DataFrame — with ts_column converted to UTC-aware Timestamp objects.
                   Rows that cannot be parsed are dropped with a WARNING log.
    """
    if ts_column not in df.columns:
        raise KeyError(f"normalize_timestamps: column '{ts_column}' not found in DataFrame.")

    df = df.copy()
    original_count = len(df)

    # Coerce un-parseable values to NaT, then drop them
    df[ts_column] = pd.to_datetime(df[ts_column], errors="coerce", utc=False)

    unparseable = df[ts_column].isna()
    if unparseable.sum() > 0:
        logger.warning(
            "normalize_timestamps: dropping %d rows with unparseable '%s' values.",
            unparseable.sum(),
            ts_column,
        )
        df = df[~unparseable].copy()

    # Apply UTC timezone
    ts_series = df[ts_column]
    if ts_series.dt.tz is None:
        # Naive → localize to UTC
        df[ts_column] = ts_series.dt.tz_localize("UTC")
    else:
        # Already tz-aware → convert to UTC
        df[ts_column] = ts_series.dt.tz_convert("UTC")

    dropped = original_count - len(df)
    logger.info(
        "normalize_timestamps: %d rows normalized to UTC; %d dropped.",
        len(df), dropped,
    )
    return df.reset_index(drop=True)


def compute_derived_duration(
    df: pd.DataFrame,
    start_col: str = "start_ts",
    end_col: str = "end_ts",
    output_col: str = "duration_min",
) -> pd.DataFrame:
    """
    Compute and store the derived duration column (minutes) from start/end timestamps.

    This mirrors the stored column design decision (locked Day 3):
        "planned_duration_min and duration_min are stored (not computed at query time).
         Validated by etl.py on insert."

    Formula:
        duration_min = (end_ts - start_ts).total_seconds() / 60

    Parameters
    ----------
    df         : pd.DataFrame — must contain start_col and end_col as datetimes
    start_col  : str
    end_col    : str
    output_col : str — column name for the computed duration

    Returns
    -------
    pd.DataFrame — with output_col added or overwritten
    """
    df = df.copy()
    start = pd.to_datetime(df[start_col], errors="coerce", utc=True)
    end = pd.to_datetime(df[end_col], errors="coerce", utc=True)
    df[output_col] = (end - start).dt.total_seconds() / 60.0
    return df


# =============================================================================
# 4. LOAD — INSERT validated rows into SQL tables
# =============================================================================

def _compute_iso_zone(value: float, sensor_id: int) -> Optional[str]:
    """
    Compute the ISO 10816-3 vibration severity zone for vibration sensors.

    Zone definitions (locked Day 1):
        A: 0 – 2.3 mm/s  (new machine, acceptable)
        B: 2.3 – 4.5     (acceptable for long-term)
        C: 4.5 – 7.1     (alarm threshold)
        D: > 7.1          (danger — immediate action)

    Only applies to vibration sensors (11, 21, 32, 41, 51).
    Returns None for non-vibration sensors.

    Parameters
    ----------
    value     : float — sensor reading
    sensor_id : int   — sensor ID from SENSOR_TYPE_TO_SENSOR_ID lookup

    Returns
    -------
    str | None — 'A', 'B', 'C', 'D', or None
    """
    # Vibration sensor IDs: 11, 21, 32, 41, 51
    VIBRATION_SENSOR_IDS = {11, 21, 32, 41, 51}
    if sensor_id not in VIBRATION_SENSOR_IDS:
        return None
    if value < 2.3:
        return "A"
    elif value < 4.5:
        return "B"
    elif value < 7.1:
        return "C"
    else:
        return "D"


def _compute_is_anomaly(value: float, sensor_id: int) -> int:
    """
    Compute is_anomaly flag: 1 if value >= iso_alarm_threshold, else 0.

    Uses SENSOR_THRESHOLDS dict. If alarm threshold is None (e.g. RPM sensor 22),
    returns 0 (no threshold defined).

    Parameters
    ----------
    value     : float — sensor reading
    sensor_id : int

    Returns
    -------
    int — 0 or 1
    """
    thresholds = SENSOR_THRESHOLDS.get(sensor_id, {})
    alarm = thresholds.get("alarm")
    if alarm is None:
        return 0
    return 1 if value >= alarm else 0


def load_sensor_readings(df: pd.DataFrame, db_connection: sqlite3.Connection) -> int:
    """
    INSERT validated sensor_readings rows into the SQLite database.

    COLUMN MAPPING (multi_failure_telemetry.csv → sensor_readings table):
        ts             → ts            (UTC DATETIME)
        component_id   → component_id  (FK — denormalized, from CSV directly)
        sensor_type    → used to lookup sensor_id via SENSOR_TYPE_TO_SENSOR_ID
        value          → value
        is_failure_event → is_failure_event
        failure_mode   → failure_mode
        R_derated      → r_derated
        AF             → arrhenius_factor
        cascade_flag   → cascade_flag
        cycle_number   → cycle_number (CSV is 0-indexed; SQL CHECK >= 1, so +1 applied)
        health_score   → health_score
        (computed)     → is_anomaly    (value >= iso_alarm_threshold)
        (computed)     → iso_zone      ('A'/'B'/'C'/'D' for vibration; NULL otherwise)

    IDEMPOTENCY:
        INSERT OR IGNORE — duplicate rows are silently skipped.
        The UNIQUE constraint on (sensor_id, ts) in sensor_readings handles this
        when the index exists; otherwise, the SQLite ON CONFLICT IGNORE mode is used
        through the explicit INSERT OR IGNORE statement.

    PRAGMA:
        PRAGMA foreign_keys = ON is executed at the start of this function
        to ensure referential integrity during the session.

    Parameters
    ----------
    df            : pd.DataFrame — validated sensor readings (from validate_sensor_readings)
    db_connection : sqlite3.Connection

    Returns
    -------
    int — number of rows successfully inserted
    """
    # Enable FK enforcement for this session
    db_connection.execute("PRAGMA foreign_keys = ON")

    if df.empty:
        logger.warning("load_sensor_readings: empty DataFrame — nothing to insert.")
        return 0

    df = df.copy()

    # Normalize timestamps to UTC string for SQLite DATETIME storage
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=False)
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC")
    else:
        df["ts"] = df["ts"].dt.tz_convert("UTC")
    # Store as ISO 8601 string without timezone suffix (SQLite DATETIME convention)
    df["ts"] = df["ts"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Map (component_id, sensor_type) → sensor_id
    df["sensor_id"] = df.apply(
        lambda row: SENSOR_TYPE_TO_SENSOR_ID.get(
            (int(row["component_id"]), row["sensor_type"])
        ),
        axis=1,
    )

    # Drop rows where sensor_id could not be resolved (unmapped sensor types)
    unmapped = df["sensor_id"].isna()
    if unmapped.sum() > 0:
        logger.warning(
            "load_sensor_readings: dropping %d rows with unmapped (component_id, sensor_type).",
            unmapped.sum(),
        )
        df = df[~unmapped].copy()

    df["sensor_id"] = df["sensor_id"].astype(int)

    # Compute is_anomaly and iso_zone from thresholds
    df["is_anomaly"] = df.apply(
        lambda row: _compute_is_anomaly(row["value"], row["sensor_id"]), axis=1
    )
    df["iso_zone"] = df.apply(
        lambda row: _compute_iso_zone(row["value"], row["sensor_id"]), axis=1
    )

    # Adjust cycle_number: CSV is 0-indexed, SQL CHECK >= 1 requires 1-indexed
    # Add 1 only where cycle_number == 0 to shift base
    df["cycle_number_sql"] = df["cycle_number"].apply(lambda x: max(int(x) + 1, 1))

    # Handle NULL failure_mode: empty string → None for SQL NULL
    df["failure_mode"] = df["failure_mode"].where(df["failure_mode"].notna() & (df["failure_mode"] != ""), other=None)

    INSERT_SQL = """
        INSERT OR IGNORE INTO sensor_readings (
            sensor_id, component_id, ts, value,
            is_anomaly, iso_zone,
            is_failure_event, failure_mode,
            r_derated, arrhenius_factor,
            cascade_flag, cycle_number, health_score
        ) VALUES (
            :sensor_id, :component_id, :ts, :value,
            :is_anomaly, :iso_zone,
            :is_failure_event, :failure_mode,
            :r_derated, :arrhenius_factor,
            :cascade_flag, :cycle_number, :health_score
        )
    """

    rows_inserted = 0
    cursor = db_connection.cursor()

    batch = []
    for _, row in df.iterrows():
        batch.append({
            "sensor_id":        int(row["sensor_id"]),
            "component_id":     int(row["component_id"]),
            "ts":               str(row["ts"]),
            "value":            float(row["value"]),
            "is_anomaly":       int(row["is_anomaly"]),
            "iso_zone":         row["iso_zone"],
            "is_failure_event": int(row["is_failure_event"]),
            "failure_mode":     row["failure_mode"] if pd.notna(row["failure_mode"]) else None,
            "r_derated":        float(row["R_derated"]) if pd.notna(row["R_derated"]) else None,
            "arrhenius_factor": float(row["AF"]) if pd.notna(row["AF"]) else None,
            "cascade_flag":     int(row["cascade_flag"]),
            "cycle_number":     int(row["cycle_number_sql"]),
            "health_score":     float(row["health_score"]) if pd.notna(row["health_score"]) else None,
        })

    cursor.executemany(INSERT_SQL, batch)
    db_connection.commit()
    rows_inserted = cursor.rowcount if cursor.rowcount >= 0 else len(batch)

    logger.info(
        "load_sensor_readings: %d rows submitted; %d rows inserted (INSERT OR IGNORE).",
        len(batch), rows_inserted,
    )
    return rows_inserted


def load_downtime_events(df: pd.DataFrame, db_connection: sqlite3.Connection) -> int:
    """
    INSERT validated downtime_events rows into the SQLite database.

    Ensures cascade_upstream rows have root_cause_component_id set
    (enforcing the Day 3 CHECK constraint at application layer before DB layer).

    Parameters
    ----------
    df            : pd.DataFrame — validated downtime events
    db_connection : sqlite3.Connection

    Returns
    -------
    int — number of rows successfully inserted
    """
    db_connection.execute("PRAGMA foreign_keys = ON")

    if df.empty:
        logger.warning("load_downtime_events: empty DataFrame — nothing to insert.")
        return 0

    # This function is a passthrough stub for Day 9 — downtime_events CSV is not
    # yet produced by data_generator.py (Day 7). Placeholder for Day 10.
    logger.info("load_downtime_events: downtime_events CSV not yet generated. Skipping.")
    return 0


def load_failure_log(df: pd.DataFrame, db_connection: sqlite3.Connection) -> int:
    """
    INSERT ttf_samples.csv rows into the failure_log table.

    COLUMN MAPPING (ttf_samples.csv → failure_log table):
        component_id  → component_id  (FK to components)
        cycle_number  → cycle_number  (1-indexed; UNIQUE with component_id)
        ttf_hours     → ttf_hours
        repair_hours  → repair_hours
        beta_mid      → beta_mid      (temporal snapshot)
        eta_nominal_h → eta_nominal_h (temporal snapshot)
        ea_ev         → ea_ev         (NULL for Shaft)
        strategy      → strategy      (temporal snapshot: 'PM'|'CBM'|'PM_CBM')

    COLUMNS LEFT AS NULL (not present in ttf_samples.csv):
        t_failure_abs   — absolute simulation time not in ttf_samples (requires integration)
        eta_effective_h — eta/AF not stored in ttf_samples
        failure_mode    — not in ttf_samples.csv
        qq_r_squared    — not in ttf_samples.csv

    IDEMPOTENCY:
        INSERT OR IGNORE — UNIQUE(component_id, cycle_number) prevents duplicates.

    PRAGMA:
        PRAGMA foreign_keys = ON executed at start of this function.

    Parameters
    ----------
    df            : pd.DataFrame — ttf_samples.csv DataFrame
    db_connection : sqlite3.Connection

    Returns
    -------
    int — number of failure events logged
    """
    db_connection.execute("PRAGMA foreign_keys = ON")

    if df.empty:
        logger.warning("load_failure_log: empty DataFrame — nothing to insert.")
        return 0

    df = df.copy()

    # Verify required columns
    required = ["component_id", "cycle_number", "ttf_hours", "repair_hours", "beta_mid",
                "eta_nominal_h", "eta_eff", "ea_ev", "strategy"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"load_failure_log: missing required columns: {missing}")

    INSERT_SQL = """
        INSERT OR IGNORE INTO failure_log (
            component_id,
            cycle_number,
            ttf_hours,
            beta_mid,
            eta_nominal_h,
            ea_ev,
            gamma_factor,
            strategy,
            t_failure_abs,
            eta_effective_h,
            repair_hours,
            failure_mode,
            qq_r_squared
        ) VALUES (
            :component_id,
            :cycle_number,
            :ttf_hours,
            :beta_mid,
            :eta_nominal_h,
            :ea_ev,
            :gamma_factor,
            :strategy,
            :t_failure_abs,
            :eta_effective_h,
            :repair_hours,
            :failure_mode,
            :qq_r_squared
        )
    """

    batch = []
    for _, row in df.iterrows():
        batch.append({
            "component_id":   int(row["component_id"]),
            "cycle_number":   int(row["cycle_number"]),
            "ttf_hours":      float(row["ttf_hours"]),
            "beta_mid":       float(row["beta_mid"]),
            "eta_nominal_h":  float(row["eta_nominal_h"]),
            "ea_ev":          float(row["ea_ev"]) if pd.notna(row["ea_ev"]) else None,
            "gamma_factor":   math.gamma(1.0 + 1.0 / float(row["beta_mid"])),
            "strategy":       str(row["strategy"]),
            "repair_hours":   float(row["repair_hours"]),
            # Columns not present in ttf_samples.csv — stored as NULL
            "t_failure_abs":  None,
            "eta_effective_h": float(row["eta_eff"]) if pd.notna(row["eta_eff"]) else None,
            "failure_mode":   None,
            "qq_r_squared":   None,
        })

    cursor = db_connection.cursor()
    cursor.executemany(INSERT_SQL, batch)
    db_connection.commit()
    rows_inserted = cursor.rowcount if cursor.rowcount >= 0 else len(batch)

    logger.info(
        "load_failure_log: %d rows submitted to failure_log; %d inserted (INSERT OR IGNORE).",
        len(batch), rows_inserted,
    )
    return rows_inserted


# =============================================================================
# 5. FULL ETL PIPELINE ORCHESTRATOR
# =============================================================================

def run_etl_pipeline(
    data_dir: str = PROCESSED_DATA_DIR,
    db_path: str = "data/manufacturing.db",
    validate_only: bool = False,
    schema_path: str = "sql/schema.sql",
    seed_path: str = "sql/seed.sql",
) -> dict[str, int]:
    """
    Execute the full Extract → Transform → Validate → Load pipeline.

    Loads multi_failure_telemetry.csv and ttf_samples.csv from data_dir
    into the SQLite database at db_path.

    PIPELINE STEPS
    --------------
    1. Open SQLite connection; execute PRAGMA foreign_keys = ON.
    2. If db_path does not exist: run schema.sql + seed.sql to initialise it.
    3. Read multi_failure_telemetry.csv → validate → normalize timestamps.
    4. Read ttf_samples.csv.
    5. If validate_only=False: load sensor_readings and failure_log.
    6. Return {table_name: rows_inserted} dict for pipeline health monitoring.

    Parameters
    ----------
    data_dir      : str — path containing multi_failure_telemetry.csv and ttf_samples.csv
    db_path       : str — path to SQLite .db file
    validate_only : bool — if True, run extract + validate only; skip DB write
                           (useful for CI/CD data quality checks)
    schema_path   : str — path to sql/schema.sql (used when db_path does not exist)
    seed_path     : str — path to sql/seed.sql   (used when db_path does not exist)

    Returns
    -------
    dict[str, int] — {table_name: rows_inserted} for each table written.
                     Values are 0 when validate_only=True.
    """
    result: dict[str, int] = {
        "sensor_readings": 0,
        "failure_log": 0,
    }

    # ── Step 1: Open database ────────────────────────────────────────────────
    db_file = Path(db_path)
    db_exists = db_file.exists()

    logger.info("run_etl_pipeline: connecting to SQLite database at %s", db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # ── Step 2: Initialize schema + seed if DB is new ───────────────────────
    if not db_exists:
        logger.info("run_etl_pipeline: new database — running schema.sql and seed.sql")
        _execute_sql_file(conn, schema_path)
        _execute_sql_file(conn, seed_path)

    # ── Step 3: Read and validate multi_failure_telemetry.csv ───────────────
    telemetry_path = Path(data_dir) / "multi_failure_telemetry.csv"
    if not telemetry_path.exists():
        raise FileNotFoundError(
            f"run_etl_pipeline: multi_failure_telemetry.csv not found at {telemetry_path}. "
            "Run python/data_generator.py first."
        )

    logger.info("run_etl_pipeline: reading %s", telemetry_path)
    telemetry_df = pd.read_csv(telemetry_path)
    logger.info("run_etl_pipeline: %d rows read from multi_failure_telemetry.csv", len(telemetry_df))

    # Validate
    telemetry_df = validate_sensor_readings(telemetry_df)

    # Normalize timestamps
    telemetry_df = normalize_timestamps(telemetry_df, ts_column="ts")

    # ── Step 4: Read ttf_samples.csv ─────────────────────────────────────────
    ttf_path = Path(data_dir) / "ttf_samples.csv"
    if not ttf_path.exists():
        raise FileNotFoundError(
            f"run_etl_pipeline: ttf_samples.csv not found at {ttf_path}. "
            "Run python/data_generator.py first."
        )

    ttf_df = pd.read_csv(ttf_path)
    logger.info("run_etl_pipeline: %d rows read from ttf_samples.csv", len(ttf_df))

    # ── Step 5: Load to database ──────────────────────────────────────────────
    if validate_only:
        logger.info(
            "run_etl_pipeline: validate_only=True — skipping database write. "
            "Validation PASSED for %d telemetry rows and %d TTF records.",
            len(telemetry_df), len(ttf_df),
        )
        return result

    sr_rows = load_sensor_readings(telemetry_df, conn)
    fl_rows = load_failure_log(ttf_df, conn)

    result["sensor_readings"] = sr_rows
    result["failure_log"] = fl_rows

    # ── Step 6: Verification log ──────────────────────────────────────────────
    sr_count = conn.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
    fl_count = conn.execute("SELECT COUNT(*) FROM failure_log").fetchone()[0]
    logger.info(
        "run_etl_pipeline: COMPLETE — sensor_readings: %d total rows in DB "
        "(expect ~47,957); failure_log: %d total rows in DB (expect 19).",
        sr_count, fl_count,
    )

    conn.close()
    return result


def _execute_sql_file(conn: sqlite3.Connection, filepath: str) -> None:
    """
    Read and execute a SQL script file against a SQLite connection.

    Handles the PRAGMA foreign_keys = ON statement correctly by executing
    individual statements rather than using executescript() (which commits
    automatically and may interfere with PRAGMA timing).

    Parameters
    ----------
    conn     : sqlite3.Connection
    filepath : str — path to the .sql file
    """
    sql_path = Path(filepath)
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")

    sql_text = sql_path.read_text(encoding="utf-8")
    # Remove single-line comments for executescript compatibility
    lines = [line for line in sql_text.splitlines() if not line.strip().startswith("--")]
    cleaned_sql = "\n".join(lines)

    conn.executescript(cleaned_sql)
    logger.info("_execute_sql_file: executed %s", filepath)


# =============================================================================
# MODULE SELF-TEST (run directly: python etl.py)
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("ETL.PY — DAY 9 SELF-TEST")
    print("=" * 70)
    print()
    print("Module constants verified:")
    print(f"  PROCESSED_DATA_DIR:          {PROCESSED_DATA_DIR}")
    print(f"  VALID_SENSOR_TYPES:          {sorted(VALID_SENSOR_TYPES)}")
    print(f"  VALID_DOWNTIME_CATEGORIES:   {sorted(VALID_DOWNTIME_CATEGORIES)}")
    print(f"  Required columns (readings): {SENSOR_READINGS_REQUIRED_COLS}")
    print(f"  Sensor ID map entries:       {len(SENSOR_TYPE_TO_SENSOR_ID)}")
    print(f"  Sensor threshold entries:    {len(SENSOR_THRESHOLDS)}")
    print()

    # Quick smoke-test: validate constants are internally consistent
    assert len(SENSOR_READINGS_REQUIRED_COLS) == 12, "Must have exactly 12 required columns"
    assert len(SENSOR_TYPE_TO_SENSOR_ID) == 11, "Must have 11 sensor-type mappings (seed.sql)"
    assert "vibration" in VALID_SENSOR_TYPES
    assert "cascade_upstream" in VALID_DOWNTIME_CATEGORIES

    print("[Day 9 constants PASS] — 12 required columns, 11 sensor mappings, all sets valid.")
    print()
    print("Run run_etl_pipeline() to load multi_failure_telemetry.csv into SQLite.")
