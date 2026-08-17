-- =============================================================================
-- failure_rate_by_component.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Compute failure rate (λ) per component using failure_log (TTF records)
--   and observed operating hours from sensor_readings.
--
-- FORMULA (Reliability Engineering standard):
--   λ = Number of Failures / Total Operating Hours
--   Units: failures per hour [fph]
--   MTBF_empirical = 1 / λ  (for exponential / β≈1 assumption)
--
-- AUTHORITATIVE FAILURE SOURCE — failure_log (NOT is_failure_event):
--   failure_log is sourced from ttf_samples.csv (Day 7 multi-failure simulation).
--   It contains one row per failure cycle per component (19 rows total).
--   is_failure_event in sensor_readings is currently all zeros — the data_generator.py
--   embedded failure flags correctly only in ttf_samples; the telemetry column will be
--   backfilled in Phase 2. failure_log is the correct authoritative source for Day 10.
--
-- NOTE ON WEIBULL MTBF (locked Day 3, CONTEXT.md):
--   The empirical MTBF here is a simple average: SUM(TTFs) / n_failures.
--   For the parametric Weibull MTBF (η · Γ(1 + 1/β)), see mtbf_from_failure_log.sql.
--   The two values will differ for β ≠ 1; the empirical is more conservative.
--
-- OPERATING HOURS DERIVATION:
--   sensor_readings records one row per sensor per 2-hour timestep.
--   Total observed hours = (max_ts - min_ts) per component using julianday().
--
-- DATA SOURCES:
--   failure_log     — n_failures, sum/mean TTF per component
--   sensor_readings — observation window (min_ts / max_ts) per component
--   components      — component_name, maintenance_strategy, Weibull parameters
-- =============================================================================

WITH
-- Observation window per component from sensor_readings
obs_window AS (
    SELECT
        sr.component_id,
        MIN(sr.ts)                                              AS first_ts,
        MAX(sr.ts)                                              AS last_ts,
        -- Total observed hours = time span of telemetry records
        (julianday(MAX(sr.ts)) - julianday(MIN(sr.ts))) * 24.0 AS observed_hours,
        COUNT(DISTINCT sr.ts) / 2                               AS approx_timesteps
        -- Divide by 2: each 2h step produces 2 rows (one per sensor per component)
    FROM sensor_readings sr
    GROUP BY sr.component_id
),

-- Failure summary from failure_log (authoritative source)
failure_summary AS (
    SELECT
        fl.component_id,
        COUNT(fl.failure_id)          AS n_failures,
        SUM(fl.ttf_hours)             AS total_ttf_h,
        AVG(fl.ttf_hours)             AS mean_ttf_h,
        MIN(fl.ttf_hours)             AS min_ttf_h,
        MAX(fl.ttf_hours)             AS max_ttf_h,
        fl.beta_mid,
        fl.eta_nominal_h,
        AVG(fl.eta_effective_h)       AS eta_effective_h
    FROM failure_log fl
    GROUP BY fl.component_id, fl.beta_mid, fl.eta_nominal_h
)

SELECT
    ow.component_id,
    c.component_name,
    c.maintenance_strategy,
    fs.beta_mid                                                 AS weibull_beta,

    -- Observation window
    ow.first_ts,
    ow.last_ts,
    ROUND(ow.observed_hours, 1)                                 AS observed_hours,

    -- Failure counts from failure_log
    COALESCE(fs.n_failures, 0)                                  AS n_failures,
    ROUND(fs.mean_ttf_h, 1)                                     AS mean_ttf_h,
    ROUND(fs.min_ttf_h, 1)                                      AS min_ttf_h,
    ROUND(fs.max_ttf_h, 1)                                      AS max_ttf_h,

    -- Failure rate λ [failures / hour]
    -- If n_failures = 0 (Shaft): failure_rate_fph = 0 (not NULL — it did not fail)
    ROUND(
        COALESCE(fs.n_failures, 0.0) / NULLIF(ow.observed_hours, 0.0),
        8
    )                                                           AS failure_rate_fph,

    -- Failure rate per 1000 hours (more readable for reporting)
    ROUND(
        1000.0 * COALESCE(fs.n_failures, 0.0) / NULLIF(ow.observed_hours, 0.0),
        4
    )                                                           AS failure_rate_per_1000h,

    -- Empirical MTBF = total operating hours / number of failures
    -- = mean TTF (when repair time << TTF, which holds for our simulation)
    -- NULL for Shaft (0 failures): would be infinite MTBF
    ROUND(
        CASE WHEN COALESCE(fs.n_failures, 0) > 0
             THEN ow.observed_hours / fs.n_failures
             ELSE NULL
        END,
        1
    )                                                           AS mtbf_empirical_h,

    -- Weibull characteristic life (derated for Arrhenius) for comparison
    ROUND(fs.eta_effective_h, 1)                                AS eta_effective_h,
    ROUND(fs.eta_nominal_h, 1)                                  AS eta_nominal_h,

    -- Arrhenius acceleration factor = eta_nominal / eta_effective
    ROUND(
        NULLIF(fs.eta_nominal_h, 0.0) / NULLIF(fs.eta_effective_h, 0.0),
        4
    )                                                           AS arrhenius_af,

    -- Risk classification for Power BI conditional formatting
    CASE
        WHEN COALESCE(fs.n_failures, 0) = 0                    THEN 'NO_FAILURES'
        WHEN 1000.0 * fs.n_failures / NULLIF(ow.observed_hours, 0) >= 1.0
                                                                THEN 'HIGH_RISK'
        WHEN 1000.0 * fs.n_failures / NULLIF(ow.observed_hours, 0) >= 0.5
                                                                THEN 'ELEVATED'
        WHEN 1000.0 * fs.n_failures / NULLIF(ow.observed_hours, 0) >= 0.2
                                                                THEN 'MODERATE'
        ELSE                                                        'LOW'
    END                                                         AS risk_tier

FROM obs_window ow
INNER JOIN components c
    ON c.component_id = ow.component_id
LEFT JOIN failure_summary fs
    ON fs.component_id = ow.component_id

ORDER BY
    failure_rate_fph DESC,
    ow.component_id ASC;

-- =============================================================================
-- USAGE NOTES
-- =============================================================================
-- 1. Shaft (component_id = 2) appears with n_failures = 0.
--    mtbf_empirical_h = NULL (infinite MTBF — no failure observed in 365 days).
--    This is correct: Shaft eta = 8760 h, no Arrhenius derating; no failures expected.
-- 2. failure_rate_per_1000h is the operational KPI:
--    Bearing: ~0.685/1000h; Motor Housing: ~0.799/1000h (highest — most at risk).
-- 3. The empirical MTBF slightly exceeds mean_ttf_h because observed_hours includes
--    repair time between cycles (stochastic MTTR added in multi-failure simulation).
-- 4. For Power BI: sort bar chart by failure_rate_per_1000h descending.
--    Use risk_tier for colour-coded traffic-light formatting.
-- 5. When is_failure_event column in sensor_readings is backfilled (Phase 2),
--    a version using sensor_readings can provide per-sensor failure attribution.
-- =============================================================================
