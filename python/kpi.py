"""
kpi.py — Manufacturing Analytics FYP
======================================
OEE (Overall Equipment Effectiveness) Calculation Engine
Day 2 Draft — Phase 1, Sub-phase 1.1

PURPOSE
-------
Translate the three OEE pillars — Availability, Performance, Quality — into
concrete Python functions that operate on data pulled from the SQL database.
Each function is documented with:
  - The mathematical formula it implements
  - The exact SQL table + column names it consumes
  - The expected return value and its units

MATHEMATICAL FOUNDATION
-----------------------
OEE = Availability (A) x Performance (P) x Quality (Q)

Where:
  A = (Planned Production Time - Downtime) / Planned Production Time
  P = (Ideal Cycle Time x Total Count) / Run Time
  Q = Good Count / Total Count

World-class OEE target = 85%+ (Nakajima, 1988)
For a series system of 5 components, system OEE is constrained by the
weakest-performing component.  We calculate both:
  (a) per-component OEE  -> for drill-down diagnostics
  (b) system OEE         -> A_sys x P_sys x Q_sys  (series product rule)

SQL DATA REQUIREMENTS
---------------------
Tables consumed by this module (to be created in schema.sql, Day 3):

  Table: production_shifts
    - shift_id              INTEGER PRIMARY KEY
    - component_id          INTEGER  FK -> components.component_id
    - shift_date            DATE
    - planned_start_ts      DATETIME   -- scheduled start of production window
    - planned_end_ts        DATETIME   -- scheduled end of production window
    - planned_duration_min  FLOAT      -- (planned_end - planned_start) in minutes

  Table: downtime_events
    - downtime_id           INTEGER PRIMARY KEY
    - component_id          INTEGER  FK -> components.component_id
    - shift_id              INTEGER  FK -> production_shifts.shift_id
    - start_ts              DATETIME
    - end_ts                DATETIME
    - duration_min          FLOAT    -- (end_ts - start_ts) in minutes
    - downtime_category     VARCHAR  -- 'unplanned_failure' | 'planned_maintenance'
                                     --  | 'changeover' | 'idle' | 'cascade_upstream'
    - downtime_type         VARCHAR  -- 'equipment' | 'process' | 'quality'
    - failure_mode          VARCHAR  -- e.g. 'bearing_seizure', 'overtemp_shutdown'
    - component_name        VARCHAR  -- denormalized for query convenience

  Table: production_counts
    - count_id              INTEGER PRIMARY KEY
    - component_id          INTEGER  FK -> components.component_id
    - shift_id              INTEGER  FK -> production_shifts.shift_id
    - total_units           INTEGER  -- all units produced (good + defective)
    - good_units            INTEGER  -- units passing quality inspection
    - defective_units       INTEGER  -- units rejected / scrapped
    - rework_units          INTEGER  -- units requiring rework (counted as defective for OEE)
    - ideal_cycle_time_min  FLOAT    -- nameplate/design cycle time per unit (minutes)
    - defect_source_component_id  INTEGER FK -> components
                                     -- root-cause attribution for quality drill-down

  Table: sensor_readings  (already in Day 1 schema -- referenced for Performance calc)
    - reading_id    INTEGER PRIMARY KEY
    - component_id  INTEGER  FK -> components.component_id
    - ts            DATETIME
    - rpm           FLOAT    -- actual machine speed (rotations per minute)
    - rpm_rated     FLOAT    -- nameplate rated speed
    - load_pct      FLOAT    -- % of rated load (0-100)

  Table: components
    - component_id      INTEGER PRIMARY KEY
    - component_name    VARCHAR  -- 'Bearing','Shaft','Motor Housing','Coupling','Gearbox'
    - position_in_chain INTEGER  -- 1 through 5 (series order)

SERIES SYSTEM NOTE
------------------
Because [Bearing]->[Shaft]->[Motor Housing]->[Coupling]->[Gearbox] is a series chain:
  - If Bearing is down, ALL downstream components are also effectively down.
  - We track downtime at the component level but roll up to system level for OEE.
  - A downtime_event for Bearing cascades: downstream components are tagged with
    downtime_category = 'cascade_upstream' so they are not double-penalised
    in their individual availability but ARE visible in the system drill-down.
"""

from __future__ import annotations

import pandas as pd
from typing import Optional


# =============================================================================
# CONSTANTS
# =============================================================================

COMPONENTS: list[str] = [
    "Bearing",
    "Shaft",
    "Motor Housing",
    "Coupling",
    "Gearbox",
]

# Cascade order: index 0 is upstream (Bearing), index 4 is most downstream
SERIES_ORDER: dict[str, int] = {name: idx + 1 for idx, name in enumerate(COMPONENTS)}

# World-class OEE benchmark (Nakajima, 1988)
OEE_WORLD_CLASS: float = 0.85

# Minimum acceptable OEE before escalation alert
OEE_ALERT_THRESHOLD: float = 0.65


# =============================================================================
# HELPER UTILITIES
# =============================================================================

def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Perform division, returning `default` if denominator is zero.
    Prevents ZeroDivisionError when a shift had zero planned time or zero count.

    Parameters
    ----------
    numerator   : float
    denominator : float
    default     : float -- returned when denominator == 0 (default: 0.0)

    Returns
    -------
    float -- result of division or default
    """
    if denominator == 0:
        return default
    return numerator / denominator


def validate_oee_component(value: float, label: str) -> float:
    """
    Clamp an OEE sub-factor to [0.0, 1.0] and warn if out of range.
    Values > 1.0 indicate a data error (e.g., more good units than total units).

    Parameters
    ----------
    value : float -- computed sub-factor
    label : str   -- 'Availability' | 'Performance' | 'Quality'

    Returns
    -------
    float -- clamped to [0, 1]
    """
    if not (0.0 <= value <= 1.0):
        print(f"[WARN] {label} = {value:.4f} is outside [0, 1]. "
              f"Clamping and flagging for data review.")
        return max(0.0, min(1.0, value))
    return value


# =============================================================================
# 1. AVAILABILITY
# =============================================================================

def compute_availability(
    planned_duration_min: float,
    downtime_min: float,
    exclude_categories: Optional[list[str]] = None,
) -> float:
    """
    Calculate Availability for a single component over a single shift.

    FORMULA
    -------
        Run Time = Planned Production Time - Unplanned Downtime
        A = Run Time / Planned Production Time

    NOTE on planned vs unplanned:
        - Planned maintenance (PM windows) may be excluded from the denominator
          (Planned Production Time) because they represent scheduled non-production
          time, not a loss.
        - Unplanned failures ARE losses and reduce A.
        - This project counts BOTH in downtime_min by default; caller can filter
          via `exclude_categories` (e.g., exclude 'planned_maintenance').

    SERIES TOPOLOGY RULE:
        An upstream failure (e.g., Bearing seizure) causes downstream stoppages.
        For the root component: downtime_category = 'unplanned_failure'.
        For downstream components: downtime_category = 'cascade_upstream'.
        We include cascade_upstream in SYSTEM OEE but allow filtering for
        COMPONENT OEE to isolate root cause.

    SQL COLUMNS CONSUMED
    --------------------
        production_shifts.planned_duration_min   -> planned_duration_min
        downtime_events.duration_min             -> summed into downtime_min
        downtime_events.downtime_category        -> filtered by exclude_categories
        (JOIN: downtime_events.shift_id     = production_shifts.shift_id)
        (JOIN: downtime_events.component_id = production_shifts.component_id)

    EQUIVALENT SQL  (to be saved as sql/queries/oee_availability.sql)
    ------------------------------------------------------------------
        SELECT
            ps.shift_id,
            ps.component_id,
            ps.planned_duration_min,
            COALESCE(SUM(de.duration_min), 0)                                   AS total_downtime_min,
            ps.planned_duration_min - COALESCE(SUM(de.duration_min), 0)         AS run_time_min,
            (ps.planned_duration_min - COALESCE(SUM(de.duration_min), 0))
                / NULLIF(ps.planned_duration_min, 0)                            AS availability
        FROM production_shifts ps
        LEFT JOIN downtime_events de
            ON  ps.shift_id     = de.shift_id
            AND ps.component_id = de.component_id
            AND de.downtime_category NOT IN ('planned_maintenance')
        GROUP BY ps.shift_id, ps.component_id, ps.planned_duration_min;

    Parameters
    ----------
    planned_duration_min : float -- total planned production window in minutes
    downtime_min         : float -- total unplanned (or all) downtime in minutes
    exclude_categories   : list[str] | None -- categories already filtered out

    Returns
    -------
    float in [0.0, 1.0] -- Availability factor
    """
    run_time_min = planned_duration_min - downtime_min
    availability = safe_divide(run_time_min, planned_duration_min)
    return validate_oee_component(availability, "Availability")


# =============================================================================
# 2. PERFORMANCE
# =============================================================================

def compute_performance(
    total_units: int,
    ideal_cycle_time_min: float,
    run_time_min: float,
) -> float:
    """
    Calculate Performance (Speed Loss) for a single component over a shift.

    FORMULA
    -------
        P = (Ideal Cycle Time x Total Count) / Run Time
          = Total Count / (Run Time / Ideal Cycle Time)
          = Actual Rate / Ideal Rate

    INTERPRETATION
    ---------------
        Performance < 1.0: the machine ran slower than its nameplate design speed.
        Causes in our 5-component system:
          - Bearing:        Lubricant degradation -> friction loss -> reduced RPM
          - Shaft:          Imbalance -> operator reduces speed -> lower throughput
          - Motor Housing:  Thermal derating -> motor runs at reduced power
          - Coupling:       Misalignment-induced vibration -> speed reduction
          - Gearbox:        Tooth wear -> increased friction -> output RPM drops

        Performance > 1.0: machine ran faster than rated -- DATA ERROR, will be clamped.

    ALTERNATIVE FORMULA (RPM-based, when unit counts are unavailable)
    ------------------------------------------------------------------
        P_rpm = actual_rpm / rated_rpm
        (uses sensor_readings.rpm and sensor_readings.rpm_rated)

    SQL COLUMNS CONSUMED
    --------------------
        production_counts.total_units            -> total_units
        production_counts.ideal_cycle_time_min   -> ideal_cycle_time_min
        (run_time_min derived from Availability calculation above)

        OR (RPM-based alternative):
        sensor_readings.rpm        -> actual_rpm  (AVG over shift window)
        sensor_readings.rpm_rated  -> rated_rpm   (constant per component)

    EQUIVALENT SQL  (to be saved as sql/queries/oee_performance.sql)
    -----------------------------------------------------------------
        SELECT
            pc.shift_id,
            pc.component_id,
            pc.total_units,
            pc.ideal_cycle_time_min,
            rt.run_time_min,
            (pc.total_units * pc.ideal_cycle_time_min)
                / NULLIF(rt.run_time_min, 0)                 AS performance
        FROM production_counts pc
        JOIN (
            SELECT shift_id, component_id,
                   planned_duration_min - COALESCE(SUM(duration_min), 0) AS run_time_min
            FROM production_shifts ps
            LEFT JOIN downtime_events de USING (shift_id, component_id)
            WHERE de.downtime_category NOT IN ('planned_maintenance')
            GROUP BY shift_id, component_id, planned_duration_min
        ) rt USING (shift_id, component_id);

    Parameters
    ----------
    total_units          : int   -- all units produced (good + defective) in the shift
    ideal_cycle_time_min : float -- nameplate time to produce one unit (minutes)
    run_time_min         : float -- actual operating time (planned - downtime), minutes

    Returns
    -------
    float in [0.0, 1.0] -- Performance factor
    """
    ideal_time_consumed = total_units * ideal_cycle_time_min
    performance = safe_divide(ideal_time_consumed, run_time_min)
    return validate_oee_component(performance, "Performance")


def compute_performance_rpm(actual_rpm: float, rated_rpm: float) -> float:
    """
    RPM-based Performance fallback when discrete unit counts are not available.

    FORMULA
    -------
        P = actual_rpm / rated_rpm

    SQL COLUMNS CONSUMED
    --------------------
        sensor_readings.rpm        -> actual_rpm  (AVG over shift window)
        sensor_readings.rpm_rated  -> rated_rpm   (constant per component)
        (filter: sensor_readings.ts BETWEEN shift_start AND shift_end)

    Returns
    -------
    float in [0.0, 1.0] -- Performance factor (RPM proxy)
    """
    performance = safe_divide(actual_rpm, rated_rpm)
    return validate_oee_component(performance, "Performance (RPM)")


# =============================================================================
# 3. QUALITY
# =============================================================================

def compute_quality(good_units: int, total_units: int) -> float:
    """
    Calculate Quality (First-Pass Yield) for a single component over a shift.

    FORMULA
    -------
        Q = Good Count / Total Count

    DEFINITION OF 'GOOD'
    ----------------------
        good_units = total_units - defective_units - rework_units
        Rework is counted as a quality loss in OEE -- even if eventually salvaged,
        the first-pass cycle time was wasted.

    SERIES TOPOLOGY -- QUALITY PROPAGATION
    ----------------------------------------
        In a series chain, a defect introduced at the Bearing stage (e.g.,
        vibration spike causes surface roughness) propagates forward. The
        downstream component may produce a unit subsequently scrapped at
        the final Gearbox inspection.
        Quality attribution:
          - Defect is recorded against ROOT CAUSE component via
            production_counts.defect_source_component_id.
          - FINAL inspection point captures defective_units in the count table.
          - Root cause attribution enables the Power BI Quality drill-down.

        Q_system = Q_Bearing x Q_Shaft x Q_Motor x Q_Coupling x Q_Gearbox
        (multiplicative -- each stage independently contributes defects)

    SQL COLUMNS CONSUMED
    --------------------
        production_counts.good_units                   -> good_units
        production_counts.total_units                  -> total_units
        production_counts.defective_units              -> reconciliation check
        production_counts.rework_units                 -> included in defective for OEE
        production_counts.defect_source_component_id   -> drill-down attribution

    EQUIVALENT SQL  (to be saved as sql/queries/oee_quality.sql)
    -------------------------------------------------------------
        SELECT
            pc.shift_id,
            pc.component_id,
            pc.good_units,
            pc.total_units,
            pc.good_units / NULLIF(CAST(pc.total_units AS FLOAT), 0)   AS quality
        FROM production_counts pc;

    Parameters
    ----------
    good_units  : int -- units passing first-pass inspection
    total_units : int -- all units produced (good + defective + rework)

    Returns
    -------
    float in [0.0, 1.0] -- Quality factor (First-Pass Yield)
    """
    quality = safe_divide(good_units, total_units)
    return validate_oee_component(quality, "Quality")


# =============================================================================
# 4. OEE COMPOSITE -- SINGLE COMPONENT
# =============================================================================

def compute_oee(
    availability: float,
    performance: float,
    quality: float,
) -> dict[str, float]:
    """
    Compute composite OEE and classify against world-class benchmarks.

    FORMULA
    -------
        OEE = Availability x Performance x Quality

    DECOMPOSITION -- SIX BIG LOSSES (Nakajima)
    -------------------------------------------
    AVAILABILITY losses (Downtime losses):
      [Loss 1] Unplanned Breakdowns     -- sudden equipment failure
      [Loss 2] Setup & Changeover       -- e.g., re-greasing bearing, tooling swap

    PERFORMANCE losses (Speed losses):
      [Loss 3] Minor Stops & Idling     -- brief stoppages < 5 min (not logged as DT)
      [Loss 4] Reduced Speed            -- running below rated RPM

    QUALITY losses (Defect losses):
      [Loss 5] Production Defects       -- scrap / rework during stable production
      [Loss 6] Start-up Rejects         -- defects during initial warm-up

    Our 5-component system maps these as:
      Bearing:       Loss 1, 2 dominant  -- high PM frequency = high setup loss
      Shaft:         Loss 3, 4 dominant  -- imbalance forces speed reduction
      Motor Housing: Loss 4 dominant     -- thermal derating reduces output speed
      Coupling:      Loss 3 dominant     -- misalignment causes micro-stops
      Gearbox:       Loss 1, 5 dominant  -- tooth wear -> defective torque output

    OEE STATUS TIERS
    -----------------
        >= 85%  : WORLD_CLASS
        >= 75%  : ACCEPTABLE
        >= 65%  : ALERT
        <  65%  : CRITICAL

    Parameters
    ----------
    availability : float -- A factor [0, 1]
    performance  : float -- P factor [0, 1]
    quality      : float -- Q factor [0, 1]

    Returns
    -------
    dict with keys:
        'availability'    : float
        'performance'     : float
        'quality'         : float
        'oee'             : float
        'oee_pct'         : float  -- OEE as percentage
        'world_class_gap' : float  -- difference from 85% (negative = below)
        'status'          : str    -- 'WORLD_CLASS' | 'ACCEPTABLE' | 'ALERT' | 'CRITICAL'
    """
    oee = availability * performance * quality

    if oee >= OEE_WORLD_CLASS:
        status = "WORLD_CLASS"
    elif oee >= 0.75:
        status = "ACCEPTABLE"
    elif oee >= OEE_ALERT_THRESHOLD:
        status = "ALERT"
    else:
        status = "CRITICAL"

    return {
        "availability":    round(availability, 4),
        "performance":     round(performance, 4),
        "quality":         round(quality, 4),
        "oee":             round(oee, 4),
        "oee_pct":         round(oee * 100, 2),
        "world_class_gap": round(oee - OEE_WORLD_CLASS, 4),
        "status":          status,
    }


# =============================================================================
# 5. SYSTEM OEE -- SERIES TOPOLOGY
# =============================================================================

def compute_system_oee(component_oee_records: list[dict]) -> dict[str, float]:
    """
    Compute system-level OEE for the 5-component series chain.

    SERIES SYSTEM OEE FORMULAS
    ---------------------------
        A_sys = min(A_1, A_2, A_3, A_4, A_5)
            The system cannot run when ANY component is down.
            Upstream downtime cascades, so the minimum is the binding constraint.

        P_sys = min(P_1, P_2, P_3, P_4, P_5)
            Throughput is limited by the slowest component (bottleneck law).
            A Motor Housing running at 60% RPM caps all downstream throughput at 60%.

        Q_sys = Q_1 x Q_2 x Q_3 x Q_4 x Q_5
            Each component independently introduces defects; quality losses
            accumulate multiplicatively.
            e.g., 99% x 98% x 99% x 99% x 97% = ~92% system first-pass yield.

        OEE_sys = A_sys x P_sys x Q_sys

    WHY min() FOR A AND P:
        Series reliability block theory: the chain is only as strong as its
        weakest link. A Bearing seizure (A_Bearing = 0) collapses A_sys to 0
        regardless of downstream component performance.

    WHY PRODUCT FOR Q:
        Each component's defect probability is independent. The probability of
        a unit passing ALL inspection points is the product of individual yields.
        This is consistent with series reliability block math: R_sys = prod(R_i).

    Parameters
    ----------
    component_oee_records : list[dict]
        Each dict must have keys: 'component_name', 'availability',
        'performance', 'quality', 'oee'.
        (i.e., the output of compute_oee() plus 'component_name')

    Returns
    -------
    dict with system-level OEE breakdown:
        all keys from compute_oee() plus:
        'bottleneck_availability' : str  -- component_name of the min A
        'bottleneck_performance'  : str  -- component_name of the min P
        'component_breakdown'     : list[dict] -- per-component records passed in
    """
    if not component_oee_records:
        return {"error": "No component records provided"}

    availabilities = [r["availability"] for r in component_oee_records]
    performances   = [r["performance"]  for r in component_oee_records]
    qualities      = [r["quality"]      for r in component_oee_records]
    names          = [r.get("component_name", f"Comp_{i}")
                      for i, r in enumerate(component_oee_records)]

    a_sys = min(availabilities)
    p_sys = min(performances)
    q_sys = 1.0
    for q in qualities:
        q_sys *= q

    system_result = compute_oee(a_sys, p_sys, q_sys)
    system_result["bottleneck_availability"] = names[availabilities.index(a_sys)]
    system_result["bottleneck_performance"]  = names[performances.index(p_sys)]
    system_result["component_breakdown"]     = component_oee_records

    return system_result


# =============================================================================
# 6. BATCH COMPUTATION FROM DATAFRAMES
# =============================================================================

def oee_from_dataframes(
    shifts_df: pd.DataFrame,
    downtime_df: pd.DataFrame,
    counts_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute per-shift, per-component OEE from three SQL-sourced DataFrames.

    EXPECTED DATAFRAME SCHEMAS
    ---------------------------
    shifts_df columns:
        shift_id, component_id, component_name, planned_duration_min

    downtime_df columns:
        shift_id, component_id, duration_min, downtime_category
        (filter to exclude 'planned_maintenance' before passing if desired)

    counts_df columns:
        shift_id, component_id, total_units, good_units, ideal_cycle_time_min

    Returns
    -------
    pd.DataFrame with columns:
        shift_id, component_id, component_name,
        planned_duration_min, downtime_min, run_time_min,
        availability, performance, quality, oee, oee_pct, status

    POWER BI INTEGRATION NOTE:
        Export this DataFrame to:  data/processed/oee_by_shift.csv
        Key Power BI measures reference:
            oee_by_shift[oee_pct]      -> KPI card "System OEE"
            oee_by_shift[availability] -> "Six Big Losses - Downtime" bar
            oee_by_shift[performance]  -> "Six Big Losses - Speed" bar
            oee_by_shift[quality]      -> "Six Big Losses - Defects" bar
    """
    # STEP 1: Aggregate downtime per shift per component
    downtime_agg = (
        downtime_df
        .groupby(["shift_id", "component_id"], as_index=False)["duration_min"]
        .sum()
        .rename(columns={"duration_min": "downtime_min"})
    )

    # STEP 2: Merge shifts with downtime
    merged = shifts_df.merge(downtime_agg, on=["shift_id", "component_id"], how="left")
    merged["downtime_min"] = merged["downtime_min"].fillna(0.0)
    merged["run_time_min"] = merged["planned_duration_min"] - merged["downtime_min"]

    # STEP 3: Merge with production counts
    merged = merged.merge(counts_df, on=["shift_id", "component_id"], how="left")

    # STEP 4: Compute OEE factors row-wise
    results = []
    for _, row in merged.iterrows():
        a = compute_availability(row["planned_duration_min"], row["downtime_min"])
        p = compute_performance(
            int(row.get("total_units", 0)),
            float(row.get("ideal_cycle_time_min", 1.0)),
            float(row["run_time_min"]),
        )
        q = compute_quality(
            int(row.get("good_units", 0)),
            int(row.get("total_units", 1))
        )
        oee_result = compute_oee(a, p, q)
        results.append({
            "shift_id":             row["shift_id"],
            "component_id":         row["component_id"],
            "component_name":       row.get("component_name", ""),
            "planned_duration_min": row["planned_duration_min"],
            "downtime_min":         row["downtime_min"],
            "run_time_min":         row["run_time_min"],
            **oee_result,
        })

    return pd.DataFrame(results)


# =============================================================================
# 7. OEE TREND ANALYSIS
# =============================================================================

def rolling_oee(oee_df: pd.DataFrame, window: int = 7) -> pd.DataFrame:
    """
    Compute rolling average OEE over a sliding window to reveal trends.

    FORMULA
    -------
        OEE_rolling(t) = mean(OEE[t-window+1 : t])

    This is the foundation of the degradation trend line in Power BI.
    A declining rolling OEE over 7 shifts signals an emerging reliability
    problem BEFORE a catastrophic failure -- bridging Descriptive Analytics
    (what is happening) to Diagnostic Analytics (why).

    SQL COLUMNS CONSUMED (after oee_by_shift.csv is loaded)
    --------------------------------------------------------
        oee_by_shift.shift_date    -> time axis
        oee_by_shift.component_id  -> partition key
        oee_by_shift.oee           -> rolling input

    Parameters
    ----------
    oee_df : pd.DataFrame -- must contain: shift_date, component_id, oee
    window : int -- rolling window in shifts (default: 7)

    Returns
    -------
    pd.DataFrame with added column: oee_rolling_avg
    """
    oee_df = oee_df.sort_values(["component_id", "shift_date"])
    oee_df["oee_rolling_avg"] = (
        oee_df.groupby("component_id")["oee"]
        .transform(lambda x: x.rolling(window=window, min_periods=1).mean())
    )
    return oee_df


# =============================================================================
# PSEUDO-CODE: FULL OEE PIPELINE (to be wired up in report.py, Day 16+)
# =============================================================================
#
# def run_oee_pipeline(db_connection, shift_date: str) -> None:
#
#     # STEP 1 -- Pull data from SQL
#     shifts_df   = pd.read_sql(
#         "SELECT * FROM production_shifts WHERE shift_date = ?",
#         db_connection, params=[shift_date])
#     downtime_df = pd.read_sql(
#         "SELECT * FROM downtime_events WHERE shift_id IN (?)",
#         db_connection, params=[tuple(shifts_df.shift_id)])
#     counts_df   = pd.read_sql(
#         "SELECT * FROM production_counts WHERE shift_id IN (?)",
#         db_connection, params=[tuple(shifts_df.shift_id)])
#
#     # STEP 2 -- Compute per-component OEE
#     oee_df = oee_from_dataframes(shifts_df, downtime_df, counts_df)
#
#     # STEP 3 -- Compute system OEE (series model)
#     component_records = oee_df.to_dict("records")
#     system_oee = compute_system_oee(component_records)
#
#     # STEP 4 -- Append rolling trend
#     oee_df = rolling_oee(oee_df, window=7)
#
#     # STEP 5 -- Export to CSV for Power BI
#     oee_df.to_csv("data/processed/oee_by_shift.csv", index=False)
#
#     # STEP 6 -- Trigger Power BI dataset refresh (via REST API -- Phase 3)
#     pass
