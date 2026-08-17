"""
test_reliability.py — Manufacturing & Industrial Analytics FYP
==============================================================
Unit tests for python/reliability.py

Day 4 — Phase 1, Sub-phase 1.2 (Environment Setup)

COVERAGE
--------
This test module covers the three core reliability functions that have
mathematical ground-truth values we can verify analytically:

    1. weibull_reliability(t, beta, eta)   → R(t) = exp(-(t/η)^β)
    2. mtbf_weibull(beta, eta)             → η · Γ(1 + 1/β)
    3. arrhenius_acceleration_factor(ea_ev, t_use_celsius, t_stress_celsius)
                                           → exp[(Ea/k)(1/T_use − 1/T_stress)]

DESIGN PRINCIPLES
-----------------
- All expected values are pre-computed analytically (by hand or exact formula),
  not by calling the production function itself.  This prevents circular testing.
- Floating-point comparisons use pytest.approx() with appropriate rel/abs tolerances.
- Edge cases, boundary conditions, and ValueError guards are explicitly tested.
- Component parameter values are taken directly from COMPONENT_WEIBULL_PARAMS in
  reliability.py to ensure tests stay in sync with the locked Day 1 parameters.
- No DB connections or file I/O — all tests are pure-function unit tests.

HOW TO RUN
----------
From the project root (with .venv activated):

    pytest tests/test_reliability.py -v
    pytest tests/test_reliability.py -v --tb=short
    pytest tests/test_reliability.py -v --cov=python/reliability --cov-report=term-missing

DEPENDENCY
----------
Requires: pytest>=7.4.0, scipy>=1.11.0 (see requirements.txt)
"""

import math
import sys
import os
import pytest

# ---------------------------------------------------------------------------
# Make sure the python/ module directory is importable regardless of how
# pytest is invoked (from project root or from tests/ directory).
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from reliability import (
    BOLTZMANN_EV_PER_K,
    KELVIN_OFFSET,
    COMPONENT_WEIBULL_PARAMS,
    celsius_to_kelvin,
    weibull_reliability,
    weibull_hazard,
    mtbf_weibull,
    arrhenius_acceleration_factor,
    validate_weibull_params,
    series_system_reliability,
    availability_from_mtbf_mttr,
)

from scipy.special import gamma as scipy_gamma


# ===========================================================================
# SECTION 1 — weibull_reliability(t, beta, eta)
# ===========================================================================
# Formula:  R(t) = exp(-(t/η)^β)
# Key reference points:
#   R(0)  = 1.0                    (zero elapsed time → certain survival)
#   R(η)  = exp(-1) ≈ 0.36788     (at characteristic life, ~63.2% have failed)
#   R(∞)  → 0.0                   (all eventually fail)
# ===========================================================================

class TestWeibullReliability:
    """Tests for weibull_reliability(t, beta, eta)."""

    # ── Boundary condition: t = 0 ──────────────────────────────────────────
    def test_r_at_t_zero_is_one(self):
        """R(0) must equal 1.0 for any valid β, η — certain survival at start."""
        assert weibull_reliability(0, beta=2.5, eta=4380.0) == pytest.approx(1.0)
        assert weibull_reliability(0, beta=1.75, eta=8760.0) == pytest.approx(1.0)
        assert weibull_reliability(0, beta=3.0, eta=4380.0) == pytest.approx(1.0)

    # ── Characteristic life: R(η) = exp(-1) ───────────────────────────────
    def test_r_at_characteristic_life(self):
        """R(η) = e^(-1) ≈ 0.36788 — canonical Weibull identity."""
        expected = math.exp(-1)   # ≈ 0.36788
        # Works for any β because (η/η)^β = 1^β = 1 always
        assert weibull_reliability(4380.0, beta=2.5,  eta=4380.0) == pytest.approx(expected, rel=1e-9)
        assert weibull_reliability(4380.0, beta=3.5,  eta=4380.0) == pytest.approx(expected, rel=1e-9)
        assert weibull_reliability(4380.0, beta=1.75, eta=4380.0) == pytest.approx(expected, rel=1e-9)

    # ── Specific β = 1 (exponential special case) ──────────────────────────
    def test_r_exponential_special_case(self):
        """β = 1 → R(t) = exp(-t/η) — recovers the exponential model exactly."""
        t, eta = 1000.0, 5000.0
        expected = math.exp(-t / eta)
        assert weibull_reliability(t, beta=1.0, eta=eta) == pytest.approx(expected, rel=1e-10)

    # ── Bearing parameters (β = 3.0, η = 4380 h) ─────────────────────────
    def test_bearing_at_half_life(self):
        """
        Bearing β_mid = 3.0, η = 4380 h.
        At t = 2190 h (half of η):
          R(2190) = exp(-(2190/4380)^3.0)
                  = exp(-(0.5)^3)
                  = exp(-0.125) ≈ 0.88249
        """
        t, beta, eta = 2190.0, 3.0, 4380.0
        expected = math.exp(-((t / eta) ** beta))  # = exp(-0.125)
        result = weibull_reliability(t, beta=beta, eta=eta)
        assert result == pytest.approx(expected, rel=1e-9)
        # Sanity: R should be in (0, 1)
        assert 0.0 < result < 1.0

    # ── Motor Housing parameters (β = 2.15, η = 6570 h) ──────────────────
    def test_motor_housing_at_rated_life(self):
        """Motor Housing: β_mid = 2.15, η = 6570 h. R(η) ≈ 0.36788."""
        params = COMPONENT_WEIBULL_PARAMS["Motor Housing"]
        beta = params["beta_mid"]
        eta  = params["eta_hours"]
        expected = math.exp(-1.0)  # R(η) = e^-1 always
        assert weibull_reliability(eta, beta=beta, eta=eta) == pytest.approx(expected, rel=1e-9)

    # ── Monotonically decreasing with t ───────────────────────────────────
    def test_r_decreases_monotonically_with_time(self):
        """R(t) must be strictly decreasing for increasing t (β > 1 wear-out regime)."""
        beta, eta = 2.5, 4380.0
        times = [0, 500, 1000, 2000, 4380, 6000, 10000]
        reliabilities = [weibull_reliability(t, beta, eta) for t in times]
        for i in range(len(reliabilities) - 1):
            assert reliabilities[i] > reliabilities[i + 1], (
                f"R not decreasing: R({times[i]})={reliabilities[i]:.6f} "
                f">= R({times[i+1]})={reliabilities[i+1]:.6f}"
            )

    # ── Result is always in [0, 1] ─────────────────────────────────────────
    def test_r_always_in_unit_interval(self):
        """R(t) ∈ [0, 1] for all valid inputs."""
        test_cases = [
            (0,     2.5,  4380.0),
            (1000,  3.0,  4380.0),
            (4380,  2.5,  4380.0),
            (50000, 3.5,  4380.0),   # very long time → R ≈ 0
        ]
        for t, beta, eta in test_cases:
            r = weibull_reliability(t, beta, eta)
            assert 0.0 <= r <= 1.0, f"R({t}, {beta}, {eta}) = {r} — out of [0,1]"

    # ── β effect: higher β → slower early decay, sharper late decay ───────
    def test_higher_beta_slower_early_faster_late(self):
        """
        For t < η: higher β → higher R (slower early degradation, concentrated wear).
        For t > η: higher β → lower R (steeper post-η drop-off).
        """
        eta = 4380.0
        t_early = 1000.0   # t < η
        t_late  = 7000.0   # t > η

        r_early_low_beta  = weibull_reliability(t_early, beta=1.5, eta=eta)
        r_early_high_beta = weibull_reliability(t_early, beta=3.5, eta=eta)
        assert r_early_high_beta > r_early_low_beta  # wear-out concentrated late

        r_late_low_beta  = weibull_reliability(t_late, beta=1.5, eta=eta)
        r_late_high_beta = weibull_reliability(t_late, beta=3.5, eta=eta)
        assert r_late_high_beta < r_late_low_beta   # steeper drop after η

    # ── Input validation: negative t ──────────────────────────────────────
    def test_negative_t_raises_value_error(self):
        """Negative time is physically meaningless — must raise ValueError."""
        with pytest.raises(ValueError, match="t must be"):
            weibull_reliability(-1.0, beta=2.5, eta=4380.0)

    # ── Input validation: β ≤ 0 ───────────────────────────────────────────
    def test_zero_beta_raises_value_error(self):
        with pytest.raises(ValueError, match="β must be"):
            weibull_reliability(1000.0, beta=0.0, eta=4380.0)

    def test_negative_beta_raises_value_error(self):
        with pytest.raises(ValueError, match="β must be"):
            weibull_reliability(1000.0, beta=-1.0, eta=4380.0)

    # ── Input validation: η ≤ 0 ───────────────────────────────────────────
    def test_zero_eta_raises_value_error(self):
        with pytest.raises(ValueError, match="η must be"):
            weibull_reliability(1000.0, beta=2.5, eta=0.0)

    def test_negative_eta_raises_value_error(self):
        with pytest.raises(ValueError, match="η must be"):
            weibull_reliability(1000.0, beta=2.5, eta=-100.0)


# ===========================================================================
# SECTION 2 — mtbf_weibull(beta, eta)
# ===========================================================================
# Formula:  MTBF = η · Γ(1 + 1/β)
# Reference: Gamma function identity Γ(n+1) = n! for integer n.
#
# Pre-computed expected values (verified by hand):
#   Bearing   β=3.0,  η=4380:   Γ(4/3) ≈ 0.89298  → MTBF ≈ 3911.14 h
#   Shaft     β=1.75, η=8760:   Γ(1+1/1.75)=Γ(1.571) ≈ 0.89005 → MTBF ≈ 7797.8 h
#   β=1 (exponential): Γ(2)=1! = 1.0  → MTBF = η exactly
#   β=2:               Γ(3/2)=√π/2 ≈ 0.88623 → MTBF = η · 0.88623
# ===========================================================================

class TestMtbfWeibull:
    """Tests for mtbf_weibull(beta, eta)."""

    # ── β = 1 special case: MTBF = η ──────────────────────────────────────
    def test_mtbf_exponential_case_equals_eta(self):
        """
        When β = 1: Γ(1 + 1/1) = Γ(2) = 1! = 1.0
        Therefore MTBF = η · 1.0 = η exactly.
        This recovers the classical MTBF = 1/λ = η result for the exponential model.
        """
        eta = 5000.0
        assert mtbf_weibull(beta=1.0, eta=eta) == pytest.approx(eta, rel=1e-10)

    # ── β = 2 standard case ────────────────────────────────────────────────
    def test_mtbf_beta_2(self):
        """
        β = 2: Γ(1 + 0.5) = Γ(1.5) = (√π)/2 ≈ 0.88623
        MTBF(β=2, η=1000) = 1000 × 0.88623 ≈ 886.23
        """
        eta = 1000.0
        expected = eta * scipy_gamma(1.5)  # Γ(1.5) = √π/2
        assert mtbf_weibull(beta=2.0, eta=eta) == pytest.approx(expected, rel=1e-9)

    # ── Bearing mid-point parameters (β = 3.0, η = 4380 h) ───────────────
    def test_mtbf_bearing_midpoint(self):
        """
        Bearing β_mid = 3.0, η = 4380 h.
        Γ(1 + 1/3) = Γ(4/3) — computed by scipy_gamma.
        MTBF = 4380 × Γ(4/3) ≈ 3911 h ≈ 163 days.
        (This example is explicitly documented in reliability.py docstring.)
        """
        beta, eta = 3.0, 4380.0
        expected = eta * scipy_gamma(1.0 + 1.0 / beta)
        result = mtbf_weibull(beta=beta, eta=eta)
        assert result == pytest.approx(expected, rel=1e-9)
        # Sanity: MTBF for wear-out (β > 1) must be < η
        assert result < eta, "For β > 1, MTBF must be less than η"

    # ── Gearbox mid-point parameters (β = 2.5, η = 4380 h) ───────────────
    def test_mtbf_gearbox_midpoint(self):
        """Gearbox β_mid = 2.5, η = 4380 h — verify against direct formula."""
        params = COMPONENT_WEIBULL_PARAMS["Gearbox"]
        beta = params["beta_mid"]
        eta  = params["eta_hours"]
        expected = eta * scipy_gamma(1.0 + 1.0 / beta)
        assert mtbf_weibull(beta=beta, eta=eta) == pytest.approx(expected, rel=1e-9)

    # ── Shaft parameters (β = 1.75, η = 8760 h) ───────────────────────────
    def test_mtbf_shaft_midpoint(self):
        """Shaft β_mid = 1.75, η = 8760 h."""
        params = COMPONENT_WEIBULL_PARAMS["Shaft"]
        beta = params["beta_mid"]
        eta  = params["eta_hours"]
        expected = eta * scipy_gamma(1.0 + 1.0 / beta)
        assert mtbf_weibull(beta=beta, eta=eta) == pytest.approx(expected, rel=1e-9)

    # ── MTBF is proportional to η ─────────────────────────────────────────
    def test_mtbf_proportional_to_eta(self):
        """Doubling η should double MTBF (Γ factor is a function of β only)."""
        beta = 2.5
        mtbf_1 = mtbf_weibull(beta=beta, eta=1000.0)
        mtbf_2 = mtbf_weibull(beta=beta, eta=2000.0)
        assert mtbf_2 == pytest.approx(2.0 * mtbf_1, rel=1e-9)

    # ── MTBF decreases as β increases (for β > 1, higher β → more concentrated end-of-life) ──
    def test_mtbf_decreases_with_higher_beta(self):
        """
        For the same η, higher β (stronger wear-out) compresses the distribution
        around the characteristic life → MTBF / η ratio decreases as β increases.
        """
        eta = 4380.0
        mtbf_low  = mtbf_weibull(beta=1.5, eta=eta)
        mtbf_high = mtbf_weibull(beta=3.5, eta=eta)
        assert mtbf_low > mtbf_high

    # ── All 5 component MTBFs are positive ────────────────────────────────
    def test_all_component_mtbfs_are_positive(self):
        """Verify positive MTBF for all 5 locked component parameter sets."""
        for comp_name, params in COMPONENT_WEIBULL_PARAMS.items():
            result = mtbf_weibull(beta=params["beta_mid"], eta=params["eta_hours"])
            assert result > 0.0, f"MTBF not positive for {comp_name}: {result}"

    # ── Input validation ──────────────────────────────────────────────────
    def test_zero_beta_raises_value_error(self):
        with pytest.raises(ValueError, match="β must be"):
            mtbf_weibull(beta=0.0, eta=4380.0)

    def test_zero_eta_raises_value_error(self):
        with pytest.raises(ValueError, match="η must be"):
            mtbf_weibull(beta=2.5, eta=0.0)

    def test_negative_beta_raises_value_error(self):
        with pytest.raises(ValueError, match="β must be"):
            mtbf_weibull(beta=-1.0, eta=4380.0)


# ===========================================================================
# SECTION 3 — arrhenius_acceleration_factor(ea_ev, t_use_celsius, t_stress_celsius)
# ===========================================================================
# Formula:  AF = exp[ (Ea / k) · (1/T_use − 1/T_stress) ]
#
# k = BOLTZMANN_EV_PER_K = 8.617e-5 eV/K
# T = °C + 273.15 (conversion to Kelvin)
#
# Pre-computed ground-truth values:
#   Rule of thumb (Day 1): Ea ≈ 0.7 eV, +10 °C → AF ≈ 2.0
#     T_use = 60 °C = 333.15 K,  T_stress = 70 °C = 343.15 K
#     AF = exp[(0.7 / 8.617e-5)(1/333.15 - 1/343.15)]
#        = exp[8123.65 × (0.003002 - 0.002915)]
#        = exp[8123.65 × 8.726e-5]
#        ≈ exp[0.7090] ≈ 2.032  (very close to 2× rule)
#
#   T_use = T_stress → AF = exp(0) = 1.0  (no acceleration)
#
#   T_stress < T_use → AF < 1.0  (stress is cooler — deceleration)
# ===========================================================================

class TestArrheniusAccelerationFactor:
    """Tests for arrhenius_acceleration_factor(ea_ev, t_use_celsius, t_stress_celsius)."""

    # ── Identity: T_use = T_stress → AF = 1.0 ────────────────────────────
    def test_af_equals_one_when_temperatures_equal(self):
        """
        When T_use = T_stress: exponent = (Ea/k)(1/T - 1/T) = 0 → AF = e^0 = 1.0.
        The 'stress' condition is identical to use — no acceleration.
        """
        for ea in [0.6, 0.7, 0.8, 1.0]:
            af = arrhenius_acceleration_factor(ea_ev=ea, t_use_celsius=60.0, t_stress_celsius=60.0)
            assert af == pytest.approx(1.0, rel=1e-9), f"AF ≠ 1.0 at equal temps for Ea={ea}"

    # ── Rule of thumb: Ea=0.7 eV, +10 °C → AF ≈ 2× ─────────────────────
    def test_day1_rule_of_thumb_10deg_approx_2x(self):
        """
        Day 1 Arrhenius rule of thumb (locked, CONTEXT.md):
          +10 °C at Ea ≈ 0.7 eV produces approximately 2× acceleration.
        Tolerance: 10% (rule of thumb is approximate — actual AF varies with base temp).
        """
        af = arrhenius_acceleration_factor(
            ea_ev=0.7,
            t_use_celsius=60.0,
            t_stress_celsius=70.0,
        )
        # Should be close to 2.0 but not exactly (depends on T_use absolute value)
        assert af == pytest.approx(2.0, rel=0.15), (
            f"Rule-of-thumb violated: AF = {af:.4f}, expected ≈ 2.0 (±15% tolerance)"
        )

    # ── Exact value: Bearing Ea = 0.80 eV at 70→90 °C ───────────────────
    def test_bearing_ea_exact_value(self):
        """
        Bearing Ea = 0.80 eV.  T_use = 70 °C, T_stress = 90 °C (+20 °C).
        AF = exp[(0.80 / 8.617e-5) · (1/343.15 - 1/363.15)]
        Pre-computed: exponent ≈ 9283.3 × (0.002915 - 0.002754)
                               ≈ 9283.3 × 1.613e-4 ≈ 1.497
        AF ≈ exp(1.497) ≈ 4.470
        """
        ea = 0.80
        t_use_k    = celsius_to_kelvin(70.0)
        t_stress_k = celsius_to_kelvin(90.0)
        expected_exp = (ea / BOLTZMANN_EV_PER_K) * (1.0 / t_use_k - 1.0 / t_stress_k)
        expected_af  = math.exp(expected_exp)

        result = arrhenius_acceleration_factor(ea_ev=ea, t_use_celsius=70.0, t_stress_celsius=90.0)
        assert result == pytest.approx(expected_af, rel=1e-9)
        # Bearing AF > 1 for stress > use
        assert result > 1.0

    # ── Motor Housing Ea = 1.00 eV (highest Ea — most thermally sensitive) ─
    def test_motor_housing_highest_af(self):
        """
        Motor Housing has the highest Ea = 1.00 eV.
        At same temperature step, it should have the highest AF of all components.
        """
        t_use, t_stress = 60.0, 80.0
        af_motor   = arrhenius_acceleration_factor(1.00, t_use, t_stress)
        af_bearing = arrhenius_acceleration_factor(0.80, t_use, t_stress)
        af_gearbox = arrhenius_acceleration_factor(0.70, t_use, t_stress)
        af_coupling = arrhenius_acceleration_factor(0.60, t_use, t_stress)

        assert af_motor > af_bearing > af_gearbox > af_coupling, (
            "AF ordering by Ea violated — higher Ea must produce higher AF at same ΔT"
        )

    # ── AF > 1 when T_stress > T_use ─────────────────────────────────────
    def test_af_greater_than_one_for_stress_above_use(self):
        """T_stress > T_use → 1/T_use > 1/T_stress → exponent > 0 → AF > 1."""
        af = arrhenius_acceleration_factor(ea_ev=0.7, t_use_celsius=40.0, t_stress_celsius=80.0)
        assert af > 1.0

    # ── AF < 1 when T_stress < T_use (deceleration) ───────────────────────
    def test_af_less_than_one_for_stress_below_use(self):
        """T_stress < T_use → exponent < 0 → AF < 1 (stress is cooler — slows ageing)."""
        af = arrhenius_acceleration_factor(ea_ev=0.7, t_use_celsius=80.0, t_stress_celsius=40.0)
        assert af < 1.0

    # ── Higher Ea → higher AF (for same temperature step) ─────────────────
    def test_higher_ea_gives_higher_af(self):
        """For the same ΔT, higher Ea produces higher AF — more thermally sensitive."""
        t_use, t_stress = 60.0, 90.0
        af_low_ea  = arrhenius_acceleration_factor(0.60, t_use, t_stress)
        af_high_ea = arrhenius_acceleration_factor(1.00, t_use, t_stress)
        assert af_high_ea > af_low_ea

    # ── Gearbox: AF at rated operating → oil alarm boundary ────────────────
    def test_gearbox_oil_alarm_af(self):
        """
        Gearbox Ea = 0.70 eV.
        Nominal sump temperature = 70 °C.
        Alarm threshold = 90 °C (from seed.sql sensor 53).
        AF should be meaningfully > 1 (oil degrades significantly faster).
        """
        af = arrhenius_acceleration_factor(ea_ev=0.70, t_use_celsius=70.0, t_stress_celsius=90.0)
        assert af > 1.5, f"Gearbox oil alarm AF = {af:.3f} — expected > 1.5"

    # ── Arrhenius is monotonically increasing with ΔT ─────────────────────
    def test_af_increases_with_temperature_step(self):
        """AF increases monotonically as the stress temperature rises above T_use."""
        t_use = 60.0
        stress_temps = [61, 70, 80, 90, 100, 120]
        afs = [arrhenius_acceleration_factor(0.7, t_use, t) for t in stress_temps]
        for i in range(len(afs) - 1):
            assert afs[i] < afs[i + 1], (
                f"AF not increasing at T_stress={stress_temps[i+1]}: AF={afs[i+1]:.4f}"
            )

    # ── Input validation: Ea ≤ 0 ──────────────────────────────────────────
    def test_zero_ea_raises_value_error(self):
        with pytest.raises(ValueError, match="Activation energy Ea must be"):
            arrhenius_acceleration_factor(ea_ev=0.0, t_use_celsius=60.0, t_stress_celsius=70.0)

    def test_negative_ea_raises_value_error(self):
        with pytest.raises(ValueError, match="Activation energy Ea must be"):
            arrhenius_acceleration_factor(ea_ev=-0.5, t_use_celsius=60.0, t_stress_celsius=70.0)

    # ── Shaft exclusion reminder (not tested here, tested at component level) ──
    def test_shaft_has_no_ea_in_params(self):
        """
        The Shaft component has activation_energy_ev = None in COMPONENT_WEIBULL_PARAMS.
        This test confirms the None value is correctly stored (not accidentally set).
        The arrhenius_acceleration_factor function should NOT be called with None —
        this is enforced at the caller level (kpi.py / report.py).
        """
        shaft_ea = COMPONENT_WEIBULL_PARAMS["Shaft"]["ea_ev"]
        assert shaft_ea is None, (
            "Shaft Ea must be None — fatigue-dominant failure is not thermally modelled"
        )


# ===========================================================================
# SECTION 4 — Integration / Parametric sweep tests
# ===========================================================================
# These tests validate cross-function consistency and the series reliability model.
# ===========================================================================

class TestReliabilityIntegration:
    """Cross-function consistency and series reliability tests."""

    # ── weibull_reliability + mtbf_weibull: R(MTBF) ≈ 0.368 for β > 1? ──
    def test_r_at_mtbf_is_above_one_third_for_wear_out(self):
        """
        For β > 1 (wear-out), R(MTBF) > e^(-1) ≈ 0.3679 because MTBF < η.
        The Gamma factor in MTBF = η·Γ(1+1/β) is < 1 for β > 1 → MTBF < η → R(MTBF) > R(η).
        """
        beta, eta = 3.0, 4380.0
        mtbf = mtbf_weibull(beta=beta, eta=eta)
        r_at_mtbf = weibull_reliability(mtbf, beta=beta, eta=eta)
        # R(MTBF) > e^(-1) for β > 1 (MTBF concentrates before the distribution mass)
        assert r_at_mtbf > math.exp(-1.0), (
            f"R(MTBF) = {r_at_mtbf:.4f} should exceed e^(-1) ≈ {math.exp(-1):.4f} "
            f"for β={beta}"
        )

    # ── Series system reliability is <= min(individual R_i) ───────────────
    def test_series_system_r_leq_min_component_r(self):
        """R_sys = ∏ R_i ≤ min(R_i) for any probability in [0,1]."""
        t = 2000.0
        component_rs = {
            comp_name: weibull_reliability(
                t,
                params["beta_mid"],
                params["eta_hours"]
            )
            for comp_name, params in COMPONENT_WEIBULL_PARAMS.items()
        }
        result = series_system_reliability(component_rs)
        r_sys    = result["R_system"]
        r_min_i  = min(component_rs.values())
        assert r_sys <= r_min_i, (
            f"R_sys ({r_sys:.6f}) exceeds min component R ({r_min_i:.6f}) — "
            "series model invariant violated"
        )

    # ── Series system weakest component identification ─────────────────────
    def test_series_weakest_component_is_minimum_reliability(self):
        """The weakest_component key must correspond to the lowest R_i value."""
        comp_rs = {
            "Bearing":       0.95,
            "Shaft":         0.98,
            "Motor Housing": 0.60,   # intentionally lowest
            "Coupling":      0.92,
            "Gearbox":       0.85,
        }
        result = series_system_reliability(comp_rs)
        assert result["weakest_component"] == "Motor Housing"

    # ── System R_sys matches product formula ──────────────────────────────
    def test_series_r_sys_equals_product(self):
        """R_sys = ∏ R_i (direct product) must match series_system_reliability()."""
        comp_rs = {
            "Bearing":       0.92,
            "Shaft":         0.96,
            "Motor Housing": 0.88,
            "Coupling":      0.94,
            "Gearbox":       0.90,
        }
        expected = 0.92 * 0.96 * 0.88 * 0.94 * 0.90
        result = series_system_reliability(comp_rs)
        assert result["R_system"] == pytest.approx(expected, rel=1e-6)

    # ── availability_from_mtbf_mttr consistency check ─────────────────────
    def test_availability_bridge_bearing_params(self):
        """
        For Bearing β=3.0, η=4380 h: MTBF ≈ 3911 h.
        With a representative MTTR = 8 h (1 shift corrective repair):
          A = MTBF / (MTBF + MTTR) = 3911 / 3919 ≈ 0.99796
        """
        beta, eta, mttr = 3.0, 4380.0, 8.0
        mtbf = mtbf_weibull(beta=beta, eta=eta)
        a = availability_from_mtbf_mttr(mtbf, mttr)
        expected = mtbf / (mtbf + mttr)
        assert a == pytest.approx(expected, rel=1e-9)
        assert 0.99 < a < 1.0, f"Expected availability close to 1 for high MTBF; got {a:.5f}"

    # ── Parametric sweep: all 5 components, multiple t values ─────────────
    @pytest.mark.parametrize("comp_name", list(COMPONENT_WEIBULL_PARAMS.keys()))
    @pytest.mark.parametrize("t_fraction", [0.0, 0.25, 0.5, 1.0, 1.5, 2.0])
    def test_all_components_at_eta_fractions(self, comp_name, t_fraction):
        """
        Parametric sweep: all 5 components × 6 time fractions of η.
        Ensures weibull_reliability and mtbf_weibull both execute without error
        and return physically valid values.
        """
        params = COMPONENT_WEIBULL_PARAMS[comp_name]
        beta = params["beta_mid"]
        eta  = params["eta_hours"]
        t    = t_fraction * eta

        r    = weibull_reliability(t, beta, eta)
        mtbf = mtbf_weibull(beta, eta)

        assert 0.0 <= r <= 1.0, f"{comp_name} R({t:.0f})={r:.6f} out of [0,1]"
        assert mtbf > 0.0,      f"{comp_name} MTBF={mtbf:.2f} not positive"

    # ── All components: Arrhenius AF computed for Ea-bearing components ────
    @pytest.mark.parametrize("comp_name,ea,t_use,t_stress", [
        ("Bearing",       0.80, 60.0, 80.0),
        ("Motor Housing", 1.00, 80.0, 130.0),
        ("Gearbox",       0.70, 70.0, 90.0),
        ("Coupling",      0.60, 50.0, 70.0),
    ])
    def test_arrhenius_for_ea_bearing_components(self, comp_name, ea, t_use, t_stress):
        """
        Each thermally-governed component should have AF > 1 when T_stress > T_use.
        Shaft is excluded from this parametric test (Ea = None).
        """
        af = arrhenius_acceleration_factor(ea_ev=ea, t_use_celsius=t_use, t_stress_celsius=t_stress)
        assert af > 1.0, (
            f"{comp_name}: AF = {af:.4f} ≤ 1 with T_stress > T_use — Arrhenius violated"
        )
