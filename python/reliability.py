"""
reliability.py — Manufacturing Analytics FYP
=============================================
Weibull Reliability Functions, MTBF / MTTR, and Arrhenius Acceleration Model
Day 3 Draft — Phase 1, Sub-phase 1.2

PURPOSE
-------
Implement the statistical reliability functions established in Day 1 theory:
  - Weibull reliability function R(t)
  - Weibull hazard function h(t)
  - MTBF from Weibull parameters (β, η) via the Gamma function
  - MTTR calculation from maintenance event records
  - Arrhenius Acceleration Factor (AF) for temperature-stressed components
  - Series-system reliability (R_sys = ∏ R_i(t))

All functions are documented with:
  - The exact mathematical formula implemented
  - The SQL table + column names that supply input data
  - Constraints inherited from the Day 1 parameter table
  - Expected return type and units

MATHEMATICAL FOUNDATION (Day 1 theory — LOCKED)
------------------------------------------------
Weibull Reliability:
    R(t) = exp(-(t/η)^β)

    β (shape parameter):
        β < 1  → infant mortality (decreasing failure rate)
        β = 1  → random / memoryless (exponential model)
        β > 1  → wear-out (increasing failure rate)  ← dominant for our 5 components

Weibull Hazard Function (instantaneous failure rate):
    h(t) = (β/η) · (t/η)^(β-1)

MTBF (Mean Time Between Failures) — Weibull:
    MTBF = η · Γ(1 + 1/β)
    where Γ is the Gamma function (scipy.special.gamma)

Arrhenius Acceleration Factor:
    AF = exp[(Ea/k) · (1/T_use − 1/T_stress)]
    Ea = activation energy (eV), component-specific
    k  = 8.617 × 10⁻⁵ eV/K (Boltzmann's constant)
    T  = absolute temperature in Kelvin (°C + 273.15)
    Rule of thumb: +10 °C ≈ 2× failure rate for Ea ≈ 0.7 eV

Series System Reliability:
    R_system(t) = R_Bearing(t) × R_Shaft(t) × R_MotorHousing(t)
                  × R_Coupling(t) × R_Gearbox(t)

SQL DATA REQUIREMENTS
---------------------
Table: components (read-only lookups)
    - component_id          INTEGER PK
    - weibull_beta_min      FLOAT   -- lower bound of β range
    - weibull_beta_max      FLOAT   -- upper bound of β range
    - weibull_eta_hours     FLOAT   -- η characteristic life (operating hours)
    - activation_energy_ev  FLOAT   -- Ea for Arrhenius; NULL for Shaft

Table: maintenance_events (MTTR source)
    - event_id              INTEGER PK
    - component_id          INTEGER FK → components
    - maintenance_type      VARCHAR -- 'corrective' | 'preventive'
    - start_ts              DATETIME
    - end_ts                DATETIME
    - repair_duration_hours FLOAT   -- (end_ts - start_ts) / 3600

Table: failure_log (MTBF source)
    - log_id                INTEGER PK
    - component_id          INTEGER FK → components
    - failure_ts            DATETIME
    - failure_mode          VARCHAR

Table: sensor_readings (Arrhenius temperature input)
    - component_id          INTEGER FK
    - ts                    DATETIME
    - value                 FLOAT   -- temperature in °C (when sensor_type = 'temperature')

PER-COMPONENT WEIBULL PARAMETERS (locked Day 1; Ea/eta calibrated Day 9)
-----------------------------------------------
Component       β range      Ea (eV)   Primary Sensor     Strategy
─────────────── ──────────── ───────── ────────────────── ─────────
Bearing         [2.5, 3.5]   0.65 ¹   Vibration RMS      PM
Shaft           [1.5, 2.0]   N/A       Vibration 1× harm. CBM
Motor Housing   [1.8, 2.5]   0.85 ²   Temperature        CBM
Coupling        [1.5, 2.0]   0.60      Vibration 2× harm. CBM
Gearbox         [2.0, 3.0]   0.70      Vib. envelope+oil  PM+CBM

¹ Bearing Ea: reduced 0.80→0.65 eV on Day 9 to fix R²=0.808 Q-Q failure.
  Ea=0.80 + 80°C alarm caused AF≈3.6× compression — too aggressive for 365d window.
² Motor Housing: Ea reduced 1.00→0.85 eV + eta raised 6570→8000h on Day 9.
  Ea=1.00 at 130°C alarm gave AF≈4.5× (effective η≈1460h), collapsing R² to 0.721.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
from scipy.special import gamma as scipy_gamma


# =============================================================================
# PHYSICAL / MATHEMATICAL CONSTANTS
# =============================================================================

BOLTZMANN_EV_PER_K: float = 8.617e-5   # Boltzmann's constant in eV/K (k)
KELVIN_OFFSET: float = 273.15           # 0 °C in Kelvin

# Per-component Weibull parameters (Day 1, locked).
# β midpoints are used when a single representative value is needed.
# η (characteristic life) values are placeholder estimates; calibrated in Phase 2
# against simulated run-to-failure data using scipy.stats.weibull_min.fit().
COMPONENT_WEIBULL_PARAMS: dict[str, dict] = {
    "Bearing": {
        "beta_min": 2.5, "beta_max": 3.5, "beta_mid": 3.0,
        "eta_hours": 4380.0,    # ≈ 6 months continuous operation at rated load
        "ea_ev": 0.65,          # Day 9 calibration: reduced from 0.80→0.65 eV to fix
                                # R²=0.808 (lifecycle compression at 80°C alarm was excessive)
        "maintenance_strategy": "PM",
    },
    "Shaft": {
        "beta_min": 1.5, "beta_max": 2.0, "beta_mid": 1.75,
        "eta_hours": 8760.0,    # ≈ 1 year
        "ea_ev": None,          # fatigue-dominant; not thermally modelled
        "maintenance_strategy": "CBM",
    },
    "Motor Housing": {
        "beta_min": 1.8, "beta_max": 2.5, "beta_mid": 2.15,
        "eta_hours": 8000.0,    # Day 9 calibration: increased from 6570→8000h to
                                # restore adequate lifecycle spread for Weibull fitting
        "ea_ev": 0.85,          # Day 9 calibration: reduced from 1.00→0.85 eV;
                                # 1.00 eV at 130°C alarm was causing AF≈4.5× compression
                                # (effective η≈1460h → only ~6 failures/year, skewing R²)
        "maintenance_strategy": "CBM",
    },
    "Coupling": {
        "beta_min": 1.5, "beta_max": 2.0, "beta_mid": 1.75,
        "eta_hours": 5256.0,    # ≈ 7 months
        "ea_ev": 0.60,
        "maintenance_strategy": "CBM",
    },
    "Gearbox": {
        "beta_min": 2.0, "beta_max": 3.0, "beta_mid": 2.5,
        "eta_hours": 4380.0,    # ≈ 6 months
        "ea_ev": 0.70,
        "maintenance_strategy": "PM_CBM",
    },
}

# ISO 10816-3 Vibration severity zone boundaries (mm/s RMS), locked Day 1
ISO_VIBRATION_ZONES: dict[str, tuple[float, float]] = {
    "A": (0.0,  2.3),    # new / acceptable
    "B": (2.3,  4.5),    # acceptable long-term
    "C": (4.5,  7.1),    # alarm threshold → trigger CBM inspection
    "D": (7.1, float("inf")),   # danger → immediate shutdown
}


# =============================================================================
# HELPER UTILITIES
# =============================================================================

def celsius_to_kelvin(temp_celsius: float) -> float:
    """
    Convert temperature from Celsius to Kelvin.

    Formula:
        T_K = T_C + 273.15

    Parameters
    ----------
    temp_celsius : float — temperature in degrees Celsius

    Returns
    -------
    float — temperature in Kelvin
    """
    return temp_celsius + KELVIN_OFFSET


def validate_weibull_params(beta: float, eta: float) -> None:
    """
    Raise ValueError if Weibull parameters are physically invalid.

    Constraints:
        β > 0 (shape parameter must be strictly positive)
        η > 0 (scale parameter = characteristic life must be strictly positive)

    Parameters
    ----------
    beta : float — Weibull shape parameter β
    eta  : float — Weibull scale parameter η (characteristic life, hours)

    Returns
    -------
    None — raises ValueError on invalid input
    """
    if beta <= 0:
        raise ValueError(f"Weibull β must be > 0; received {beta}")
    if eta <= 0:
        raise ValueError(f"Weibull η must be > 0; received {eta}")


# =============================================================================
# 1. WEIBULL RELIABILITY FUNCTION — R(t)
# =============================================================================

def weibull_reliability(t: float, beta: float, eta: float) -> float:
    """
    Calculate the Weibull reliability (survival probability) at time t.

    FORMULA
    -------
        R(t) = exp(-(t/η)^β)

    INTERPRETATION
    ---------------
        R(t) is the probability that the component survives (does not fail)
        up to time t, given parameters β and η.

        R(0)    = 1.0  (certain survival at time zero)
        R(η)    ≈ 0.368  (at characteristic life, 63.2% have failed)
        R(∞)    = 0.0  (certain failure eventually)

    RELATIONSHIP TO β (Day 1 theory):
        β < 1  → h(t) decreasing: infant-mortality failures dominate
        β = 1  → h(t) constant:  exponential / random failures
        β > 1  → h(t) increasing: wear-out failures dominate (our components)

    SQL DATA SOURCE
    ---------------
        β:  components.weibull_beta_min, weibull_beta_max
            (use midpoint or fitted value from Phase 2)
        η:  components.weibull_eta_hours
        t:  derived from sensor_readings.ts or maintenance_events timestamps

    Parameters
    ----------
    t    : float — elapsed operating time (hours); must be >= 0
    beta : float — Weibull shape parameter β (> 0)
    eta  : float — Weibull scale parameter η, characteristic life (hours, > 0)

    Returns
    -------
    float — survival probability R(t) in [0.0, 1.0]
    """
    # Stub: implementation to be fleshed out in Phase 2 (Day 16+)
    # when fitted β, η values are available from run-to-failure simulation data.
    validate_weibull_params(beta, eta)
    if t < 0:
        raise ValueError(f"Time t must be >= 0; received {t}")
    return float(math.exp(-((t / eta) ** beta)))


# =============================================================================
# 2. WEIBULL HAZARD FUNCTION — h(t)
# =============================================================================

def weibull_hazard(t: float, beta: float, eta: float) -> float:
    """
    Calculate the Weibull instantaneous failure rate (hazard function) at time t.

    FORMULA
    -------
        h(t) = (β / η) · (t / η)^(β-1)

    INTERPRETATION
    ---------------
        h(t) is the conditional probability of failure per unit time,
        given survival up to time t. Also called the hazard rate or
        instantaneous failure rate.

        Units: failures per operating hour.

        For our components (β > 1):
            h(t) is monotonically increasing — the longer the component runs
            without maintenance, the higher its instantaneous failure probability.
            This is the wear-out regime and justifies Preventive Maintenance (PM).

        Special case (β = 1): h(t) = 1/η = λ (constant rate, exponential model).

    VIVA DEFENCE NOTE:
        h(t) increasing is why we don't use the exponential model (which assumes
        constant λ). The exponential model would UNDERESTIMATE failure risk at
        long operating ages — a critical error for maintenance planning.

    SQL DATA SOURCE
    ---------------
        Same as weibull_reliability() — β from components, t from event timestamps.

    Parameters
    ----------
    t    : float — elapsed operating time (hours); must be > 0 for meaningful result
    beta : float — Weibull shape parameter β (> 0)
    eta  : float — Weibull scale parameter η, characteristic life (hours, > 0)

    Returns
    -------
    float — instantaneous failure rate h(t) in [0, ∞); units: failures / hour
    """
    validate_weibull_params(beta, eta)
    if t < 0:
        raise ValueError(f"Time t must be >= 0; received {t}")
    if t == 0 and beta < 1:
        return float("inf")    # h(0) → ∞ for infant-mortality case (β < 1)
    return float((beta / eta) * ((t / eta) ** (beta - 1)))


# =============================================================================
# 3. MTBF FROM WEIBULL PARAMETERS
# =============================================================================

def mtbf_weibull(beta: float, eta: float) -> float:
    """
    Calculate Mean Time Between Failures (MTBF) from Weibull parameters.

    FORMULA
    -------
        MTBF = η · Γ(1 + 1/β)

    where Γ is the Gamma function (generalized factorial).

    DERIVATION
    ----------
        MTBF = ∫₀^∞ R(t) dt = ∫₀^∞ exp(-(t/η)^β) dt

    Substituting u = (t/η)^β, the integral resolves to η · Γ(1 + 1/β).

    SPECIAL CASE:
        β = 1 (exponential model): Γ(2) = 1!, so MTBF = η · 1 = η = 1/λ.
        This recovers the familiar MTBF = 1/failure_rate identity.

    PRACTICAL EXAMPLE (Bearing, β = 3.0, η = 4380 h):
        Γ(1 + 1/3) = Γ(4/3) ≈ 0.893
        MTBF = 4380 × 0.893 ≈ 3912 hours ≈ 163 days

    CALIBRATION NOTE (Phase 2 — Day 16+):
        β and η will be fitted via Maximum Likelihood Estimation (MLE) using
        scipy.stats.weibull_min.fit() on simulated run-to-failure data.
        Until then, midpoint β values and placeholder η from COMPONENT_WEIBULL_PARAMS
        are used for architecture validation.

    SQL DATA SOURCE
    ---------------
        β: components.weibull_beta_min + weibull_beta_max → midpoint
        η: components.weibull_eta_hours

    Parameters
    ----------
    beta : float — Weibull shape parameter β (> 0)
    eta  : float — Weibull scale parameter η, characteristic life (hours, > 0)

    Returns
    -------
    float — MTBF in operating hours
    """
    validate_weibull_params(beta, eta)
    return float(eta * scipy_gamma(1.0 + 1.0 / beta))


# =============================================================================
# 4. MTBF FROM HISTORICAL FAILURE DATA
# =============================================================================

def mtbf_from_history(
    failure_timestamps: list[float],
    total_operating_hours: Optional[float] = None,
) -> float:
    """
    Calculate empirical MTBF from a sequence of failure event timestamps.

    FORMULA
    -------
    Method A — Inter-arrival mean (when multiple failures are observed):
        MTBF = mean(t₂−t₁, t₃−t₂, ..., tₙ−tₙ₋₁)

    Method B — Ratio (when total operating time is known):
        MTBF = total_operating_hours / number_of_failures

    This function applies Method B when total_operating_hours is provided,
    otherwise falls back to Method A.

    ACCURACY CONSIDERATION
    ----------------------
        Empirical MTBF from small sample sizes is statistically unreliable.
        With n < 10 failures, confidence intervals are wide.
        Weibull MLE (mtbf_weibull) is preferred once β and η are calibrated.
        Use this function as a cross-check during Phase 2 validation.

    SQL DATA SOURCE
    ---------------
        failure_timestamps: derived from failure_log.failure_ts (epoch seconds or hours)
        total_operating_hours: derived from sensor_readings time span per component_id

    Parameters
    ----------
    failure_timestamps   : list[float] — ordered list of failure event times (hours
                           from start of observation, or UNIX timestamps in hours)
    total_operating_hours : float | None — total hours of operation observed.
                            If None, uses inter-arrival mean (Method A).

    Returns
    -------
    float — empirical MTBF in hours; raises ValueError if fewer than 2 events
    """
    if len(failure_timestamps) < 2:
        raise ValueError(
            f"At least 2 failure timestamps required for MTBF calculation; "
            f"received {len(failure_timestamps)}. "
            f"Use mtbf_weibull() for single-event or analytical estimates."
        )

    sorted_ts = sorted(failure_timestamps)

    if total_operating_hours is not None:
        if total_operating_hours <= 0:
            raise ValueError("total_operating_hours must be positive")
        n_failures = len(sorted_ts)
        return float(total_operating_hours / n_failures)

    # Method A: mean of inter-arrival times
    inter_arrivals = [sorted_ts[i+1] - sorted_ts[i] for i in range(len(sorted_ts) - 1)]
    return float(sum(inter_arrivals) / len(inter_arrivals))


# =============================================================================
# 5. MTTR — MEAN TIME TO REPAIR
# =============================================================================

def mttr_from_maintenance_records(
    repair_durations_hours: list[float],
    maintenance_type_filter: Optional[str] = "corrective",
) -> dict[str, float]:
    """
    Calculate Mean Time To Repair (MTTR) from maintenance event repair durations.

    FORMULA
    -------
        MTTR = (Σ repair_duration_hours) / n_repairs

    MTTR vs MTBF — Maintenance Effectiveness Relationship
    ------------------------------------------------------
        Availability ≈ MTBF / (MTBF + MTTR)     [exponential approximation]

    This formula is an approximation used for illustrative interpretation.
    The exact availability depends on the full time distribution of repairs;
    for the OEE engine (kpi.py), we use shift-level measured downtime directly.

    FILTER LOGIC
    ------------
        maintenance_type_filter = 'corrective'
            Only repair events (unplanned failures) — true MTTR.
            Planned PM durations are NOT included (they are scheduled downtime,
            distinct from fault diagnosis + repair time).
        maintenance_type_filter = 'preventive'
            PM duration analysis — useful for scheduling optimization.
        maintenance_type_filter = None
            All maintenance events included — use for aggregate analysis.

    SQL DATA SOURCE
    ---------------
        repair_durations_hours: from maintenance_events.repair_duration_hours
            WHERE maintenance_type = maintenance_type_filter
              AND component_id     = <target component>
        (maintenance_events table: to be created in schema.sql Day 4–5)

    VIVA DEFENCE NOTE:
        MTTR encompasses: fault detection time + diagnosis time + parts procurement
        + active repair time + functional test time. In our simulated data, only
        active repair is modelled. The PHM research distinction between these phases
        is a common viva question (see README.md Day 3 viva section).

    Parameters
    ----------
    repair_durations_hours  : list[float] — list of individual repair durations (hours)
    maintenance_type_filter : str | None  — label for the filter applied by caller

    Returns
    -------
    dict with keys:
        'mttr_hours'        : float  — mean repair time in hours
        'n_repairs'         : int    — number of repair events used
        'total_repair_hours': float  — sum of all repair durations
        'maintenance_type'  : str    — the filter label applied
        'approx_availability': float — MTBF/(MTBF+MTTR) approximation placeholder
                                       (set to None; requires MTBF to be passed separately)
    """
    if not repair_durations_hours:
        raise ValueError("repair_durations_hours list is empty")
    if any(d < 0 for d in repair_durations_hours):
        raise ValueError("All repair durations must be non-negative")

    n = len(repair_durations_hours)
    total = sum(repair_durations_hours)
    mttr = total / n

    return {
        "mttr_hours":         round(mttr, 4),
        "n_repairs":          n,
        "total_repair_hours": round(total, 4),
        "maintenance_type":   maintenance_type_filter or "all",
        "approx_availability": None,   # caller must provide MTBF to compute this
    }


# =============================================================================
# 6. MTBF-MTTR AVAILABILITY BRIDGE
# =============================================================================

def availability_from_mtbf_mttr(mtbf_hours: float, mttr_hours: float) -> float:
    """
    Estimate steady-state Availability from MTBF and MTTR.

    FORMULA
    -------
        A = MTBF / (MTBF + MTTR)

    This is the classic exponential approximation (Birnbaum, 1969).
    Valid strictly when failure times and repair times are both exponentially
    distributed. Used here as an analytical cross-check against the OEE
    Availability computed from shift-level downtime records (kpi.py).

    VIVA BRIDGE:
        Comparing A_weibull (this function) with A_oee (kpi.compute_availability())
        tests whether the Weibull model calibration is consistent with observed
        plant downtime data — a diagnostic analytics validation exercise.

    Parameters
    ----------
    mtbf_hours : float — Mean Time Between Failures (hours, > 0)
    mttr_hours : float — Mean Time To Repair (hours, > 0)

    Returns
    -------
    float — estimated steady-state availability A ∈ [0.0, 1.0]
    """
    if mtbf_hours <= 0:
        raise ValueError(f"MTBF must be > 0; received {mtbf_hours}")
    if mttr_hours < 0:
        raise ValueError(f"MTTR must be >= 0; received {mttr_hours}")
    return float(mtbf_hours / (mtbf_hours + mttr_hours))


# =============================================================================
# 7. ARRHENIUS ACCELERATION FACTOR
# =============================================================================

def arrhenius_acceleration_factor(
    ea_ev: float,
    t_use_celsius: float,
    t_stress_celsius: float,
) -> float:
    """
    Calculate the Arrhenius Acceleration Factor (AF) for thermally-driven failures.

    FORMULA
    -------
        AF = exp[ (Ea / k) · (1/T_use − 1/T_stress) ]

    where:
        Ea         = activation energy (eV), component-specific
        k          = 8.617 × 10⁻⁵ eV/K (Boltzmann's constant)
        T_use      = use/operating temperature (Kelvin)
        T_stress   = elevated stress temperature (Kelvin)

    INTERPRETATION
    --------------
        AF > 1: failure rate is AF times higher at T_stress than at T_use.
                e.g., AF = 8 means the component degrades 8× faster under
                stress temperature than under nominal operating temperature.

        AF < 1: stress temperature is LOWER than use temperature — unusual;
                indicates a data input error in most industrial contexts.

    RULE OF THUMB (Day 1, locked):
        +10 °C ≈ 2× failure rate for Ea ≈ 0.7 eV
        This is the Arrhenius "10-degree rule" used in electronics reliability (MIL-HDBK-217).

    PER-COMPONENT Ea VALUES (Day 1, locked):
        Bearing:       Ea = 0.80 eV  (lubricant breakdown)
        Motor Housing: Ea = 1.00 eV  (winding insulation)
        Gearbox:       Ea = 0.70 eV  (oil oxidation)
        Coupling:      Ea = 0.60 eV  (elastomer thermal ageing)
        Shaft:         Ea = N/A      (fatigue — not thermally modelled)

    SQL DATA SOURCE
    ---------------
        ea_ev:           components.activation_energy_ev
        t_use_celsius:   AVG(sensor_readings.value)
                         WHERE sensor_type = 'temperature'
                           AND ts IN nominal operating window
        t_stress_celsius: AVG(sensor_readings.value)
                         WHERE sensor_type = 'temperature'
                           AND ts IN high-load / alarm event window

    Parameters
    ----------
    ea_ev           : float — activation energy in electron-volts (eV); > 0
    t_use_celsius   : float — nominal operating temperature (°C)
    t_stress_celsius: float — elevated stress temperature (°C); must be > t_use_celsius
                              for AF > 1 (stress accelerates degradation)

    Returns
    -------
    float — Acceleration Factor AF (dimensionless); typically ≥ 1.0 for stress > use
    """
    if ea_ev <= 0:
        raise ValueError(f"Activation energy Ea must be > 0; received {ea_ev}")

    t_use_k    = celsius_to_kelvin(t_use_celsius)
    t_stress_k = celsius_to_kelvin(t_stress_celsius)

    if t_use_k <= 0 or t_stress_k <= 0:
        raise ValueError("Temperatures in Kelvin must be positive")

    exponent = (ea_ev / BOLTZMANN_EV_PER_K) * ((1.0 / t_use_k) - (1.0 / t_stress_k))
    return float(math.exp(exponent))


# =============================================================================
# 8. THERMALLY DERATED η (ADJUSTED CHARACTERISTIC LIFE)
# =============================================================================

def eta_derated(eta_nominal_hours: float, acceleration_factor: float) -> float:
    """
    Compute the thermally-derated characteristic life η under elevated temperature.

    FORMULA
    -------
        η_stressed = η_nominal / AF

    RATIONALE
    ---------
        The Acceleration Factor compresses the time axis: if the component
        normally lasts η_nominal hours at T_use, it lasts η_nominal/AF hours
        at T_stress. A higher temperature "uses up" the component's life faster.

    PRACTICAL USE (Phase 2)
    -----------------------
        η_derated is passed back into weibull_reliability() and mtbf_weibull()
        to compute condition-adjusted reliability curves during thermal events
        (Motor Housing winding over-temperature, Gearbox oil overheat).

    Parameters
    ----------
    eta_nominal_hours  : float — characteristic life at nominal temperature (hours)
    acceleration_factor: float — Arrhenius AF from arrhenius_acceleration_factor()

    Returns
    -------
    float — derated characteristic life η_stressed (hours)
    """
    if eta_nominal_hours <= 0:
        raise ValueError("eta_nominal_hours must be > 0")
    if acceleration_factor <= 0:
        raise ValueError("acceleration_factor must be > 0")
    return float(eta_nominal_hours / acceleration_factor)


# =============================================================================
# 9. SERIES SYSTEM RELIABILITY
# =============================================================================

def series_system_reliability(
    component_reliabilities: dict[str, float],
) -> dict[str, float]:
    """
    Calculate system reliability for the 5-component series pipeline.

    FORMULA
    -------
        R_system(t) = R_Bearing(t) × R_Shaft(t) × R_MotorHousing(t)
                      × R_Coupling(t) × R_Gearbox(t)
                    = ∏ R_i(t)

    RATIONALE (Day 1, locked):
        A series reliability block assumes that the failure of ANY single component
        causes system failure. The 5-component chain:
            [Bearing] → [Shaft] → [Motor Housing] → [Coupling] → [Gearbox]
        exhibits this behaviour: a Bearing seizure prevents Shaft rotation, which
        halts the entire downstream chain.

        This mirrors the OEE Availability series rule: A_sys = min(A_i), which
        in the extreme case (A_i = 0 for any i) reduces A_sys to 0 — consistent
        with R_sys = 0 when any R_i = 0.

    PARALLEL REDUNDANCY NOTE:
        If future phases model a redundant backup component, this function must
        be replaced with a parallel reliability model:
        R_parallel = 1 − ∏(1 − R_i). Not applicable in current scope.

    SQL DATA SOURCE
    ---------------
        R_i(t): computed by calling weibull_reliability(t, beta_i, eta_i) for each
                component, using parameters from components table.

    Parameters
    ----------
    component_reliabilities : dict[str, float]
        Keys: component names (must include all 5 in COMPONENTS list)
        Values: R_i(t) ∈ [0.0, 1.0] for each component at the same time t

    Returns
    -------
    dict with keys:
        'R_system'            : float — system reliability ∈ [0.0, 1.0]
        'weakest_component'   : str   — component with lowest R_i(t)
        'component_breakdown' : dict  — input dictionary, passed through
    """
    if not component_reliabilities:
        raise ValueError("component_reliabilities must not be empty")

    r_values = list(component_reliabilities.values())
    if any(r < 0 or r > 1 for r in r_values):
        raise ValueError("All individual reliabilities must be in [0, 1]")

    r_system = 1.0
    for r in r_values:
        r_system *= r

    weakest = min(component_reliabilities, key=lambda k: component_reliabilities[k])

    return {
        "R_system":            round(r_system, 6),
        "weakest_component":   weakest,
        "component_breakdown": component_reliabilities,
    }


# =============================================================================
# 10. ALL-COMPONENT RELIABILITY SNAPSHOT
# =============================================================================

def compute_all_component_reliabilities(
    t_hours: float,
    beta_overrides: Optional[dict[str, float]] = None,
    eta_overrides: Optional[dict[str, float]] = None,
) -> dict[str, dict]:
    """
    Compute Weibull reliability, hazard rate, and MTBF for all 5 components
    at a given operating time t, using the locked parameter table.

    This is the primary function called by the reporting pipeline (report.py)
    to generate the reliability snapshot table for Power BI Fleet Overview page.

    WORKFLOW
    --------
        1. For each component, retrieve β_mid and η from COMPONENT_WEIBULL_PARAMS
           (or overrides from Phase 2 fitted values).
        2. Compute R(t) via weibull_reliability().
        3. Compute h(t) via weibull_hazard().
        4. Compute MTBF via mtbf_weibull().
        5. Aggregate to system level via series_system_reliability().

    POWER BI INTEGRATION
    --------------------
        Output is exported to: data/processed/reliability_snapshot.csv
        Columns: component_name, t_hours, beta, eta, R_t, h_t, mtbf_hours, iso_zone

    Parameters
    ----------
    t_hours        : float — operating time at which to evaluate all functions (hours)
    beta_overrides : dict | None — {component_name: fitted_beta} to override defaults
    eta_overrides  : dict | None — {component_name: fitted_eta}  to override defaults

    Returns
    -------
    dict with one sub-dict per component, plus 'system' key:
        {
          'Bearing': {
              'beta': float, 'eta': float,
              'R_t': float, 'h_t': float, 'mtbf_hours': float
          },
          ...
          'system': {'R_system': float, 'weakest_component': str}
        }
    """
    results: dict[str, dict] = {}
    r_snapshot: dict[str, float] = {}

    for comp_name, params in COMPONENT_WEIBULL_PARAMS.items():
        beta = (beta_overrides or {}).get(comp_name, params["beta_mid"])
        eta  = (eta_overrides  or {}).get(comp_name, params["eta_hours"])

        r_t    = weibull_reliability(t_hours, beta, eta)
        h_t    = weibull_hazard(t_hours, beta, eta)
        mtbf_h = mtbf_weibull(beta, eta)

        results[comp_name] = {
            "beta":       round(beta, 4),
            "eta":        round(eta, 2),
            "R_t":        round(r_t, 6),
            "h_t":        round(h_t, 8),
            "mtbf_hours": round(mtbf_h, 2),
        }
        r_snapshot[comp_name] = r_t

    system = series_system_reliability(r_snapshot)
    results["system"] = {
        "R_system":          system["R_system"],
        "weakest_component": system["weakest_component"],
    }

    return results


# =============================================================================
# PSEUDO-CODE: RELIABILITY PIPELINE (to be wired up in report.py, Day 16+)
# =============================================================================
#
# def run_reliability_pipeline(db_connection, eval_time_hours: float) -> None:
#
#     # STEP 1 — Fetch fitted Weibull params from DB (Phase 2 — after MLE fitting)
#     params_df = pd.read_sql(
#         "SELECT component_name, weibull_beta_mid, weibull_eta_hours "
#         "FROM components", db_connection
#     )
#
#     # STEP 2 — Compute reliability snapshot at current cumulative operating hours
#     beta_ov = dict(zip(params_df.component_name, params_df.weibull_beta_mid))
#     eta_ov  = dict(zip(params_df.component_name, params_df.weibull_eta_hours))
#     snapshot = compute_all_component_reliabilities(eval_time_hours, beta_ov, eta_ov)
#
#     # STEP 3 — Compute empirical MTBF from failure_log
#     for comp_name in COMPONENT_WEIBULL_PARAMS:
#         fail_df = pd.read_sql(
#             "SELECT failure_ts FROM failure_log WHERE component_name = ?",
#             db_connection, params=[comp_name]
#         )
#         if len(fail_df) >= 2:
#             fail_times = [ts.timestamp() / 3600 for ts in fail_df.failure_ts]
#             empirical_mtbf = mtbf_from_history(fail_times)
#             snapshot[comp_name]["empirical_mtbf_hours"] = round(empirical_mtbf, 2)
#
#     # STEP 4 — Compute MTTR from maintenance_events
#     for comp_name in COMPONENT_WEIBULL_PARAMS:
#         repair_df = pd.read_sql(
#             "SELECT repair_duration_hours FROM maintenance_events "
#             "WHERE component_name = ? AND maintenance_type = 'corrective'",
#             db_connection, params=[comp_name]
#         )
#         if not repair_df.empty:
#             mttr_result = mttr_from_maintenance_records(
#                 repair_df.repair_duration_hours.tolist(), "corrective"
#             )
#             snapshot[comp_name]["mttr_hours"] = mttr_result["mttr_hours"]
#             if "empirical_mtbf_hours" in snapshot[comp_name]:
#                 snapshot[comp_name]["availability_estimate"] = availability_from_mtbf_mttr(
#                     snapshot[comp_name]["empirical_mtbf_hours"],
#                     mttr_result["mttr_hours"]
#                 )
#
#     # STEP 5 — Export to CSV for Power BI
#     rows = []
#     for comp, data in snapshot.items():
#         if comp != "system":
#             rows.append({"component": comp, **data})
#     pd.DataFrame(rows).to_csv("data/processed/reliability_snapshot.csv", index=False)
