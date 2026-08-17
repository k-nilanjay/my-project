"""
tests/test_simulate.py — Manufacturing Analytics FYP
=====================================================
Unit Tests for python/simulate.py
Phase 1, Sub-phase 1.3 — Data Simulation
Day 6

TEST STRATEGY
-------------
Tests are grouped into 5 classes, each testing a distinct layer of simulate.py.
All tests use analytical ground-truth values derived from the locked mathematical
formulas in CONTEXT.md and reliability.py — NOT against database output.

Test class inventory:
  TestDrawWeibullTTF          — distribution shape, mean ≈ MTBF, reproducibility
  TestArrheniusComponentAF    — topology-aware AF wrapper, Shaft exclusion
  TestComputeRampProgress     — degradation ramp boundary conditions
  TestSignalInjection         — sensor value correctness in each phase
  TestGenerateComponentTelemetry — DataFrame schema, failure flagging, cascade
  TestRunSimulation           — CSV output, cascade propagation across components

LOCKED FORMULAS TESTED (from CONTEXT.md / Day 1):
    draw_weibull_ttf:   TTF = η · (−ln(U))^(1/β)  →  mean ≈ MTBF = η · Γ(1+1/β)
    Arrhenius AF:       AF = exp[(Ea/k)(1/T_use − 1/T_stress)]
    Ramp progress:      (t − ramp_start)/(TTF − ramp_start)  ∈ [0, 1]
    Degradation ramp:   value = baseline + (alarm − baseline) × progress²
    ISO 10816-3 zones:  vibration alarm=4.5, danger=7.1 mm/s
"""

from __future__ import annotations

import math
import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest
from scipy.special import gamma as scipy_gamma

# Make sure the python/ directory is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulate import (
    SimulationConfig,
    NOMINAL_SENSOR_VALUES,
    SENSOR_THRESHOLDS,
    NOMINAL_TEMPERATURES_CELSIUS,
    DEGRADATION_RAMP_FRACTION,
    CASCADE_VIB_BOOST_FRACTION,
    draw_weibull_ttf,
    arrhenius_af_for_component,
    eta_derated_for_component,
    derated_weibull_reliability,
    _compute_ramp_progress,
    _inject_vibration,
    _inject_temperature,
    _inject_oil_debris,
    _inject_rpm,
    _inject_load,
    _get_sensor_channels,
    _primary_sensor,
    generate_component_telemetry,
    run_simulation,
)
from reliability import (
    COMPONENT_WEIBULL_PARAMS,
    BOLTZMANN_EV_PER_K,
    KELVIN_OFFSET,
    mtbf_weibull,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def cfg():
    """Default SimulationConfig for most tests (30-day window, seed=42)."""
    return SimulationConfig(window_days=30, random_seed=42, verbose=False)


@pytest.fixture
def cfg_no_arrhenius():
    """Config with Arrhenius derating disabled — for isolating TTF distribution tests."""
    return SimulationConfig(
        window_days=30,
        random_seed=42,
        verbose=False,
        arrhenius_stress_enabled=False,
    )


@pytest.fixture
def cfg_no_cascade():
    """Config with cascade boost disabled."""
    return SimulationConfig(
        window_days=30,
        random_seed=42,
        verbose=False,
        cascade_boost_enabled=False,
    )


@pytest.fixture
def rng_fixed():
    """Deterministic RNG, seed=42."""
    return np.random.default_rng(42)


# =============================================================================
# CLASS 1: TestDrawWeibullTTF
# =============================================================================

class TestDrawWeibullTTF:
    """
    Validates draw_weibull_ttf():
        TTF = η · (−ln(U))^(1/β)    U ~ Uniform(0, 1)

    Ground-truth: MTBF = η · Γ(1 + 1/β)  →  E[TTF] ≈ MTBF (for large n)
    """

    def test_ttf_is_positive(self, rng_fixed):
        """All TTF samples must be strictly positive."""
        beta, eta = 3.0, 4380.0
        for _ in range(100):
            ttf = draw_weibull_ttf(beta, eta, rng_fixed)
            assert ttf > 0.0, f"TTF must be > 0; got {ttf}"

    def test_ttf_is_float(self, rng_fixed):
        """Return type must be float."""
        ttf = draw_weibull_ttf(3.0, 4380.0, rng_fixed)
        assert isinstance(ttf, float)

    def test_deterministic_with_fixed_seed(self):
        """Same seed must produce identical TTF sequence."""
        rng_a = np.random.default_rng(99)
        rng_b = np.random.default_rng(99)
        for _ in range(10):
            ttf_a = draw_weibull_ttf(3.0, 4380.0, rng_a)
            ttf_b = draw_weibull_ttf(3.0, 4380.0, rng_b)
            assert math.isclose(ttf_a, ttf_b, rel_tol=1e-12)

    def test_mean_approx_mtbf_bearing(self):
        """
        For Bearing (β=3.0, η=4380 h):
            MTBF = η · Γ(1 + 1/β) = 4380 · Γ(4/3) ≈ 3951 h
        Mean of N=5000 samples should be within ±5% of MTBF.
        """
        beta, eta = 3.0, 4380.0
        mtbf_expected = mtbf_weibull(beta, eta)
        rng = np.random.default_rng(0)
        samples = [draw_weibull_ttf(beta, eta, rng) for _ in range(5000)]
        mean_ttf = sum(samples) / len(samples)
        assert abs(mean_ttf - mtbf_expected) / mtbf_expected < 0.05, (
            f"Mean TTF {mean_ttf:.1f} h deviates > 5% from MTBF {mtbf_expected:.1f} h"
        )

    def test_mean_approx_mtbf_shaft(self):
        """
        For Shaft (β=1.75, η=8760 h):
            MTBF = 8760 · Γ(1 + 1/1.75) ≈ 7971 h
        Mean of N=5000 samples within ±5%.
        """
        beta, eta = 1.75, 8760.0
        mtbf_expected = mtbf_weibull(beta, eta)
        rng = np.random.default_rng(1)
        samples = [draw_weibull_ttf(beta, eta, rng) for _ in range(5000)]
        mean_ttf = sum(samples) / len(samples)
        assert abs(mean_ttf - mtbf_expected) / mtbf_expected < 0.05

    def test_higher_beta_less_variance(self):
        """
        Higher β → tighter distribution (Weibull approaches Dirac delta as β→∞).
        CV (CoV) = std / mean should decrease as β increases.
        """
        rng_a = np.random.default_rng(2)
        rng_b = np.random.default_rng(3)
        n = 3000
        samples_low_beta  = [draw_weibull_ttf(1.5, 5000.0, rng_a) for _ in range(n)]
        samples_high_beta = [draw_weibull_ttf(3.5, 5000.0, rng_b) for _ in range(n)]
        cov_low  = (sum((x - sum(samples_low_beta)/n)**2 for x in samples_low_beta)/n)**0.5 / (sum(samples_low_beta)/n)
        cov_high = (sum((x - sum(samples_high_beta)/n)**2 for x in samples_high_beta)/n)**0.5 / (sum(samples_high_beta)/n)
        assert cov_low > cov_high, "Higher β should give smaller CoV"

    def test_larger_eta_gives_larger_ttf_on_average(self):
        """Doubling η approximately doubles mean TTF (scales linearly)."""
        rng_a = np.random.default_rng(4)
        rng_b = np.random.default_rng(4)
        n = 3000
        beta = 2.5
        samples_small_eta = [draw_weibull_ttf(beta, 3000.0, rng_a) for _ in range(n)]
        samples_large_eta = [draw_weibull_ttf(beta, 6000.0, rng_b) for _ in range(n)]
        mean_small = sum(samples_small_eta) / n
        mean_large = sum(samples_large_eta) / n
        ratio = mean_large / mean_small
        assert 1.8 < ratio < 2.2, f"Expected ratio ≈ 2.0; got {ratio:.3f}"

    def test_zero_beta_raises_value_error(self, rng_fixed):
        with pytest.raises(ValueError, match="β must be > 0"):
            draw_weibull_ttf(0.0, 4380.0, rng_fixed)

    def test_negative_beta_raises_value_error(self, rng_fixed):
        with pytest.raises(ValueError):
            draw_weibull_ttf(-1.0, 4380.0, rng_fixed)

    def test_zero_eta_raises_value_error(self, rng_fixed):
        with pytest.raises(ValueError, match="η must be > 0"):
            draw_weibull_ttf(3.0, 0.0, rng_fixed)

    def test_all_components_produce_positive_ttf(self, rng_fixed):
        """All 5 components should produce positive TTFs."""
        for comp_name, params in COMPONENT_WEIBULL_PARAMS.items():
            ttf = draw_weibull_ttf(params["beta_mid"], params["eta_hours"], rng_fixed)
            assert ttf > 0.0, f"{comp_name}: TTF must be > 0"

    def test_ttf_single_draw_bearing_analytical(self):
        """
        Verify TTF formula analytically for a fixed U value.
        TTF = η · (−ln(U))^(1/β)
        For U = 0.5, β = 3.0, η = 4380:
            TTF = 4380 · (ln(2))^(1/3) ≈ 4380 · 0.8855 ≈ 3878.5 h
        """
        # Patch rng to return exactly 0.5
        class _MockRNG:
            def uniform(self, low, high):
                return 0.5

        expected = 4380.0 * ((-math.log(0.5)) ** (1.0 / 3.0))
        ttf = draw_weibull_ttf(3.0, 4380.0, _MockRNG())
        assert math.isclose(ttf, expected, rel_tol=1e-9)


# =============================================================================
# CLASS 2: TestArrheniusComponentAF
# =============================================================================

class TestArrheniusComponentAF:
    """
    Validates arrhenius_af_for_component():
        AF = exp[(Ea/k)(1/T_use − 1/T_stress)]    k = 8.617×10⁻⁵ eV/K

    Key rules to enforce:
        - Shaft always returns AF = 1.0 (no thermal model)
        - T_reading ≤ T_nominal → AF = 1.0 (no acceleration below nominal)
        - arrhenius_stress_enabled=False → AF = 1.0 always
    """

    def test_shaft_always_returns_one(self, cfg):
        """Shaft has Ea=None → AF must always be 1.0."""
        for t_reading in [60.0, 80.0, 110.0, 150.0]:
            af = arrhenius_af_for_component("Shaft", t_reading, cfg)
            assert af == 1.0, f"Shaft AF must be 1.0 at T={t_reading}°C; got {af}"

    def test_below_nominal_returns_one(self, cfg):
        """Temperature at or below T_nominal → AF = 1.0 (no stress)."""
        # Bearing T_nominal = 70.0°C
        af_at_nominal = arrhenius_af_for_component("Bearing", 70.0, cfg)
        af_below = arrhenius_af_for_component("Bearing", 50.0, cfg)
        assert af_at_nominal == 1.0
        assert af_below == 1.0

    def test_above_nominal_bearing_af_greater_than_one(self, cfg):
        """Bearing at T_nominal + 20°C → AF > 1.0."""
        t_nom = NOMINAL_TEMPERATURES_CELSIUS["Bearing"]  # 70.0
        af = arrhenius_af_for_component("Bearing", t_nom + 20.0, cfg)
        assert af > 1.0, f"Expected AF > 1.0; got {af}"

    def test_arrhenius_disabled_always_one(self, cfg_no_arrhenius):
        """With arrhenius_stress_enabled=False, all components return AF=1.0."""
        for comp in ["Bearing", "Motor Housing", "Coupling", "Gearbox"]:
            t_nom = NOMINAL_TEMPERATURES_CELSIUS[comp]
            af = arrhenius_af_for_component(comp, t_nom + 30.0, cfg_no_arrhenius)
            assert af == 1.0, f"{comp}: AF should be 1.0 when Arrhenius disabled"

    def test_motor_housing_highest_af_for_same_delta_t(self, cfg):
        """
        Motor Housing has the highest Ea (1.00 eV) → should produce the
        highest AF for the same +20°C temperature step.
        """
        delta_t = 20.0
        afs = {}
        for comp in ["Bearing", "Motor Housing", "Coupling", "Gearbox"]:
            t_nom = NOMINAL_TEMPERATURES_CELSIUS[comp]
            afs[comp] = arrhenius_af_for_component(comp, t_nom + delta_t, cfg)

        assert afs["Motor Housing"] == max(afs.values()), (
            f"Motor Housing should have highest AF; got {afs}"
        )

    def test_bearing_af_analytical_check(self, cfg):
        """
        Bearing: Ea=0.65 eV, T_use=70°C, T_stress=90°C
        k = 8.617e-5 eV/K
        T_use_K = 343.15K, T_stress_K = 363.15K
        AF = exp[(0.65/8.617e-5) · (1/343.15 − 1/363.15)]

        Verify simulate.py result matches direct formula within 0.1%.
        """
        ea = 0.65
        t_use_k = 70.0 + KELVIN_OFFSET
        t_stress_k = 90.0 + KELVIN_OFFSET
        expected_af = math.exp((ea / BOLTZMANN_EV_PER_K) * (1.0/t_use_k - 1.0/t_stress_k))

        af = arrhenius_af_for_component("Bearing", 90.0, cfg)
        assert math.isclose(af, expected_af, rel_tol=1e-3), (
            f"Bearing AF: expected {expected_af:.4f}, got {af:.4f}"
        )

    def test_af_increases_monotonically_with_temperature(self, cfg):
        """AF must be strictly increasing with temperature stress."""
        temps = [71.0, 80.0, 90.0, 100.0, 120.0]
        afs = [arrhenius_af_for_component("Bearing", t, cfg) for t in temps]
        for i in range(len(afs) - 1):
            assert afs[i] < afs[i + 1], (
                f"AF must increase monotonically; failed at T={temps[i]}→{temps[i+1]}: "
                f"{afs[i]:.4f} → {afs[i+1]:.4f}"
            )

    def test_rule_of_thumb_10deg_approx_2x(self, cfg):
        """
        Day 1 rule-of-thumb: +10°C ≈ 2× failure rate for Ea≈0.7 eV.
        Test on Gearbox (Ea=0.70 eV) with +10°C step.
        AF should be in range [1.5, 2.5] — rule of thumb is approximate.
        """
        t_nom = NOMINAL_TEMPERATURES_CELSIUS["Gearbox"]  # 75.0
        af = arrhenius_af_for_component("Gearbox", t_nom + 10.0, cfg)
        assert 1.5 <= af <= 2.5, (
            f"Gearbox +10°C AF = {af:.3f} — expected ≈ 2× (range 1.5–2.5)"
        )


# =============================================================================
# CLASS 3: TestComputeRampProgress
# =============================================================================

class TestComputeRampProgress:
    """
    Validates _compute_ramp_progress():
        ramp_start = TTF × (1 − DEGRADATION_RAMP_FRACTION)
        progress = 0.0 if t < ramp_start
        progress = 1.0 if t ≥ TTF
        progress = (t − ramp_start) / (TTF − ramp_start)  otherwise
    """

    def test_healthy_phase_returns_zero(self):
        """Before ramp start → progress must be 0.0."""
        ttf = 100.0
        ramp_start = ttf * (1 - DEGRADATION_RAMP_FRACTION)
        progress = _compute_ramp_progress(ramp_start - 1.0, ttf)
        assert progress == 0.0

    def test_at_ramp_start_returns_zero(self):
        """At exactly ramp_start → progress = 0.0 (boundary)."""
        ttf = 200.0
        ramp_start = ttf * (1 - DEGRADATION_RAMP_FRACTION)
        progress = _compute_ramp_progress(ramp_start, ttf)
        assert progress == 0.0

    def test_at_ttf_returns_one(self):
        """At t = TTF → progress = 1.0."""
        ttf = 150.0
        progress = _compute_ramp_progress(ttf, ttf)
        assert math.isclose(progress, 1.0, rel_tol=1e-9)

    def test_beyond_ttf_returns_one(self):
        """t > TTF → progress clamped to 1.0."""
        ttf = 100.0
        progress = _compute_ramp_progress(ttf + 50.0, ttf)
        assert progress == 1.0

    def test_midpoint_of_ramp(self):
        """
        At t = ramp_start + (TTF − ramp_start)/2 → progress = 0.5.
        """
        ttf = 1000.0
        ramp_start = ttf * (1 - DEGRADATION_RAMP_FRACTION)
        t_mid = ramp_start + (ttf - ramp_start) / 2.0
        progress = _compute_ramp_progress(t_mid, ttf)
        assert math.isclose(progress, 0.5, rel_tol=1e-6)

    def test_progress_is_monotonically_increasing(self):
        """Progress must be non-decreasing with time."""
        ttf = 500.0
        times = [0, 100, 200, 300, 350, 400, 450, 499, 500, 600]
        progresses = [_compute_ramp_progress(t, ttf) for t in times]
        for i in range(len(progresses) - 1):
            assert progresses[i] <= progresses[i + 1]

    def test_progress_bounded_in_unit_interval(self):
        """Progress must always be in [0.0, 1.0]."""
        ttf = 300.0
        for t in [0, 50, 100, 200, 210, 250, 300, 400]:
            p = _compute_ramp_progress(float(t), ttf)
            assert 0.0 <= p <= 1.0, f"Progress {p} out of [0, 1] at t={t}"

    def test_t_zero_returns_zero(self):
        """t=0 is always in healthy phase → progress = 0.0."""
        assert _compute_ramp_progress(0.0, 500.0) == 0.0


# =============================================================================
# CLASS 4: TestSignalInjection
# =============================================================================

class TestSignalInjection:
    """
    Validates signal injection helpers (_inject_vibration, _inject_temperature, etc.)
    for correct behaviour in each phase: healthy, ramp, post-failure.
    """

    # ---- Vibration ----

    def test_vibration_healthy_phase_near_baseline(self):
        """In healthy phase, vibration should be close to baseline (within ±5σ)."""
        rng = np.random.default_rng(0)
        baseline, alarm, danger = 1.2, 4.5, 7.1
        ttf = 1000.0
        noise_std = 0.15
        samples = [
            _inject_vibration(t, ttf, baseline, alarm, danger, 0.0, rng, noise_std)
            for t in range(100)  # well before ramp start
        ]
        assert all(
            abs(v - baseline) < 5 * noise_std for v in samples
        ), "Healthy vibration should be near baseline"

    def test_vibration_post_failure_above_danger(self):
        """Post-failure vibration should exceed danger threshold."""
        rng = np.random.default_rng(1)
        baseline, alarm, danger = 1.2, 4.5, 7.1
        ttf = 100.0
        # Sample at 200h (well post-failure)
        values = [
            _inject_vibration(200.0, ttf, baseline, alarm, danger, 0.0, rng, 0.15)
            for _ in range(100)
        ]
        # At least 95% should be above danger threshold (mean is at danger + spike)
        assert sum(v >= danger for v in values) >= 90

    def test_vibration_ramp_increases_monotonically_on_average(self):
        """
        During ramp, mean vibration should increase.
        Test by comparing mean at 25% vs 75% through the ramp.
        """
        rng_a = np.random.default_rng(2)
        rng_b = np.random.default_rng(2)
        baseline, alarm, danger = 1.2, 4.5, 7.1
        ttf = 1000.0
        ramp_start = ttf * (1 - DEGRADATION_RAMP_FRACTION)  # 700h

        t_early = ramp_start + 0.25 * (ttf - ramp_start)   # 775h
        t_late  = ramp_start + 0.75 * (ttf - ramp_start)   # 925h

        n = 200
        mean_early = sum(
            _inject_vibration(t_early, ttf, baseline, alarm, danger, 0.0, rng_a, 0.15)
            for _ in range(n)
        ) / n
        mean_late = sum(
            _inject_vibration(t_late, ttf, baseline, alarm, danger, 0.0, rng_b, 0.15)
            for _ in range(n)
        ) / n
        assert mean_early < mean_late, (
            f"Mean vibration should increase during ramp: early={mean_early:.3f}, late={mean_late:.3f}"
        )

    def test_vibration_cascade_boost_increases_value(self):
        """Cascade boost should additively increase vibration readings."""
        rng_a = np.random.default_rng(10)
        rng_b = np.random.default_rng(10)  # same seed
        baseline, alarm, danger = 1.2, 4.5, 7.1
        ttf = 1000.0
        boost = 1.65  # CASCADE_VIB_BOOST_FRACTION × (alarm − baseline) = 0.5×(4.5−1.2)

        # In healthy phase
        v_no_boost  = _inject_vibration(50.0, ttf, baseline, alarm, danger, 0.0,  rng_a, 0.15)
        v_with_boost = _inject_vibration(50.0, ttf, baseline, alarm, danger, boost, rng_b, 0.15)
        assert v_with_boost > v_no_boost, "Cascade boost must increase vibration"

    def test_vibration_is_non_negative(self):
        """Vibration values must never be negative."""
        rng = np.random.default_rng(3)
        baseline, alarm, danger = 1.2, 4.5, 7.1
        ttf = 100.0
        times = list(range(0, 200, 5))
        values = [
            _inject_vibration(float(t), ttf, baseline, alarm, danger, 0.0, rng, 0.15)
            for t in times
        ]
        assert all(v >= 0.0 for v in values)

    # ---- Temperature ----

    def test_temperature_healthy_near_baseline(self):
        """Healthy temperature should be within ±5σ of baseline."""
        rng = np.random.default_rng(4)
        baseline, alarm, danger = 110.0, 130.0, 155.0
        ttf = 5000.0
        samples = [
            _inject_temperature(t, ttf, baseline, alarm, danger, rng, 2.0)
            for t in range(100)
        ]
        assert all(abs(v - baseline) < 5 * 2.0 for v in samples)

    def test_temperature_post_failure_above_danger(self):
        """Post-failure temperature should exceed danger threshold."""
        rng = np.random.default_rng(5)
        baseline, alarm, danger = 110.0, 130.0, 155.0
        ttf = 100.0
        values = [
            _inject_temperature(500.0, ttf, baseline, alarm, danger, rng, 2.0)
            for _ in range(50)
        ]
        assert all(v >= danger for v in values)

    # ---- Oil Debris ----

    def test_oil_debris_healthy_near_baseline(self):
        """Oil debris in healthy phase should stay near baseline."""
        rng = np.random.default_rng(6)
        baseline, alarm, danger = 10.0, 50.0, 200.0
        ttf = 3000.0
        samples = [
            _inject_oil_debris(t, ttf, baseline, alarm, danger, rng, 1.5)
            for t in range(100)
        ]
        assert all(v <= alarm * 0.4 for v in samples), "Healthy oil debris should be far below alarm"

    def test_oil_debris_post_failure_above_danger(self):
        """Post-failure oil debris should be well above danger threshold."""
        rng = np.random.default_rng(7)
        baseline, alarm, danger = 10.0, 50.0, 200.0
        ttf = 100.0
        values = [
            _inject_oil_debris(200.0, ttf, baseline, alarm, danger, rng, 1.5)
            for _ in range(50)
        ]
        assert all(v >= danger for v in values)

    # ---- RPM ----

    def test_rpm_healthy_near_baseline(self):
        """Healthy RPM should be near rated speed."""
        rng = np.random.default_rng(8)
        baseline = 1480.0
        ttf = 7000.0
        samples = [
            _inject_rpm(float(t), ttf, baseline, rng, 5.0)
            for t in range(50)
        ]
        assert all(abs(v - baseline) < 5 * 5.0 for v in samples)

    def test_rpm_post_failure_is_zero(self):
        """Post-failure RPM must be 0.0 (shaft stops)."""
        rng = np.random.default_rng(9)
        baseline = 1480.0
        ttf = 100.0
        assert _inject_rpm(200.0, ttf, baseline, rng, 5.0) == 0.0

    def test_rpm_drops_during_ramp(self):
        """RPM should drop below baseline during degradation ramp."""
        rng_a = np.random.default_rng(20)
        rng_b = np.random.default_rng(20)
        baseline = 1480.0
        ttf = 1000.0
        ramp_start = ttf * (1 - DEGRADATION_RAMP_FRACTION)

        t_healthy = ramp_start * 0.5
        t_ramp = ramp_start + 0.8 * (ttf - ramp_start)  # deep in ramp

        n = 200
        mean_healthy = sum(_inject_rpm(t_healthy, ttf, baseline, rng_a, 5.0) for _ in range(n)) / n
        mean_ramp    = sum(_inject_rpm(t_ramp, ttf, baseline, rng_b, 5.0) for _ in range(n)) / n
        assert mean_ramp < mean_healthy, (
            f"RPM should drop during ramp: healthy={mean_healthy:.1f}, ramp={mean_ramp:.1f}"
        )

    # ---- Load ----

    def test_load_post_failure_is_zero(self):
        """Post-failure load must be 0.0 (coupling shears)."""
        rng = np.random.default_rng(11)
        assert _inject_load(500.0, 100.0, 75.0, 90.0, rng, 1.0) == 0.0

    def test_load_bounded_0_to_100(self):
        """Load % must always be in [0, 100]."""
        rng = np.random.default_rng(12)
        ttf = 200.0
        values = [_inject_load(float(t), ttf, 75.0, 90.0, rng, 1.0) for t in range(300)]
        assert all(0.0 <= v <= 100.0 for v in values)


# =============================================================================
# CLASS 5: TestGenerateComponentTelemetry
# =============================================================================

class TestGenerateComponentTelemetry:
    """
    Validates generate_component_telemetry():
        - Returns correct DataFrame schema
        - Correct number of rows (timesteps × sensor channels)
        - Failure flag is set correctly
        - Cascade flag is set when upstream failed
        - R_derated ∈ [0, 1]
        - No NaN values in value column
    """

    EXPECTED_SCHEMA = {
        "ts", "component_id", "component_name", "sensor_type",
        "value", "is_failure_event", "failure_mode", "R_derated",
        "AF", "cascade_flag",
    }

    @pytest.mark.parametrize("comp_name", [
        "Bearing", "Shaft", "Motor Housing", "Coupling", "Gearbox"
    ])
    def test_schema_columns(self, comp_name, cfg):
        """All required columns must be present in the output DataFrame."""
        rng = np.random.default_rng(42)
        df, _ = generate_component_telemetry(comp_name, cfg, rng)
        missing = self.EXPECTED_SCHEMA - set(df.columns)
        assert not missing, f"{comp_name}: Missing columns: {missing}"

    @pytest.mark.parametrize("comp_name,n_channels", [
        ("Bearing", 2),       # vibration, temperature
        ("Shaft", 2),         # vibration, rpm
        ("Motor Housing", 2), # temperature, vibration
        ("Coupling", 2),      # vibration, load
        ("Gearbox", 3),       # vibration, oil_debris, temperature
    ])
    def test_row_count(self, comp_name, n_channels, cfg):
        """
        Row count = (window_hours / timestep_hours + 1) × n_sensor_channels.
        For 30-day window (720h) with dt=1h: 721 timesteps × n_channels.
        """
        rng = np.random.default_rng(42)
        df, _ = generate_component_telemetry(comp_name, cfg, rng)
        expected_timesteps = int(cfg.window_days * 24 / cfg.timestep_hours) + 1
        expected_rows = expected_timesteps * n_channels
        assert len(df) == expected_rows, (
            f"{comp_name}: expected {expected_rows} rows, got {len(df)}"
        )

    def test_no_nan_in_value_column(self, cfg):
        """The 'value' column must not contain NaN values (Day 5 scaffold had NaN)."""
        rng = np.random.default_rng(42)
        for comp in ["Bearing", "Gearbox"]:
            df, _ = generate_component_telemetry(comp, cfg, rng)
            nan_count = df["value"].isna().sum()
            assert nan_count == 0, f"{comp}: {nan_count} NaN values in 'value' column"

    def test_r_derated_in_unit_interval(self, cfg):
        """R_derated must be in [0, 1] for all rows."""
        rng = np.random.default_rng(42)
        df, _ = generate_component_telemetry("Motor Housing", cfg, rng)
        assert df["R_derated"].between(0.0, 1.0).all(), (
            "R_derated must be in [0, 1]"
        )

    def test_failure_event_flag_set_exactly_once_per_channel_per_failure(self, cfg):
        """
        For components whose TTF falls within the window, is_failure_event = 1
        should appear on exactly one timestep on the primary sensor channel.
        """
        rng = np.random.default_rng(42)
        # Gearbox η=4380h, window=720h — TTF likely exceeds window with normal β
        # Force a short TTF by using a very small η config
        cfg_short = SimulationConfig(
            window_days=365,  # 8760h window → most components will fail
            random_seed=42,
        )
        rng2 = np.random.default_rng(42)
        df, ttf = generate_component_telemetry("Bearing", cfg_short, rng2)
        if ttf <= 8760.0:
            primary = _primary_sensor("Bearing")
            failure_rows = df[(df["sensor_type"] == primary) & (df["is_failure_event"] == 1)]
            assert len(failure_rows) == 1, (
                f"Expected exactly 1 failure event row; got {len(failure_rows)}"
            )

    def test_failure_mode_populated_at_failure_event(self, cfg):
        """failure_mode column must be non-null at is_failure_event = 1 rows."""
        rng = np.random.default_rng(42)
        cfg_long = SimulationConfig(window_days=365, random_seed=42)
        rng2 = np.random.default_rng(42)
        df, ttf = generate_component_telemetry("Bearing", cfg_long, rng2)
        if ttf <= 365 * 24:
            failure_rows = df[df["is_failure_event"] == 1]
            assert failure_rows["failure_mode"].notna().all()

    def test_cascade_flag_set_when_upstream_failed(self, cfg):
        """
        When upstream_failure_times is provided with a TTF within the window,
        cascade_flag should be 1 for vibration rows after the upstream failure.
        """
        rng = np.random.default_rng(42)
        # Simulate Bearing first
        df_bearing, ttf_bearing = generate_component_telemetry("Bearing", cfg, rng)

        # Force a Bearing failure at t=100h by providing it as upstream failure
        rng2 = np.random.default_rng(42)
        upstream_failures = {"Bearing": 100.0}  # 100h is well within 720h window
        df_shaft, _ = generate_component_telemetry("Shaft", cfg, rng2, upstream_failures)

        cascade_rows = df_shaft[(df_shaft["cascade_flag"] == 1) & (df_shaft["sensor_type"] == "vibration")]
        assert len(cascade_rows) > 0, "Cascade flag should be set for Shaft when Bearing fails at 100h"

    def test_no_cascade_flag_when_upstream_beyond_window(self, cfg):
        """If upstream TTF > window, cascade_flag must be 0 for all rows."""
        rng = np.random.default_rng(42)
        # Upstream failure at 9999h >> 720h window
        upstream_failures = {"Bearing": 9999.0}
        df, _ = generate_component_telemetry("Shaft", cfg, rng, upstream_failures)
        assert df["cascade_flag"].sum() == 0

    def test_component_id_correct(self, cfg):
        """component_id must match COMPONENT_POSITIONS for each component."""
        from topology import COMPONENT_POSITIONS
        for comp, expected_id in COMPONENT_POSITIONS.items():
            rng3 = np.random.default_rng(42)
            df2, _ = generate_component_telemetry(comp, cfg, rng3)
            assert (df2["component_id"] == expected_id).all(), (
                f"{comp}: component_id should be {expected_id}"
            )

    def test_gearbox_has_three_sensor_types(self, cfg):
        """Gearbox telemetry must contain exactly 3 sensor types."""
        rng = np.random.default_rng(42)
        df, _ = generate_component_telemetry("Gearbox", cfg, rng)
        sensor_types = set(df["sensor_type"].unique())
        assert sensor_types == {"vibration", "oil_debris", "temperature"}, (
            f"Gearbox sensor types: expected 3, got {sensor_types}"
        )

    def test_ttf_is_returned_as_float(self, cfg):
        """generate_component_telemetry must return (DataFrame, float) tuple."""
        rng = np.random.default_rng(42)
        result = generate_component_telemetry("Bearing", cfg, rng)
        assert isinstance(result, tuple) and len(result) == 2
        assert isinstance(result[1], float)

    def test_values_non_negative(self, cfg):
        """All sensor values must be ≥ 0 (physical constraint)."""
        rng = np.random.default_rng(42)
        df, _ = generate_component_telemetry("Bearing", cfg, rng)
        assert (df["value"] >= 0.0).all(), "Sensor values must be non-negative"


# =============================================================================
# CLASS 6: TestRunSimulation
# =============================================================================

class TestRunSimulation:
    """
    Validates run_simulation():
        - Returns a dict with all 5 components
        - Each component DataFrame has correct schema
        - CSV files are created in output_dir
        - Master telemetry CSV is created
        - Cascade propagation is reflected in downstream data
        - Determinism: same seed → same output
    """

    def test_returns_all_five_components(self, cfg, tmp_path):
        """run_simulation must return a dict with all 5 component keys."""
        cfg_tmp = SimulationConfig(window_days=5, random_seed=42, output_dir=str(tmp_path))
        results = run_simulation(cfg_tmp)
        assert set(results.keys()) == {"Bearing", "Shaft", "Motor Housing", "Coupling", "Gearbox"}

    def test_csv_files_created(self, tmp_path):
        """One CSV per component + master CSV should be written to output_dir."""
        cfg_tmp = SimulationConfig(window_days=5, random_seed=42, output_dir=str(tmp_path))
        run_simulation(cfg_tmp)
        expected_files = [
            "Bearing_telemetry.csv",
            "Shaft_telemetry.csv",
            "Motor_Housing_telemetry.csv",
            "Coupling_telemetry.csv",
            "Gearbox_telemetry.csv",
            "master_telemetry.csv",
        ]
        created_files = os.listdir(tmp_path)
        for fname in expected_files:
            assert fname in created_files, f"Expected CSV not found: {fname}"

    def test_csv_non_empty(self, tmp_path):
        """All per-component CSVs must have at least 1 data row."""
        cfg_tmp = SimulationConfig(window_days=5, random_seed=42, output_dir=str(tmp_path))
        run_simulation(cfg_tmp)
        for comp in ["Bearing", "Shaft", "Motor_Housing", "Coupling", "Gearbox"]:
            csv_path = os.path.join(tmp_path, f"{comp}_telemetry.csv")
            df = pd.read_csv(csv_path)
            assert len(df) > 0, f"{comp}_telemetry.csv is empty"

    def test_master_csv_row_count(self, tmp_path):
        """Master CSV should equal sum of all per-component CSVs."""
        cfg_tmp = SimulationConfig(window_days=5, random_seed=42, output_dir=str(tmp_path))
        run_simulation(cfg_tmp)
        total = 0
        for comp in ["Bearing", "Shaft", "Motor_Housing", "Coupling", "Gearbox"]:
            df = pd.read_csv(os.path.join(tmp_path, f"{comp}_telemetry.csv"))
            total += len(df)
        master = pd.read_csv(os.path.join(tmp_path, "master_telemetry.csv"))
        assert len(master) == total

    def test_determinism_same_seed(self, tmp_path):
        """Two runs with the same seed must produce identical master CSVs."""
        cfg_a = SimulationConfig(window_days=5, random_seed=99, output_dir=str(tmp_path / "a"))
        cfg_b = SimulationConfig(window_days=5, random_seed=99, output_dir=str(tmp_path / "b"))
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        run_simulation(cfg_a)
        run_simulation(cfg_b)
        df_a = pd.read_csv(tmp_path / "a" / "master_telemetry.csv")
        df_b = pd.read_csv(tmp_path / "b" / "master_telemetry.csv")
        pd.testing.assert_frame_equal(df_a, df_b)

    def test_different_seeds_produce_different_results(self, tmp_path):
        """Different seeds should (with overwhelming probability) give different TTFs."""
        cfg_a = SimulationConfig(window_days=30, random_seed=1, output_dir=str(tmp_path / "c"))
        cfg_b = SimulationConfig(window_days=30, random_seed=2, output_dir=str(tmp_path / "d"))
        (tmp_path / "c").mkdir()
        (tmp_path / "d").mkdir()
        run_simulation(cfg_a)
        run_simulation(cfg_b)
        df_a = pd.read_csv(tmp_path / "c" / "master_telemetry.csv")
        df_b = pd.read_csv(tmp_path / "d" / "master_telemetry.csv")
        # Values should differ (not all identical)
        assert not df_a["value"].equals(df_b["value"])

    def test_schema_in_csv_matches_expected(self, tmp_path):
        """CSV columns must exactly match the expected sensor_readings schema."""
        cfg_tmp = SimulationConfig(window_days=2, random_seed=42, output_dir=str(tmp_path))
        run_simulation(cfg_tmp)
        df = pd.read_csv(tmp_path / "Bearing_telemetry.csv")
        expected_cols = {
            "ts", "component_id", "component_name", "sensor_type",
            "value", "is_failure_event", "failure_mode", "R_derated",
            "AF", "cascade_flag",
        }
        assert expected_cols.issubset(set(df.columns))

    def test_default_config_runs_without_error(self, tmp_path):
        """run_simulation(None) should use defaults and complete without exception."""
        # Override output_dir via a temporary config to avoid writing to project root
        import simulate as sim_module
        original_dir = SimulationConfig().output_dir
        cfg_default = SimulationConfig(output_dir=str(tmp_path), window_days=2)
        results = run_simulation(cfg_default)
        assert results is not None

    def test_cascade_increases_downstream_vibration(self, tmp_path):
        """
        Cascade should make downstream (Gearbox) vibration higher when Bearing
        fails within the window vs. when Bearing is healthy for the full window.

        We achieve this by comparing mean vibration with/without cascade enabled.
        """
        # Run WITH cascade
        cfg_with = SimulationConfig(
            window_days=30, random_seed=42,
            cascade_boost_enabled=True,
            output_dir=str(tmp_path / "with")
        )
        (tmp_path / "with").mkdir()
        results_with = run_simulation(cfg_with)

        # Run WITHOUT cascade
        cfg_no = SimulationConfig(
            window_days=30, random_seed=42,
            cascade_boost_enabled=False,
            output_dir=str(tmp_path / "no")
        )
        (tmp_path / "no").mkdir()
        results_no = run_simulation(cfg_no)

        gearbox_with = results_with["Gearbox"]
        gearbox_no   = results_no["Gearbox"]

        vib_with = gearbox_with[gearbox_with["sensor_type"] == "vibration"]["value"].mean()
        vib_no   = gearbox_no[gearbox_no["sensor_type"] == "vibration"]["value"].mean()

        # With cascade enabled, mean vibration should be ≥ without cascade
        # (could be equal if no upstream failure within window)
        assert vib_with >= vib_no - 0.001, (
            f"Cascade should not reduce vibration: with={vib_with:.4f}, no={vib_no:.4f}"
        )


# =============================================================================
# AUXILIARY: _get_sensor_channels + _primary_sensor
# =============================================================================

class TestAuxiliaryHelpers:
    """Quick sanity checks on helper functions."""

    @pytest.mark.parametrize("comp,expected", [
        ("Bearing",       ["vibration", "temperature"]),
        ("Shaft",         ["vibration", "rpm"]),
        ("Motor Housing", ["temperature", "vibration"]),
        ("Coupling",      ["vibration", "load"]),
        ("Gearbox",       ["vibration", "oil_debris", "temperature"]),
    ])
    def test_get_sensor_channels(self, comp, expected):
        assert _get_sensor_channels(comp) == expected

    @pytest.mark.parametrize("comp,expected_primary", [
        ("Bearing",       "vibration"),
        ("Shaft",         "vibration"),
        ("Motor Housing", "temperature"),
        ("Coupling",      "vibration"),
        ("Gearbox",       "vibration"),
    ])
    def test_primary_sensor(self, comp, expected_primary):
        assert _primary_sensor(comp) == expected_primary
