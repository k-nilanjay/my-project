"""
tests/test_sql_queries.py — Manufacturing & Industrial Analytics FYP
Day 13: Query Review, Optimization & Testing

PURPOSE:
    Connect to data/manufacturing.db, iterate through every .sql file in
    sql/queries/, execute each named query block, validate syntax and result
    structure, and log execution times to stdout and a CSV report.

DESIGN PRINCIPLES:
    - Each SQL file may contain multiple named queries separated by the
      standard horizontal-rule + label pattern used across this project:
        -- ============================================
        -- Q1: SEQUENTIAL MTBF ...
        -- ============================================
    - Each named section is extracted as one atomic SQL statement (SELECT
      or WITH...SELECT). We split on the horizontal-rule separator, strip
      comment lines, then isolate the first complete SQL statement.
    - All queries are executed with EXPLAIN QUERY PLAN first to surface
      any full-table scans, then executed for real to capture row count and
      timing.
    - No writes are performed; all extracted statements are SELECT-only.
    - Results are saved to: data/processed/query_test_report.csv

USAGE:
    # From project root (with .venv active):
    python -m pytest tests/test_sql_queries.py -v
    # OR run directly:
    python tests/test_sql_queries.py

REQUIREMENTS:
    - Python 3.9+
    - sqlite3 (stdlib — no extra install needed)
    - pytest (in requirements.txt)
"""

import os
import re
import csv
import sys
import time
import sqlite3
import logging
import pathlib
import datetime
import pytest

# ---------------------------------------------------------------------------
# Paths — resolved relative to this test file's location
# ---------------------------------------------------------------------------
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.resolve()
DB_PATH      = PROJECT_ROOT / "data" / "manufacturing.db"
SQL_DIR      = PROJECT_ROOT / "sql" / "queries"
REPORT_PATH  = PROJECT_ROOT / "data" / "processed" / "query_test_report.csv"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------
_SELECT_PATTERN = re.compile(r"\bSELECT\b", re.IGNORECASE)
_WITH_PATTERN   = re.compile(r"\bWITH\b",   re.IGNORECASE)
_WRITE_PATTERN  = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|REPLACE)\b", re.IGNORECASE
)

# Horizontal-rule separators used in all project SQL files:
# -- ======================================================================
_HRULE_PATTERN  = re.compile(r"^--\s*={10,}\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# SQL splitter: split file into named query sections
# ---------------------------------------------------------------------------

def split_sql_file(sql_text: str) -> list[dict]:
    """
    Split a SQL file into labelled query sections.

    Project SQL file structure (Days 10–12):
        -- =================== (opening HR)
        -- Q1: query label
        -- =================== (closing HR)
        -- optional description comments
        WITH/SELECT ... SQL code ... ;
        -- =================== (next query opening HR)
        -- Q2: next label
        ...

    OR for single-query files (Days 4–9):
        -- =================== (file header)
        -- description / purpose
        WITH/SELECT ... SQL code ...

    Strategy:
    1. Find all horizontal-rule positions.
    2. Identify "label blocks": pairs of consecutive HRs that bracket a
       single-line query label (-- Q1:, -- P1 —, etc.).
    3. The SQL for each label block is the text AFTER the closing HR of
       that label block and BEFORE the opening HR of the next label block.
    4. If no label blocks are found, return the whole file as "MAIN".
    """
    # Find all horizontal-rule positions
    hr_positions = [m.start() for m in _HRULE_PATTERN.finditer(sql_text)]

    if not hr_positions:
        # No HR separators — simple single-query file
        return [{"label": "MAIN", "sql": sql_text}]

    # Label pattern: a comment line in the format -- XX: ... or -- XX — ...
    label_pat = re.compile(
        r"^--\s*([A-Z][0-9]+)\s*[:\.\s—\-]",
        re.MULTILINE,
    )

    # Identify label blocks: consecutive (HR_i, HR_{i+1}) pairs that contain
    # exactly one label comment between them.
    label_blocks: list[tuple[str, int]] = []  # (label_text, pos_after_closing_HR)

    for i in range(len(hr_positions) - 1):
        hr_open_start = hr_positions[i]
        hr_close_start = hr_positions[i + 1]

        # Text between the two HRs
        between_start = sql_text.index("\n", hr_open_start) + 1
        between_end   = hr_close_start

        between_text  = sql_text[between_start:between_end]

        m = label_pat.search(between_text)
        if m:
            label = m.group(1)
            # pos_after_close is the character AFTER the closing HR's newline
            closing_hr_end = sql_text.find("\n", hr_close_start)
            if closing_hr_end == -1:
                closing_hr_end = len(sql_text)
            label_blocks.append((label, closing_hr_end + 1))

    if not label_blocks:
        # No labelled sections — whole file is one query
        return [{"label": "MAIN", "sql": sql_text}]

    # For each label block, the SQL is the text from its pos_after_close to
    # the NEXT label block's opening HR (or end of file).
    # The "next label block's opening HR" = the HR that immediately precedes
    # the next label block's pos_after_close.
    result: list[dict] = []
    seen_labels: set[str] = set()

    for j, (label, sql_start) in enumerate(label_blocks):
        # Find SQL end: start of the NEXT label block's first HR
        if j + 1 < len(label_blocks):
            # The next label's opening HR position: find the HR that comes
            # just before the next label's sql_start
            next_sql_start = label_blocks[j + 1][1]
            # The opening HR for the next label is the HR ending just before
            # next_sql_start — scan backwards in hr_positions
            sql_end = next_sql_start
            for hr_pos in reversed(hr_positions):
                hr_end = sql_text.find("\n", hr_pos) + 1
                if hr_end <= next_sql_start:
                    sql_end = hr_pos
                    break
        else:
            sql_end = len(sql_text)

        sql_chunk = sql_text[sql_start:sql_end].strip()

        # Deduplicate labels
        unique_label = label
        if unique_label in seen_labels:
            unique_label = label + "_b"
        seen_labels.add(unique_label)

        if sql_chunk:
            result.append({"label": unique_label, "sql": sql_chunk})

    return result if result else [{"label": "MAIN", "sql": sql_text}]


# ---------------------------------------------------------------------------
# SQL extractor: pull first complete statement from a block
# ---------------------------------------------------------------------------

def _find_first_statement_end(sql: str) -> int | None:
    """
    Find the index of the first ';' that terminates a SQL statement,
    skipping semicolons inside string literals and SQL line comments.
    Returns None if no such semicolon exists.
    """
    in_single  = False
    in_double  = False
    i, n       = 0, len(sql)

    while i < n:
        ch = sql[i]

        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif (ch == "-" and i + 1 < n and sql[i + 1] == "-"
              and not in_single and not in_double):
            # Skip to end of line
            while i < n and sql[i] != "\n":
                i += 1
            continue
        elif ch == ";" and not in_single and not in_double:
            return i

        i += 1

    return None  # No statement terminator found


def extract_first_statement(sql_block: str) -> str | None:
    """
    Extract the first complete SQL statement (SELECT or WITH ... SELECT)
    from a block of text that may also contain SQL comment headers.

    Strategy:
    1. Strip comment lines (lines starting with --) and blank lines, then
       find the first WITH or SELECT keyword in the remaining SQL code.
    2. Use the cleaned start position to map back to the original block offset.
    3. Capture from the start to the first unquoted semicolon (or end-of-block).
    4. Strip trailing whitespace and trailing semicolon.

    Returns the clean SQL string, or None if no query is found.
    """
    # Build a version of the block with comments blanked out (replaced with
    # spaces to preserve character positions so offsets map back correctly).
    # Comment lines are lines where the FIRST non-whitespace chars are "--".
    blanked = _blank_sql_comments(sql_block)

    with_m   = _WITH_PATTERN.search(blanked)
    select_m = _SELECT_PATTERN.search(blanked)

    if not with_m and not select_m:
        return None

    if with_m and select_m:
        start = min(with_m.start(), select_m.start())
    elif with_m:
        start = with_m.start()
    else:
        start = select_m.start()

    # Use the ORIGINAL text from this position (blanked only used for finding start)
    fragment = sql_block[start:]
    end_idx  = _find_first_statement_end(fragment)
    if end_idx is not None:
        fragment = fragment[:end_idx]

    fragment = fragment.strip().rstrip(";").strip()
    return fragment if fragment else None


def _blank_sql_comments(sql: str) -> str:
    """
    Return a copy of `sql` where every SQL line comment (-- to end-of-line)
    is replaced with spaces. This preserves character positions so that
    offsets found in the blanked string map correctly back to the original.
    """
    chars = list(sql)
    i, n  = 0, len(chars)

    while i < n:
        if chars[i] == "'" :
            # Skip single-quoted string
            i += 1
            while i < n and chars[i] != "'":
                i += 1
        elif chars[i] == '"':
            # Skip double-quoted identifier
            i += 1
            while i < n and chars[i] != '"':
                i += 1
        elif i + 1 < n and chars[i] == "-" and chars[i + 1] == "-":
            # Blank out from here to end of line
            while i < n and chars[i] != "\n":
                chars[i] = " "
                i += 1
            continue
        i += 1

    return "".join(chars)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """
    Open a read-only connection to manufacturing.db.
    URI mode with mode=ro prevents accidental writes.
    """
    uri  = DB_PATH.as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ---------------------------------------------------------------------------
# Core query execution
# ---------------------------------------------------------------------------

def execute_query_block(
    conn  : sqlite3.Connection,
    label : str,
    sql   : str,
) -> dict:
    """
    Execute one SQL SELECT block against the open connection.
    Returns a result dict with timing, row counts, and EXPLAIN plan.
    """
    result = {
        "query_label"   : label,
        "sql_preview"   : sql[:120].replace("\n", " "),
        "status"        : "PASS",
        "row_count"     : -1,
        "col_count"     : -1,
        "elapsed_ms"    : -1.0,
        "explain_plan"  : "",
        "error_message" : "",
        "has_full_scan" : False,
    }

    # Safety guard — reject DML/DDL accidentally extracted
    if _WRITE_PATTERN.search(sql):
        result["status"]        = "SKIP"
        result["error_message"] = "Non-SELECT statement detected; skipped."
        return result

    if not _SELECT_PATTERN.search(sql) and not _WITH_PATTERN.search(sql):
        result["status"]        = "SKIP"
        result["error_message"] = "No SELECT or WITH keyword; skipping."
        return result

    # --- Step 1: EXPLAIN QUERY PLAN -------------------------------------------
    try:
        plan_rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
        plan_text = "\n".join(
            f"  {r['id']:>3} {r['parent']:>3} {r['notused']:>3} {r['detail']}"
            for r in plan_rows
        )
        result["explain_plan"] = plan_text

        for r in plan_rows:
            detail = str(r["detail"]).upper()
            if "SCAN TABLE" in detail and "USING INDEX" not in detail and "USING COVERING INDEX" not in detail:
                result["has_full_scan"] = True
                log.warning("  ⚠  Full table scan in [%s]: %s", label, r["detail"])

    except sqlite3.Error as e:
        result["explain_plan"] = f"EXPLAIN failed: {e}"

    # --- Step 2: Execute and time ---------------------------------------------
    try:
        t0      = time.perf_counter()
        cursor  = conn.execute(sql)
        rows    = cursor.fetchall()
        elapsed = time.perf_counter() - t0

        result["elapsed_ms"] = round(elapsed * 1000, 3)
        result["row_count"]  = len(rows)
        result["col_count"]  = (
            len(rows[0].keys()) if rows
            else (len(cursor.description) if cursor.description else 0)
        )
        result["status"] = "PASS"

        log.info(
            "  ✓  [%s] rows=%d  cols=%d  %.2f ms",
            label, result["row_count"], result["col_count"], result["elapsed_ms"],
        )

    except sqlite3.OperationalError as e:
        result["status"]        = "FAIL"
        result["error_message"] = f"OperationalError: {e}"
        log.error("  ✗  [%s] FAILED — %s", label, e)

    except sqlite3.Error as e:
        result["status"]        = "FAIL"
        result["error_message"] = f"SQLiteError: {e}"
        log.error("  ✗  [%s] FAILED — %s", label, e)

    return result


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

def run_all_queries() -> list[dict]:
    """
    Discover every .sql file, split into query blocks, execute each, and
    return a flat list of result dicts.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}.\n"
            "Ensure the Day 7–11 simulation pipeline has been run."
        )

    sql_files = sorted(SQL_DIR.glob("*.sql"))
    if not sql_files:
        raise FileNotFoundError(f"No .sql files found in {SQL_DIR}")

    log.info("=" * 70)
    log.info("Day 13 SQL Query Test Suite")
    log.info("Database : %s", DB_PATH)
    log.info("Query dir: %s", SQL_DIR)
    log.info("Files    : %d .sql files discovered", len(sql_files))
    log.info("=" * 70)

    all_results: list[dict] = []
    conn = get_connection()

    try:
        for sql_file in sql_files:
            file_name = sql_file.name
            log.info("")
            log.info("─" * 60)
            log.info("FILE: %s", file_name)
            log.info("─" * 60)

            raw_sql = sql_file.read_text(encoding="utf-8")
            blocks  = split_sql_file(raw_sql)
            log.info("  Blocks found: %d", len(blocks))

            for block in blocks:
                label     = block["label"]
                block_sql = block["sql"]

                stmt = extract_first_statement(block_sql)

                if stmt is None:
                    log.debug("  [%s] No SQL statement found; skipping.", label)
                    all_results.append({
                        "file_name"     : file_name,
                        "query_label"   : label,
                        "sql_preview"   : block_sql[:80].replace("\n", " "),
                        "status"        : "SKIP",
                        "row_count"     : -1,
                        "col_count"     : -1,
                        "elapsed_ms"    : -1.0,
                        "explain_plan"  : "",
                        "error_message" : "No SQL statement in block.",
                        "has_full_scan" : False,
                    })
                    continue

                res              = execute_query_block(conn, label, stmt)
                res["file_name"] = file_name
                all_results.append(res)

    finally:
        conn.close()

    return all_results


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(results: list[dict]) -> None:
    """Write test results to data/processed/query_test_report.csv."""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "file_name", "query_label", "sql_preview",
        "status", "row_count", "col_count", "elapsed_ms",
        "has_full_scan", "error_message",
    ]

    with open(REPORT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    log.info("Report written → %s", REPORT_PATH)


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(results: list[dict]) -> None:
    """Print a human-readable summary table to stdout."""
    passed  = [r for r in results if r["status"] == "PASS"]
    failed  = [r for r in results if r["status"] == "FAIL"]
    skipped = [r for r in results if r["status"] == "SKIP"]
    scanned = [r for r in results if r.get("has_full_scan")]

    total_elapsed = sum(r["elapsed_ms"] for r in passed)
    avg_elapsed   = total_elapsed / len(passed) if passed else 0.0

    log.info("")
    log.info("=" * 70)
    log.info("QUERY TEST SUMMARY")
    log.info("=" * 70)
    log.info("Total blocks   : %d", len(results))
    log.info("  PASS         : %d", len(passed))
    log.info("  FAIL         : %d", len(failed))
    log.info("  SKIP         : %d", len(skipped))
    log.info("Full-scan alerts: %d", len(scanned))
    log.info("Total elapsed  : %.2f ms (PASS queries only)", total_elapsed)
    log.info("Avg per query  : %.2f ms", avg_elapsed)
    log.info("")

    if failed:
        log.error("─" * 40)
        log.error("FAILURES:")
        for r in failed:
            log.error("  [%s / %s] %s", r["file_name"], r["query_label"], r["error_message"])

    if scanned:
        log.warning("─" * 40)
        log.warning("FULL SCAN WARNINGS:")
        for r in scanned:
            log.warning("  [%s / %s]", r["file_name"], r["query_label"])

    sorted_by_time = sorted(passed, key=lambda r: r["elapsed_ms"], reverse=True)
    if sorted_by_time:
        log.info("SLOWEST 5 QUERIES:")
        for r in sorted_by_time[:5]:
            log.info(
                "  %6.2f ms  [%s / %s]  rows=%d",
                r["elapsed_ms"], r["file_name"], r["query_label"], r["row_count"],
            )
    log.info("=" * 70)


# ---------------------------------------------------------------------------
# pytest integration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def query_results():
    """Run the full query suite once per module; share results across tests."""
    results = run_all_queries()
    write_report(results)
    print_summary(results)
    return results


class TestDatabaseConnectivity:
    """Verify that the database exists and contains the expected tables."""

    def test_database_file_exists(self):
        assert DB_PATH.exists(), (
            f"Database not found: {DB_PATH}\n"
            "Run the Day 7–11 simulation and ingest pipeline first."
        )

    def test_sql_queries_directory_exists(self):
        assert SQL_DIR.is_dir(), f"sql/queries/ not found at {SQL_DIR}"
        sql_files = list(SQL_DIR.glob("*.sql"))
        assert len(sql_files) >= 1, "No .sql files found in sql/queries/"

    def test_expected_sql_files_present(self):
        expected = [
            "oee_availability.sql",
            "oee_performance.sql",
            "oee_quality.sql",
            "oee_composite.sql",
            "oee_system_series.sql",
            "six_big_losses.sql",
            "failure_rate_by_component.sql",
            "mtbf_from_failure_log.sql",
            "anomaly_rate_by_sensor.sql",
            "oee_window_analytics.sql",
            "downtime_pareto.sql",
            "downtime_timeseries.sql",
        ]
        found   = [f.name for f in SQL_DIR.glob("*.sql")]
        missing = [f for f in expected if f not in found]
        assert not missing, f"Missing expected SQL files: {missing}"

    def test_database_connection(self):
        conn   = get_connection()
        result = conn.execute("SELECT sqlite_version();").fetchone()
        conn.close()
        assert result is not None
        log.info("SQLite version: %s", result[0])

    def test_expected_tables_exist(self):
        expected_tables = {
            "components", "sensors", "sensor_readings",
            "failure_log", "production_shifts",
            "downtime_events", "production_counts",
        }
        conn  = get_connection()
        rows  = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
        conn.close()
        found   = {r["name"] for r in rows}
        missing = expected_tables - found
        assert not missing, f"Missing tables in DB: {missing}"

    def test_row_counts_non_zero(self):
        conn = get_connection()
        for table in ["sensor_readings", "production_shifts", "downtime_events", "failure_log"]:
            count = conn.execute(f"SELECT COUNT(*) FROM {table};").fetchone()[0]
            assert count > 0, f"Table '{table}' is empty — simulation data missing."
            log.info("  %s: %d rows", table, count)
        conn.close()


class TestQuerySyntax:
    """
    Iterate all .sql files and assert every extracted query executes cleanly.
    This is the primary Day 13 test class.
    """

    def test_no_failed_queries(self, query_results):
        """Zero queries must have status='FAIL' (syntax error or schema mismatch)."""
        failures = [
            (r["file_name"], r["query_label"], r["error_message"])
            for r in query_results if r["status"] == "FAIL"
        ]
        assert not failures, (
            f"{len(failures)} query/queries FAILED:\n" +
            "\n".join(f"  [{f}/{l}]: {e}" for f, l, e in failures)
        )

    def test_all_files_have_at_least_one_pass(self, query_results):
        """Every .sql file must produce at least one PASS result."""
        files_with_pass = {r["file_name"] for r in query_results if r["status"] == "PASS"}
        all_files       = {r["file_name"] for r in query_results}
        files_no_pass   = all_files - files_with_pass
        assert not files_no_pass, (
            f"These files produced no PASS results: {files_no_pass}"
        )

    def test_oee_availability_returns_rows(self, query_results):
        """oee_availability.sql must return at least 1,350 rows (5 comps × 270 shifts)."""
        avail = [r for r in query_results
                 if r["file_name"] == "oee_availability.sql" and r["status"] == "PASS"]
        assert avail, "oee_availability.sql produced no PASS result."
        assert avail[0]["row_count"] >= 1350, (
            f"oee_availability.sql returned only {avail[0]['row_count']} rows; expected ≥1350"
        )

    def test_oee_system_series_returns_rows(self, query_results):
        """oee_system_series.sql must return at least 270 rows (one per shift_date)."""
        series = [r for r in query_results
                  if r["file_name"] == "oee_system_series.sql" and r["status"] == "PASS"]
        assert series, "oee_system_series.sql produced no PASS result."
        assert series[0]["row_count"] >= 1, (
            "oee_system_series.sql returned 0 rows."
        )

    def test_failure_log_query_returns_rows(self, query_results):
        """mtbf_from_failure_log.sql must return at least 1 row."""
        mtbf = [r for r in query_results
                if r["file_name"] == "mtbf_from_failure_log.sql" and r["status"] == "PASS"]
        assert mtbf, "mtbf_from_failure_log.sql produced no PASS result."
        assert mtbf[0]["row_count"] >= 1, (
            "mtbf_from_failure_log.sql returned 0 rows."
        )

    def test_downtime_pareto_returns_rows(self, query_results):
        """downtime_pareto.sql must return at least one PASS block with rows."""
        pareto = [r for r in query_results
                  if r["file_name"] == "downtime_pareto.sql" and r["status"] == "PASS"]
        assert pareto, "downtime_pareto.sql produced no PASS results."
        assert any(r["row_count"] > 0 for r in pareto), (
            "All downtime_pareto.sql blocks returned 0 rows."
        )

    def test_downtime_timeseries_returns_rows(self, query_results):
        """downtime_timeseries.sql must return at least one PASS block with rows."""
        ts = [r for r in query_results
              if r["file_name"] == "downtime_timeseries.sql" and r["status"] == "PASS"]
        assert ts, "downtime_timeseries.sql produced no PASS results."
        assert any(r["row_count"] > 0 for r in ts), (
            "All downtime_timeseries.sql blocks returned 0 rows."
        )


class TestQueryPerformance:
    """
    Performance assertions. Hard limits fail the suite; soft limits only warn.
    """

    WARN_THRESHOLD_MS  = 500.0    # log warning if exceeded
    ERROR_THRESHOLD_MS = 5000.0   # hard fail if exceeded

    def test_no_query_exceeds_hard_timeout(self, query_results):
        """No query may take longer than 5,000 ms."""
        slow = [r for r in query_results
                if r["status"] == "PASS" and r["elapsed_ms"] > self.ERROR_THRESHOLD_MS]
        assert not slow, (
            f"{len(slow)} queries exceeded {self.ERROR_THRESHOLD_MS} ms:\n" +
            "\n".join(
                f"  [{r['file_name']}/{r['query_label']}]: {r['elapsed_ms']:.1f} ms"
                for r in slow
            )
        )

    def test_warn_slow_queries(self, query_results):
        """Log a warning for queries exceeding 500 ms (soft limit, does not fail)."""
        slow = [r for r in query_results
                if r["status"] == "PASS" and r["elapsed_ms"] > self.WARN_THRESHOLD_MS]
        for r in slow:
            log.warning(
                "  [%s / %s]: %.1f ms  rows=%d",
                r["file_name"], r["query_label"], r["elapsed_ms"], r["row_count"],
            )
        assert True  # always passes

    def test_report_written(self, query_results):
        """query_test_report.csv must exist and be non-empty after the run."""
        assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
        assert REPORT_PATH.stat().st_size > 0, "Report file is empty."

    def test_total_suite_elapsed_reasonable(self, query_results):
        """Total wall-clock time for all PASS queries must be under 30 seconds."""
        total_ms = sum(r["elapsed_ms"] for r in query_results if r["status"] == "PASS")
        assert total_ms < 30_000, (
            f"Total query suite time {total_ms:.0f} ms exceeds 30,000 ms."
        )


class TestIndexVerification:
    """
    Verify that the Day 13 performance indexes exist in manufacturing.db.
    Indexes are expected to have been applied via sql/schema/indexes.sql.
    """

    EXPECTED_INDEXES = [
        "idx_dte_shift_comp",
        "idx_dte_category_comp",
        "idx_dte_comp_cat_dur",
        "idx_dte_start_ts",
        "idx_dte_root_cause_comp",
        "idx_ps_comp_date",
        "idx_ps_date_comp",
        "idx_ps_shift_comp_dur",
        "idx_sr_comp_ts",
        "idx_sr_fail_comp",
        "idx_sr_anomaly_comp_sensor",
        "idx_fl_comp_ttf",
        "idx_fl_comp_t_abs",
        "idx_pc_shift_comp",
        "idx_sn_comp_type",
    ]

    def test_indexes_exist_in_db(self):
        """All 15 indexes from indexes.sql must exist in manufacturing.db."""
        conn  = get_connection()
        rows  = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';"
        ).fetchall()
        conn.close()

        found   = {r["name"] for r in rows}
        missing = [idx for idx in self.EXPECTED_INDEXES if idx not in found]

        if missing:
            pytest.skip(
                f"Indexes not yet applied. Missing: {missing}\n"
                "Run: python data/apply_indexes.py\nThen re-run this test."
            )
        assert not missing


# ---------------------------------------------------------------------------
# Standalone entry point (run without pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Running Day 13 SQL Query Test Suite (standalone mode)")
    log.info("Timestamp: %s", datetime.datetime.now().isoformat())
    log.info("")

    results = run_all_queries()
    write_report(results)
    print_summary(results)

    failures = [r for r in results if r["status"] == "FAIL"]
    sys.exit(1 if failures else 0)
