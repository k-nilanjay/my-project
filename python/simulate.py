"""
simulate.py — Manufacturing & Industrial Analytics FYP
=======================================================
Sensor Data Generator: Weibull TTF Injection + Arrhenius Topology + Signal Degradation
Phase 1, Sub-phase 1.3 — Data Simulation
Day 5 (scaffold) → Day 6 (full implementation)

PURPOSE
-------
Generate synthetic sensor telemetry for all 5 pipeline components over a
configurable simulation window (default: 30 days × 24 h = 720 hours).

The generator is governed by two mathematical models (locked Day 1):

  1. WEIBULL TIME-TO-FAILURE INJECTION
     -----------------------------------------------
     Each component's time-to-failure (TTF) is drawn from a Weibull distribution
     parameterised by (β, η) from COMPONENT_WEIBULL_PARAMS in reliability.py.

     TTF ~ Weibull(β, η)    →    F(t) = 1 − R(t) = 1 − exp(−(t/η)^β)

     Inverse-CDF sampling (Weibull quantile function):
         TTF = η · (−ln(U))^(1/β)     where U ~ Uniform(0, 1)

  2. ARRHENIUS TOPOLOGY LOGIC
     -----------------------------------------------
     Components with Ea > 0 (all except Shaft) have their characteristic life
     η derated by the Arrhenius Acceleration Factor when operating above nominal
     temperature:

         AF = exp[(Ea/k) · (1/T_use − 1/T_stress)]    [Arrhenius equation]
         η_derated = η_nominal / AF                     [compressed life]

     The derated η is then used to draw the TTF from the Weibull distribution,
     producing a shorter expected life under elevated temperature.

     SHAFT EXCLUSION: Shaft has Ea = None (fatigue-dominant failure mode).
     topology.is_arrhenius_applicable("Shaft") returns False. The Shaft TTF is
     drawn from the nominal Weibull distribution without thermal derating.

  3. SIGNAL DEGRADATION MODEL (Day 6 — implemented)
     -----------------------------------------------
     Each sensor signal follows a two-phase profile:
       a. Healthy phase [0, TTF × (1 − RAMP_FRACTION)]:
              value = baseline + Gaussian noise
       b. Degradation ramp [TTF × (1 − RAMP_FRACTION), TTF]:
              ramp_progress = (t − ramp_start) / (TTF − ramp_start)  ∈ [0, 1]
              value = baseline + (alarm_threshold − baseline) × ramp_progress²
                      + Gaussian noise
          The quadratic ramp (ramp_progress²) reflects slow initial wear
          accelerating to threshold near TTF — consistent with Weibull β > 1.
       c. Post-failure [TTF, window_end]:
              is_failure_event = 1 at t == TTF timestep
              value = danger_threshold + positive spike noise (runaway degradation)

  4. CASCADE PROPAGATION (Day 6 — implemented)
     -----------------------------------------------
     When component at position N fails (has TTF within the window), all downstream
     components (positions N+1 through 5) receive an accelerated degradation boost:
         cascade_vib_boost = 0.5 × (alarm_threshold − baseline)
     This boost is applied additively from the upstream TTF onward, simulating
     the physical effect of upstream failure on downstream sensor readings.

SIMULATION ARCHITECTURE
----------------------------------------------------------------------
  ┌───────────────────────────────────────────────────────────────┐
  │  SimulationConfig — dataclass holding all run parameters      │
  └─────────────────────────────┬─────────────────────────────────┘
                                │
  ┌─────────────────────────────▼─────────────────────────────────┐
  │  generate_component_telemetry(component_name, config, rng)    │
  │    - Draw TTF from Weibull (with Arrhenius derating for η)    │
  │    - Inject degradation ramp on all sensor channels           │
  │    - Flag is_failure_event = 1 at TTF timestep               │
  │    - Accepts upstream_failure_times for cascade boost         │
  │    - Return: pd.DataFrame (one row per timestep per sensor)   │
  └─────────────────────────────┬─────────────────────────────────┘
                                │ called for each of 5 components
  ┌─────────────────────────────▼─────────────────────────────────┐
  │  run_simulation(config)                                        │
  │    - Iterates PIPELINE_ORDER (topology.topological_sort())    │
  │    - Collects TTF from each component; propagates downstream  │
  │    - Writes 5 CSVs + master CSV to data/raw/                  │
  │    - Returns dict {component_name: DataFrame}                 │
  └───────────────────────────────────────────────────────────────┘

SQL OUTPUT TARGETS
------------------
  data/raw/<ComponentName>_telemetry.csv
      → loaded by etl.py into sensor_readings table

  Columns generated (matching sensor_readings schema):
      ts                 DATETIME  — ISO 8601 timestamp
      component_id       INTEGER   — from topology.COMPONENT_POSITIONS
      component_name     VARCHAR   — component name string
      sensor_type        VARCHAR   — 'vibration' | 'temperature' | 'oil_debris' | 'rpm' | 'load'
      value              FLOAT     — sensor reading
      is_failure_event   INTEGER   — 1 if this reading coincides with a TTF event
      failure_mode       VARCHAR   — NULL unless is_failure_event = 1
      R_derated          FLOAT     — condition-adjusted Weibull reliability at this timestep
      AF                 FLOAT     — Arrhenius Acceleration Factor at this timestep
      cascade_flag       INTEGER   — 1 if reading is elevated due to upstream cascade

MATHEMATICAL FOUNDATIONS (Day 1, locked — from CONTEXT.md)
------------------------------------------------------------
Weibull R(t):       R(t) = exp(−(t/η)^β)
Weibull quantile:   TTF  = η · (−ln(U))^(1/β)    U ~ Uniform(0,1)
Arrhenius AF:       AF   = exp[(Ea/k) · (1/T_use − 1/T_stress)]
η derated:          η*   = η / AF
Derated R(t):       R*(t) = exp(−(t/η*)^β)    [condition-adjusted reliability]
Series R_sys:       R_sys = ∏ R_i(t)           [from reliability.series_system_reliability]
Degradation ramp:   value = baseline + (alarm − baseline) × ramp_progress²    [quadratic]
"""

from __future__ import annotations

import datetime
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Internal project imports
from reliability import (
    COMPONENT_WEIBULL_PARAMS,
    BOLTZMANN_EV_PER_K,
    arrhenius_acceleration_factor,
    eta_derated,
    weibull_reliability,
    celsius_to_kelvin,
)
from topology import (
    COMPONENT_POSITIONS,
    PIPELINE_ORDER,
    COMPONENT_TOPOLOGY_META,
    get_downstream_components,
    get_cascade_affected_positions,
    is_arrhenius_applicable,
    topological_sort,
)


# =============================================================================
# SIMULATION CONFIGURATION
# =============================================================================

# Nominal operating temperatures (°C) per component — baseline for Arrhenius derating.
# These are the "T_use" temperatures: the design-point operating temperatures
# at which the Ea and η values from seed.sql are valid.
# Any sensor reading above T_nominal triggers Arrhenius derating.
NOMINAL_TEMPERATURES_CELSIUS: dict[str, float] = {
    "Bearing":       70.0,   # typical deep-groove ball bearing running temp
    "Shaft":         None,   # Arrhenius not applicable (fatigue dominant)
    "Motor Housing": 110.0,  # IEC Class F rated temperature midpoint
    "Coupling":      60.0,   # elastomer coupling nominal operating temperature
    "Gearbox":       75.0,   # gear oil operating temperature (below 90°C alarm)
}

# Baseline sensor signal levels (nominal, no degradation).
# Values correspond to ISO Zone A / healthy operating range.
NOMINAL_SENSOR_VALUES: dict[str, dict[str, float]] = {
    "Bearing": {
        "vibration":    1.2,    # mm/s RMS — ISO Zone A midpoint
        "temperature":  70.0,   # °C — nominal running temperature
    },
    "Shaft": {
        "vibration":    1.0,    # mm/s RMS — 1× harmonic broadband proxy
        "rpm":          1480.0, # rpm — rated motor speed (4-pole, 50 Hz ≈ 1500 rpm)
    },
    "Motor Housing": {
        "temperature":  110.0,  # °C — IEC Class F midpoint
        "vibration":    0.8,    # mm/s RMS — structure-borne looseness baseline
    },
    "Coupling": {
        "vibration":    1.1,    # mm/s RMS — 2× harmonic baseline
        "load":         75.0,   # % — nominal load (below 90% alarm)
    },
    "Gearbox": {
        "vibration":    1.5,    # mm/s RMS — envelope analysis baseline
        "oil_debris":   10.0,   # particles/mL — healthy oil
        "temperature":  75.0,   # °C — sump temperature nominal
    },
}

# Alarm and danger thresholds per sensor type (from seed.sql, Day 4 locked)
SENSOR_THRESHOLDS: dict[str, dict[str, dict[str, float]]] = {
    "Bearing": {
        "vibration":   {"alarm": 4.5,   "danger": 7.1},    # ISO 10816-3
        "temperature": {"alarm": 80.0,  "danger": 100.0},  # grease degradation
    },
    "Shaft": {
        "vibration":   {"alarm": 4.5,   "danger": 7.1},
        "rpm":         {"alarm": None,  "danger": None},    # no ISO threshold
    },
    "Motor Housing": {
        "temperature": {"alarm": 130.0, "danger": 155.0},  # IEC 60085 Class F
        "vibration":   {"alarm": 4.5,   "danger": 7.1},
    },
    "Coupling": {
        "vibration":   {"alarm": 4.5,   "danger": 7.1},
        "load":        {"alarm": 90.0,  "danger": 100.0},  # elastomer design load
    },
    "Gearbox": {
        "vibration":   {"alarm": 4.5,   "danger": 7.1},
        "oil_debris":  {"alarm": 50.0,  "danger": 200.0},  # ISO 4406 particles/mL
        "temperature": {"alarm": 90.0,  "danger": 110.0},  # oil oxidation risk
    },
}

# Failure modes per component (string that populates failure_mode column)
FAILURE_MODES: dict[str, str] = {
    "Bearing":       "rolling_element_fatigue",
    "Shaft":         "fatigue_imbalance",
    "Motor Housing": "winding_insulation_degradation",
    "Coupling":      "elastomer_ageing",
    "Gearbox":       "gear_tooth_pitting",
}

# RPM drop profile: RPM falls as component degrades (Shaft only)
# RPM at start of degradation ramp, as a fraction of nominal
RPM_RAMP_FLOOR_FRACTION: float = 0.80  # RPM drops to 80% of nominal at failure

# Degradation ramp fraction: last RAMP_FRACTION of TTF shows increasing signals
# e.g. 0.30 → degradation ramp begins at 70% of TTF
DEGRADATION_RAMP_FRACTION: float = 0.30

# Cascade vibration boost: fraction of (alarm − baseline) added to downstream
# components once an upstream component fails
CASCADE_VIB_BOOST_FRACTION: float = 0.50


@dataclass
class SimulationConfig:
    """
    Configuration dataclass for a simulation run.

    All parameters are documented below with their units and rationale.
    Default values produce a 30-day run with seed=42 (reproducible).
    """

    # Time window
    window_days: int = 30
    """Number of calendar days to simulate. Default 30 covers ~1 MTBF cycle
    for the shortest-lived component (Bearing/Gearbox: η ≈ 4380 h / 365 ≈ 12 days
    per month of simulated data). Simulation time is in operating hours, not
    calendar hours — assumes 24 h/day continuous operation for simplicity."""

    timestep_hours: float = 1.0
    """Resolution of the telemetry time series. 1-hour intervals produce
    720 rows per component per 30-day window — manageable for SQLite dev DB."""

    # Reproducibility
    random_seed: int = 42
    """Seed for numpy.random.default_rng() so that simulation runs are
    deterministic for academic reproducibility. Set to None for non-deterministic."""

    # Output paths
    output_dir: str = "data/raw"
    """Directory where per-component CSV files are written."""

    # Operating temperature (used as T_use in Arrhenius derating)
    nominal_temperatures: dict[str, Optional[float]] = field(
        default_factory=lambda: dict(NOMINAL_TEMPERATURES_CELSIUS)
    )

    # Degradation noise model
    noise_std_vibration: float = 0.15
    """Standard deviation of Gaussian noise added to vibration readings (mm/s RMS).
    Represents sensor measurement uncertainty and ambient vibration variation."""

    noise_std_temperature: float = 2.0
    """Standard deviation of Gaussian noise added to temperature readings (°C)."""

    noise_std_oil_debris: float = 1.5
    """Standard deviation of Gaussian noise added to oil debris counts (particles/mL)."""

    noise_std_rpm: float = 5.0
    """Standard deviation of Gaussian noise added to RPM readings."""

    noise_std_load: float = 1.0
    """Standard deviation of Gaussian noise added to load % readings."""

    # Arrhenius stress scenario
    arrhenius_stress_enabled: bool = True
    """If True, apply Arrhenius derating when sensor temperature exceeds T_nominal.
    Setting False produces nominal Weibull failures without thermal acceleration."""

    # Cascade boost
    cascade_boost_enabled: bool = True
    """If True, downstream components receive signal boost when an upstream
    component fails — modelling the physical cascade propagation."""

    # Verbose output for debugging
    verbose: bool = False


# =============================================================================
# 1. WEIBULL TIME-TO-FAILURE INJECTION
# =============================================================================

def draw_weibull_ttf(
    beta: float,
    eta: float,
    rng: np.random.Generator,
) -> float:
    """
    Draw a single time-to-failure (TTF) sample from a Weibull distribution
    using the inverse-CDF (quantile function) method.

    FORMULA
    -------
        TTF = η · (−ln(U))^(1/β)     where U ~ Uniform(0, 1)

    DERIVATION
    ----------
    The Weibull CDF is F(t) = 1 − exp(−(t/η)^β).
    Setting F(t) = U (a uniform random variable on [0,1]) and solving for t:

        1 − exp(−(t/η)^β) = U
        exp(−(t/η)^β)     = 1 − U         [1-U is also Uniform(0,1)]
        −(t/η)^β          = ln(1-U)
        (t/η)^β           = −ln(1-U)
        t                 = η · (−ln(1-U))^(1/β)

    In practice we replace (1-U) with U since U is Uniform(0,1) and
    (1-U) is identically distributed:
        TTF = η · (−ln(U))^(1/β)

    This is the standard Weibull quantile function used in Monte Carlo
    reliability simulation (e.g., MIL-HDBK-189C, Meeker & Escobar 1998).

    VIVA DEFENCE NOTE:
        The inverse-CDF method is preferred over numpy's built-in Weibull sampler
        (np.random.weibull) because it makes the (β, η) parameterisation explicit,
        avoids the unit-scale convention difference, and is identical to the formula
        taught in reliability engineering curricula. Both produce the same
        distribution — this version is more transparent.

    Parameters
    ----------
    beta : float — Weibull shape parameter β (> 0); controls failure rate shape
    eta  : float — Weibull scale parameter η (> 0); characteristic life in hours
    rng  : np.random.Generator — seeded random generator for reproducibility

    Returns
    -------
    float — sampled time-to-failure in hours (> 0)
    """
    if beta <= 0:
        raise ValueError(f"β must be > 0; received {beta}")
    if eta <= 0:
        raise ValueError(f"η must be > 0; received {eta}")

    u = rng.uniform(low=1e-9, high=1.0 - 1e-9)  # avoid ln(0) at boundaries
    ttf = eta * ((-math.log(u)) ** (1.0 / beta))
    return float(ttf)


# =============================================================================
# 2. ARRHENIUS ACCELERATION FACTOR (topology-aware wrapper)
# =============================================================================

def arrhenius_af_for_component(
    component_name: str,
    t_reading_celsius: float,
    config: SimulationConfig,
) -> float:
    """
    Compute the Arrhenius Acceleration Factor for a specific component given
    its current sensor temperature reading.

    This is the topology-aware wrapper around reliability.arrhenius_acceleration_factor().
    It enforces the Shaft exclusion rule (Ea = None) and retrieves the correct
    Ea value from COMPONENT_WEIBULL_PARAMS.

    FORMULA (from reliability.py, Day 1 locked)
    -------
        AF = exp[(Ea/k) · (1/T_use − 1/T_stress)]

    where:
        Ea       = activation energy (eV) from COMPONENT_WEIBULL_PARAMS
        k        = 8.617×10⁻⁵ eV/K (Boltzmann's constant)
        T_use    = nominal operating temperature (K) from config.nominal_temperatures
        T_stress = current sensor reading (K) from t_reading_celsius

    Parameters
    ----------
    component_name     : str   — must be a valid PIPELINE_ORDER component
    t_reading_celsius  : float — current temperature sensor reading (°C)
    config             : SimulationConfig

    Returns
    -------
    float — Acceleration Factor AF ≥ 1.0 (when T_reading > T_nominal)
            Returns 1.0 (no derating) when:
              - Arrhenius is not applicable (Shaft)
              - config.arrhenius_stress_enabled is False
              - T_reading ≤ T_nominal (no stress above nominal)
    """
    if not config.arrhenius_stress_enabled:
        return 1.0

    if not is_arrhenius_applicable(component_name):
        return 1.0   # Shaft: fatigue-dominant, no thermal model

    t_nominal = config.nominal_temperatures.get(component_name)
    if t_nominal is None:
        return 1.0

    if t_reading_celsius <= t_nominal:
        return 1.0   # not above nominal → no acceleration

    ea = COMPONENT_WEIBULL_PARAMS[component_name]["ea_ev"]
    if ea is None:
        return 1.0

    return arrhenius_acceleration_factor(ea, t_nominal, t_reading_celsius)


# =============================================================================
# 3. DERATED η WRAPPER (topology-aware)
# =============================================================================

def eta_derated_for_component(
    component_name: str,
    t_reading_celsius: float,
    config: SimulationConfig,
) -> float:
    """
    Compute the thermally derated characteristic life η* for a component
    given its current temperature sensor reading.

    FORMULA (from reliability.py, Day 1 locked)
    -------
        η* = η_nominal / AF

    Parameters
    ----------
    component_name     : str   — pipeline component name
    t_reading_celsius  : float — current temperature reading (°C)
    config             : SimulationConfig

    Returns
    -------
    float — derated characteristic life η* in hours
    """
    eta_nominal = COMPONENT_WEIBULL_PARAMS[component_name]["eta_hours"]
    af = arrhenius_af_for_component(component_name, t_reading_celsius, config)
    return eta_derated(eta_nominal, af)


# =============================================================================
# 4. DERATED WEIBULL RELIABILITY (condition-adjusted R(t))
# =============================================================================

def derated_weibull_reliability(
    component_name: str,
    t_elapsed_hours: float,
    t_reading_celsius: float,
    config: SimulationConfig,
    beta_override: Optional[float] = None,
) -> dict[str, float]:
    """
    Compute condition-adjusted Weibull reliability R*(t) accounting for
    Arrhenius temperature derating on the characteristic life η.

    FORMULA CHAIN
    -------
        Step 1: AF = exp[(Ea/k) · (1/T_use − 1/T_stress)]
        Step 2: η* = η_nominal / AF
        Step 3: R*(t) = exp(−(t/η*)^β) = exp(−(t · AF / η_nominal)^β)

    Parameters
    ----------
    component_name      : str
    t_elapsed_hours     : float — elapsed operating time (≥ 0)
    t_reading_celsius   : float — current temperature sensor reading (°C)
    config              : SimulationConfig
    beta_override       : float | None — override β (use fitted MLE value if available)

    Returns
    -------
    dict with keys: R_nominal, R_derated, AF, eta_nominal, eta_derated, beta, component
    """
    if t_elapsed_hours < 0:
        raise ValueError(f"t_elapsed_hours must be ≥ 0; received {t_elapsed_hours}")

    params       = COMPONENT_WEIBULL_PARAMS[component_name]
    beta         = beta_override if beta_override is not None else params["beta_mid"]
    eta_nom      = params["eta_hours"]

    af           = arrhenius_af_for_component(component_name, t_reading_celsius, config)
    eta_star     = eta_derated(eta_nom, af)

    r_nominal    = weibull_reliability(t_elapsed_hours, beta, eta_nom)
    r_derated    = weibull_reliability(t_elapsed_hours, beta, eta_star)

    return {
        "R_nominal":   round(r_nominal, 6),
        "R_derated":   round(r_derated, 6),
        "AF":          round(af, 4),
        "eta_nominal": round(eta_nom, 2),
        "eta_derated": round(eta_star, 2),
        "beta":        round(beta, 4),
        "component":   component_name,
    }


# =============================================================================
# 5. SIGNAL INJECTION HELPERS (Day 6)
# =============================================================================

def _compute_ramp_progress(
    t_hours: float,
    ttf_hours: float,
    ramp_fraction: float = DEGRADATION_RAMP_FRACTION,
) -> float:
    """
    Compute the degradation ramp progress ∈ [0.0, 1.0] at time t_hours.

    The ramp begins at (1 − ramp_fraction) × TTF and reaches 1.0 at TTF.

    FORMULA
    -------
        ramp_start = TTF × (1 − ramp_fraction)
        If t < ramp_start:   progress = 0.0  (healthy phase)
        If t >= TTF:         progress = 1.0  (failure reached)
        Else: progress = (t − ramp_start) / (TTF − ramp_start)   ∈ (0, 1)

    The quadratic shape (progress²) applied by the caller models slow initial
    wear that accelerates toward failure — consistent with Weibull β > 1
    (wear-out failure mode).

    Parameters
    ----------
    t_hours      : float — current simulation time (hours)
    ttf_hours    : float — Weibull-sampled time to failure (hours)
    ramp_fraction: float — fraction of TTF over which degradation ramp occurs

    Returns
    -------
    float — ramp progress ∈ [0.0, 1.0]
    """
    ramp_start = ttf_hours * (1.0 - ramp_fraction)
    if t_hours < ramp_start:
        return 0.0
    if t_hours >= ttf_hours:
        return 1.0
    return (t_hours - ramp_start) / (ttf_hours - ramp_start)


def _inject_vibration(
    t_hours: float,
    ttf_hours: float,
    baseline: float,
    alarm: float,
    danger: float,
    cascade_boost: float,
    rng: np.random.Generator,
    noise_std: float,
) -> float:
    """
    Compute a vibration sensor reading with degradation ramp and cascade boost.

    SIGNAL MODEL
    ------------
    Healthy phase (t < ramp_start):
        value = baseline + N(0, noise_std)

    Degradation ramp (ramp_start ≤ t < TTF):
        ramp_progress ∈ (0, 1)
        value = baseline + (alarm − baseline) × ramp_progress² + N(0, noise_std)
        [Quadratic ramp: slow at first, accelerates toward alarm near TTF]

    Post-failure (t ≥ TTF):
        value = danger + |N(0, noise_std × 3)|  [runaway above danger threshold]

    Cascade boost (applied when upstream component has failed):
        value += cascade_boost   [additive displacement after upstream failure]

    Parameters
    ----------
    t_hours      : float — current time (hours)
    ttf_hours    : float — Weibull TTF for this component
    baseline     : float — nominal healthy vibration (mm/s RMS)
    alarm        : float — ISO 10816-3 Zone C alarm threshold
    danger       : float — ISO 10816-3 Zone D danger threshold
    cascade_boost: float — additional vibration from upstream failure (0 if no cascade)
    rng          : np.random.Generator
    noise_std    : float — Gaussian noise σ

    Returns
    -------
    float — vibration reading in mm/s RMS (always ≥ 0)
    """
    progress = _compute_ramp_progress(t_hours, ttf_hours)

    if t_hours >= ttf_hours:
        # Post-failure: runaway beyond danger threshold
        value = danger + abs(rng.normal(0.0, noise_std * 3.0))
    elif progress > 0.0:
        # Degradation ramp: quadratic rise baseline → alarm
        ramp_value = baseline + (alarm - baseline) * (progress ** 2)
        value = ramp_value + rng.normal(0.0, noise_std)
    else:
        # Healthy phase
        value = baseline + rng.normal(0.0, noise_std)

    # Apply cascade boost (0.0 when no upstream failure)
    value += cascade_boost

    return max(0.0, round(float(value), 4))


def _inject_temperature(
    t_hours: float,
    ttf_hours: float,
    baseline: float,
    alarm: float,
    danger: float,
    rng: np.random.Generator,
    noise_std: float,
) -> float:
    """
    Compute a temperature sensor reading with degradation ramp.

    SIGNAL MODEL (analogous to vibration)
    -------
    Healthy:     value = baseline + N(0, noise_std)
    Ramp:        value = baseline + (alarm − baseline) × ramp_progress² + N(0, noise_std)
    Post-failure: value = danger + |N(0, noise_std × 2)|

    Temperature does NOT receive a cascade boost directly — instead the
    upstream failure affects downstream component loads, which is modelled
    by increasing the component's own ramp rate (this is captured automatically
    by the cascade-adjusted TTF).

    Returns
    -------
    float — temperature in °C (always ≥ 0)
    """
    progress = _compute_ramp_progress(t_hours, ttf_hours)

    if t_hours >= ttf_hours:
        value = danger + abs(rng.normal(0.0, noise_std * 2.0))
    elif progress > 0.0:
        ramp_value = baseline + (alarm - baseline) * (progress ** 2)
        value = ramp_value + rng.normal(0.0, noise_std)
    else:
        value = baseline + rng.normal(0.0, noise_std)

    return max(0.0, round(float(value), 4))


def _inject_oil_debris(
    t_hours: float,
    ttf_hours: float,
    baseline: float,
    alarm: float,
    danger: float,
    rng: np.random.Generator,
    noise_std: float,
) -> float:
    """
    Compute an oil debris count reading with exponential ramp near TTF.

    OIL DEBRIS MODEL
    ----------------
    Oil debris (wear particles per mL) follows an exponential accumulation
    profile rather than quadratic — gear pitting generates particles
    exponentially as tooth surface degrades (consistent with ISO 4406).

    Healthy:      value = baseline + |N(0, noise_std)|
    Ramp:         value = baseline + (alarm − baseline) × exp(3 × ramp_progress − 3)
                  [Exponential ramp: slow release initially, rapid near failure]
    Post-failure: value = danger + |N(0, noise_std × 5)|   [severe contamination]

    Returns
    -------
    float — oil debris count (particles/mL, always ≥ 0)
    """
    progress = _compute_ramp_progress(t_hours, ttf_hours)

    if t_hours >= ttf_hours:
        value = danger + abs(rng.normal(0.0, noise_std * 5.0))
    elif progress > 0.0:
        # Exponential ramp: e^(3p-3) maps [0→1] onto [e^-3 ≈ 0.05 → 1.0]
        exp_ramp = math.exp(3.0 * progress - 3.0)
        value = baseline + (alarm - baseline) * exp_ramp + rng.normal(0.0, noise_std)
    else:
        value = baseline + abs(rng.normal(0.0, noise_std))

    return max(0.0, round(float(value), 4))


def _inject_rpm(
    t_hours: float,
    ttf_hours: float,
    baseline_rpm: float,
    rng: np.random.Generator,
    noise_std: float,
) -> float:
    """
    Compute an RPM reading that drops linearly as a component approaches failure.

    RPM DROP MODEL
    --------------
    The Shaft (primary RPM consumer) experiences reduced speed as imbalance
    worsens — the motor controller throttles to prevent vibration overshoot.

    Healthy:     rpm = baseline + N(0, noise_std)
    Ramp:        rpm = baseline − (baseline × (1 − RPM_RAMP_FLOOR_FRACTION)) × ramp_progress
                 [Linear drop from baseline to floor fraction of baseline]
    Post-failure: rpm = 0.0 (shaft stops)

    Returns
    -------
    float — RPM reading (always ≥ 0)
    """
    progress = _compute_ramp_progress(t_hours, ttf_hours)

    if t_hours >= ttf_hours:
        return 0.0
    elif progress > 0.0:
        rpm_drop = baseline_rpm * (1.0 - RPM_RAMP_FLOOR_FRACTION) * progress
        value = baseline_rpm - rpm_drop + rng.normal(0.0, noise_std)
    else:
        value = baseline_rpm + rng.normal(0.0, noise_std)

    return max(0.0, round(float(value), 2))


def _inject_load(
    t_hours: float,
    ttf_hours: float,
    baseline_load: float,
    alarm: float,
    rng: np.random.Generator,
    noise_std: float,
) -> float:
    """
    Compute a load (%) reading that rises as a coupling degrades.

    LOAD MODEL
    ----------
    A degrading coupling transfers load less efficiently, causing the motor
    to draw increasing load (current increases → load % rises toward alarm).

    Healthy:      load = baseline + N(0, noise_std)
    Ramp:         load = baseline + (alarm − baseline) × ramp_progress²
    Post-failure: load = 0.0 (coupling shears — no load transmitted)

    Returns
    -------
    float — load % ∈ [0, 100]
    """
    progress = _compute_ramp_progress(t_hours, ttf_hours)

    if t_hours >= ttf_hours:
        return 0.0
    elif progress > 0.0:
        ramp_value = baseline_load + (alarm - baseline_load) * (progress ** 2)
        value = ramp_value + rng.normal(0.0, noise_std)
    else:
        value = baseline_load + rng.normal(0.0, noise_std)

    return float(max(0.0, min(100.0, round(float(value), 2))))


# =============================================================================
# 6. SINGLE-COMPONENT TELEMETRY GENERATOR (Day 6 — full implementation)
# =============================================================================

def generate_component_telemetry(
    component_name: str,
    config: SimulationConfig,
    rng: np.random.Generator,
    upstream_failure_times: Optional[Dict[str, float]] = None,
) -> Tuple[pd.DataFrame, float]:
    """
    Generate synthetic sensor telemetry for one pipeline component over
    the full simulation window.

    ALGORITHM
    ---------
    1. Determine effective η: apply Arrhenius derating if temperature > T_nominal.
       For the TTF draw, the temperature sensor's alarm threshold is used as the
       representative stress temperature (conservative: component is assumed to
       operate at alarm level during its degradation phase).
    2. Draw TTF via draw_weibull_ttf(β, η_effective, rng).
    3. For each timestep t in [0, window_hours]:
       a. Compute ramp_progress = _compute_ramp_progress(t, TTF)
       b. For each sensor channel of this component:
          - Call the appropriate _inject_*() helper
          - Compute R*(t) via derated_weibull_reliability()
          - Set is_failure_event = 1 when t == TTF timestep (within Δt tolerance)
       c. Apply cascade_boost to vibration channels if any upstream component
          has failed before time t (upstream_failure_times dict).
    4. Return (DataFrame, ttf_hours).

    SIGNAL CHANNELS PER COMPONENT
    ------------------------------
    Bearing:       vibration (primary), temperature
    Shaft:         vibration (primary), rpm
    Motor Housing: temperature (primary), vibration
    Coupling:      vibration (primary), load
    Gearbox:       vibration (primary), oil_debris, temperature

    Parameters
    ----------
    component_name        : str — pipeline component name
    config                : SimulationConfig
    rng                   : np.random.Generator — seeded generator
    upstream_failure_times: dict[str, float] | None
        Map of {upstream_component_name: ttf_hours} for components that have
        already been simulated. None means no upstream failures (i.e., Bearing).

    Returns
    -------
    Tuple[pd.DataFrame, float]
        - DataFrame: one row per (timestep, sensor_channel) pair
          Columns: ts, component_id, component_name, sensor_type, value,
                   is_failure_event, failure_mode, R_derated, AF, cascade_flag
        - float: TTF in hours drawn for this component
    """
    if upstream_failure_times is None:
        upstream_failure_times = {}

    params   = COMPONENT_WEIBULL_PARAMS[component_name]
    beta     = params["beta_mid"]
    eta_nom  = params["eta_hours"]
    comp_id  = COMPONENT_POSITIONS[component_name]
    thresholds = SENSOR_THRESHOLDS[component_name]
    baselines  = NOMINAL_SENSOR_VALUES[component_name]
    failure_mode_str = FAILURE_MODES[component_name]

    window_hours = config.window_days * 24
    timesteps    = [i * config.timestep_hours for i in range(int(window_hours / config.timestep_hours) + 1)]

    # --- Determine effective η for TTF draw ---
    # Use the temperature alarm level as the Arrhenius stress temperature for TTF draw.
    # This is conservative: it represents the expected temperature during the
    # degradation phase when Arrhenius acceleration is most relevant.
    if is_arrhenius_applicable(component_name) and "temperature" in thresholds:
        t_stress_for_draw = thresholds["temperature"]["alarm"]
        eta_eff = eta_derated_for_component(component_name, t_stress_for_draw, config)
    else:
        eta_eff = eta_nom

    # --- Draw TTF from Weibull ---
    ttf_hours = draw_weibull_ttf(beta, eta_eff, rng)

    if config.verbose:
        in_window = ttf_hours <= window_hours
        print(f"    {component_name}: TTF = {ttf_hours:.1f} h "
              f"({'IN WINDOW' if in_window else 'beyond window'}), "
              f"eta_eff = {eta_eff:.0f} h, beta = {beta:.2f}")

    # --- Determine cascade boost schedule ---
    # Find the earliest upstream failure time (if any) within the window
    earliest_upstream_failure: Optional[float] = None
    if config.cascade_boost_enabled and upstream_failure_times:
        upstream_failures_in_window = [
            t for t in upstream_failure_times.values()
            if t <= window_hours
        ]
        if upstream_failures_in_window:
            earliest_upstream_failure = min(upstream_failures_in_window)

    # Pre-compute cascade vibration boost magnitude
    # = CASCADE_VIB_BOOST_FRACTION × (alarm − baseline) for primary vibration channel
    if "vibration" in baselines and "vibration" in thresholds:
        vib_baseline = baselines["vibration"]
        vib_alarm    = thresholds["vibration"]["alarm"]
        cascade_vib_boost = CASCADE_VIB_BOOST_FRACTION * (vib_alarm - vib_baseline)
    else:
        cascade_vib_boost = 0.0

    # --- Build telemetry rows ---
    records = []

    for t_hours in timesteps:
        ts_str   = _hours_to_iso(t_hours)
        # Determine if cascade boost applies at this timestep
        cascade_active = (
            earliest_upstream_failure is not None
            and t_hours >= earliest_upstream_failure
        )
        boost_this_step = cascade_vib_boost if cascade_active else 0.0

        # Is this the failure event timestep?
        # We flag failure at the first timestep t ≥ TTF (within 1 timestep tolerance)
        is_failure = 1 if (ttf_hours <= window_hours and t_hours >= ttf_hours
                           and t_hours < ttf_hours + config.timestep_hours) else 0

        # Compute reliability at this timestep
        # Use the temperature reading to drive Arrhenius (proxy: use nominal for now)
        t_nominal = config.nominal_temperatures.get(component_name)
        t_for_reliability = t_nominal if t_nominal is not None else 25.0
        rel_dict = derated_weibull_reliability(
            component_name,
            max(0.0, t_hours),
            t_for_reliability,
            config,
        )
        r_derated = rel_dict["R_derated"]
        af_val    = rel_dict["AF"]

        # --- Inject all sensor channels for this component ---
        channels = _get_sensor_channels(component_name)

        for sensor_type in channels:
            baseline  = baselines.get(sensor_type, 0.0)

            if sensor_type == "vibration":
                alarm  = thresholds["vibration"]["alarm"]
                danger = thresholds["vibration"]["danger"]
                value  = _inject_vibration(
                    t_hours, ttf_hours, baseline, alarm, danger,
                    boost_this_step, rng, config.noise_std_vibration,
                )

            elif sensor_type == "temperature":
                alarm  = thresholds["temperature"]["alarm"]
                danger = thresholds["temperature"]["danger"]
                value  = _inject_temperature(
                    t_hours, ttf_hours, baseline, alarm, danger,
                    rng, config.noise_std_temperature,
                )

            elif sensor_type == "oil_debris":
                alarm  = thresholds["oil_debris"]["alarm"]
                danger = thresholds["oil_debris"]["danger"]
                value  = _inject_oil_debris(
                    t_hours, ttf_hours, baseline, alarm, danger,
                    rng, config.noise_std_oil_debris,
                )

            elif sensor_type == "rpm":
                value = _inject_rpm(
                    t_hours, ttf_hours, baseline,
                    rng, config.noise_std_rpm,
                )

            elif sensor_type == "load":
                alarm = thresholds["load"]["alarm"]
                value = _inject_load(
                    t_hours, ttf_hours, baseline, alarm,
                    rng, config.noise_std_load,
                )
            else:
                value = baseline  # fallback: flat nominal

            records.append({
                "ts":               ts_str,
                "component_id":     comp_id,
                "component_name":   component_name,
                "sensor_type":      sensor_type,
                "value":            value,
                "is_failure_event": is_failure if sensor_type == _primary_sensor(component_name) else 0,
                "failure_mode":     failure_mode_str if (is_failure == 1 and sensor_type == _primary_sensor(component_name)) else None,
                "R_derated":        round(r_derated, 6),
                "AF":               round(af_val, 4),
                "cascade_flag":     1 if (cascade_active and sensor_type == "vibration") else 0,
            })

    df = pd.DataFrame(records)
    return df, ttf_hours


# =============================================================================
# 7. FULL SIMULATION RUN (Day 6 — full implementation with cascade propagation)
# =============================================================================

def run_simulation(config: Optional[SimulationConfig] = None) -> dict[str, pd.DataFrame]:
    """
    Execute a full simulation run for all 5 pipeline components.

    Iterates components in topological order (Bearing → Gearbox), applies
    cascade failure propagation, and writes one CSV per component plus a
    master telemetry CSV to config.output_dir.

    CASCADE PROPAGATION ALGORITHM
    ------------------------------
    1. Simulate Bearing first. Record its TTF.
    2. Simulate Shaft, passing Bearing's TTF as upstream_failure_times.
       If Bearing fails within the window, Shaft receives cascade boost from
       the Bearing failure timestep onward.
    3. Repeat for Motor Housing (upstream: Bearing, Shaft), Coupling, Gearbox.
    4. The cascade boost is applied independently of Shaft's own TTF — a
       downstream component can fail from its own Weibull TTF OR be degraded
       by upstream cascade signals, whichever comes first in the window.

    Note: Cascade does NOT shorten the downstream TTF directly. Instead, it
    elevates the downstream sensor signals visually. In the diagnostic phase
    (Days 24–27), anomaly detection on these elevated signals will produce
    cascade_upstream failure flags — consistent with the Day 2 locked taxonomy.

    Parameters
    ----------
    config : SimulationConfig | None — uses defaults if None

    Returns
    -------
    dict[str, pd.DataFrame] — {component_name: telemetry_df}
    """
    if config is None:
        config = SimulationConfig()

    rng = np.random.default_rng(config.random_seed)

    if config.verbose:
        print(f"[simulate.py] Starting simulation: {config.window_days} days, "
              f"dt = {config.timestep_hours} h, seed = {config.random_seed}")

    os.makedirs(config.output_dir, exist_ok=True)

    results: dict[str, pd.DataFrame] = {}
    component_ttfs: dict[str, float] = {}  # tracks TTF for each component
    component_order = topological_sort()   # [Bearing, Shaft, Motor Housing, Coupling, Gearbox]

    window_hours = config.window_days * 24

    for comp_name in component_order:
        if config.verbose:
            print(f"  Simulating: {comp_name}")

        # Build upstream_failure_times from components already simulated
        upstream_names = [c for c in component_order if c != comp_name
                          and COMPONENT_POSITIONS[c] < COMPONENT_POSITIONS[comp_name]]
        upstream_failure_times = {
            name: component_ttfs[name]
            for name in upstream_names
            if name in component_ttfs and component_ttfs[name] <= window_hours
        }

        df, ttf = generate_component_telemetry(
            comp_name, config, rng, upstream_failure_times
        )

        results[comp_name] = df
        component_ttfs[comp_name] = ttf

        # Write per-component CSV
        safe_name = comp_name.replace(" ", "_")
        csv_path = os.path.join(config.output_dir, f"{safe_name}_telemetry.csv")
        df.to_csv(csv_path, index=False)

        if config.verbose:
            n_failure_rows = df["is_failure_event"].sum()
            n_cascade_rows = df["cascade_flag"].sum()
            ttf_str = f"{ttf:.1f} h" if ttf <= window_hours else f"{ttf:.1f} h (beyond window)"
            print(f"    -> TTF = {ttf_str} | failure rows = {n_failure_rows} | "
                  f"cascade rows = {n_cascade_rows} | CSV: {csv_path}")

    # Write master telemetry CSV (all components concatenated)
    master_df = pd.concat(list(results.values()), ignore_index=True)
    master_path = os.path.join(config.output_dir, "master_telemetry.csv")
    master_df.to_csv(master_path, index=False)

    if config.verbose:
        print(f"\n[simulate.py] Master telemetry written: {master_path} ({len(master_df)} rows)")
        print("[simulate.py] Simulation complete.")
        print("\n  Component TTF Summary:")
        for comp, ttf in component_ttfs.items():
            in_window = ttf <= window_hours
            print(f"    {comp:<16}  TTF = {ttf:>8.1f} h  {'<< IN WINDOW' if in_window else '(beyond window)'}")

    return results


# =============================================================================
# PRIVATE UTILITIES
# =============================================================================

def _get_sensor_channels(component_name: str) -> List[str]:
    """
    Return the ordered list of sensor channels for a given component.

    This matches the sensor layout from sql/seed.sql (Day 4, locked):
        Bearing:       [vibration, temperature]       sensor_ids 11, 12
        Shaft:         [vibration, rpm]               sensor_ids 21, 22
        Motor Housing: [temperature, vibration]       sensor_ids 31, 32
        Coupling:      [vibration, load]              sensor_ids 41, 42
        Gearbox:       [vibration, oil_debris, temperature]  sensor_ids 51, 52, 53

    The primary sensor is always listed first (consistent with topology.py
    COMPONENT_TOPOLOGY_META['primary_sensor_type']).
    """
    channels = {
        "Bearing":       ["vibration", "temperature"],
        "Shaft":         ["vibration", "rpm"],
        "Motor Housing": ["temperature", "vibration"],
        "Coupling":      ["vibration", "load"],
        "Gearbox":       ["vibration", "oil_debris", "temperature"],
    }
    return channels.get(component_name, ["vibration"])


def _primary_sensor(component_name: str) -> str:
    """
    Return the primary sensor type for a component.
    Failure events are flagged only on the primary sensor row.
    """
    return COMPONENT_TOPOLOGY_META[component_name]["primary_sensor_type"]


def _hours_to_iso(hours: float, base_year: int = 2026) -> str:
    """
    Convert simulation hours (offset from t=0) to an ISO 8601 timestamp string.

    t=0 is anchored to 2026-07-20 00:00:00 (Day 5 simulation start).

    Parameters
    ----------
    hours     : float — simulation hours elapsed
    base_year : int   — anchor year for the timestamp

    Returns
    -------
    str — ISO 8601 datetime string, e.g. '2026-07-20T06:00:00'
    """
    base  = datetime.datetime(base_year, 7, 20, 0, 0, 0)
    delta = datetime.timedelta(hours=hours)
    return (base + delta).strftime("%Y-%m-%dT%H:%M:%S")


# =============================================================================
# MODULE SELF-TEST (run directly: python simulate.py)
# =============================================================================

if __name__ == "__main__":
    import pprint

    print("=" * 70)
    print("SIMULATE.PY -- SELF-TEST (Day 6 — full signal injection)")
    print("=" * 70)

    cfg = SimulationConfig(window_days=30, random_seed=42, verbose=True)

    # --- Test 1: draw_weibull_ttf ---
    rng_test = np.random.default_rng(42)
    print("\n[1] Weibull TTF samples (5 draws per component):")
    for comp in PIPELINE_ORDER:
        params = COMPONENT_WEIBULL_PARAMS[comp]
        beta   = params["beta_mid"]
        eta    = params["eta_hours"]
        ttfs   = [round(draw_weibull_ttf(beta, eta, rng_test), 1) for _ in range(5)]
        print(f"  {comp:<16}  beta={beta:.2f}  eta={eta:.0f}h  -> TTF samples: {ttfs}")

    # --- Test 2: Single component telemetry ---
    print("\n[2] Single-component telemetry (Bearing, 30-day window):")
    rng2 = np.random.default_rng(42)
    df_b, ttf_b = generate_component_telemetry("Bearing", cfg, rng2)
    print(f"  Rows: {len(df_b)} | Columns: {list(df_b.columns)}")
    print(f"  TTF: {ttf_b:.1f} h | Failure events: {df_b['is_failure_event'].sum()}")
    print(f"  Value range (vibration): "
          f"{df_b[df_b['sensor_type']=='vibration']['value'].min():.3f} to "
          f"{df_b[df_b['sensor_type']=='vibration']['value'].max():.3f} mm/s")

    # --- Test 3: Full simulation run ---
    print("\n[3] Full simulation run (30-day window):")
    telemetry = run_simulation(cfg)
    for comp, df in telemetry.items():
        n_fail = df["is_failure_event"].sum()
        n_casc = df["cascade_flag"].sum()
        print(f"  {comp:<16}  rows={len(df)}  failure_events={n_fail}  cascade_rows={n_casc}")

    print("\n[PASS] Day 6 signal injection tests complete.")
