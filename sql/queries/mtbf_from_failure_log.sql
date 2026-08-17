-- =============================================================================
-- mtbf_from_failure_log.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Compute MTBF (Mean Time Between Failures) directly from the failure_log table
--   (sourced from ttf_samples.csv, Day 7 multi-failure simulation).
--
-- TWO MTBF ESTIMATES (for viva comparison):
--
--   1. EMPIRICAL MTBF (from failure_log):
--      MTBF_empirical = SUM(ttf_hours) / COUNT(failure_id)
--      = sum of all observed TTFs divided by total failure count
--      This is the maximum likelihood estimate for the exponential distribution.
--
--   2. WEIBULL MTBF (parametric formula, locked Day 3, CONTEXT.md):
--      MTBF_weibull = η · Γ(1 + 1/β)
--      For β = 3.0 (Bearing): MTBF = η · Γ(1.333) = η · 0.8930
--      For β = 2.15 (Motor Housing): MTBF = η · Γ(1.465) = η · 0.8859
--      For β = 2.5 (Gearbox): MTBF = η · Γ(1.4) = η · 0.8873
--      For β = 1.75 (Coupling): MTBF = η · Γ(1.571) = η · 0.9002
--      NOTE: SQLite has no Gamma function. The Weibull MTBF pre-computed values
--            are stored here as constants for reference. The Python reliability.py
--            module (mtbf_weibull()) performs the full calculation.
--
-- eta_effective_h (Day 10 — locked):
--   = eta_nominal_h / AF  where AF = exp[(Ea/k) · (1/T_use − 1/T_stress)]
--   This is the Arrhenius-derated characteristic life used for the actual TTF draws.
--   Expected MTBF from the derated distribution:
--     MTBF_derated = eta_effective_h · Γ(1 + 1/β)
--
-- DATA SOURCE:
--   failure_log — populated by etl.load_failure_log() from ttf_samples.csv
--   components  — component_name, weibull_beta_mid, weibull_eta_hours
-- =============================================================================

WITH
-- Aggregate TTF statistics per component from failure_log
ttf_stats AS (
    SELECT
        fl.component_id,
        COUNT(fl.failure_id)                AS n_failures,
        SUM(fl.ttf_hours)                   AS total_ttf_h,
        AVG(fl.ttf_hours)                   AS mean_ttf_h,
        MIN(fl.ttf_hours)                   AS min_ttf_h,
        MAX(fl.ttf_hours)                   AS max_ttf_h,

        -- Empirical MTBF = arithmetic mean of TTF samples
        -- MLE estimator for exponential model; biased for Weibull β ≠ 1
        AVG(fl.ttf_hours)                   AS mtbf_empirical_h,

        -- Standard deviation of TTF (for CoV calculation)
        -- SQLite: no STDDEV() — computed via Var(X) = E[X²] - E[X]²
        SQRT(
            AVG(fl.ttf_hours * fl.ttf_hours) - AVG(fl.ttf_hours) * AVG(fl.ttf_hours)
        )                                    AS stddev_ttf_h,

        -- eta_effective_h for MTBF_derated calculation
        -- All cycles for a given component share the same eta_effective_h
        AVG(fl.eta_effective_h)             AS eta_effective_h,
        fl.eta_nominal_h,
        fl.beta_mid,
        AVG(fl.gamma_factor)                AS gamma_factor,
        fl.ea_ev,
        fl.strategy
    FROM failure_log fl
    GROUP BY
        fl.component_id,
        fl.eta_nominal_h,
        fl.beta_mid,
        fl.ea_ev,
        fl.strategy
)

SELECT
    ts.component_id,
    c.component_name,
    ts.strategy,
    ts.beta_mid,
    ts.ea_ev,

    -- Failure count
    ts.n_failures,

    -- Empirical MTBF from TTF samples [hours]
    ROUND(ts.mtbf_empirical_h, 1)               AS mtbf_empirical_h,

    -- Standard deviation and Coefficient of Variation (CoV = σ/μ)
    -- CoV interpretation for Weibull:
    --   β = 1 (exponential) → CoV ≈ 1.00
    --   β > 1 (wear-out)    → CoV < 1.00 (less variation; more predictable)
    ROUND(ts.stddev_ttf_h, 1)                   AS stddev_ttf_h,
    ROUND(
        ts.stddev_ttf_h / NULLIF(ts.mtbf_empirical_h, 0.0),
        4
    )                                            AS cov_ttf,

    -- Arrhenius derating
    ROUND(ts.eta_nominal_h, 1)                  AS eta_nominal_h,
    ROUND(ts.eta_effective_h, 1)                AS eta_effective_h,
    ROUND(
        ts.eta_nominal_h / NULLIF(ts.eta_effective_h, 0.0),
        4
    )                                            AS arrhenius_af,

    -- Weibull MTBF (parametric): eta_effective_h × Gamma(1 + 1/beta_mid)
    ROUND(
        ts.eta_effective_h * ts.gamma_factor,
        1
    )                                            AS mtbf_weibull_derated_h,

    -- Nominal (non-derated) Weibull MTBF for comparison
    ROUND(
        ts.eta_nominal_h * ts.gamma_factor,
        1
    )                                            AS mtbf_weibull_nominal_h,

    -- Ratio: how far the empirical MTBF deviates from Weibull parametric
    -- Values close to 1.0 validate the Weibull model against simulation
    ROUND(
        ts.mtbf_empirical_h / NULLIF(
            ts.eta_effective_h * ts.gamma_factor,
            0.0
        ),
        4
    )                                            AS empirical_vs_weibull_ratio

FROM ttf_stats ts
INNER JOIN components c
    ON c.component_id = ts.component_id

ORDER BY
    ts.component_id ASC;

-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- 1. Shaft (component_id = 2) will NOT appear in this query output — it has
--    zero failures in the 365-day simulation window (eta = 8760 h, no Arrhenius).
--    That is correct behaviour (see Day 7 CONTEXT.md entry).
-- 2. The empirical_vs_weibull_ratio should be close to 1.0 for well-calibrated
--    Weibull simulations. Values far from 1.0 indicate insufficient sample size
--    (Bearing n=6, Motor Housing n=7 — expected with limited cycles in 365 days).
-- 3. For Power BI: use mtbf_empirical_h for the maintenance scheduling KPI card.
--    Use mtbf_weibull_derated_h for the Weibull theory comparison tooltip.
-- 4. cov_ttf < 1 for all wear-out components (β > 1) is a reliability model
--    validation check — it confirms wear-out failure mode is correctly captured.
-- =============================================================================
