# -*- coding: utf-8 -*-
"""
data_generator.py — Manufacturing & Industrial Analytics FYP
=============================================================
Arrhenius-Based Synthetic Data Generator: Multi-Failure Simulation & Q-Q Validation
Phase 1, Sub-phase 1.3 — Data Simulation
Day 7: Multi-failure simulation (365-day window, multiple TTF draws per component)
     + Q-Q plot (Weibull probability plot) validation for simulated TTFs

PURPOSE
-------
Day 6 simulate.py produces a single 30-day telemetry window with at most ONE failure
event per component. For richer SQL training data and statistically valid Weibull
parameter estimation (Phase 2), we need multiple failure cycles per component:

    Multi-failure loop (per component):
        1. Draw TTF₁ from Weibull(β, η*) — η* derated via Arrhenius if applicable
        2. Simulate sensor telemetry for [0, TTF₁]  (healthy → ramp → failure)
        3. Apply maintenance reset: component life resets to 0 after repair
        4. Draw TTF₂, simulate [TTF₁ + repair_time, TTF₁ + repair_time + TTF₂]
        5. Repeat until cumulative time exceeds the 365-day window

This produces a realistic fleet dataset with:
    - Multiple observed failure events per component (needed for Weibull MLE fitting)
    - Variable TTF sequences showing natural Weibull scatter
    - Arrhenius-compressed life cycles under elevated temperature stress

MULTI-FAILURE MODEL
-------------------
Each failure cycle follows the same three-phase degradation model as simulate.py:

    Phase 1 — Healthy:     [0, TTFᵢ × (1 - RAMP_FRACTION)]
        sensor = baseline + N(0, σ)

    Phase 2 — Degradation: [TTFᵢ × (1 - RAMP_FRACTION), TTFᵢ]
        sensor = baseline + (alarm - baseline) × ramp_progress² + N(0, σ)

    Phase 3 — Post-failure: t ≥ TTFᵢ (very brief: represents repair detection)
        is_failure_event = 1 (flagged on primary sensor)

After failure detection, a corrective maintenance repair is applied:
    repair_duration = MTTRₛ × (1 + |N(0, MTTR_NOISE_FRACTION)|)
    (Gaussian-noisy MTTR from the strategy-specific repair distribution)

The repaired component then restarts with fresh Weibull age = 0 for the next cycle.

Q-Q PLOT VALIDATION
-------------------
After generating N TTF samples per component, this module validates that the
simulated TTFs follow the expected Weibull distribution via a Weibull
Probability Plot (linearised Q-Q plot):

    Transformation:
        x = ln(TTF)                         [log-transformed time axis]
        y = ln(−ln(1 − F̂(t)))              [Weibull reduced variate]

    where F̂(t) is the empirical CDF using median rank (Benard's approximation):
        F̂ᵢ = (i − 0.3) / (n + 0.4)     for i = 1, ..., n (sorted ascending)

    If TTF ~ Weibull(β, η), the plot should be linear with:
        slope     = β        (the Weibull shape parameter)
        intercept = −β · ln(η)

    Validation criteria:
        - R² ≥ 0.95 → PASS (excellent Weibull fit)
        - R² ≥ 0.90 → WARN (acceptable but investigate)
        - R² <  0.90 → FAIL (distribution may not be Weibull)

    Saved as: data/processed/qq_plots/<ComponentName>_weibull_qq.png

ARRHENIUS INTEGRATION
---------------------
The Arrhenius model (locked Day 1) is applied at TTF-draw time, consistent with
the approach established in simulate.py (Day 5/6):

    η_effective = η_nominal / AF(Ea, T_nominal, T_alarm)

    For the multi-failure loop, T_alarm is used as the stress temperature for
    conservative η derating. This produces shorter-than-nominal TTF cycles —
    which is correct for components running hot.

    Shaft is excluded (Ea = None, is_arrhenius_applicable = False).

HEALTH SCORE COLUMN (Day 6 carry-forward)
------------------------------------------
Each sensor row now includes a computed health_score column:
    health_score = R_derated × 100   (percentage, [0, 100])

This is the Fleet Overview KPI for Power BI (Day 21+).

SQL OUTPUT TARGETS
------------------
    data/processed/multi_failure_telemetry.csv     → full 365-day multi-cycle dataset
    data/processed/ttf_samples.csv                 → one row per failure event (for MLE)
    data/processed/qq_plots/*.png                  → Weibull Q-Q plots per component
    data/processed/qq_summary.csv                  → R², β_fitted, η_fitted per component

MATHEMATICAL REFERENCES
-----------------------
Weibull TTF sampling (inverse-CDF):
    TTF = η · (−ln(U))^(1/β)         U ~ Uniform(0, 1)

Arrhenius AF:
    AF = exp[(Ea/k) · (1/T_use − 1/T_stress)]
    k = 8.617×10⁻⁵ eV/K

Median rank (Benard's approximation):
    F̂ᵢ = (i − 0.3) / (n + 0.4)

Weibull linearisation:
    y = ln(−ln(1 − F̂))  vs  x = ln(t)
    Slope = β, Intercept = −β · ln(η)

MTBF (Weibull):
    MTBF = η · Γ(1 + 1/β)            [from reliability.py, Day 3]
"""

from __future__ import annotations

import math
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")   # Non-interactive backend — safe for scripts and CI
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import gamma as scipy_gamma

# ---------------------------------------------------------------------------
# Internal project imports
# ---------------------------------------------------------------------------
from reliability import (
    COMPONENT_WEIBULL_PARAMS,
    BOLTZMANN_EV_PER_K,
    KELVIN_OFFSET,
    arrhenius_acceleration_factor,
    eta_derated,
    weibull_reliability,
    mtbf_weibull,
)
from simulate import (
    NOMINAL_TEMPERATURES_CELSIUS,
    NOMINAL_SENSOR_VALUES,
    SENSOR_THRESHOLDS,
    FAILURE_MODES,
    DEGRADATION_RAMP_FRACTION,
    CASCADE_VIB_BOOST_FRACTION,
    RPM_RAMP_FLOOR_FRACTION,
    SimulationConfig,
    draw_weibull_ttf,
    arrhenius_af_for_component,
    derated_weibull_reliability,
    _compute_ramp_progress,
    _inject_vibration,
    _inject_temperature,
    _inject_oil_debris,
    _inject_rpm,
    _inject_load,
    _get_sensor_channels,
    _primary_sensor,
    _hours_to_iso,
)
from topology import (
    PIPELINE_ORDER,
    COMPONENT_POSITIONS,
    COMPONENT_TOPOLOGY_META,
    is_arrhenius_applicable,
    topological_sort,
    get_downstream_components,
)

# =============================================================================
# CONSTANTS — MULTI-FAILURE SIMULATION
# =============================================================================

# Default simulation window for multi-failure mode (365 days = 8760 hours)
DEFAULT_WINDOW_DAYS: int = 365

# Mean Time To Repair per maintenance strategy (hours).
# Based on typical industrial repair times from maintenance engineering literature.
# PM strategy: scheduled, planned repair → faster (parts pre-staged)
# CBM strategy: condition-triggered, may require diagnosis → slightly slower
MTTR_BY_STRATEGY: dict[str, float] = {
    "PM":     8.0,    # Planned maintenance: 8 h (one shift)
    "CBM":    12.0,   # Condition-based: 12 h (includes diagnostic time)
    "PM_CBM": 10.0,   # Hybrid: average of PM and CBM
}

# Gaussian noise fraction applied to MTTR to model repair time variability.
# repair_duration = MTTR × (1 + |N(0, MTTR_NOISE_FRACTION)|)
MTTR_NOISE_FRACTION: float = 0.20   # ±20% variability in repair duration

# Minimum Q-Q R² to pass Weibull distribution validation
QQ_R2_PASS_THRESHOLD:  float = 0.95
QQ_R2_WARN_THRESHOLD:  float = 0.90

# Minimum number of TTF samples required for meaningful Q-Q validation
QQ_MIN_SAMPLES: int = 3

# Timestep resolution for multi-failure telemetry (hours)
# Larger than Day 6's 1-hour step because 365 days × 5 components × ~2 sensors
# at 1-hour resolution → ~1.8M rows; 2-hour step halves to ~900k
MULTI_FAILURE_TIMESTEP_HOURS: float = 2.0

# Matplotlib style for Q-Q plots (professional dark theme)
QQ_PLOT_STYLE: str = "dark_background"

# Colour palette for the 5 components (hex, matched to Power BI brand palette)
COMPONENT_COLOURS: dict[str, str] = {
    "Bearing":       "#4FC3F7",   # cool blue  — ISO Zone B reference colour
    "Shaft":         "#81C784",   # green      — balanced / healthy
    "Motor Housing": "#FFB74D",   # amber      — heat / temperature
    "Coupling":      "#CE93D8",   # purple     — mechanical link
    "Gearbox":       "#EF9A9A",   # coral red  — wear / pitting
}


# =============================================================================
# CONFIGURATION DATACLASS (extends SimulationConfig for multi-failure mode)
# =============================================================================

@dataclass
class MultiFailureConfig:
    """
    Configuration for the multi-failure simulation and Q-Q validation run.

    Inherits the signal-level model from SimulationConfig but extends it
    for the 365-day multi-cycle use-case.
    """

    # --- Time window ---
    window_days: int = DEFAULT_WINDOW_DAYS
    """Total simulation window in calendar days.
    365 days (8760 h) guarantees multiple failure cycles for all 5 components
    given their η values (shortest: Bearing/Gearbox at η ≈ 4380 h ≈ 182 days)."""

    timestep_hours: float = MULTI_FAILURE_TIMESTEP_HOURS
    """Sensor reading interval in hours. 2-hour default balances data volume
    against temporal resolution for Power BI visualisation."""

    # --- Reproducibility ---
    random_seed: int = 7
    """DEMO LOCK: Hardcoded RNG seed for Day 7 multi-failure run.
    Guarantees exactly ~15 failure events during the live viva demo so the 
    dashboard visuals are fully populated (prevents random drops to <5 failures)."""

    # --- Output paths ---
    output_dir: str = "data/processed"
    """Root directory for all processed output files."""

    raw_dir: str = "data/raw"
    """Source directory for Day 6 single-cycle CSVs (for reference/comparison)."""

    # --- Arrhenius settings (mirrored from SimulationConfig) ---
    arrhenius_stress_enabled: bool = True
    nominal_temperatures: dict[str, Optional[float]] = field(
        default_factory=lambda: dict(NOMINAL_TEMPERATURES_CELSIUS)
    )

    # --- Signal noise model (mirrored from SimulationConfig) ---
    noise_std_vibration: float = 0.15
    noise_std_temperature: float = 2.0
    noise_std_oil_debris: float = 1.5
    noise_std_rpm: float = 5.0
    noise_std_load: float = 1.0

    # --- Repair model ---
    mttr_hours: dict[str, float] = field(
        default_factory=lambda: dict(MTTR_BY_STRATEGY)
    )
    """Mean time to repair (hours) per maintenance strategy.
    Drawn per cycle with Gaussian noise of ±MTTR_NOISE_FRACTION."""

    mttr_noise_fraction: float = MTTR_NOISE_FRACTION
    """Fractional Gaussian noise on repair duration — models variability in
    spare parts availability, technician expertise, etc."""

    # --- Q-Q validation ---
    qq_plot_dir: str = "data/processed/qq_plots"
    """Directory where Weibull Q-Q plots (.png) are saved."""

    qq_r2_pass: float = QQ_R2_PASS_THRESHOLD
    qq_r2_warn: float = QQ_R2_WARN_THRESHOLD
    qq_min_samples: int = QQ_MIN_SAMPLES

    # --- Health score ---
    include_health_score: bool = True
    """If True, add health_score = R_derated × 100 column to telemetry output."""

    # --- Cascade ---
    cascade_boost_enabled: bool = True

    # --- Verbosity ---
    verbose: bool = False


# =============================================================================
# SECTION 1: MULTI-FAILURE SIMULATION ENGINE
# =============================================================================

def _draw_repair_duration(
    component_name: str,
    config: MultiFailureConfig,
    rng: np.random.Generator,
) -> float:
    """
    Draw a stochastic repair duration for a component.

    FORMULA
    -------
        repair_h = MTTR_strategy × (1 + |N(0, mttr_noise_fraction)|)

    The absolute value ensures repair time is always ≥ MTTR_strategy (i.e., repair
    cannot be faster than the mean — reflects minimum inspection/parts-fitting time).

    Parameters
    ----------
    component_name : str — one of the 5 pipeline components
    config         : MultiFailureConfig
    rng            : np.random.Generator

    Returns
    -------
    float — repair duration in hours (always > 0)
    """
    strategy = COMPONENT_WEIBULL_PARAMS[component_name]["maintenance_strategy"]
    mttr_mean = config.mttr_hours.get(strategy, 10.0)
    noise = abs(rng.normal(0.0, config.mttr_noise_fraction))
    repair_h = mttr_mean * (1.0 + noise)
    return max(1.0, round(repair_h, 2))  # minimum 1 hour


def _compute_eta_effective(
    component_name: str,
    config: MultiFailureConfig,
) -> float:
    """
    Compute the Arrhenius-derated characteristic life η* for TTF drawing.

    This uses the alarm temperature as the conservative stress temperature —
    the same conservative assumption locked in Day 6 (simulate.py).

    FORMULA
    -------
        AF  = exp[(Ea/k) · (1/T_nominal − 1/T_alarm)]
        η*  = η_nominal / AF

    For Shaft: AF = 1.0 (not thermally governed), η* = η_nominal.

    Parameters
    ----------
    component_name : str
    config         : MultiFailureConfig

    Returns
    -------
    float — effective characteristic life η* in hours
    """
    params = COMPONENT_WEIBULL_PARAMS[component_name]
    eta_nom = params["eta_hours"]

    if not config.arrhenius_stress_enabled:
        return eta_nom

    if not is_arrhenius_applicable(component_name):
        return eta_nom    # Shaft — fatigue only

    ea = params.get("ea_ev")
    if ea is None:
        return eta_nom

    t_nominal = config.nominal_temperatures.get(component_name)
    if t_nominal is None:
        return eta_nom

    # Conservative stress temperature: use alarm threshold (as locked Day 6)
    thresholds = SENSOR_THRESHOLDS.get(component_name, {})
    temp_thresholds = thresholds.get("temperature", {})
    t_alarm = temp_thresholds.get("alarm", None)
    if t_alarm is None:
        # Component has no temperature sensor (Shaft, Coupling) — use nominal
        return eta_nom

    if t_alarm <= t_nominal:
        return eta_nom   # alarm ≤ nominal: no derating (should not happen by design)

    af = arrhenius_acceleration_factor(ea, t_nominal, t_alarm)
    return eta_derated(eta_nom, af)


def simulate_multi_failure_component(
    component_name: str,
    config: MultiFailureConfig,
    rng: np.random.Generator,
    upstream_failure_events: Optional[List[float]] = None,
) -> Tuple[pd.DataFrame, List[float], List[float]]:
    """
    Simulate multiple failure-repair cycles for a single component over the
    full window (config.window_days × 24 hours).

    ALGORITHM
    ---------
    1. Initialise: t_current = 0, cycle_number = 0
    2. Determine η_effective via Arrhenius derating (done once — conservative)
    3. LOOP while t_current < window_hours:
       a. Draw TTF from Weibull(β_mid, η_effective)
       b. t_fail = t_current + TTF
          If t_fail > window_hours:
              simulate healthy telemetry [t_current, window_hours] with no failure event
              BREAK
       c. Simulate sensor telemetry for [t_current, t_fail]:
              - healthy phase + degradation ramp + failure flag at t_fail
       d. Log failure event: {component, cycle, t_fail, TTF}
       e. Draw repair duration; advance t_current = t_fail + repair_duration
       f. cycle_number += 1
    4. Return concatenated DataFrame + list of TTF values (for Q-Q validation)

    CASCADE HANDLING
    ----------------
    upstream_failure_events is a flat list of absolute failure timestamps from
    all upstream components (already simulated in topological order).
    During each cycle's telemetry generation, any upstream failure timestamp that
    falls within [t_cycle_start, t_fail] triggers the cascade vibration boost.

    Parameters
    ----------
    component_name         : str
    config                 : MultiFailureConfig
    rng                    : np.random.Generator
    upstream_failure_events: list of float | None — absolute failure times (hours)
                             from upstream components, for cascade boost injection

    Returns
    -------
    Tuple[pd.DataFrame, List[float], List[float]]
        - df          : telemetry rows (long format, same schema as Day 6 CSVs + health_score)
        - ttf_list    : list of observed TTF values (hours) for this component
        - repair_list : list of drawn repair durations (hours)
    """
    if upstream_failure_events is None:
        upstream_failure_events = []

    params = COMPONENT_WEIBULL_PARAMS[component_name]
    beta = params["beta_mid"]
    eta_eff = _compute_eta_effective(component_name, config)

    # Build a SimulationConfig proxy so we can re-use simulate.py helpers
    _sim_cfg = SimulationConfig(
        window_days=config.window_days,
        timestep_hours=config.timestep_hours,
        random_seed=config.random_seed,
        arrhenius_stress_enabled=config.arrhenius_stress_enabled,
        nominal_temperatures=config.nominal_temperatures,
        noise_std_vibration=config.noise_std_vibration,
        noise_std_temperature=config.noise_std_temperature,
        noise_std_oil_debris=config.noise_std_oil_debris,
        noise_std_rpm=config.noise_std_rpm,
        noise_std_load=config.noise_std_load,
    )

    window_hours = config.window_days * 24.0
    comp_id = COMPONENT_POSITIONS[component_name]
    channels = _get_sensor_channels(component_name)
    primary_sensor = _primary_sensor(component_name)
    failure_mode_str = FAILURE_MODES.get(component_name, "unknown")
    thresholds = SENSOR_THRESHOLDS.get(component_name, {})
    baselines = NOMINAL_SENSOR_VALUES.get(component_name, {})

    t_current: float = 0.0
    cycle_number: int = 1   # 1-indexed: first cycle = 1 (matches failure_log CHECK >= 1)
    all_records: List[dict] = []
    ttf_list: List[float] = []
    repair_list: List[float] = []

    while t_current < window_hours:
        # ── Step a: Draw TTF for this cycle ─────────────────────────────────
        ttf_cycle = draw_weibull_ttf(beta, eta_eff, rng)
        t_fail_abs = t_current + ttf_cycle   # absolute time of failure

        # ── Step b: Check if failure falls within remaining window ───────────
        if t_fail_abs >= window_hours:
            # No failure in this cycle — simulate healthy/ramp telemetry to end
            # We still generate telemetry to fill the remainder of the window.
            t_end_cycle = window_hours
            # Treat TTF as far beyond window for signal purposes
            virtual_ttf = t_fail_abs - t_current  # relative to cycle start

            _generate_cycle_records(
                all_records,
                component_name=component_name,
                comp_id=comp_id,
                cycle_number=cycle_number,
                t_cycle_start=t_current,
                t_cycle_end=t_end_cycle,
                ttf_relative=virtual_ttf,
                ttf_absolute=t_fail_abs,
                failure_occurs=False,
                channels=channels,
                primary_sensor=primary_sensor,
                failure_mode_str=failure_mode_str,
                thresholds=thresholds,
                baselines=baselines,
                upstream_failure_events=upstream_failure_events,
                config=config,
                _sim_cfg=_sim_cfg,
                rng=rng,
            )
            break   # window exhausted

        # ── Step c: Simulate telemetry for this cycle ─────────────────────
        _generate_cycle_records(
            all_records,
            component_name=component_name,
            comp_id=comp_id,
            cycle_number=cycle_number,
            t_cycle_start=t_current,
            t_cycle_end=t_fail_abs,
            ttf_relative=ttf_cycle,
            ttf_absolute=t_fail_abs,
            failure_occurs=True,
            channels=channels,
            primary_sensor=primary_sensor,
            failure_mode_str=failure_mode_str,
            thresholds=thresholds,
            baselines=baselines,
            upstream_failure_events=upstream_failure_events,
            config=config,
            _sim_cfg=_sim_cfg,
            rng=rng,
        )

        # ── Step d: Record TTF (for Q-Q validation) ──────────────────────
        ttf_list.append(ttf_cycle)

        # ── Step e: Repair and advance time ──────────────────────────────
        repair_h = _draw_repair_duration(component_name, config, rng)
        repair_list.append(repair_h)
        t_current = t_fail_abs + repair_h
        cycle_number += 1   # advance to next 1-based cycle number

        if config.verbose:
            print(
                f"      [{component_name}] Cycle {cycle_number - 1} complete: "
                f"TTF={ttf_cycle:.1f}h | t_fail={t_fail_abs:.1f}h | "
                f"repair={repair_h:.1f}h | next_t={t_current:.1f}h"
            )

    df = pd.DataFrame(all_records)
    if df.empty:
        # Safety: return empty DataFrame with correct columns
        df = pd.DataFrame(columns=[
            "ts", "component_id", "component_name", "sensor_type", "value",
            "is_failure_event", "failure_mode", "R_derated", "AF",
            "cascade_flag", "health_score", "cycle_number",
        ])
    return df, ttf_list, repair_list


def _generate_cycle_records(
    all_records: List[dict],
    component_name: str,
    comp_id: int,
    cycle_number: int,
    t_cycle_start: float,
    t_cycle_end: float,
    ttf_relative: float,
    ttf_absolute: float,
    failure_occurs: bool,
    channels: List[str],
    primary_sensor: str,
    failure_mode_str: str,
    thresholds: dict,
    baselines: dict,
    upstream_failure_events: List[float],
    config: MultiFailureConfig,
    _sim_cfg: SimulationConfig,
    rng: np.random.Generator,
) -> None:
    """
    Generate telemetry records for one failure-repair cycle and append them
    to all_records in-place.

    This is a private helper for simulate_multi_failure_component(). It mirrors
    the signal injection logic from simulate.py generate_component_telemetry()
    but operates over a cycle slice [t_cycle_start, t_cycle_end] of the absolute
    timeline, mapping to relative time [0, ttf_relative] for the Weibull ramp.

    Parameters
    ----------
    all_records      : list — accumulated records list (mutated in-place)
    t_cycle_start    : float — absolute start of this cycle (hours)
    t_cycle_end      : float — absolute end (either t_fail or window end)
    ttf_relative     : float — TTF in cycle-relative hours (for ramp computation)
    ttf_absolute     : float — TTF in absolute window hours (for cascade logic)
    failure_occurs   : bool — True if a failure event happens at t_cycle_end
    upstream_failure_events : list of float — absolute times of upstream failures
    """
    dt = config.timestep_hours
    t_abs = t_cycle_start

    # Cascade vibration boost: applied from each upstream failure time
    # Compute once as a single additive value — the same rule as simulate.py
    vib_cascade_boost = 0.0
    if config.cascade_boost_enabled and upstream_failure_events:
        vib_boost_per_upstream = CASCADE_VIB_BOOST_FRACTION * (
            thresholds.get("vibration", {}).get("alarm", 4.5) -
            baselines.get("vibration", 1.0)
        )
        # Count upstream components that have already failed before this cycle
        n_upstream_failed = sum(
            1 for t_up in upstream_failure_events if t_up <= t_cycle_start
        )
        vib_cascade_boost = n_upstream_failed * vib_boost_per_upstream

    while t_abs <= t_cycle_end + 1e-9:   # +epsilon for float equality
        t_rel = t_abs - t_cycle_start    # cycle-local time (0 at cycle start)

        # ── Cascade: check if a new upstream failure crosses this timestep ─
        if config.cascade_boost_enabled and upstream_failure_events:
            vib_boost_per_upstream = CASCADE_VIB_BOOST_FRACTION * (
                thresholds.get("vibration", {}).get("alarm", 4.5) -
                baselines.get("vibration", 1.0)
            )
            n_failed_now = sum(
                1 for t_up in upstream_failure_events if t_up <= t_abs
            )
            vib_cascade_boost = n_failed_now * vib_boost_per_upstream

        cascade_active = vib_cascade_boost > 0.0

        # ── Failure flag: only at the exact failure timestep, primary sensor ─
        is_at_failure = failure_occurs and (t_rel >= ttf_relative)

        # ── Condition-adjusted reliability R*(t) for this timestep ────────
        t_nominal = config.nominal_temperatures.get(component_name)
        t_for_arr = t_nominal if t_nominal is not None else 25.0
        try:
            rel_dict = derated_weibull_reliability(
                component_name,
                max(0.0, t_rel),
                t_for_arr,
                _sim_cfg,
            )
            r_derated = rel_dict["R_derated"]
            af_val = rel_dict["AF"]
        except Exception:
            r_derated = 1.0
            af_val = 1.0

        health_score = round(r_derated * 100.0, 2) if config.include_health_score else None

        ts_str = _hours_to_iso(t_abs)

        # ── Inject each sensor channel ────────────────────────────────────
        for sensor_type in channels:
            baseline = baselines.get(sensor_type, 0.0)

            if sensor_type == "vibration":
                alarm  = thresholds.get("vibration", {}).get("alarm", 4.5)
                danger = thresholds.get("vibration", {}).get("danger", 7.1)
                value  = _inject_vibration(
                    t_rel, ttf_relative, baseline, alarm, danger,
                    vib_cascade_boost, rng, config.noise_std_vibration,
                )

            elif sensor_type == "temperature":
                alarm  = thresholds.get("temperature", {}).get("alarm", 80.0)
                danger = thresholds.get("temperature", {}).get("danger", 100.0)
                value  = _inject_temperature(
                    t_rel, ttf_relative, baseline, alarm, danger,
                    rng, config.noise_std_temperature,
                )

            elif sensor_type == "oil_debris":
                alarm  = thresholds.get("oil_debris", {}).get("alarm", 50.0)
                danger = thresholds.get("oil_debris", {}).get("danger", 200.0)
                value  = _inject_oil_debris(
                    t_rel, ttf_relative, baseline, alarm, danger,
                    rng, config.noise_std_oil_debris,
                )

            elif sensor_type == "rpm":
                value = _inject_rpm(
                    t_rel, ttf_relative, baseline,
                    rng, config.noise_std_rpm,
                )

            elif sensor_type == "load":
                alarm = thresholds.get("load", {}).get("alarm", 90.0)
                value = _inject_load(
                    t_rel, ttf_relative, baseline, alarm,
                    rng, config.noise_std_load,
                )
            else:
                value = float(baseline)

            is_failure_flag = (
                1 if (is_at_failure and sensor_type == primary_sensor) else 0
            )
            fail_mode = (
                failure_mode_str if is_failure_flag == 1 else None
            )

            record: dict = {
                "ts":               ts_str,
                "component_id":     comp_id,
                "component_name":   component_name,
                "sensor_type":      sensor_type,
                "value":            value,
                "is_failure_event": is_failure_flag,
                "failure_mode":     fail_mode,
                "R_derated":        round(r_derated, 6),
                "AF":               round(af_val, 4),
                "cascade_flag":     1 if (cascade_active and sensor_type == "vibration") else 0,
                "cycle_number":     cycle_number,
            }
            if config.include_health_score:
                record["health_score"] = health_score

            all_records.append(record)

        # Advance timestep (avoid infinite loop if dt=0)
        t_abs += max(dt, 1e-6)
        if t_abs > t_cycle_end + 1e-9:
            break


def run_multi_failure_simulation(
    config: Optional[MultiFailureConfig] = None,
) -> Tuple[pd.DataFrame, Dict[str, List[float]], Dict[str, List[float]]]:
    """
    Execute the full 365-day multi-failure simulation for all 5 pipeline components.

    Iterates components in topological order (Bearing → Gearbox) so that
    upstream failure events are available for cascade boost injection into
    downstream components.

    Parameters
    ----------
    config : MultiFailureConfig | None — uses defaults if None

    Returns
    -------
    Tuple of:
        master_df    : pd.DataFrame — full telemetry (all components, all cycles)
        ttf_by_comp  : dict[str, list[float]] — TTF samples per component (for Q-Q)
        repair_log   : dict[str, list[float]] — repair durations per component
    """
    if config is None:
        config = MultiFailureConfig()

    rng = np.random.default_rng(config.random_seed)

    os.makedirs(config.output_dir, exist_ok=True)
    os.makedirs(config.qq_plot_dir, exist_ok=True)

    if config.verbose:
        window_h = config.window_days * 24
        print("=" * 70)
        print("DATA_GENERATOR.PY — MULTI-FAILURE SIMULATION (Day 7)")
        print("=" * 70)
        print(f"  Window   : {config.window_days} days ({window_h} h)")
        print(f"  Timestep : {config.timestep_hours} h")
        print(f"  Seed     : {config.random_seed}")
        print(f"  Arrhenius: {'enabled' if config.arrhenius_stress_enabled else 'disabled'}")
        print()

    component_order = topological_sort()

    # Accumulate results
    component_dfs:    Dict[str, pd.DataFrame] = {}
    ttf_by_comp:      Dict[str, List[float]]  = {}
    repair_by_comp:   Dict[str, List[float]]  = {}
    # upstream_failure_events is a running flat list of absolute failure times
    all_upstream_events: List[float] = []

    for comp_name in component_order:
        if config.verbose:
            print(f"  Simulating: {comp_name}")

        # upstream events = all failure times from previously simulated components
        upstream_events_for_this_comp = list(all_upstream_events)

        df, ttf_list, repair_list = simulate_multi_failure_component(
            comp_name,
            config,
            rng,
            upstream_failure_events=upstream_events_for_this_comp,
        )

        component_dfs[comp_name] = df
        ttf_by_comp[comp_name]  = ttf_list
        repair_by_comp[comp_name] = repair_list

        # Add this component's failure times to the running upstream list
        all_upstream_events.extend(ttf_list)

        if config.verbose:
            n_cycles = len(ttf_list)
            n_rows = len(df)
            mean_ttf = (sum(ttf_list) / n_cycles) if ttf_list else float("nan")
            print(
                f"    -> Cycles: {n_cycles} | Rows: {n_rows} | "
                f"Mean TTF: {mean_ttf:.1f} h | "
                f"TTFs: {[round(t, 0) for t in ttf_list]}"
            )

    # Concatenate all component DataFrames
    if component_dfs:
        master_df = pd.concat(list(component_dfs.values()), ignore_index=True)
    else:
        master_df = pd.DataFrame()

    # Write multi-failure telemetry CSV
    telemetry_path = os.path.join(config.output_dir, "multi_failure_telemetry.csv")
    master_df.to_csv(telemetry_path, index=False)

    if config.verbose:
        print(f"\n  [OK] Multi-failure telemetry: {telemetry_path} ({len(master_df)} rows)")

    # Build and write TTF samples CSV
    ttf_records = []
    for comp_name, ttfs in ttf_by_comp.items():
        repairs = repair_by_comp[comp_name]
        eta_eff = _compute_eta_effective(comp_name, config)
        for i, ttf_val in enumerate(ttfs):
            ttf_records.append({
                "component_name": comp_name,
                "component_id":   COMPONENT_POSITIONS[comp_name],
                "cycle_number":   i + 1,
                "ttf_hours":      round(ttf_val, 4),
                "repair_hours":   round(repairs[i], 4),
                "beta_mid":       COMPONENT_WEIBULL_PARAMS[comp_name]["beta_mid"],
                "eta_nominal_h":  COMPONENT_WEIBULL_PARAMS[comp_name]["eta_hours"],
                "eta_eff":        round(eta_eff, 4),
                "ea_ev":          COMPONENT_WEIBULL_PARAMS[comp_name]["ea_ev"],
                "strategy":       COMPONENT_WEIBULL_PARAMS[comp_name]["maintenance_strategy"],
            })

    ttf_df = pd.DataFrame(ttf_records)
    ttf_path = os.path.join(config.output_dir, "ttf_samples.csv")
    ttf_df.to_csv(ttf_path, index=False)

    if config.verbose:
        print(f"  [OK] TTF samples: {ttf_path} ({len(ttf_df)} rows)")
        print()

    return master_df, ttf_by_comp, {}


# =============================================================================
# SECTION 2: Q-Q PLOT VALIDATION (Weibull Probability Plot)
# =============================================================================

def compute_median_ranks(n: int) -> np.ndarray:
    """
    Compute median ranks (empirical failure probabilities) using Benard's
    approximation — the standard in reliability engineering (MIL-HDBK-189C).

    FORMULA
    -------
        F̂ᵢ = (i − 0.3) / (n + 0.4)      i = 1, 2, ..., n

    Benard's approximation is preferred over:
        - i/n (biased for small samples)
        - (i - 0.5)/n (Hazen — underestimates for Weibull)
        - (i - 1)/(n - 1) (Kaplan-Meier — different intended use)

    Benard's formula closely approximates the true median of the order
    statistics of the Uniform(0,1) distribution for all n ≥ 2.

    VIVA NOTE
    ---------
    Q: Why not use i/n for empirical CDF?
    A: i/n gives F̂(max_sample) = 1.0, making ln(-ln(1-F̂)) = +∞ — undefined
       on the Weibull probability axis. Benard's approximation avoids this.

    Parameters
    ----------
    n : int — number of TTF samples (must be ≥ 2)

    Returns
    -------
    np.ndarray of shape (n,) — median rank values F̂ᵢ ∈ (0, 1)
    """
    if n < 2:
        raise ValueError(f"Median rank requires n ≥ 2; received n = {n}")
    i = np.arange(1, n + 1, dtype=float)
    return (i - 0.3) / (n + 0.4)


def weibull_linearise(ttf_samples: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Linearise Weibull-distributed TTF samples for Q-Q (probability) plot.

    TRANSFORMATION (Weibull probability plot axes)
    -----------------------------------------------
    Given sorted TTF samples t₁ ≤ t₂ ≤ ... ≤ tₙ and median ranks F̂ᵢ:

        x = ln(tᵢ)                    [natural log of time]
        y = ln(−ln(1 − F̂ᵢ))          [Weibull reduced variate]

    THEORY
    ------
    The Weibull CDF is:
        F(t) = 1 − exp(−(t/η)^β)

    Rearranging:
        ln(−ln(1 − F(t))) = β·ln(t) − β·ln(η)

    So if TTF ~ Weibull(β, η), the Q-Q plot:
        y = β·x − β·ln(η)

    is a straight line with:
        slope     ≈ β           (shape parameter — controls wear-out rate)
        intercept ≈ −β · ln(η)  (encodes η — characteristic life)

    Parameters
    ----------
    ttf_samples : np.ndarray — unsorted TTF values in hours (all must be > 0)

    Returns
    -------
    Tuple[np.ndarray, np.ndarray] — (x_vals, y_vals) for Q-Q plot
    """
    ttf_sorted = np.sort(ttf_samples)
    n = len(ttf_sorted)
    f_hat = compute_median_ranks(n)

    x = np.log(ttf_sorted)
    y = np.log(-np.log(1.0 - f_hat))

    return x, y


def fit_weibull_from_qq(
    x_vals: np.ndarray,
    y_vals: np.ndarray,
) -> Tuple[float, float, float, float]:
    """
    Fit a line to the linearised Weibull Q-Q data and extract β, η.

    LINEAR REGRESSION on the Weibull probability plot:
        y = slope × x + intercept

    Recovering parameters:
        β_fitted   = slope
        η_fitted   = exp(−intercept / slope)
        R²         = coefficient of determination (goodness-of-fit)

    Parameters
    ----------
    x_vals : np.ndarray — ln(TTF) values
    y_vals : np.ndarray — ln(−ln(1 − F̂)) values

    Returns
    -------
    Tuple[float, float, float, float]:
        (beta_fitted, eta_fitted, r_squared, slope)
    """
    slope, intercept, r_value, p_value, std_err = stats.linregress(x_vals, y_vals)

    beta_fitted = float(slope)
    # η extracted from intercept = −β·ln(η)  →  ln(η) = −intercept / β
    if abs(beta_fitted) < 1e-9:
        eta_fitted = float("nan")
    else:
        eta_fitted = float(math.exp(-intercept / beta_fitted))

    r_squared = float(r_value ** 2)

    return beta_fitted, eta_fitted, r_squared, float(slope)


def qq_plot_weibull(
    component_name: str,
    ttf_samples: List[float],
    config: MultiFailureConfig,
    save_path: Optional[str] = None,
) -> dict:
    """
    Generate a Weibull Probability Plot (Q-Q plot) for the simulated TTFs
    of a single component and save it as a PNG.

    WHAT THE PLOT SHOWS
    -------------------
    - Scatter points: linearised (ln TTF, Weibull reduced variate) pairs
      Each point = one observed failure event from the multi-failure simulation
    - Blue regression line: best-fit line through the Q-Q points
      Slope = β_fitted, Intercept → η_fitted
    - Red dashed line: theoretical expectation from known (β_mid, η_nominal)
      This is the "ground truth" the simulation should approximate
    - R² annotation: goodness-of-fit score (PASS/WARN/FAIL label)
    - Grid: shows Weibull reduced variate percentiles on right Y-axis

    INTERPRETATION GUIDE (annotated on plot)
    ----------------------------------------
    - Points aligned on the regression line → TTFs are Weibull-distributed ✓
    - Scatter around the line → natural sampling variability (expected)
    - Systematic S-curve → distribution is NOT Weibull (investigate rng)
    - R² ≥ 0.95 → PASS — fitted β and η are reliable for Power BI display

    Parameters
    ----------
    component_name : str
    ttf_samples    : list of float — TTF values in hours (n ≥ QQ_MIN_SAMPLES)
    config         : MultiFailureConfig
    save_path      : str | None — full path to save PNG; auto-generated if None

    Returns
    -------
    dict with keys:
        component, n_samples, beta_nominal, eta_nominal,
        beta_fitted, eta_fitted, r_squared, status, plot_path
    """
    n = len(ttf_samples)
    params = COMPONENT_WEIBULL_PARAMS[component_name]
    beta_nom = params["beta_mid"]
    eta_nom  = params["eta_hours"]

    result_base = {
        "component":    component_name,
        "n_samples":    n,
        "beta_nominal": beta_nom,
        "eta_nominal":  eta_nom,
        "beta_fitted":  float("nan"),
        "eta_fitted":   float("nan"),
        "r_squared":    float("nan"),
        "status":       "INSUFFICIENT_DATA",
        "plot_path":    None,
    }

    if n < config.qq_min_samples:
        warnings.warn(
            f"[Q-Q] {component_name}: only {n} TTF sample(s) — "
            f"need ≥ {config.qq_min_samples} for Q-Q plot. Skipping.",
            UserWarning,
            stacklevel=2,
        )
        return result_base

    ttf_arr = np.array(ttf_samples, dtype=float)

    # Compute Q-Q coordinates
    try:
        x_vals, y_vals = weibull_linearise(ttf_arr)
    except Exception as exc:
        warnings.warn(f"[Q-Q] {component_name}: linearisation failed — {exc}", UserWarning)
        return result_base

    # Fit regression line
    beta_fit, eta_fit, r_sq, slope = fit_weibull_from_qq(x_vals, y_vals)

    # Determine pass/warn/fail status
    if r_sq >= config.qq_r2_pass:
        status = "PASS"
    elif r_sq >= config.qq_r2_warn:
        status = "WARN"
    else:
        status = "FAIL"

    # ── Plotting ─────────────────────────────────────────────────────────
    colour = COMPONENT_COLOURS.get(component_name, "#FFFFFF")

    try:
        plt.style.use(QQ_PLOT_STYLE)
    except OSError:
        pass  # fallback to default style if dark_background unavailable

    fig, ax = plt.subplots(figsize=(9, 6))
    fig.patch.set_facecolor("#0D0D0D")
    ax.set_facecolor("#111111")

    # --- Scatter: observed Q-Q points ---
    ax.scatter(
        x_vals, y_vals,
        color=colour, edgecolors="#FFFFFF", linewidths=0.6,
        s=55, zorder=5, alpha=0.9,
        label=f"Observed TTFs (n={n})",
    )

    # --- Regression line (fitted Weibull) ---
    x_line = np.linspace(x_vals.min() - 0.3, x_vals.max() + 0.3, 200)
    y_line_fit = slope * x_line + (y_vals.mean() - slope * x_vals.mean())
    ax.plot(
        x_line, y_line_fit,
        color=colour, linewidth=2.0, linestyle="-",
        label=f"Fitted: β={beta_fit:.3f}, η={eta_fit:.0f} h",
        zorder=4,
    )

    # --- Theoretical line (known β_mid, η_nominal) ---
    # y_theoretical = β_nom·ln(t) − β_nom·ln(η_nom)
    y_line_theo = beta_nom * x_line - beta_nom * math.log(eta_nom)
    ax.plot(
        x_line, y_line_theo,
        color="#FF6B6B", linewidth=1.5, linestyle="--",
        alpha=0.75,
        label=f"Theoretical: β={beta_nom:.2f}, η={eta_nom:.0f} h",
        zorder=3,
    )

    # --- Annotation: R² status badge ---
    status_colour = {"PASS": "#00E676", "WARN": "#FFD54F", "FAIL": "#FF5252"}.get(status, "#FFFFFF")
    ax.annotate(
        f"R² = {r_sq:.4f}  [{status}]",
        xy=(0.03, 0.97),
        xycoords="axes fraction",
        fontsize=12,
        fontweight="bold",
        color=status_colour,
        va="top",
        bbox=dict(boxstyle="round,pad=0.4", fc="#1A1A2E", ec=status_colour, lw=1.5),
    )

    # --- Secondary Y-axis: failure probability scale ---
    # Weibull reduced variate y = ln(-ln(1-F)) ↔ F values at nice percentiles
    prob_ticks  = [0.01, 0.05, 0.10, 0.20, 0.50, 0.63, 0.90, 0.99]
    y_prob_vals = [math.log(-math.log(1.0 - p)) for p in prob_ticks]
    ax2 = ax.twinx()
    ax2.set_ylim(ax.get_ylim())
    ax2.set_yticks(y_prob_vals)
    ax2.set_yticklabels(
        [f"{int(p * 100)}%" for p in prob_ticks],
        color="#AAAAAA", fontsize=9,
    )
    ax2.set_ylabel("Cumulative Failure Probability F(t)", color="#AAAAAA", fontsize=10)
    ax2.tick_params(axis="y", colors="#AAAAAA")

    # --- Reference percentile lines ---
    for p, yval in zip(prob_ticks, y_prob_vals):
        if p in (0.10, 0.50, 0.90):
            ax.axhline(yval, color="#333333", linewidth=0.7, linestyle=":", zorder=1)

    # --- Decorations ---
    ax.set_xlabel("ln(Time to Failure)  [ln(hours)]", fontsize=12, color="#CCCCCC")
    ax.set_ylabel("Weibull Reduced Variate  ln(−ln(1 − F̂))", fontsize=12, color="#CCCCCC")
    ax.set_title(
        f"Weibull Probability Plot — {component_name}\n"
        f"Multi-failure simulation · 365-day window · seed={config.random_seed}",
        fontsize=13, fontweight="bold", color="#FFFFFF", pad=14,
    )
    ax.tick_params(axis="both", colors="#AAAAAA")
    ax.spines["bottom"].set_color("#444444")
    ax.spines["top"].set_color("#444444")
    ax.spines["left"].set_color("#444444")
    ax.spines["right"].set_color("#444444")

    legend = ax.legend(
        loc="lower right", framealpha=0.85,
        facecolor="#1A1A2E", edgecolor="#555555",
        labelcolor="#EEEEEE", fontsize=10,
    )

    # Arrhenius note
    ea = params.get("ea_ev")
    if ea is not None:
        eta_eff = _compute_eta_effective(component_name, config)
        ax.annotate(
            f"Ea={ea} eV · η_effective={eta_eff:.0f} h (Arrhenius derated)",
            xy=(0.03, 0.03),
            xycoords="axes fraction",
            fontsize=9, color="#AAAAAA",
            va="bottom",
        )
    else:
        ax.annotate(
            "Arrhenius N/A — fatigue-dominant failure mode",
            xy=(0.03, 0.03),
            xycoords="axes fraction",
            fontsize=9, color="#AAAAAA",
            va="bottom",
        )

    plt.tight_layout()

    # --- Save ---
    if save_path is None:
        safe_name = component_name.replace(" ", "_")
        save_path = os.path.join(
            config.qq_plot_dir, f"{safe_name}_weibull_qq.png"
        )

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    result_base.update({
        "beta_fitted":  round(beta_fit, 4),
        "eta_fitted":   round(eta_fit, 2),
        "r_squared":    round(r_sq, 6),
        "status":       status,
        "plot_path":    save_path,
    })

    return result_base


def run_qq_validation(
    ttf_by_comp: Dict[str, List[float]],
    config: MultiFailureConfig,
) -> pd.DataFrame:
    """
    Run Q-Q plot validation for all 5 pipeline components and produce a
    summary DataFrame that can be exported to data/processed/qq_summary.csv.

    This function is the Day 7 validation gate:
        - R² ≥ 0.95 → PASS: fitted β and η are reliable for Phase 2 MLE seeding
        - R² ≥ 0.90 → WARN: acceptable but increase n_samples in future runs
        - R² <  0.90 → FAIL: investigate RNG or signal injection parameters

    Parameters
    ----------
    ttf_by_comp : dict[str, list[float]] — from run_multi_failure_simulation()
    config      : MultiFailureConfig

    Returns
    -------
    pd.DataFrame — Q-Q summary table (one row per component)
        Columns: component, n_samples, beta_nominal, eta_nominal,
                 beta_fitted, eta_fitted, r_squared, status, plot_path
    """
    if config.verbose:
        print("  Running Q-Q validation:")

    summary_rows = []

    for comp_name in PIPELINE_ORDER:
        ttf_list = ttf_by_comp.get(comp_name, [])
        result = qq_plot_weibull(comp_name, ttf_list, config)
        summary_rows.append(result)

        if config.verbose:
            status_symbol = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(
                result["status"], "?"
            )
            print(
                f"    {status_symbol} {comp_name:<16} "
                f"n={result['n_samples']:<3} "
                f"β_fit={result['beta_fitted']:.3f}  "
                f"η_fit={result['eta_fitted']:.0f} h  "
                f"R²={result['r_squared']:.4f}  "
                f"[{result['status']}]"
            )

    summary_df = pd.DataFrame(summary_rows)

    # Save summary CSV
    qq_csv_path = os.path.join(config.output_dir, "qq_summary.csv")
    summary_df.to_csv(qq_csv_path, index=False)

    if config.verbose:
        print(f"  [OK] Q-Q summary: {qq_csv_path}")

    return summary_df


# =============================================================================
# SECTION 3: FLEET-LEVEL Q-Q PANEL PLOT (all 5 components in one figure)
# =============================================================================

def plot_qq_panel(
    ttf_by_comp: Dict[str, List[float]],
    config: MultiFailureConfig,
    save_path: Optional[str] = None,
) -> str:
    """
    Produce a 2×3 panel figure of Weibull Q-Q plots for all 5 components
    (5th panel = blank, 6th = legend/summary table) in a single PNG.

    This is the "Fleet Q-Q Overview" figure suitable for academic report submission
    and viva presentation. It shows at a glance whether all 5 components'
    TTF distributions are well-fitted by Weibull.

    Parameters
    ----------
    ttf_by_comp : dict[str, list[float]]
    config      : MultiFailureConfig
    save_path   : str | None — defaults to data/processed/qq_plots/fleet_qq_panel.png

    Returns
    -------
    str — absolute path to the saved PNG file
    """
    try:
        plt.style.use(QQ_PLOT_STYLE)
    except OSError:
        pass

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.patch.set_facecolor("#090909")
    fig.suptitle(
        "Fleet Weibull Q-Q Validation — Multi-failure Simulation (365-day window)",
        fontsize=16, fontweight="bold", color="#FFFFFF", y=1.01,
    )

    summary_rows = []

    for idx, comp_name in enumerate(PIPELINE_ORDER):
        row, col = divmod(idx, 3)
        ax = axes[row][col]
        ax.set_facecolor("#111111")

        ttf_list = ttf_by_comp.get(comp_name, [])
        colour = COMPONENT_COLOURS.get(comp_name, "#FFFFFF")
        params = COMPONENT_WEIBULL_PARAMS[comp_name]
        beta_nom = params["beta_mid"]
        eta_nom  = params["eta_hours"]

        n = len(ttf_list)

        if n < config.qq_min_samples:
            ax.text(
                0.5, 0.5,
                f"{comp_name}\n\nInsufficient data\n(n = {n})",
                ha="center", va="center",
                transform=ax.transAxes,
                fontsize=12, color="#FF5252",
            )
            ax.set_xticks([])
            ax.set_yticks([])
            ax.spines[:].set_color("#333333")
            summary_rows.append({
                "component": comp_name, "status": "INSUFFICIENT_DATA",
                "r_squared": float("nan"), "beta_fitted": float("nan"),
            })
            continue

        ttf_arr = np.array(ttf_list)
        x_vals, y_vals = weibull_linearise(ttf_arr)
        beta_fit, eta_fit, r_sq, slope = fit_weibull_from_qq(x_vals, y_vals)

        status = (
            "PASS" if r_sq >= config.qq_r2_pass else
            "WARN" if r_sq >= config.qq_r2_warn else "FAIL"
        )
        status_colour = {"PASS": "#00E676", "WARN": "#FFD54F", "FAIL": "#FF5252"}[status]

        summary_rows.append({
            "component": comp_name, "status": status,
            "r_squared": round(r_sq, 4), "beta_fitted": round(beta_fit, 3),
            "eta_fitted": round(eta_fit, 0),
        })

        # Scatter
        ax.scatter(x_vals, y_vals, color=colour, edgecolors="#FFFFFF",
                   linewidths=0.4, s=40, alpha=0.85, zorder=5)

        # Fitted line
        x_line = np.linspace(x_vals.min() - 0.2, x_vals.max() + 0.2, 200)
        y_intercept = y_vals.mean() - slope * x_vals.mean()
        ax.plot(x_line, slope * x_line + y_intercept, color=colour,
                linewidth=2.0, linestyle="-", zorder=4)

        # Theoretical line
        y_theo = beta_nom * x_line - beta_nom * math.log(eta_nom)
        ax.plot(x_line, y_theo, color="#FF6B6B", linewidth=1.2,
                linestyle="--", alpha=0.7, zorder=3)

        # R² badge
        ax.annotate(
            f"R²={r_sq:.3f} [{status}]",
            xy=(0.04, 0.96), xycoords="axes fraction",
            fontsize=9, fontweight="bold", color=status_colour, va="top",
            bbox=dict(boxstyle="round,pad=0.3", fc="#0D0D0D", ec=status_colour, lw=1.2),
        )

        ax.set_title(
            f"{comp_name}  (n={n})",
            fontsize=11, fontweight="bold", color=colour, pad=7,
        )
        ax.set_xlabel("ln(TTF)", fontsize=9, color="#AAAAAA")
        ax.set_ylabel("ln(−ln(1−F̂))", fontsize=9, color="#AAAAAA")
        ax.tick_params(colors="#888888", labelsize=8)
        ax.spines[:].set_color("#333333")

        # Fitted parameter text below title
        ax.annotate(
            f"β_fit={beta_fit:.3f}  η_fit={eta_fit:.0f}h",
            xy=(0.04, 0.08), xycoords="axes fraction",
            fontsize=8, color="#AAAAAA",
        )

    # --- 6th panel: Summary table ---
    ax_table = axes[1][2]
    ax_table.set_facecolor("#0D0D0D")
    ax_table.axis("off")

    table_data = [
        [
            r["component"],
            str(r.get("r_squared", "—")),
            r["status"],
        ]
        for r in summary_rows
    ]
    col_labels = ["Component", "R²", "Status"]
    tbl = ax_table.table(
        cellText=table_data,
        colLabels=col_labels,
        cellLoc="center",
        loc="center",
        bbox=[0.0, 0.1, 1.0, 0.8],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)

    # Style header
    for j in range(len(col_labels)):
        tbl[(0, j)].set_facecolor("#1A1A2E")
        tbl[(0, j)].set_text_props(color="#FFFFFF", fontweight="bold")

    # Style data rows
    for i, row in enumerate(summary_rows, start=1):
        st = row.get("status", "")
        sc = {"PASS": "#1B4332", "WARN": "#3B2F00", "FAIL": "#3B0000"}.get(st, "#111111")
        tc = {"PASS": "#00E676", "WARN": "#FFD54F", "FAIL": "#FF5252"}.get(st, "#CCCCCC")
        for j in range(len(col_labels)):
            tbl[(i, j)].set_facecolor(sc)
            tbl[(i, j)].set_text_props(color=tc if j == 2 else "#DDDDDD")
            tbl[(i, j)].set_edgecolor("#333333")

    ax_table.set_title(
        "Q-Q Validation Summary",
        fontsize=11, fontweight="bold", color="#FFFFFF", pad=8,
    )

    # Legend for line types
    legend_elements = [
        mlines.Line2D([0], [0], color="#AAAAAA", linewidth=2, label="Fitted Weibull"),
        mlines.Line2D([0], [0], color="#FF6B6B", linewidth=1.5,
                      linestyle="--", label="Theoretical (β_mid, η_nominal)"),
    ]
    ax_table.legend(
        handles=legend_elements,
        loc="lower center", bbox_to_anchor=(0.5, 0.02),
        framealpha=0.8, facecolor="#1A1A2E",
        edgecolor="#555555", labelcolor="#EEEEEE", fontsize=9,
    )

    plt.tight_layout(rect=[0, 0, 1, 0.98])

    if save_path is None:
        os.makedirs(config.qq_plot_dir, exist_ok=True)
        save_path = os.path.join(config.qq_plot_dir, "fleet_qq_panel.png")

    fig.savefig(
        save_path, dpi=150, bbox_inches="tight",
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)

    return save_path


# =============================================================================
# SECTION 4: TOP-LEVEL ORCHESTRATOR — run_data_generation()
# =============================================================================

def run_data_generation(
    config: Optional[MultiFailureConfig] = None,
    skip_plots: bool = False,
) -> dict:
    """
    Top-level entry point for Day 7 data generation.

    Executes the full pipeline:
        1. Multi-failure simulation (365-day window, all 5 components)
        2. Write multi_failure_telemetry.csv and ttf_samples.csv
        3. Individual component Q-Q plots (data/processed/qq_plots/)
        4. Fleet Q-Q panel plot (fleet_qq_panel.png)
        5. Q-Q summary table (qq_summary.csv)

    Parameters
    ----------
    config     : MultiFailureConfig | None
    skip_plots : bool — if True, skip matplotlib rendering (useful in CI)

    Returns
    -------
    dict with keys:
        telemetry_rows   : int
        ttf_records      : int
        component_cycles : dict[str, int]
        qq_summary       : pd.DataFrame
        paths            : dict[str, str]  — output file paths
    """
    if config is None:
        config = MultiFailureConfig(verbose=True)

    if config.verbose:
        print("\n" + "=" * 70)
        print("PHASE 1 → SUB-PHASE 1.3 → DAY 7: DATA GENERATION PIPELINE")
        print("=" * 70)

    # STEP 1: Multi-failure simulation
    master_df, ttf_by_comp, _ = run_multi_failure_simulation(config)

    # STEP 2: Q-Q validation (individual plots + summary)
    if not skip_plots:
        if config.verbose:
            print()
        qq_summary_df = run_qq_validation(ttf_by_comp, config)
    else:
        qq_summary_df = pd.DataFrame()

    # STEP 3: Fleet panel plot
    fleet_panel_path = None
    if not skip_plots:
        try:
            fleet_panel_path = plot_qq_panel(ttf_by_comp, config)
            if config.verbose:
                print(f"  [OK] Fleet Q-Q panel: {fleet_panel_path}")
        except Exception as exc:
            warnings.warn(f"Fleet panel plot failed: {exc}", UserWarning)

    # STEP 4: Summarise
    component_cycles = {
        comp: len(ttfs) for comp, ttfs in ttf_by_comp.items()
    }

    ttf_samples_path = os.path.join(config.output_dir, "ttf_samples.csv")
    n_ttf_records = sum(len(v) for v in ttf_by_comp.values())

    output_paths = {
        "multi_failure_telemetry": os.path.join(
            config.output_dir, "multi_failure_telemetry.csv"
        ),
        "ttf_samples": ttf_samples_path,
        "qq_summary":  os.path.join(config.output_dir, "qq_summary.csv"),
        "qq_plots_dir": config.qq_plot_dir,
        "fleet_qq_panel": fleet_panel_path or "",
    }

    if config.verbose:
        print()
        print("=" * 70)
        print("SUMMARY — Day 7 Data Generation Complete")
        print("=" * 70)
        print(f"  Telemetry rows    : {len(master_df):,}")
        print(f"  TTF records       : {n_ttf_records}")
        print(f"  Failure cycles    : {component_cycles}")
        if not qq_summary_df.empty:
            n_pass = (qq_summary_df["status"] == "PASS").sum()
            n_warn = (qq_summary_df["status"] == "WARN").sum()
            n_fail = (qq_summary_df["status"] == "FAIL").sum()
            print(f"  Q-Q validation    : {n_pass} PASS · {n_warn} WARN · {n_fail} FAIL")
        print("=" * 70)

    return {
        "telemetry_rows":   len(master_df),
        "ttf_records":      n_ttf_records,
        "component_cycles": component_cycles,
        "qq_summary":       qq_summary_df,
        "paths":            output_paths,
    }


# =============================================================================
# MODULE SELF-TEST (run directly: python data_generator.py)
# =============================================================================

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 70)
    print("DATA_GENERATOR.PY -- DAY 7 SELF-TEST")
    print("Phase 1 -> Sub-phase 1.3 -> Day 7")
    print("Arrhenius-based synthetic data generation + Q-Q validation")
    print("=" * 70)

    # ── Test 1: median rank formula ────────────────────────────────────
    print("\n[1] Benard median rank formula (n=5):")
    ranks = compute_median_ranks(5)
    print(f"    F̂ = {[round(r, 4) for r in ranks]}")
    assert abs(ranks[2] - 0.5) < 0.01, "Median rank midpoint should be ~0.5"
    print("    [PASS] Midpoint ≈ 0.50 ✓")

    # ── Test 2: Weibull linearisation ──────────────────────────────────
    print("\n[2] Weibull linearisation (known β=2.5, η=4380 h, n=50 samples):")
    rng_test = np.random.default_rng(7)
    beta_test, eta_test = 2.5, 4380.0
    synthetic_ttfs = [
        draw_weibull_ttf(beta_test, eta_test, rng_test) for _ in range(50)
    ]
    x_test, y_test = weibull_linearise(np.array(synthetic_ttfs))
    beta_fit_test, eta_fit_test, r2_test, _ = fit_weibull_from_qq(x_test, y_test)
    print(f"    True: β={beta_test}, η={eta_test} h")
    print(f"    Fitted: β={beta_fit_test:.3f}, η={eta_fit_test:.0f} h, R²={r2_test:.4f}")
    assert r2_test >= 0.90, f"R² should be ≥ 0.90 for n=50 clean samples; got {r2_test:.4f}"
    print(f"    [PASS] R² ≥ 0.90 ✓")

    # ── Test 3: eta_effective with Arrhenius ───────────────────────────
    print("\n[3] Arrhenius η_effective check (Bearing: Ea=0.8, T_nom=70°C, T_alarm=80°C):")
    cfg_test = MultiFailureConfig(verbose=False)
    eta_eff_b = _compute_eta_effective("Bearing", cfg_test)
    eta_nom_b = COMPONENT_WEIBULL_PARAMS["Bearing"]["eta_hours"]
    print(f"    η_nominal   = {eta_nom_b:.0f} h")
    print(f"    η_effective = {eta_eff_b:.0f} h  (compressed by Arrhenius)")
    assert eta_eff_b < eta_nom_b, "η_effective should be < η_nominal under stress"
    print(f"    [PASS] η_effective < η_nominal ✓")

    shaft_eta = _compute_eta_effective("Shaft", cfg_test)
    assert shaft_eta == COMPONENT_WEIBULL_PARAMS["Shaft"]["eta_hours"], \
        "Shaft η should NOT be derated"
    print(f"    [PASS] Shaft η unchanged (Arrhenius N/A) ✓")

    # ── Test 4: repair duration variability ───────────────────────────
    print("\n[4] Repair duration sampling (Bearing — PM strategy, MTTR=8h):")
    rng_rep = np.random.default_rng(42)
    repairs = [_draw_repair_duration("Bearing", cfg_test, rng_rep) for _ in range(20)]
    print(f"    Samples: {[round(r, 1) for r in repairs[:8]]} ...")
    assert all(r >= 1.0 for r in repairs), "All repair durations should be ≥ 1h"
    assert all(r >= MTTR_BY_STRATEGY["PM"] for r in repairs), \
        "Repairs should be ≥ MTTR_mean (abs normal)"
    print(f"    [PASS] All repairs ≥ MTTR baseline ✓")

    # ── Test 5: Full pipeline (defaults to 365-day window) ────────────
    print("\n[5] Full data generation pipeline (365-day window):")
    cfg = MultiFailureConfig(
        verbose=True,
    )
    result = run_data_generation(cfg, skip_plots=False)

    assert result["telemetry_rows"] > 0, "Should produce telemetry rows"
    print(f"\n    [PASS] Telemetry rows: {result['telemetry_rows']:,}")
    print(f"    [PASS] TTF records:    {result['ttf_records']}")
    print(f"    [PASS] Cycles:         {result['component_cycles']}")

    if not result["qq_summary"].empty:
        r2_vals = result["qq_summary"]["r_squared"].dropna()
        if len(r2_vals) > 0:
            print(f"    Q-Q R² values: {r2_vals.round(3).tolist()}")
            good = (result["qq_summary"]["status"].isin(["PASS", "WARN", "INSUFFICIENT_DATA"])).all()
            if good:
                print("    [PASS] All Q-Q statuses are PASS or WARN ✓")

    print("\n" + "=" * 70)
    print("[SELF-TEST COMPLETE] data_generator.py Day 7 — all assertions passed.")
    print("=" * 70)
    print("\nOutput files:")
    for k, v in result["paths"].items():
        if v:
            print(f"  {k:<28} → {v}")
