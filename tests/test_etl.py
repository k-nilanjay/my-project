"""
tests/test_etl.py — Manufacturing Analytics FYP
================================================
Day 9 Unit Tests — ETL Pipeline Validation and Normalization

PURPOSE
-------
Covers validate_sensor_readings() and normalize_timestamps() from python/etl.py.
Tests are written at the function unit level, not end-to-end database level.

TEST STRATEGY
-------------
- Build minimal DataFrames that satisfy or violate exactly one validation rule.
- Each test is small, fast, and independent (no file I/O, no SQLite connection).
- Follow the pass / fail pattern: each rule gets a "pass" test and a "fail" test.

IMPORTS
-------
etl.py is in python/, so we add the python/ directory to sys.path before import.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root or tests/
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from etl import (  # noqa: E402
    SENSOR_READINGS_REQUIRED_COLS,
    VALID_SENSOR_TYPES,
    normalize_timestamps,
    validate_sensor_readings,
)


# ===========================================================================
# FIXTURES — Minimal valid DataFrames
# ===========================================================================

def _make_valid_telemetry_row(**overrides) -> dict:
    """
    Return a dict representing one valid multi_failure_telemetry.csv row.
    All 12 required columns are present with valid values (Bearing vibration).
    Use **overrides to modify individual fields for negative tests.
    """
    base = {
        "ts":               "2026-07-20T00:00:00",
        "component_id":     1,
        "component_name":   "Bearing",
        "sensor_type":      "vibration",
        "value":            1.5,
        "is_failure_event": 0,
        "failure_mode":     None,
        "R_derated":        0.98,
        "AF":               1.0,
        "cascade_flag":     0,
        "cycle_number":     0,
        "health_score":     98.0,
    }
    base.update(overrides)
    return base


def _make_valid_df(n: int = 3, **overrides) -> pd.DataFrame:
    """Return a DataFrame with n identical valid rows, each overridden by **overrides."""
    return pd.DataFrame([_make_valid_telemetry_row(**overrides)] * n)


# ===========================================================================
# CLASS 1: TestValidateSensorReadings — validation pass/fail for each rule
# ===========================================================================

class TestValidateSensorReadings:
    """Unit tests for etl.validate_sensor_readings()."""

    # ── Rule 1: All required columns present ─────────────────────────────────

    def test_pass_all_required_columns_present(self):
        """Valid DataFrame with all 12 columns → all rows retained."""
        df = _make_valid_df(5)
        result = validate_sensor_readings(df)
        assert len(result) == 5

    def test_fail_missing_required_column_raises(self):
        """Missing one required column → ValueError raised (columns checked first)."""
        df = _make_valid_df(3).drop(columns=["sensor_type"])
        with pytest.raises(ValueError, match="missing required columns"):
            validate_sensor_readings(df)

    def test_fail_missing_multiple_columns_raises(self):
        """Missing two columns → ValueError lists both."""
        df = _make_valid_df(3).drop(columns=["ts", "value"])
        with pytest.raises(ValueError, match="missing required columns"):
            validate_sensor_readings(df)

    # ── Rule 2: No NULLs in mandatory columns ────────────────────────────────

    def test_pass_none_in_optional_column_allowed(self):
        """failure_mode = None (optional column) → row retained."""
        df = _make_valid_df(3, failure_mode=None)
        result = validate_sensor_readings(df)
        assert len(result) == 3

    def test_fail_null_in_ts_drops_row(self):
        """ts = None → row dropped."""
        rows = [_make_valid_telemetry_row(), _make_valid_telemetry_row(ts=None)]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    def test_fail_null_in_component_id_drops_row(self):
        """component_id = None → row dropped."""
        rows = [_make_valid_telemetry_row(), _make_valid_telemetry_row(component_id=None)]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    def test_fail_null_in_value_drops_row(self):
        """value = None → row dropped."""
        rows = [_make_valid_telemetry_row(), _make_valid_telemetry_row(value=None)]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    # ── Rule 3: sensor_type ∈ VALID_SENSOR_TYPES ─────────────────────────────

    def test_pass_all_five_valid_sensor_types(self):
        """Each of the 5 valid sensor_types passes validation."""
        for stype in VALID_SENSOR_TYPES:
            df = _make_valid_df(2, sensor_type=stype)
            result = validate_sensor_readings(df)
            assert len(result) == 2, f"sensor_type '{stype}' should pass"

    def test_fail_invalid_sensor_type_drops_row(self):
        """sensor_type = 'pressure' (not in valid set) → row dropped."""
        rows = [
            _make_valid_telemetry_row(sensor_type="vibration"),
            _make_valid_telemetry_row(sensor_type="pressure"),   # invalid
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1
        assert result.iloc[0]["sensor_type"] == "vibration"

    def test_fail_empty_sensor_type_drops_row(self):
        """sensor_type = '' (empty string) → not in valid set → row dropped."""
        rows = [
            _make_valid_telemetry_row(sensor_type="temperature"),
            _make_valid_telemetry_row(sensor_type=""),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    def test_fail_mixed_case_sensor_type_drops_row(self):
        """sensor_type = 'Vibration' (wrong case) → not in set → dropped."""
        rows = [
            _make_valid_telemetry_row(sensor_type="vibration"),
            _make_valid_telemetry_row(sensor_type="Vibration"),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    # ── Rule 4: value >= 0.0 ─────────────────────────────────────────────────

    def test_pass_value_zero_retained(self):
        """value = 0.0 → exactly on lower bound → retained."""
        df = _make_valid_df(3, value=0.0)
        result = validate_sensor_readings(df)
        assert len(result) == 3

    def test_pass_value_positive_retained(self):
        """value = 150.0 (high temperature reading) → retained."""
        df = _make_valid_df(3, sensor_type="temperature", value=150.0)
        result = validate_sensor_readings(df)
        assert len(result) == 3

    def test_fail_negative_value_drops_row(self):
        """value = -0.001 → below 0 → dropped."""
        rows = [
            _make_valid_telemetry_row(value=2.5),
            _make_valid_telemetry_row(value=-0.001),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1
        assert result.iloc[0]["value"] == 2.5

    def test_fail_large_negative_value_drops_row(self):
        """value = -999.0 → dropped."""
        df = _make_valid_df(2, value=-999.0)
        result = validate_sensor_readings(df)
        assert len(result) == 0

    # ── Rule 5: is_failure_event ∈ {0, 1} ────────────────────────────────────

    def test_pass_is_failure_event_zero(self):
        """is_failure_event = 0 → valid."""
        df = _make_valid_df(3, is_failure_event=0)
        result = validate_sensor_readings(df)
        assert len(result) == 3

    def test_pass_is_failure_event_one(self):
        """is_failure_event = 1 → valid."""
        df = _make_valid_df(3, is_failure_event=1)
        result = validate_sensor_readings(df)
        assert len(result) == 3

    def test_fail_is_failure_event_two_drops_row(self):
        """is_failure_event = 2 → not in {0,1} → dropped."""
        rows = [
            _make_valid_telemetry_row(is_failure_event=0),
            _make_valid_telemetry_row(is_failure_event=2),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    # ── Rule 6: cascade_flag ∈ {0, 1} ────────────────────────────────────────

    def test_pass_cascade_flag_zero_and_one(self):
        """cascade_flag ∈ {0, 1} → both valid."""
        rows = [
            _make_valid_telemetry_row(cascade_flag=0),
            _make_valid_telemetry_row(cascade_flag=1),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 2

    def test_fail_cascade_flag_invalid_value_drops_row(self):
        """cascade_flag = 99 → dropped."""
        rows = [
            _make_valid_telemetry_row(cascade_flag=0),
            _make_valid_telemetry_row(cascade_flag=99),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    # ── Rule 7: R_derated ∈ [0.0, 1.0] where not NULL ───────────────────────

    def test_pass_r_derated_null_allowed(self):
        """R_derated = NaN → optional, retained."""
        df = _make_valid_df(3, R_derated=float("nan"))
        result = validate_sensor_readings(df)
        assert len(result) == 3

    def test_pass_r_derated_boundary_values(self):
        """R_derated = 0.0 and 1.0 → on boundaries → both retained."""
        rows = [
            _make_valid_telemetry_row(R_derated=0.0),
            _make_valid_telemetry_row(R_derated=1.0),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 2

    def test_fail_r_derated_above_one_drops_row(self):
        """R_derated = 1.01 → out of [0,1] → dropped."""
        rows = [
            _make_valid_telemetry_row(R_derated=0.85),
            _make_valid_telemetry_row(R_derated=1.01),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    def test_fail_r_derated_negative_drops_row(self):
        """R_derated = -0.1 → out of [0,1] → dropped."""
        rows = [
            _make_valid_telemetry_row(R_derated=0.7),
            _make_valid_telemetry_row(R_derated=-0.1),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    # ── Rule 8: health_score ∈ [0.0, 100.0] where not NULL ──────────────────

    def test_pass_health_score_null_allowed(self):
        """health_score = NaN → optional → retained."""
        df = _make_valid_df(3, health_score=float("nan"))
        result = validate_sensor_readings(df)
        assert len(result) == 3

    def test_pass_health_score_boundary_values(self):
        """health_score = 0.0 and 100.0 → both retained."""
        rows = [
            _make_valid_telemetry_row(health_score=0.0),
            _make_valid_telemetry_row(health_score=100.0),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 2

    def test_fail_health_score_above_100_drops_row(self):
        """health_score = 100.1 → out of [0,100] → dropped."""
        rows = [
            _make_valid_telemetry_row(health_score=95.0),
            _make_valid_telemetry_row(health_score=100.1),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    def test_fail_health_score_negative_drops_row(self):
        """health_score = -5.0 → dropped."""
        rows = [
            _make_valid_telemetry_row(health_score=80.0),
            _make_valid_telemetry_row(health_score=-5.0),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    # ── Rule 9: ts parseable as ISO 8601 ─────────────────────────────────────

    def test_fail_unparseable_ts_drops_row(self):
        """ts = 'not-a-date' → unparseable → dropped."""
        rows = [
            _make_valid_telemetry_row(ts="2026-07-20T00:00:00"),
            _make_valid_telemetry_row(ts="not-a-date"),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    # ── Empty DataFrame edge case ─────────────────────────────────────────────

    def test_pass_empty_dataframe_returns_empty(self):
        """Empty DataFrame with correct columns → empty result (no crash)."""
        df = pd.DataFrame(columns=SENSOR_READINGS_REQUIRED_COLS)
        result = validate_sensor_readings(df)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    # ── Multiple rules violated in same row ───────────────────────────────────

    def test_fail_multiple_violations_in_one_row(self):
        """Row violating value<0 AND invalid sensor_type → dropped."""
        rows = [
            _make_valid_telemetry_row(),
            _make_valid_telemetry_row(value=-1.0, sensor_type="invalid_type"),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 1

    # ── Return type and index ─────────────────────────────────────────────────

    def test_pass_result_is_dataframe(self):
        """Return type is always pd.DataFrame."""
        df = _make_valid_df(5)
        result = validate_sensor_readings(df)
        assert isinstance(result, pd.DataFrame)

    def test_pass_result_index_is_reset(self):
        """Returned DataFrame has a clean RangeIndex (reset_index called)."""
        rows = [
            _make_valid_telemetry_row(value=1.0),
            _make_valid_telemetry_row(value=-1.0),  # dropped
            _make_valid_telemetry_row(value=2.0),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert list(result.index) == list(range(len(result)))

    def test_pass_original_df_not_mutated(self):
        """Original DataFrame is not modified by validate_sensor_readings."""
        df = _make_valid_df(3, value=-5.0)   # all rows should be dropped
        original_len = len(df)
        _ = validate_sensor_readings(df)
        assert len(df) == original_len   # original unchanged


# ===========================================================================
# CLASS 2: TestNormalizeTimestamps — UTC normalization pass/fail
# ===========================================================================

class TestNormalizeTimestamps:
    """Unit tests for etl.normalize_timestamps()."""

    # ── Column existence guard ────────────────────────────────────────────────

    def test_fail_missing_ts_column_raises_key_error(self):
        """ts_column not in DataFrame → KeyError raised."""
        df = pd.DataFrame({"value": [1.0, 2.0]})
        with pytest.raises(KeyError, match="ts"):
            normalize_timestamps(df, ts_column="ts")

    # ── Naive ISO 8601 strings → UTC ─────────────────────────────────────────

    def test_pass_naive_iso_string_localized_to_utc(self):
        """Naive ISO 8601 string → tz_localize('UTC') → UTC-aware Timestamp."""
        df = pd.DataFrame({"ts": ["2026-07-20T00:00:00", "2026-07-20T02:00:00"]})
        result = normalize_timestamps(df, ts_column="ts")
        for ts in result["ts"]:
            assert ts.tzinfo is not None, "Result should be UTC-aware"
            assert str(ts.tzinfo) == "UTC"

    def test_pass_simulate_csv_format_with_trailing_zeros(self):
        """Typical simulate.py timestamp format with leading date part."""
        df = pd.DataFrame({"ts": [
            "2026-07-20T00:00:00",
            "2026-07-20T12:30:00",
            "2026-12-31T23:59:59",
        ]})
        result = normalize_timestamps(df, ts_column="ts")
        assert len(result) == 3
        assert result["ts"].dt.tz is not None

    # ── Custom column name ────────────────────────────────────────────────────

    def test_pass_custom_column_name(self):
        """ts_column parameter accepts non-default column names."""
        df = pd.DataFrame({"event_time": ["2026-07-20T10:00:00"]})
        result = normalize_timestamps(df, ts_column="event_time")
        assert "event_time" in result.columns
        assert result["event_time"].dt.tz is not None

    # ── Unparseable values dropped ────────────────────────────────────────────

    def test_fail_unparseable_ts_drops_row(self):
        """ts = 'INVALID' → coerce to NaT → row dropped."""
        df = pd.DataFrame({"ts": ["2026-07-20T00:00:00", "INVALID_DATE"]})
        result = normalize_timestamps(df, ts_column="ts")
        assert len(result) == 1

    def test_fail_all_invalid_ts_returns_empty(self):
        """All rows with invalid ts → empty DataFrame returned (no crash)."""
        df = pd.DataFrame({"ts": ["bad", "also-bad", ""]})
        result = normalize_timestamps(df, ts_column="ts")
        assert len(result) == 0

    # ── Already UTC-aware input ───────────────────────────────────────────────

    def test_pass_already_utc_aware_timestamps_remain_utc(self):
        """Input with UTC-aware datetimes → tz_convert → still UTC."""
        df = pd.DataFrame({"ts": pd.to_datetime(
            ["2026-07-20T00:00:00", "2026-07-20T06:00:00"], utc=True
        )})
        result = normalize_timestamps(df, ts_column="ts")
        assert len(result) == 2
        assert result["ts"].dt.tz is not None

    # ── Return type and index ─────────────────────────────────────────────────

    def test_pass_return_type_is_dataframe(self):
        """Return value is always pd.DataFrame."""
        df = pd.DataFrame({"ts": ["2026-07-20T00:00:00"]})
        result = normalize_timestamps(df, ts_column="ts")
        assert isinstance(result, pd.DataFrame)

    def test_pass_other_columns_preserved(self):
        """Non-ts columns are preserved unchanged after normalization."""
        df = pd.DataFrame({
            "ts":    ["2026-07-20T00:00:00", "2026-07-20T02:00:00"],
            "value": [1.5, 2.3],
            "sensor_type": ["vibration", "temperature"],
        })
        result = normalize_timestamps(df, ts_column="ts")
        assert "value" in result.columns
        assert "sensor_type" in result.columns
        assert list(result["value"]) == [1.5, 2.3]

    def test_pass_index_is_reset_after_dropping_rows(self):
        """After dropping unparseable rows, index is reset to RangeIndex."""
        df = pd.DataFrame({"ts": [
            "2026-07-20T00:00:00",
            "BAD_VALUE",
            "2026-07-20T04:00:00",
        ]})
        result = normalize_timestamps(df, ts_column="ts")
        assert list(result.index) == list(range(len(result)))

    def test_pass_original_df_not_mutated(self):
        """Original DataFrame ts column is not modified in-place."""
        original_values = ["2026-07-20T00:00:00", "2026-07-20T02:00:00"]
        df = pd.DataFrame({"ts": original_values})
        _ = normalize_timestamps(df, ts_column="ts")
        # Original should still be string
        assert df["ts"].iloc[0] == "2026-07-20T00:00:00"

    # ── Day 7 simulation anchor date ─────────────────────────────────────────

    def test_pass_day7_simulation_anchor_date(self):
        """Day 7 simulation starts at 2026-07-20T00:00:00 — verify correct parsing."""
        df = pd.DataFrame({"ts": ["2026-07-20T00:00:00"]})
        result = normalize_timestamps(df, ts_column="ts")
        ts = result["ts"].iloc[0]
        assert ts.year == 2026
        assert ts.month == 7
        assert ts.day == 20
        assert ts.hour == 0

    def test_pass_timestep_2h_correctly_parsed(self):
        """2-hour timestep progression (dt=2h from Day 7) is correctly parsed."""
        df = pd.DataFrame({"ts": [
            "2026-07-20T00:00:00",
            "2026-07-20T02:00:00",
            "2026-07-20T04:00:00",
        ]})
        result = normalize_timestamps(df, ts_column="ts")
        delta = result["ts"].iloc[1] - result["ts"].iloc[0]
        assert delta.total_seconds() == 7200.0  # 2 hours in seconds


# ===========================================================================
# CLASS 3: TestValidateSensorReadingsIntegration — multi-row realistic data
# ===========================================================================

class TestValidateSensorReadingsIntegration:
    """
    Integration-level tests for validate_sensor_readings() using realistic
    multi-row DataFrames that mimic multi_failure_telemetry.csv segments.
    """

    def test_pass_all_five_component_types_present(self):
        """
        Mix of rows from 5 components (Bearing, Shaft, Motor Housing,
        Coupling, Gearbox) → all retained when valid.
        """
        rows = [
            _make_valid_telemetry_row(component_id=1, sensor_type="vibration",    value=1.2),
            _make_valid_telemetry_row(component_id=2, sensor_type="rpm",          value=1490.0),
            _make_valid_telemetry_row(component_id=3, sensor_type="temperature",  value=120.0),
            _make_valid_telemetry_row(component_id=4, sensor_type="load",         value=75.0),
            _make_valid_telemetry_row(component_id=5, sensor_type="oil_debris",   value=30.0),
        ]
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 5

    def test_fail_batch_with_mixed_valid_invalid_rows(self):
        """
        10 rows where 3 are invalid → exactly 7 rows retained.
        """
        rows = (
            [_make_valid_telemetry_row(value=1.0)] * 7
            + [
                _make_valid_telemetry_row(value=-1.0),             # invalid: negative value
                _make_valid_telemetry_row(sensor_type="pressure"),  # invalid: bad type
                _make_valid_telemetry_row(is_failure_event=5),      # invalid: not in {0,1}
            ]
        )
        df = pd.DataFrame(rows)
        result = validate_sensor_readings(df)
        assert len(result) == 7

    def test_pass_failure_event_row_retained_with_failure_mode(self):
        """
        is_failure_event=1 with a failure_mode string → retained (valid failure row).
        """
        row = _make_valid_telemetry_row(
            is_failure_event=1,
            failure_mode="rolling_element_fatigue",
            R_derated=0.35,
            health_score=35.0,
        )
        df = pd.DataFrame([row])
        result = validate_sensor_readings(df)
        assert len(result) == 1
        assert result.iloc[0]["is_failure_event"] == 1

    def test_pass_cascade_flag_one_with_vibration_boost(self):
        """cascade_flag=1 with elevated vibration value → retained (cascade symptom row)."""
        row = _make_valid_telemetry_row(
            cascade_flag=1,
            sensor_type="vibration",
            value=5.8,  # Zone C — above alarm
        )
        df = pd.DataFrame([row])
        result = validate_sensor_readings(df)
        assert len(result) == 1

    def test_pass_health_score_exactly_zero_and_r_derated_near_zero(self):
        """
        Near-failure state: R_derated≈0.01, health_score≈1.0 → valid boundary values.
        """
        row = _make_valid_telemetry_row(
            R_derated=0.01,
            health_score=1.0,
            is_failure_event=0,
        )
        df = pd.DataFrame([row])
        result = validate_sensor_readings(df)
        assert len(result) == 1

    def test_fail_all_rows_invalid_returns_empty(self):
        """All rows violate value >= 0 → empty DataFrame returned."""
        df = _make_valid_df(20, value=-1.0)
        result = validate_sensor_readings(df)
        assert len(result) == 0
        assert isinstance(result, pd.DataFrame)
