"""
data_generator_oee.py — Manufacturing Analytics FYP
=====================================================
Day 11 — Phase 2.1: OEE Data Population

PURPOSE
-------
Populate the three empty OEE tables in manufacturing.db:
  - production_shifts     : one row per 8-hour shift, per component, 90 days
  - downtime_events       : aligned to failure_log TTF records + cascade propagation
  - production_counts     : unit output derived from shift run-time and rated throughput

DESIGN PRINCIPLES (locked today)
---------------------------------
1. Shifts are anchored to failure_log.  Each component's failure events appear in
   the correct shift so that the OEE queries can compute meaningful Availability.
2. Cascade rule (Day 2, CONTEXT.md): when component N fails, all downstream
   components at positions N+1…5 receive a concurrent 'cascade_upstream' downtime
   event for the full failure duration.
3. Three shift labels rotate: 'DAY' (06:00–14:00), 'SWING' (14:00–22:00),
   'NIGHT' (22:00–06:00).  Labels match the schema CHECK constraint locked Day 3.
4. Unit counts are derived stochastically from run-time using a rated throughput
   (units/hour) per component, with ±5% Gaussian noise.  Good/defective/rework
   splits follow fixed Quality baseline rates per component, degraded slightly
   in failure cycles.
5. Idempotent: INSERT OR IGNORE — safe to re-run without duplicating rows.
   NOTE: downtime_events and production_counts do NOT have UNIQUE constraints so
   the INSERT OR IGNORE trick works differently — duplicates are prevented by
   clearing tables before re-insert when this script is run.

FORMULA REFERENCES (CONTEXT.md)
---------------------------------
  A = (planned_duration_min − downtime_min) / planned_duration_min
  P = (ideal_cycle_time_min × total_units) / run_time_min
  Q = good_units / total_units

COMPONENT POSITIONS (topology.py)
-----------------------------------
  1 → Bearing        3 → Motor Housing   5 → Gearbox
  2 → Shaft          4 → Coupling

USAGE
------
  python python/data_generator_oee.py

Output: populates data/manufacturing.db tables (production_shifts, downtime_events,
        production_counts).  Prints row-count summary on completion.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# =============================================================================
# CONSTANTS
# =============================================================================

# Simulation parameters
RANDOM_SEED: int = 11               # Day 11 — distinct from simulate.py (42) and data_generator.py (7)
SIMULATION_DAYS: int = 90           # 90-day OEE observation window
SIMULATION_START: datetime = datetime(2026, 7, 20, 6, 0, 0)  # Anchored to Day 7 telemetry start

# Shift definitions — 3 shifts per calendar day per component
# Labels MUST match the CHECK constraint in schema.sql: IN ('DAY','NIGHT','SWING')
SHIFTS: List[Dict] = [
    {"label": "DAY",   "start_hour": 6,  "duration_min": 480},   # 06:00–14:00
    {"label": "SWING", "start_hour": 14, "duration_min": 480},   # 14:00–22:00
    {"label": "NIGHT", "start_hour": 22, "duration_min": 480},   # 22:00–06:00 (+1 day)
]

# Pipeline topology — positions match component_id in seed.sql
PIPELINE_ORDER: List[int] = [1, 2, 3, 4, 5]           # component_ids
COMPONENT_NAMES: Dict[int, str] = {
    1: "Bearing",
    2: "Shaft",
    3: "Motor Housing",
    4: "Coupling",
    5: "Gearbox",
}

# Maintenance strategies — needed for MTTR assignment (locked Day 1)
MAINTENANCE_STRATEGY: Dict[int, str] = {
    1: "PM",        # Bearing
    2: "CBM",       # Shaft
    3: "CBM",       # Motor Housing
    4: "CBM",       # Coupling
    5: "PM_CBM",    # Gearbox
}

# MTTR per strategy in hours (locked Day 7 — MultiFailureConfig.mttr_hours)
MTTR_HOURS: Dict[str, float] = {
    "PM":     8.0,
    "CBM":   12.0,
    "PM_CBM": 10.0,
}

# Rated throughput — units per hour per component at full speed (nameplate design rate)
# Chosen to produce realistic OEE: ~85–95% performance at nominal operation
RATED_THROUGHPUT_UPH: Dict[int, float] = {
    1: 120.0,   # Bearing       (fast-spinning machine: 120 u/h)
    2: 100.0,   # Shaft         (medium throughput)
    3:  90.0,   # Motor Housing (thermal constraint reduces rate)
    4: 110.0,   # Coupling      (mid-chain conveyor speed)
    5:  80.0,   # Gearbox       (slowest — torque step-down)
}

# Ideal cycle time (min/unit) = 60 / rated_throughput_uph
IDEAL_CYCLE_TIME_MIN: Dict[int, float] = {
    cid: 60.0 / uph for cid, uph in RATED_THROUGHPUT_UPH.items()
}

# Baseline quality rates (fraction of units that are good) — no failure in this cycle
BASELINE_QUALITY: Dict[int, float] = {
    1: 0.980,   # Bearing — surface defects rare at nominal
    2: 0.990,   # Shaft — fatigue cracks unlikely in 1 cycle
    3: 0.975,   # Motor Housing — winding partial faults cause occasional defect
    4: 0.985,   # Coupling — misalignment causes periodic reject
    5: 0.970,   # Gearbox — tooth surface variation highest reject source
}

# Quality degradation factor during a failure cycle (multiplied onto baseline)
FAILURE_QUALITY_FACTOR: float = 0.90  # quality drops ~10% in the failure shift

# Fraction of non-good units that are rework (remainder = scrap/defective)
REWORK_FRACTION: float = 0.40

# Failure mode labels per component (for downtime_events.failure_mode)
FAILURE_MODES: Dict[int, str] = {
    1: "rolling_element_fatigue",
    2: "fatigue_imbalance",
    3: "winding_insulation_degradation",
    4: "elastomer_ageing",
    5: "gear_tooth_pitting",
}

# Downtime type mapping (locked Day 2 taxonomy)
DOWNTIME_TYPE: Dict[str, str] = {
    "unplanned_failure":   "equipment",
    "planned_maintenance": "equipment",
    "changeover":          "process",
    "idle":                "process",
    "cascade_upstream":    "equipment",
}

# Planned maintenance windows inserted once per component every ~30 days
# Duration in minutes; does NOT overlap with unplanned failure shifts
PLANNED_MAINTENANCE_INTERVAL_DAYS: int = 30
PLANNED_MAINTENANCE_DURATION_MIN: float = 120.0  # 2-hour scheduled PM window per shift

# Idle event probability per shift (minor stop / material wait)
IDLE_PROBABILITY: float = 0.08        # 8% of shifts have a short idle event
IDLE_DURATION_MEAN_MIN: float = 20.0  # Mean idle event duration
IDLE_DURATION_STD_MIN: float = 8.0

# Database path (relative to project root)
DB_PATH: str = "data/manufacturing.db"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def shift_window(
    base_date: datetime,
    shift_def: Dict,
) -> Tuple[datetime, datetime]:
    """
    Compute the planned start and end timestamps for one shift on base_date.

    The 'NIGHT' shift (22:00–06:00) crosses midnight: end_ts = next calendar
    day 06:00.

    Parameters
    ----------
    base_date : datetime  — Calendar date for this shift (time component ignored)
    shift_def : dict      — One entry from SHIFTS list

    Returns
    -------
    (planned_start_ts, planned_end_ts)
    """
    day_start = base_date.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ts = day_start + timedelta(hours=shift_def["start_hour"])
    end_ts = start_ts + timedelta(minutes=shift_def["duration_min"])
    return start_ts, end_ts


def failure_overlaps_shift(
    failure_abs_start_h: float,
    failure_duration_h: float,
    window_start: datetime,
    window_end: datetime,
    sim_epoch: datetime,
) -> Tuple[bool, float, float]:
    """
    Test whether a failure event (in absolute simulation hours from sim_epoch)
    overlaps with a production shift window.

    Parameters
    ----------
    failure_abs_start_h  : float — Failure start time in hours from sim_epoch
    failure_duration_h   : float — Failure/repair duration in hours
    window_start         : datetime — Shift planned start
    window_end           : datetime — Shift planned end
    sim_epoch            : datetime — Simulation start reference (SIMULATION_START)

    Returns
    -------
    (overlaps: bool, overlap_start_h: float, overlap_end_h: float)
        overlap_* are in absolute simulation hours
    """
    # Convert shift timestamps to simulation hours
    shift_start_h = (window_start - sim_epoch).total_seconds() / 3600.0
    shift_end_h   = (window_end   - sim_epoch).total_seconds() / 3600.0

    failure_end_h = failure_abs_start_h + failure_duration_h

    # Clamp failure to shift window
    overlap_start_h = max(failure_abs_start_h, shift_start_h)
    overlap_end_h   = min(failure_end_h,       shift_end_h)

    if overlap_end_h > overlap_start_h:
        return True, overlap_start_h, overlap_end_h
    return False, 0.0, 0.0


def hours_to_dt(abs_hours: float, epoch: datetime) -> datetime:
    """Convert simulation-relative hours (float) to a datetime."""
    return epoch + timedelta(hours=abs_hours)


# =============================================================================
# STAGE 1 — Build failure event timeline from failure_log
# =============================================================================

def load_failure_events(conn: sqlite3.Connection) -> Dict[int, List[Dict]]:
    """
    Read failure_log and reconstruct the absolute failure timeline per component.

    The multi-failure simulation runs sequentially per component: cycle 1 → repair
    → cycle 2 → repair → …  Each failure starts at the cumulative sum of all
    prior TTFs and repairs.

    repair_hours may be NULL in failure_log (was not populated by data_generator.py).
    In that case, MTTR defaults from MTTR_HOURS[strategy] are used.

    Returns
    -------
    Dict[component_id, List[{cycle, ttf_h, repair_h, abs_start_h, abs_end_h, failure_mode}]]
    """
    rows = conn.execute(
        """
        SELECT fl.component_id, fl.cycle_number, fl.ttf_hours, fl.repair_hours,
               fl.failure_mode, fl.strategy
        FROM failure_log fl
        ORDER BY fl.component_id, fl.cycle_number
        """
    ).fetchall()

    timeline: Dict[int, List[Dict]] = {cid: [] for cid in PIPELINE_ORDER}

    # Accumulate absolute start time per component
    running_hours: Dict[int, float] = {cid: 0.0 for cid in PIPELINE_ORDER}

    for row in rows:
        cid, cycle, ttf_h, repair_h, failure_mode, strategy = row

        # repair_hours is NULL in failure_log — use MTTR default
        if repair_h is None:
            strat = strategy or MAINTENANCE_STRATEGY.get(cid, "CBM")
            repair_h = MTTR_HOURS.get(strat, 12.0)

        abs_fail_start_h = running_hours[cid] + ttf_h   # failure begins at TTF
        abs_fail_end_h   = abs_fail_start_h + repair_h  # failure ends after repair

        timeline[cid].append({
            "cycle":            cycle,
            "ttf_h":            ttf_h,
            "repair_h":         repair_h,
            "abs_fail_start_h": abs_fail_start_h,   # hours from SIMULATION_START
            "abs_fail_end_h":   abs_fail_end_h,
            "failure_mode":     failure_mode or FAILURE_MODES.get(cid, "unknown"),
        })

        running_hours[cid] = abs_fail_end_h  # next cycle starts after repair

    return timeline


# =============================================================================
# STAGE 2 — Generate production_shifts
# =============================================================================

def generate_shifts(conn: sqlite3.Connection) -> Dict[Tuple[int, str, str], int]:
    """
    Generate and INSERT production_shifts rows.

    90 days × 3 shifts/day × 5 components = 1,350 rows total.
    INSERT OR IGNORE is used — safe to re-run.

    Returns
    -------
    Dict[(component_id, shift_date_str, shift_label), shift_id]
    """
    rows = []

    for day_offset in range(SIMULATION_DAYS):
        base_date = SIMULATION_START + timedelta(days=day_offset)
        shift_date_str = base_date.strftime("%Y-%m-%d")

        for shift_def in SHIFTS:
            start_ts, end_ts = shift_window(base_date, shift_def)
            duration_min = shift_def["duration_min"]

            for cid in PIPELINE_ORDER:
                rows.append({
                    "component_id":       cid,
                    "shift_date":         shift_date_str,
                    "shift_label":        shift_def["label"],
                    "planned_start_ts":   start_ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "planned_end_ts":     end_ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "planned_duration_min": float(duration_min),
                })

    conn.executemany(
        """
        INSERT OR IGNORE INTO production_shifts
            (component_id, shift_date, shift_label,
             planned_start_ts, planned_end_ts, planned_duration_min)
        VALUES
            (:component_id, :shift_date, :shift_label,
             :planned_start_ts, :planned_end_ts, :planned_duration_min)
        """,
        rows,
    )
    conn.commit()

    # Read back the DB-assigned shift_ids
    db_rows = conn.execute(
        """
        SELECT shift_id, component_id, shift_date, shift_label
        FROM production_shifts
        ORDER BY shift_id
        """
    ).fetchall()

    result: Dict[Tuple[int, str, str], int] = {}
    for r in db_rows:
        sid, cid, sdate, slabel = r
        result[(cid, sdate, slabel)] = sid

    print(f"  production_shifts: {len(db_rows)} rows inserted / verified.")
    return result


# =============================================================================
# STAGE 3 — Generate downtime_events
# =============================================================================

def generate_downtime_events(
    conn: sqlite3.Connection,
    shift_map: Dict[Tuple[int, str, str], int],
    failure_timeline: Dict[int, List[Dict]],
    rng: np.random.Generator,
) -> int:
    """
    Generate and INSERT downtime_events rows for three categories:
      1. unplanned_failure — from failure_log; cascade events on downstream components
      2. planned_maintenance — fixed window every 30 days per component
      3. idle — stochastic minor stops (8% probability per shift)

    Cascade rule (CONTEXT.md Day 2):
      When component at position N fails, all components at positions N+1…5
      receive a 'cascade_upstream' event for the same duration/window.
      root_cause_component_id = failing component's component_id.

    Returns total rows inserted.
    """
    downtime_rows: List[Dict] = []

    # ── Helper: collect shift metadata once ──────────────────────────────────
    component_shifts: Dict[int, List[Tuple]] = {cid: [] for cid in PIPELINE_ORDER}
    db_shifts = conn.execute(
        """
        SELECT shift_id, component_id, shift_date, shift_label,
               planned_start_ts, planned_end_ts
        FROM production_shifts
        ORDER BY component_id, planned_start_ts
        """
    ).fetchall()

    for r in db_shifts:
        sid, cid, sdate, slabel, pstart_str, pend_str = r
        component_shifts[cid].append((sid, sdate, slabel, pstart_str, pend_str))

    # ── 1. Unplanned failures (from failure_log timeline) ────────────────────
    for cid, events in failure_timeline.items():
        for ev in events:
            abs_start_h = ev["abs_fail_start_h"]
            abs_end_h   = ev["abs_fail_end_h"]
            fail_mode   = ev["failure_mode"]

            # Root component gets 'unplanned_failure' events
            _collect_failure_downtime(
                downtime_rows,
                component_shifts[cid],
                cid,
                abs_start_h,
                abs_end_h,
                fail_mode,
                "unplanned_failure",
                root_cause_cid=None,
            )

            # Cascade: inject 'cascade_upstream' events on downstream components
            downstream_cids = [c for c in PIPELINE_ORDER if c > cid]
            for d_cid in downstream_cids:
                _collect_failure_downtime(
                    downtime_rows,
                    component_shifts[d_cid],
                    d_cid,
                    abs_start_h,
                    abs_end_h,
                    fail_mode,
                    "cascade_upstream",
                    root_cause_cid=cid,
                )

    # ── 2. Planned maintenance windows ───────────────────────────────────────
    for cid in PIPELINE_ORDER:
        for interval_start_day in range(
            PLANNED_MAINTENANCE_INTERVAL_DAYS,
            SIMULATION_DAYS,
            PLANNED_MAINTENANCE_INTERVAL_DAYS,
        ):
            pm_date = SIMULATION_START + timedelta(days=interval_start_day)
            pm_date_str = pm_date.strftime("%Y-%m-%d")

            # Place PM in the 'DAY' shift (standard practice)
            key = (cid, pm_date_str, "DAY")
            if key not in shift_map:
                continue
            sid = shift_map[key]

            # PM occupies the first 2 hours of the DAY shift
            pm_start = pm_date.replace(hour=6, minute=0, second=0, microsecond=0)
            pm_end   = pm_start + timedelta(minutes=PLANNED_MAINTENANCE_DURATION_MIN)

            downtime_rows.append({
                "component_id":           cid,
                "shift_id":               sid,
                "start_ts":               pm_start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_ts":                 pm_end.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_min":           PLANNED_MAINTENANCE_DURATION_MIN,
                "downtime_category":      "planned_maintenance",
                "downtime_type":          DOWNTIME_TYPE["planned_maintenance"],
                "failure_mode":           None,
                "component_name":         COMPONENT_NAMES[cid],
                "root_cause_component_id": None,
            })

    # ── 3. Idle events (stochastic minor stops) ───────────────────────────────
    for r in db_shifts:
        sid, cid, sdate, slabel, pstart_str, pend_str = r
        if rng.random() < IDLE_PROBABILITY:
            idle_dur_min = float(
                np.clip(
                    rng.normal(IDLE_DURATION_MEAN_MIN, IDLE_DURATION_STD_MIN),
                    5.0, 60.0,
                )
            )
            pstart_dt = datetime.strptime(pstart_str, "%Y-%m-%d %H:%M:%S")
            pend_dt   = datetime.strptime(pend_str,   "%Y-%m-%d %H:%M:%S")
            shift_dur_min = (pend_dt - pstart_dt).total_seconds() / 60.0

            max_offset_min = max(0.0, shift_dur_min * 0.75 - idle_dur_min)
            offset_min = rng.uniform(0, max_offset_min) if max_offset_min > 0 else 0.0
            idle_start = pstart_dt + timedelta(minutes=offset_min)
            idle_end   = idle_start + timedelta(minutes=idle_dur_min)

            # Clamp end to shift end
            if idle_end > pend_dt:
                idle_end = pend_dt
                idle_dur_min = (idle_end - idle_start).total_seconds() / 60.0

            if idle_dur_min < 1.0:
                continue

            downtime_rows.append({
                "component_id":           cid,
                "shift_id":               sid,
                "start_ts":               idle_start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_ts":                 idle_end.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_min":           round(idle_dur_min, 2),
                "downtime_category":      "idle",
                "downtime_type":          DOWNTIME_TYPE["idle"],
                "failure_mode":           None,
                "component_name":         COMPONENT_NAMES[cid],
                "root_cause_component_id": None,
            })

    # ── Batch INSERT ──────────────────────────────────────────────────────────
    conn.executemany(
        """
        INSERT INTO downtime_events
            (component_id, shift_id, start_ts, end_ts, duration_min,
             downtime_category, downtime_type, failure_mode,
             component_name, root_cause_component_id)
        VALUES
            (:component_id, :shift_id, :start_ts, :end_ts, :duration_min,
             :downtime_category, :downtime_type, :failure_mode,
             :component_name, :root_cause_component_id)
        """,
        downtime_rows,
    )
    conn.commit()
    print(f"  downtime_events:   {len(downtime_rows)} rows inserted.")
    return len(downtime_rows)


def _collect_failure_downtime(
    rows: List[Dict],
    shifts_for_component: List[Tuple],
    component_id: int,
    abs_start_h: float,
    abs_end_h: float,
    failure_mode: str,
    category: str,
    root_cause_cid: Optional[int],
) -> None:
    """
    Helper: find all pre-fetched shifts that overlap (abs_start_h, abs_end_h)
    for a component and append one downtime_events row per overlapping shift.

    Duration clipped to the shift window — a failure spanning multiple shifts
    creates one row per shift with the overlapping minutes only.
    """
    failure_dur_h = abs_end_h - abs_start_h

    for r in shifts_for_component:
        sid, sdate, slabel, pstart_str, pend_str = r
        pstart_dt = datetime.strptime(pstart_str, "%Y-%m-%d %H:%M:%S")
        pend_dt   = datetime.strptime(pend_str,   "%Y-%m-%d %H:%M:%S")

        overlaps, ov_start_h, ov_end_h = failure_overlaps_shift(
            abs_start_h, failure_dur_h, pstart_dt, pend_dt, SIMULATION_START
        )
        if not overlaps:
            continue

        dt_start = hours_to_dt(ov_start_h, SIMULATION_START)
        dt_end   = hours_to_dt(ov_end_h,   SIMULATION_START)
        dur_min  = round((ov_end_h - ov_start_h) * 60.0, 2)

        if dur_min < 1.0:
            continue

        rows.append({
            "component_id":            component_id,
            "shift_id":                sid,
            "start_ts":                dt_start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_ts":                  dt_end.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_min":            dur_min,
            "downtime_category":       category,
            "downtime_type":           DOWNTIME_TYPE[category],
            "failure_mode":            failure_mode if category == "unplanned_failure" else None,
            "component_name":          COMPONENT_NAMES[component_id],
            "root_cause_component_id": root_cause_cid,
        })


# =============================================================================
# STAGE 4 — Generate production_counts
# =============================================================================

def generate_production_counts(
    conn: sqlite3.Connection,
    rng: np.random.Generator,
) -> int:
    """
    Generate and INSERT production_counts rows — one per (component_id, shift_id).

    Algorithm
    ---------
    1. Compute run_time_min = planned_duration_min − SUM(unplanned + cascade + idle
       downtime).  planned_maintenance is excluded from planned time per Day 2 design.
    2. Total units = run_time_min / ideal_cycle_time_min × noise(1 ± 0.05)
    3. Quality rate = BASELINE_QUALITY[cid], degraded if the shift overlaps a failure
    4. good_units, defective_units, rework_units are derived to satisfy the
       invariant: good + defective + rework = total (locked Day 3)

    Returns total rows inserted.
    """
    # Aggregate downtime per shift per component (exclude planned_maintenance)
    downtime_agg = conn.execute(
        """
        SELECT de.shift_id, de.component_id,
               SUM(CASE WHEN de.downtime_category != 'planned_maintenance'
                        THEN de.duration_min ELSE 0.0 END) AS total_down_min
        FROM downtime_events de
        GROUP BY de.shift_id, de.component_id
        """
    ).fetchall()
    downtime_map: Dict[Tuple[int, int], float] = {}
    for r in downtime_agg:
        sid, cid, total_down = r
        downtime_map[(sid, cid)] = total_down if total_down else 0.0

    # Flag shifts that have unplanned failure events
    failure_shift_set: set = set()
    for r in conn.execute(
        "SELECT DISTINCT shift_id, component_id FROM downtime_events "
        "WHERE downtime_category = 'unplanned_failure'"
    ).fetchall():
        failure_shift_set.add((r[0], r[1]))

    # Flag shifts that have cascade events (partial degradation)
    cascade_shift_set: set = set()
    for r in conn.execute(
        "SELECT DISTINCT shift_id, component_id FROM downtime_events "
        "WHERE downtime_category = 'cascade_upstream'"
    ).fetchall():
        cascade_shift_set.add((r[0], r[1]))

    # Fetch all shifts
    all_shifts = conn.execute(
        "SELECT shift_id, component_id, planned_duration_min FROM production_shifts "
        "ORDER BY shift_id"
    ).fetchall()

    count_rows: List[Dict] = []

    for r in all_shifts:
        sid, cid, planned_dur_min = r

        # Run time
        down_min = downtime_map.get((sid, cid), 0.0)
        run_time_min = max(planned_dur_min - down_min, 0.0)

        if run_time_min < 1.0:
            # Full downtime shift — 0 production
            total_units    = 0
            good_units     = 0
            defective_units = 0
            rework_units   = 0
        else:
            # Unit count with ±5% noise around rated throughput
            ict         = IDEAL_CYCLE_TIME_MIN[cid]
            ideal_units = run_time_min / ict
            noise_factor = float(np.clip(rng.normal(1.0, 0.05), 0.85, 1.10))
            total_units  = max(1, int(ideal_units * noise_factor))

            # Quality rate — degraded on failure/cascade shifts
            q_rate = BASELINE_QUALITY[cid]
            if (sid, cid) in failure_shift_set:
                q_rate *= FAILURE_QUALITY_FACTOR
            elif (sid, cid) in cascade_shift_set:
                # Partial quality degradation from upstream cascade
                q_rate *= (1.0 + FAILURE_QUALITY_FACTOR) / 2.0
            q_rate = max(0.80, min(1.0, q_rate))

            good_units    = int(total_units * q_rate)
            non_good      = total_units - good_units
            rework_units  = int(non_good * REWORK_FRACTION)
            defective_units = non_good - rework_units

            # Reconciliation invariant (locked Day 3): good + defective + rework = total
            good_units = total_units - defective_units - rework_units

        count_rows.append({
            "component_id":              cid,
            "shift_id":                  sid,
            "total_units":               total_units,
            "good_units":                good_units,
            "defective_units":           defective_units,
            "rework_units":              rework_units,
            "ideal_cycle_time_min":      IDEAL_CYCLE_TIME_MIN[cid],
            "defect_source_component_id": None,
        })

    conn.executemany(
        """
        INSERT INTO production_counts
            (component_id, shift_id, total_units, good_units,
             defective_units, rework_units, ideal_cycle_time_min,
             defect_source_component_id)
        VALUES
            (:component_id, :shift_id, :total_units, :good_units,
             :defective_units, :rework_units, :ideal_cycle_time_min,
             :defect_source_component_id)
        """,
        count_rows,
    )
    conn.commit()
    print(f"  production_counts: {len(count_rows)} rows inserted.")
    return len(count_rows)


# =============================================================================
# STAGE 5 — Verification query
# =============================================================================

def verify_oee_tables(conn: sqlite3.Connection) -> None:
    """Run a quick spot-check OEE calculation across all populated shifts."""
    print("\n  === OEE Spot-Check (first 5 shifts, component 1) ===")
    spot = conn.execute(
        """
        WITH dt AS (
            SELECT shift_id, component_id,
                   SUM(CASE WHEN downtime_category != 'planned_maintenance'
                            THEN duration_min ELSE 0.0 END) AS down_min
            FROM downtime_events
            GROUP BY shift_id, component_id
        )
        SELECT
            ps.component_id,
            ps.shift_date,
            ps.shift_label,
            ROUND((ps.planned_duration_min - COALESCE(dt.down_min,0))
                   / ps.planned_duration_min * 100.0, 1) AS avail_pct,
            ROUND(MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units)
                   / MAX(1, ps.planned_duration_min - COALESCE(dt.down_min,0)))
                   * 100.0, 1) AS perf_pct,
            ROUND(CAST(pc.good_units AS FLOAT) / MAX(1, pc.total_units)
                   * 100.0, 1) AS qual_pct
        FROM production_shifts ps
        LEFT JOIN dt ON dt.shift_id = ps.shift_id AND dt.component_id = ps.component_id
        LEFT JOIN production_counts pc ON pc.shift_id = ps.shift_id
                                       AND pc.component_id = ps.component_id
        WHERE ps.component_id = 1
        ORDER BY ps.shift_date, ps.shift_label
        LIMIT 5
        """
    ).fetchall()

    print(f"  {'CID':>4}  {'Date':>12}  {'Sh':>5}  {'A%':>6}  {'P%':>6}  {'Q%':>6}")
    for row in spot:
        cid, sdate, slabel, a, p, q = row
        a_s = f"{a:.1f}" if a is not None else "N/A"
        p_s = f"{p:.1f}" if p is not None else "N/A"
        q_s = f"{q:.1f}" if q is not None else "N/A"
        print(f"  {cid:>4}  {sdate:>12}  {slabel:>5}  {a_s:>6}  {p_s:>6}  {q_s:>6}")

    # Summary stats across all shifts/components
    summary = conn.execute(
        """
        WITH dt AS (
            SELECT shift_id, component_id,
                   SUM(CASE WHEN downtime_category != 'planned_maintenance'
                            THEN duration_min ELSE 0.0 END) AS down_min
            FROM downtime_events GROUP BY shift_id, component_id
        )
        SELECT
            COUNT(*)                   AS n_shifts,
            ROUND(AVG((ps.planned_duration_min - COALESCE(dt.down_min,0))
                  / ps.planned_duration_min * 100.0), 1) AS avg_avail_pct,
            ROUND(AVG(CAST(pc.good_units AS FLOAT) / MAX(1, pc.total_units)
                  * 100.0), 1)        AS avg_qual_pct,
            SUM(pc.total_units)        AS total_units_all,
            SUM(pc.good_units)         AS total_good_all
        FROM production_shifts ps
        LEFT JOIN dt ON dt.shift_id = ps.shift_id AND dt.component_id = ps.component_id
        LEFT JOIN production_counts pc ON pc.shift_id = ps.shift_id
                                       AND pc.component_id = ps.component_id
        """
    ).fetchone()

    if summary:
        n, avg_a, avg_q, tot, good = summary
        n    = n    or 0
        tot  = tot  or 0
        good = good or 0
        print(f"\n  Total shifts:           {n:,}")
        print(f"  Fleet avg Availability: {avg_a}%")
        print(f"  Fleet avg Quality:      {avg_q}%")
        print(f"  Total units produced:   {tot:,}")
        print(f"  Total good units:       {good:,}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run(db_path: str = DB_PATH) -> None:
    """
    End-to-end OEE data population pipeline.

    1. Connect to existing manufacturing.db (must be pre-populated by etl.py)
    2. Load failure timeline from failure_log
    3. Generate + insert production_shifts
    4. Generate + insert downtime_events
    5. Generate + insert production_counts
    6. Run spot-check verification
    """
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(
            f"Database not found at '{db_path}'.  "
            "Run python/etl.py first to create and seed the database."
        )

    rng = np.random.default_rng(RANDOM_SEED)

    print(f"[data_generator_oee] Connecting to {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # Clear existing OEE data to ensure clean re-run
    existing_shifts = conn.execute("SELECT COUNT(*) FROM production_shifts").fetchone()[0]
    if existing_shifts > 0:
        print(f"  Clearing existing OEE data ({existing_shifts} shifts) ...")
        conn.execute("DELETE FROM production_counts")
        conn.execute("DELETE FROM downtime_events")
        conn.execute("DELETE FROM production_shifts")
        conn.commit()

    # Stage 1 — Load failure timeline from DB
    print("\n[Stage 1] Loading failure_log timeline ...")
    failure_timeline = load_failure_events(conn)
    total_events = sum(len(v) for v in failure_timeline.values())
    n_comps_with_failures = sum(1 for v in failure_timeline.values() if v)
    print(f"  {total_events} failure events across {n_comps_with_failures} components")

    # Stage 2 — Shifts
    print("\n[Stage 2] Generating production_shifts ...")
    shift_map = generate_shifts(conn)

    # Stage 3 — Downtime
    print("\n[Stage 3] Generating downtime_events ...")
    n_downtime = generate_downtime_events(conn, shift_map, failure_timeline, rng)

    # Stage 4 — Counts
    print("\n[Stage 4] Generating production_counts ...")
    n_counts = generate_production_counts(conn, rng)

    # Stage 5 — Verify
    print("\n[Stage 5] Verification ...")
    verify_oee_tables(conn)

    conn.close()
    print("\n[data_generator_oee] DONE — OEE tables populated successfully.")
    print(f"  Shifts: {len(shift_map)}  |  Downtime events: {n_downtime}  |  Count rows: {n_counts}")


if __name__ == "__main__":
    run()
