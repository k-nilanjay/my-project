#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_schema.py — Manufacturing & Industrial Analytics FYP
=============================================================
Telemetry CSV Schema Validator (Day 9 implementation)

PURPOSE
-------
Check incoming telemetry CSVs from data/raw/ against the expanded
SENSOR_READINGS_REQUIRED_COLS list defined in python/etl.py.

Catches data quality issues *before* they reach the SQL INSERT layer,
providing fast feedback during development and CI/CD runs.

VALIDATION RULES APPLIED
------------------------
1.  Required columns present   — checks for all 12 SENSOR_READINGS_REQUIRED_COLS
2.  No NULL values in critical  — ts, component_id, sensor_type, value,
    non-nullable columns          is_failure_event, cascade_flag, cycle_number
3.  value >= 0                  — physical sensor readings are non-negative
4.  is_failure_event IN {0, 1}  — binary flag
5.  cascade_flag IN {0, 1}      — binary flag
6.  cycle_number >= 1           — 1-indexed (matches schema.sql CHECK >= 1)
7.  sensor_type IN VALID_TYPES  — guards against typos
8.  health_score IN [0, 100]    — when not null
9.  R_derated IN [0.0, 1.0]     — when not null
10. arrhenius_factor > 0        — when not null

USAGE
-----
    # Validate a single CSV
    python data/validate_schema.py data/raw/Bearing_telemetry.csv

    # Validate all CSVs in a directory
    python data/validate_schema.py data/raw/

    # Validate a specific CSV and a directory
    python data/validate_schema.py data/raw/Bearing_telemetry.csv data/processed/

EXIT CODES
----------
    0 — all files passed (or WARN only)
    1 — one or more files FAILED validation
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import List, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Import the authoritative required-columns list from etl.py
# ---------------------------------------------------------------------------
# Resolve the project root (two levels up from data/) to make the import work
# regardless of the working directory from which this script is called.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "python"))

try:
    from etl import SENSOR_READINGS_REQUIRED_COLS, VALID_SENSOR_TYPES
except ImportError:
    # Fallback: define inline if etl.py is not importable (e.g. missing deps)
    SENSOR_READINGS_REQUIRED_COLS: list[str] = [
        "ts",
        "component_id",
        "component_name",
        "sensor_type",
        "value",
        "is_failure_event",
        "failure_mode",
        # Day 8 columns
        "R_derated",
        "arrhenius_factor",
        "cascade_flag",
        "cycle_number",
        "health_score",
    ]
    VALID_SENSOR_TYPES: set[str] = {
        "vibration", "temperature", "rpm", "load", "oil_debris",
    }

# Columns that must never be NULL in a valid row
_NON_NULLABLE_COLS: list[str] = [
    "ts",
    "component_id",
    "sensor_type",
    "value",
    "is_failure_event",
    "cascade_flag",
    "cycle_number",
]


# =============================================================================
# RESULT CLASSES
# =============================================================================

class ValidationResult:
    """Aggregates all issues found in a single CSV file."""

    def __init__(self, filepath: str) -> None:
        self.filepath   = filepath
        self.errors:  List[str] = []   # FAIL-level issues
        self.warnings: List[str] = []  # WARN-level issues
        self.row_count: int = 0

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    @property
    def status(self) -> str:
        if self.errors:
            return "FAIL"
        if self.warnings:
            return "WARN"
        return "PASS"

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def __str__(self) -> str:
        lines = [
            f"{'=' * 72}",
            f"File    : {self.filepath}",
            f"Rows    : {self.row_count}",
            f"Status  : {self.status}",
        ]
        if self.errors:
            lines.append(f"Errors  : {len(self.errors)}")
            for e in self.errors:
                lines.append(f"  [ERROR] {e}")
        if self.warnings:
            lines.append(f"Warnings: {len(self.warnings)}")
            for w in self.warnings:
                lines.append(f"  [WARN]  {w}")
        if self.passed and not self.warnings:
            lines.append("  All checks passed.")
        lines.append(f"{'=' * 72}")
        return "\n".join(lines)


# =============================================================================
# VALIDATION LOGIC
# =============================================================================

def validate_csv(filepath: str) -> ValidationResult:
    """
    Validate a single telemetry CSV file.

    Parameters
    ----------
    filepath : str — path to the CSV file to validate

    Returns
    -------
    ValidationResult — aggregated errors and warnings
    """
    result = ValidationResult(filepath)

    # ── Load CSV ─────────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(filepath, low_memory=False)
    except FileNotFoundError:
        result.add_error(f"File not found: {filepath}")
        return result
    except Exception as exc:
        result.add_error(f"Failed to read CSV: {exc}")
        return result

    result.row_count = len(df)

    if result.row_count == 0:
        result.add_error("CSV is empty (0 data rows).")
        return result

    # ── Rule 1: Required columns present ─────────────────────────────────────
    present_cols   = set(df.columns)
    missing_cols   = [c for c in SENSOR_READINGS_REQUIRED_COLS if c not in present_cols]
    if missing_cols:
        result.add_error(
            f"Missing required columns ({len(missing_cols)}): {missing_cols}"
        )
        # Cannot safely apply column-level checks if columns are absent
        return result

    # ── Rule 2: No NULLs in non-nullable columns ──────────────────────────────
    for col in _NON_NULLABLE_COLS:
        if col not in df.columns:
            continue   # already caught above; skip to avoid KeyError
        null_count = df[col].isna().sum()
        if null_count > 0:
            result.add_error(
                f"Column '{col}': {null_count} NULL values (must be non-nullable)."
            )

    # ── Rule 3: value >= 0 ───────────────────────────────────────────────────
    if "value" in df.columns:
        neg_count = (pd.to_numeric(df["value"], errors="coerce") < 0).sum()
        if neg_count > 0:
            result.add_error(
                f"Column 'value': {neg_count} rows with negative values (must be >= 0)."
            )

    # ── Rule 4: is_failure_event IN {0, 1} ───────────────────────────────────
    if "is_failure_event" in df.columns:
        invalid = ~df["is_failure_event"].isin([0, 1])
        if invalid.any():
            result.add_error(
                f"Column 'is_failure_event': {invalid.sum()} rows outside {{0, 1}}."
            )

    # ── Rule 5: cascade_flag IN {0, 1} ───────────────────────────────────────
    if "cascade_flag" in df.columns:
        invalid = ~df["cascade_flag"].isin([0, 1])
        if invalid.any():
            result.add_error(
                f"Column 'cascade_flag': {invalid.sum()} rows outside {{0, 1}}."
            )

    # ── Rule 6: cycle_number >= 1 (1-indexed) ────────────────────────────────
    if "cycle_number" in df.columns:
        cycle_vals = pd.to_numeric(df["cycle_number"], errors="coerce")
        invalid_count = (cycle_vals < 1).sum() + cycle_vals.isna().sum()
        if invalid_count > 0:
            result.add_error(
                f"Column 'cycle_number': {invalid_count} rows with value < 1 "
                f"(must be 1-indexed, >= 1). "
                f"Min observed: {cycle_vals.min()}"
            )

    # ── Rule 7: sensor_type validity ─────────────────────────────────────────
    if "sensor_type" in df.columns:
        invalid_types = df.loc[~df["sensor_type"].isin(VALID_SENSOR_TYPES), "sensor_type"]
        if not invalid_types.empty:
            bad_unique = invalid_types.dropna().unique().tolist()
            result.add_error(
                f"Column 'sensor_type': {len(invalid_types)} rows with invalid types: "
                f"{bad_unique}. Expected: {sorted(VALID_SENSOR_TYPES)}"
            )

    # ── Rule 8: health_score IN [0.0, 100.0] ─────────────────────────────────
    if "health_score" in df.columns:
        hs = pd.to_numeric(df["health_score"], errors="coerce")
        non_null_hs = hs.dropna()
        if not non_null_hs.empty:
            out_of_range = ((non_null_hs < 0.0) | (non_null_hs > 100.0)).sum()
            if out_of_range > 0:
                result.add_error(
                    f"Column 'health_score': {out_of_range} rows outside [0.0, 100.0]."
                )
        null_hs = hs.isna().sum()
        if null_hs > 0:
            result.add_warning(
                f"Column 'health_score': {null_hs} NULL values "
                f"(expected when include_health_score=False)."
            )

    # ── Rule 9: R_derated IN [0.0, 1.0] ─────────────────────────────────────
    if "R_derated" in df.columns:
        rd = pd.to_numeric(df["R_derated"], errors="coerce")
        non_null_rd = rd.dropna()
        if not non_null_rd.empty:
            out_of_range = ((non_null_rd < 0.0) | (non_null_rd > 1.0)).sum()
            if out_of_range > 0:
                result.add_error(
                    f"Column 'R_derated': {out_of_range} rows outside [0.0, 1.0]."
                )

    # ── Rule 10: arrhenius_factor > 0 ────────────────────────────────────────
    if "arrhenius_factor" in df.columns:
        af = pd.to_numeric(df["arrhenius_factor"], errors="coerce")
        non_null_af = af.dropna()
        if not non_null_af.empty:
            invalid_af = (non_null_af <= 0).sum()
            if invalid_af > 0:
                result.add_error(
                    f"Column 'arrhenius_factor': {invalid_af} rows with value <= 0 "
                    f"(AF must be > 0 by Arrhenius model definition)."
                )

    return result


# =============================================================================
# BATCH VALIDATION
# =============================================================================

def validate_paths(paths: List[str]) -> Tuple[List[ValidationResult], int, int]:
    """
    Validate all CSV files found at the given paths.

    Paths may be individual CSV files or directories (non-recursive).

    Parameters
    ----------
    paths : list of str — file paths or directory paths to scan

    Returns
    -------
    Tuple of (results_list, total_pass, total_fail)
    """
    csv_files: List[Path] = []

    for p_str in paths:
        p = Path(p_str)
        if p.is_dir():
            csv_files.extend(sorted(p.glob("*.csv")))
        elif p.is_file() and p.suffix.lower() == ".csv":
            csv_files.append(p)
        else:
            print(f"[SKIP] Not a CSV file or directory: {p_str}", file=sys.stderr)

    if not csv_files:
        print("[WARN] No CSV files found to validate.", file=sys.stderr)
        return [], 0, 0

    results: List[ValidationResult] = []
    n_pass, n_fail = 0, 0

    for csv_path in csv_files:
        result = validate_csv(str(csv_path))
        results.append(result)
        if result.passed:
            n_pass += 1
        else:
            n_fail += 1

    return results, n_pass, n_fail


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main() -> int:
    """
    CLI entry point. Accepts one or more file/directory paths as arguments.
    Returns exit code 0 on all-pass, 1 if any file fails.
    """
    if len(sys.argv) < 2:
        # Default: validate data/raw/ relative to this script's location
        default_dir = Path(__file__).resolve().parent / "raw"
        if default_dir.exists():
            paths = [str(default_dir)]
            print(f"No paths specified. Defaulting to: {default_dir}")
        else:
            print(
                "Usage: python validate_schema.py <csv_file_or_dir> [...]",
                file=sys.stderr,
            )
            print(
                "       No arguments given and data/raw/ does not exist.",
                file=sys.stderr,
            )
            return 1
    else:
        paths = sys.argv[1:]

    print()
    print("=" * 72)
    print("TELEMETRY CSV SCHEMA VALIDATOR — Manufacturing Analytics FYP")
    print(f"Required columns ({len(SENSOR_READINGS_REQUIRED_COLS)}): "
          f"{SENSOR_READINGS_REQUIRED_COLS}")
    print("=" * 72)
    print()

    results, n_pass, n_fail = validate_paths(paths)

    for r in results:
        print(r)
        print()

    # Summary
    total = n_pass + n_fail
    print(f"SUMMARY: {total} file(s) validated | {n_pass} PASS | {n_fail} FAIL")
    print()

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
