#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_pipeline.py -- Day 34 Deliverable
=======================================
Manufacturing & Industrial Analytics FYP
Date: August 15, 2026

PURPOSE
-------
Master orchestration script that sequentially executes the full data pipeline
end-to-end, from synthetic data generation through to EDA/analytics output,
with robust structured logging and explicit pass/fail verification at each stage.

PIPELINE SEQUENCE (3 canonical stages, Day 34 scope)
------------------------------------------------------
  Stage 1 -- DATA GENERATION
      Script : python/data_generator.py
      Inputs : Weibull params (reliability.py constants), Arrhenius Ea per component
      Outputs: data/processed/multi_failure_telemetry.csv  (~48 k rows)
               data/processed/ttf_samples.csv              (19 rows)
               data/processed/qq_summary.csv               (5 component Q-Q fits)
               data/processed/qq_plots/*.png               (Weibull Q-Q plots)

  Stage 2 -- SQLITE INGESTION
      Script : ingest.py  (wraps python/etl.py::run_etl_pipeline)
      Inputs : multi_failure_telemetry.csv, ttf_samples.csv
      Outputs: data/manufacturing.db
                 -> sensor_readings  (expect ~47,957 rows)
                 -> failure_log      (expect 19 rows)
               (schema.sql + seed.sql initialised automatically if DB absent)

  Stage 3 -- PYTHON EDA / ANALYTICS (3 sub-scripts, sequential)
      Scripts: eda_summary_stats.py, eda_trends.py, eda_correlation.py
      Inputs : data/manufacturing.db
      Outputs: data/processed/eda_sensor_stats.csv
               data/processed/eda_production_stats.csv
               data/processed/eda_downtime_stats.csv
               data/processed/eda_full_report.txt
               data/processed/plots/rolling_avg_sensor_trends.png
               data/processed/plots/shift_oee_seasonality.png
               data/processed/plots/downtime_vs_failures_stacked.png
               data/processed/corr_sensor_pivot_pearson.csv
               data/processed/corr_within_component_pearson.csv

USAGE
-----
    # Full pipeline (all 3 stages — Day 34 canonical run):
    python run_pipeline.py

    # Skip data generation (use existing CSVs):
    python run_pipeline.py --skip-generation

    # Skip generation AND ingestion (DB already populated):
    python run_pipeline.py --skip-generation --skip-ingestion

    # Dry-run: show what would be executed without running:
    python run_pipeline.py --dry-run

    # Verbose output (stream subprocess stdout/stderr in real time):
    python run_pipeline.py --verbose

    # Log run to a specific file:
    python run_pipeline.py --log-file logs/pipeline_run_day34.log

SUCCESS CRITERIA (Day 34 integration test)
------------------------------------------
    All 3 stages exit with returncode 0.
    Key output artefacts verified after run:
      [x] data/processed/multi_failure_telemetry.csv      (>= 40,000 rows)
      [x] data/manufacturing.db                           (>= 3 MB)
      [x] sensor_readings table                           (>= 47,000 rows in DB)
      [x] failure_log table                               (>= 15 rows in DB)
      [x] data/processed/eda_sensor_stats.csv             (exists, non-empty)
      [x] data/processed/eda_full_report.txt              (exists, non-empty)
      [x] data/processed/corr_sensor_pivot_pearson.csv    (exists)

EXTENDED PIPELINE (stages 4-5, from Day 20 — available with --extended flag)
------------------------------------------------------------------------------
  Stage 4 -- GRAPH CENTRALITY (graph_centrality.py)
  Stage 5 -- COMPOSITE CRITICALITY INDEX (composite_criticality.py)
  Use: python run_pipeline.py --extended

DEPENDENCIES
------------
    Python >= 3.9
    All packages in requirements.txt must be installed.
    Activate the virtual environment before running:
        Windows : .venv\\Scripts\\activate
        macOS   : source .venv/bin/activate

LOGGING
-------
    Structured log entries are written to stdout and optionally to a log file.
    Each entry carries: timestamp, level (INFO/WARNING/ERROR), stage id, and message.
    Log format: [YYYY-MM-DD HH:MM:SS] LEVEL  [StageX] message

ENVIRONMENT NOTES
-----------------
    - SQLite is used (no SQL Server required for dev environment).
    - matplotlib uses the Agg backend (headless); set via MPLBACKEND env var.
    - All paths are resolved relative to the project root (directory of this file).
    - EDA sub-scripts (3a-3c) run sequentially; parallelism is avoided because all
      three share the same SQLite DB file (write-lock contention risk).
    - If Stage 1 (data generation) is run, it OVERWRITES the multi_failure_telemetry.csv
      and ttf_samples.csv outputs. The DB is NOT deleted by Stage 1; Stage 2 uses
      INSERT OR IGNORE so repeated runs are safe.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root (directory containing this script)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON_DIR   = PROJECT_ROOT / "python"
DATA_DIR     = PROJECT_ROOT / "data"
PROCESSED    = DATA_DIR / "processed"
PLOTS_DIR    = PROCESSED / "plots"
DB_PATH      = DATA_DIR / "manufacturing.db"
LOGS_DIR     = PROJECT_ROOT / "logs"

# Python interpreter: prefer .venv, fall back to current interpreter
_VENV_WIN  = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
_VENV_UNIX = PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_WIN.exists():
    PYTHON_EXE = str(_VENV_WIN)
elif _VENV_UNIX.exists():
    PYTHON_EXE = str(_VENV_UNIX)
else:
    PYTHON_EXE = sys.executable

# ---------------------------------------------------------------------------
# ANSI colour helpers (Windows VT100 mode enabled in main())
# ---------------------------------------------------------------------------
_RESET  = "\033[0m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_CYAN   = "\033[36m"
_BOLD   = "\033[1m"


def _cprint(msg: str, color: str = _RESET) -> None:
    """Print with ANSI colour, suppressing UnicodeEncodeError on legacy terminals."""
    try:
        print(f"{color}{msg}{_RESET}", flush=True)
    except UnicodeEncodeError:
        print(msg.encode('ascii', 'ignore').decode('ascii'), flush=True)


def _banner(text: str) -> None:
    width = 72
    _cprint("=" * width, _CYAN)
    _cprint(f"  {text}", _BOLD)
    _cprint("=" * width, _CYAN)


# ---------------------------------------------------------------------------
# Structured Logger
# ---------------------------------------------------------------------------

class PipelineLogger:
    """
    Structured logger that writes to both stdout and an optional log file.

    Format: [YYYY-MM-DD HH:MM:SS] LEVEL   [StageX] message

    Levels:
        INFO    -- normal progress messages
        WARNING -- non-fatal issues (e.g., output slightly under expected size)
        ERROR   -- fatal issues that abort the pipeline
    """

    def __init__(self, log_file: Path | None = None):
        self._handlers: list[logging.Handler] = []
        fmt = logging.Formatter(
            fmt="[%(asctime)s] %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console handler (uses print for colour support)
        self._use_print = True  # we handle console colouring ourselves

        # File handler (plain text, no ANSI)
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(str(log_file), encoding="utf-8")
            fh.setFormatter(fmt)
            self._file_logger = logging.getLogger(f"pipeline_file_{id(self)}")
            self._file_logger.setLevel(logging.DEBUG)
            self._file_logger.addHandler(fh)
            self._file_logger.propagate = False
        else:
            self._file_logger = None

    def _stage_prefix(self, stage_id) -> str:
        return f"[Stage {stage_id}]" if stage_id is not None else "[Pipeline]"

    def _log(self, level: str, msg: str, stage_id=None, color: str = _RESET):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = self._stage_prefix(stage_id)
        formatted = f"[{ts}] {level:<8} {prefix} {msg}"
        _cprint(formatted, color)
        if self._file_logger is not None:
            if level == "INFO":
                self._file_logger.info(f"{prefix} {msg}")
            elif level == "WARNING":
                self._file_logger.warning(f"{prefix} {msg}")
            elif level == "ERROR":
                self._file_logger.error(f"{prefix} {msg}")

    def info(self, msg: str, stage_id=None):
        self._log("INFO", msg, stage_id, _RESET)

    def success(self, msg: str, stage_id=None):
        self._log("INFO", f"[OK] {msg}", stage_id, _GREEN)

    def warning(self, msg: str, stage_id=None):
        self._log("WARNING", msg, stage_id, _YELLOW)

    def error(self, msg: str, stage_id=None):
        self._log("ERROR", msg, stage_id, _RED)

    def section(self, title: str):
        """Print a section divider."""
        _cprint(f"\n{'--' * 36}", _CYAN)
        _cprint(f"  {title}", _BOLD)
        _cprint(f"{'--' * 36}", _CYAN)


# Global logger instance (re-configured in main)
LOG = PipelineLogger()


# ---------------------------------------------------------------------------
# Stage Definitions
# ---------------------------------------------------------------------------

#  Day 34 canonical pipeline: 3 core stages
CORE_STAGES: list[dict] = [
    {
        "id":          1,
        "name":        "Data Generation",
        "description": "Weibull/Arrhenius multi-failure simulation → CSV output",
        "script":      str(PROJECT_ROOT / "python" / "data_generator.py"),
        "args":        [],
        "outputs": [
            PROCESSED / "multi_failure_telemetry.csv",
            PROCESSED / "ttf_samples.csv",
        ],
        "skippable": True,
        "abort_on_fail": True,
    },
    {
        "id":          2,
        "name":        "SQLite Ingestion",
        "description": "CSV → SQLite: schema init + INSERT sensor_readings & failure_log",
        "script":      str(PROJECT_ROOT / "ingest.py"),
        "args":        [],
        "outputs": [
            DATA_DIR / "manufacturing.db",
        ],
        "skippable": True,
        "abort_on_fail": True,
    },
    {
        "id":          "3a",
        "name":        "EDA — Summary Statistics",
        "description": "Descriptive stats (mean, std, skewness, Shapiro-Wilk) for sensors/production/downtime",
        "script":      str(PROJECT_ROOT / "eda_summary_stats.py"),
        "args":        [],
        "outputs": [
            PROCESSED / "eda_sensor_stats.csv",
            PROCESSED / "eda_production_stats.csv",
            PROCESSED / "eda_downtime_stats.csv",
            PROCESSED / "eda_full_report.txt",
        ],
        "skippable": False,
        "abort_on_fail": True,
    },
    {
        "id":          "3b",
        "name":        "EDA — Trends & Seasonality",
        "description": "Rolling averages, OEE seasonality by shift, downtime vs failure timeline",
        "script":      str(PROJECT_ROOT / "eda_trends.py"),
        "args":        [],
        "outputs": [
            PLOTS_DIR / "rolling_avg_sensor_trends.png",
            PLOTS_DIR / "shift_oee_seasonality.png",
            PLOTS_DIR / "downtime_vs_failures_stacked.png",
        ],
        "skippable": False,
        "abort_on_fail": True,
    },
    {
        "id":          "3c",
        "name":        "EDA — Correlation Analysis",
        "description": "Pearson/Spearman matrices (sensor pivot, within-component, production KPIs)",
        "script":      str(PROJECT_ROOT / "eda_correlation.py"),
        "args":        [],
        "outputs": [
            PROCESSED / "corr_sensor_pivot_pearson.csv",
            PROCESSED / "corr_within_component_pearson.csv",
        ],
        "skippable": False,
        "abort_on_fail": True,
    },
]

# Extended pipeline stages (Day 20 additions — activated by --extended flag)
EXTENDED_STAGES: list[dict] = [
    {
        "id":          4,
        "name":        "Graph Centrality",
        "description": "Betweenness centrality, cascade reach/exposure, SRS for the 5-node DAG",
        "script":      str(PROJECT_ROOT / "graph_centrality.py"),
        "args":        [],
        "outputs": [
            PROCESSED / "graph_centrality_metrics.csv",
            PROCESSED / "graph_centrality_rankings.csv",
            PLOTS_DIR  / "dag_centrality_plot.png",
        ],
        "skippable": False,
        "abort_on_fail": True,
    },
    {
        "id":          5,
        "name":        "Composite Criticality Index",
        "description": "CCI = 0.40*SRS_norm + 0.35*Unreliability_norm + 0.25*TBR_norm per component",
        "script":      str(PROJECT_ROOT / "composite_criticality.py"),
        "args":        [],
        "outputs": [
            PROCESSED / "criticality_scores.csv",
            PLOTS_DIR  / "criticality_index_plot.png",
        ],
        "skippable": False,
        "abort_on_fail": True,
    },
]


# ---------------------------------------------------------------------------
# Post-run artefact validation specs
# ---------------------------------------------------------------------------

# Format: (path, minimum_threshold, unit)   unit in {"rows", "bytes", "db_rows:table", ""}
_CORE_CRITICAL_OUTPUTS = [
    (PROCESSED / "multi_failure_telemetry.csv",    40_000,    "rows"),
    (DATA_DIR  / "manufacturing.db",               3_000_000, "bytes"),
    (PROCESSED / "eda_sensor_stats.csv",           1,         "rows"),
    (PROCESSED / "eda_full_report.txt",            0,         ""),
    (PROCESSED / "corr_sensor_pivot_pearson.csv",  0,         ""),
]

_DB_TABLE_THRESHOLDS = [
    ("sensor_readings", 47_000),
    ("failure_log",     15),
]

_EXTENDED_CRITICAL_OUTPUTS = [
    (PROCESSED / "graph_centrality_rankings.csv",  0,         ""),
    (PROCESSED / "criticality_scores.csv",         0,         ""),
    (PLOTS_DIR / "criticality_index_plot.png",     0,         ""),
]


# ---------------------------------------------------------------------------
# Core stage runner
# ---------------------------------------------------------------------------

def _check_outputs(stage: dict, log: PipelineLogger) -> list[str]:
    """Verify expected output files exist. Returns list of missing paths."""
    missing = []
    for path in stage.get("outputs", []):
        p = Path(path)
        if not p.exists():
            missing.append(str(p))
        else:
            log.success(f"Output verified: {p.name}", stage["id"])
    return missing


def _run_stage(
    stage: dict,
    dry_run: bool = False,
    verbose: bool = False,
    log: PipelineLogger = None,
) -> tuple[bool, float]:
    """
    Execute one pipeline stage via subprocess.

    Returns
    -------
    (success: bool, elapsed_seconds: float)

    Behaviour
    ---------
    - Runs PYTHON_EXE <script> [args] as a child process.
    - Sets MPLBACKEND=Agg (headless matplotlib) and PYTHONPATH=python/ in env.
    - On returncode != 0: logs stderr tail (up to 4000 chars) and returns False.
    - On success: validates expected output files exist.
    - If dry_run=True: prints the command that would run and returns (True, 0.0).
    """
    if log is None:
        log = LOG

    sid    = stage["id"]
    name   = stage["name"]
    script = stage["script"]

    log.section(f"Stage {sid}: {name}")
    log.info(f"{stage['description']}", sid)
    log.info(f"Script: {Path(script).name}", sid)

    if not Path(script).exists():
        log.error(f"Script not found: {script}", sid)
        return False, 0.0

    if dry_run:
        log.warning(f"[DRY-RUN] Would execute: {PYTHON_EXE} {Path(script).name}", sid)
        return True, 0.0

    cmd = [PYTHON_EXE, script] + stage.get("args", [])
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    env["PYTHONPATH"] = str(PYTHON_DIR)

    log.info(f"Starting subprocess...", sid)

    if sid == 1:
        _cprint("  Generating synthetic sensor data...", _CYAN)
        _cprint("  Applying Arrhenius degradation...", _CYAN)
    elif sid == 2:
        _cprint("  Ingesting into SQLite...", _CYAN)

    t0 = time.perf_counter()

    done = False
    def spinner():
        while not done:
            sys.stdout.write('.')
            sys.stdout.flush()
            time.sleep(0.5)

    t = threading.Thread(target=spinner)
    t.start()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=(not verbose),
            text=True,
            timeout=600,  # 10-minute max per stage
        )
    except subprocess.TimeoutExpired:
        done = True
        t.join()
        sys.stdout.write('\n')
        elapsed = time.perf_counter() - t0
        log.error(f"Stage TIMED OUT after {elapsed:.0f}s (limit 600s).", sid)
        return False, elapsed
    except Exception as exc:
        done = True
        t.join()
        sys.stdout.write('\n')
        elapsed = time.perf_counter() - t0
        log.error(f"Subprocess launch failed: {exc}", sid)
        return False, elapsed

    done = True
    t.join()
    sys.stdout.write('\n')

    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        log.error(f"Stage FAILED (exit code {result.returncode}) in {elapsed:.1f}s", sid)
        if not verbose and result.stderr:
            stderr_tail = result.stderr[-4000:]
            _cprint("\n  --- STDERR TAIL ---", _RED)
            print(stderr_tail)
            _cprint("  --- END STDERR ---\n", _RED)
        return False, elapsed

    # Verify expected output files
    missing = _check_outputs(stage, log)
    if missing:
        log.warning(f"Stage exited OK but {len(missing)} output(s) missing:", sid)
        for f in missing:
            log.warning(f"  MISSING: {f}", sid)
        return False, elapsed

    log.success(f"Stage complete in {elapsed:.1f}s", sid)
    return True, elapsed


# ---------------------------------------------------------------------------
# Database row-count verification
# ---------------------------------------------------------------------------

def _verify_db_tables(log: PipelineLogger) -> bool:
    """
    Open manufacturing.db and verify row counts in key tables.
    Returns True if all thresholds are met, False otherwise.
    """
    if not DB_PATH.exists():
        log.error(f"DB not found at {DB_PATH}")
        return False

    all_ok = True
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur  = conn.cursor()
        for table, min_rows in _DB_TABLE_THRESHOLDS:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table};")
                count = cur.fetchone()[0]
                if count >= min_rows:
                    log.success(f"DB table '{table}': {count:,} rows (threshold >= {min_rows:,})")
                else:
                    log.warning(
                        f"DB table '{table}': {count:,} rows — BELOW threshold {min_rows:,}"
                    )
                    all_ok = False
            except sqlite3.OperationalError as exc:
                log.error(f"DB table '{table}' query failed: {exc}")
                all_ok = False
        conn.close()
    except sqlite3.Error as exc:
        log.error(f"Cannot open DB at {DB_PATH}: {exc}")
        return False

    return all_ok


# ---------------------------------------------------------------------------
# Post-pipeline artefact validation
# ---------------------------------------------------------------------------

def validate_pipeline_outputs(log: PipelineLogger, extended: bool = False) -> bool:
    """
    Validate all critical output artefacts after the pipeline completes.

    Checks:
      1. File existence and size/row thresholds for CSV and DB outputs.
      2. SQLite table row counts for sensor_readings and failure_log.
      3. Extended artefacts (criticality_scores.csv schema 5×16) if --extended.

    Returns True if all checks pass, False if any WARNING or ERROR is found.
    """
    log.section("POST-PIPELINE VALIDATION")

    all_ok = True

    # ---- File-level checks ----
    outputs_to_check = list(_CORE_CRITICAL_OUTPUTS)
    if extended:
        outputs_to_check.extend(_EXTENDED_CRITICAL_OUTPUTS)

    for path, threshold, unit in outputs_to_check:
        p = Path(path)

        if not p.exists():
            log.error(f"MISSING: {p.name}")
            all_ok = False
            continue

        if unit == "rows" and threshold > 0:
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    row_count = sum(1 for _ in csv.reader(fh)) - 1  # subtract header
                if row_count < threshold:
                    log.warning(
                        f"UNDERSIZE: {p.name}  ({row_count:,} rows, expected >= {threshold:,})"
                    )
                    all_ok = False
                else:
                    log.success(f"{p.name}  ({row_count:,} rows)")
            except Exception as exc:
                log.warning(f"Cannot read {p.name}: {exc}")
                all_ok = False

        elif unit == "bytes" and threshold > 0:
            sz = p.stat().st_size
            if sz < threshold:
                log.warning(
                    f"UNDERSIZE: {p.name}  ({sz:,} bytes, expected >= {threshold:,})"
                )
                all_ok = False
            else:
                log.success(f"{p.name}  ({sz / 1e6:.1f} MB)")

        else:
            sz = p.stat().st_size
            if sz == 0:
                log.warning(f"EMPTY FILE: {p.name}")
                all_ok = False
            else:
                log.success(f"{p.name}  ({sz:,} bytes)")

    # ---- Database table row counts ----
    db_ok = _verify_db_tables(log)
    if not db_ok:
        all_ok = False

    # ---- Extended: criticality_scores.csv schema check ----
    if extended:
        cs_path = PROCESSED / "criticality_scores.csv"
        if cs_path.exists():
            try:
                import pandas as pd  # noqa: PLC0415
                df = pd.read_csv(cs_path)
                rows, cols = df.shape
                if rows == 5 and cols == 16:
                    log.success(f"criticality_scores.csv schema: {rows} rows × {cols} cols")
                else:
                    log.warning(
                        f"criticality_scores.csv: {rows} rows × {cols} cols "
                        f"(expected 5 × 16)"
                    )
                    all_ok = False
            except Exception as exc:
                log.warning(f"criticality_scores.csv read error: {exc}")

    return all_ok


# ---------------------------------------------------------------------------
# Pipeline summary printer
# ---------------------------------------------------------------------------

def _print_summary(
    results: list[tuple],
    pipeline_start: float,
    validation_ok: bool,
    log: PipelineLogger,
) -> None:
    total_elapsed = time.perf_counter() - pipeline_start
    log.section("PIPELINE SUMMARY")

    stage_map = {s["id"]: s["name"] for s in CORE_STAGES + EXTENDED_STAGES}
    for sid, ok, elapsed in results:
        status_txt = "OK  " if ok else "FAIL"
        status_col = _GREEN if ok else _RED
        name = stage_map.get(sid, str(sid))
        _cprint(
            f"  Stage {str(sid):<3}  [{status_col}{status_txt}{_RESET}]  "
            f"{elapsed:>6.1f}s  {name}",
            _RESET,
        )

    v_status = (
        f"{_GREEN}All artefacts validated{_RESET}"
        if validation_ok
        else f"{_YELLOW}Validation warnings — review above{_RESET}"
    )
    _cprint(f"\n  Validation : {v_status}", _RESET)
    _cprint(f"  Total time : {total_elapsed:.1f}s", _RESET)
    _cprint("=" * 72 + "\n", _CYAN)


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_pipeline",
        description=(
            "Day 34 — Manufacturing Analytics FYP end-to-end pipeline runner.\n"
            "Executes 3 core stages: data generation -> SQLite ingestion -> Python EDA.\n"
            "Use --extended to also run graph centrality (Stage 4) and "
            "composite criticality (Stage 5)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--skip-generation",
        action="store_true",
        default=False,
        help="Skip Stage 1 (data generation). Use existing CSVs.",
    )
    p.add_argument(
        "--skip-ingestion",
        action="store_true",
        default=False,
        help="Skip Stage 2 (SQLite ingestion). Assumes DB already populated.",
    )
    p.add_argument(
        "--extended",
        action="store_true",
        default=False,
        help="Also run Stages 4 (graph centrality) and 5 (composite criticality).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the commands that would be run without executing them.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Stream subprocess stdout/stderr in real time instead of capturing.",
    )
    p.add_argument(
        "--no-validate",
        action="store_true",
        default=False,
        help="Skip the post-pipeline artefact validation step.",
    )
    p.add_argument(
        "--log-file",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Path to write a plain-text log file (in addition to stdout). "
            "Example: --log-file logs/pipeline_day34.log"
        ),
    )
    return p


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    # Enable ANSI colours on Windows 10+ (VT100 mode)
    if sys.platform == "win32":
        os.system("")

    args = build_parser().parse_args()

    # ---- Configure logger ----
    log_file_path: Path | None = None
    if args.log_file:
        log_file_path = PROJECT_ROOT / args.log_file
    elif not args.dry_run:
        # Auto-create a timestamped log file under logs/
        LOGS_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file_path = LOGS_DIR / f"pipeline_{ts}.log"

    log = PipelineLogger(log_file=log_file_path)

    # ---- Banner ----
    _banner("Manufacturing Analytics FYP — End-to-End Pipeline  (Day 34)")
    log.info(f"Project root : {PROJECT_ROOT}")
    log.info(f"Python       : {PYTHON_EXE}")
    log.info(f"Mode         : {'DRY-RUN' if args.dry_run else 'EXECUTE'}")
    log.info(f"Extended     : {'YES (Stages 4+5)' if args.extended else 'NO (core 3 stages)'}")
    if log_file_path:
        log.info(f"Log file     : {log_file_path}")

    # ---- Build stage list ----
    stages: list[dict] = list(CORE_STAGES)
    if args.extended:
        stages.extend(EXTENDED_STAGES)

    # ---- Configure skip set ----
    skip_ids: set = set()
    if args.skip_generation:
        skip_ids.add(1)
        log.warning("--skip-generation: Stage 1 (data generation) will be skipped.")
    if args.skip_ingestion:
        skip_ids.add(2)
        log.warning("--skip-ingestion:  Stage 2 (SQLite ingestion) will be skipped.")

    # ---- Validate Python environment ----
    if PYTHON_EXE != sys.executable and not Path(PYTHON_EXE).exists():
        log.warning(
            f"Virtual environment not found at {PYTHON_EXE}. "
            "Using system Python — activate .venv for dependency isolation."
        )

    # ---- Ensure output directories exist ----
    PROCESSED.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Run pipeline ----
    results: list[tuple] = []
    pipeline_start = time.perf_counter()

    for stage in stages:
        sid = stage["id"]

        if sid in skip_ids:
            log.warning(f"Skipping Stage {sid}: {stage['name']}")
            results.append((sid, True, 0.0))
            continue

        ok, elapsed = _run_stage(stage, dry_run=args.dry_run, verbose=args.verbose, log=log)
        results.append((sid, ok, elapsed))

        if not ok and stage.get("abort_on_fail", True):
            log.error(
                f"Pipeline ABORTED at Stage {sid}. "
                "Fix the error above and re-run. "
                "Use --skip-generation / --skip-ingestion to resume from an intermediate stage."
            )
            _print_summary(results, pipeline_start, False, log)
            return 1

        if not ok:
            log.warning(f"Stage {sid} failed but pipeline continues (abort_on_fail=False).")

    # ---- Post-pipeline validation ----
    validation_ok = True
    if not args.no_validate and not args.dry_run:
        validation_ok = validate_pipeline_outputs(log, extended=args.extended)

    _print_summary(results, pipeline_start, validation_ok, log)

    if log_file_path and not args.dry_run:
        log.info(f"Full log written to: {log_file_path}")

    return 0 if validation_ok else 1


if __name__ == "__main__":
    sys.exit(main())
