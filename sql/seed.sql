-- =============================================================================
-- seed.sql — Manufacturing & Industrial Analytics FYP
-- =============================================================================
-- PURPOSE:
--   Populate the `components` and `sensors` tables with the five canonical
--   pipeline components and their associated sensor metadata.
--
-- DATA SOURCES FOR VALUES:
--   - Component Weibull parameters: locked Day 1, CONTEXT.md
--     β range, η (characteristic life) from COMPONENT_WEIBULL_PARAMS in reliability.py
--   - Activation energies (Ea): Day 1 Arrhenius table, CONTEXT.md
--   - ISO vibration thresholds: ISO 10816-3 (Zone C / Zone D boundaries)
--     iso_alarm_threshold  = 4.5 mm/s  (Zone B→C boundary)
--     iso_danger_threshold = 7.1 mm/s  (Zone C→D boundary)
--   - Temperature thresholds: IEC 60085 insulation class limits (Motor Housing)
--     and lubrication degradation temperatures (Bearing, Gearbox)
--   - RPM thresholds: nameplate-equivalent rated values for the simulated plant
--   - Sample rates: 1 Hz default; vibration sensors use higher rates in practice
--     but 1 Hz is the simulation rate for this project
--
-- EXECUTION ORDER:
--   Run schema.sql first (creates tables).
--   Then run this file (seed.sql) to populate master data.
--   Then run simulation scripts (python/simulate.py) for time-series data.
--
-- SQLITE COMPATIBILITY:
--   Uses explicit component_id values. SQLite will honour these even on
--   INTEGER PRIMARY KEY columns (autoincrement is triggered only on NULL inserts).
--   Re-runs are safe: INSERT OR IGNORE prevents duplicate key errors.
--
-- SQL SERVER COMPATIBILITY:
--   Replace INSERT OR IGNORE with MERGE ... WHEN NOT MATCHED or
--   SET IDENTITY_INSERT components ON before these statements.
-- =============================================================================

-- Enable FK enforcement in SQLite (no-op in SQL Server)
PRAGMA foreign_keys = ON;

-- =============================================================================
-- SECTION 1: components table
-- =============================================================================
-- Pipeline:  Bearing(1) → Shaft(2) → Motor Housing(3) → Coupling(4) → Gearbox(5)
--
-- Weibull parameters (reliability.py COMPONENT_WEIBULL_PARAMS):
--   beta_min / beta_max : the Day 1 locked β range
--   beta_mid (computed) : (beta_min + beta_max) / 2  — used as default until Phase 2 MLE
--   eta_hours           : characteristic life η (hours) — placeholder for Phase 2 calibration
--
-- Activation energies (Arrhenius, Day 1):
--   Bearing:       0.80 eV  lubricant breakdown
--   Motor Housing: 1.00 eV  winding insulation degradation (Class B/F)
--   Gearbox:       0.70 eV  oil oxidation
--   Coupling:      0.60 eV  elastomer thermal ageing
--   Shaft:         NULL     fatigue-dominant; Arrhenius does not apply
-- =============================================================================

INSERT OR IGNORE INTO components (
    component_id,
    component_name,
    position_in_chain,
    failure_mode,
    weibull_beta_min,
    weibull_beta_max,
    weibull_beta_mid,
    weibull_eta_hours,
    activation_energy_ev,
    maintenance_strategy
) VALUES

-- ── Component 1: Bearing ─────────────────────────────────────────────────────
-- Failure mode: Rolling-element fatigue (sub-surface crack initiation) and
--               lubricant breakdown (surface adhesive wear).
-- β ∈ [2.5, 3.5]: Strong wear-out regime — justifies time-based PM intervals.
-- η = 4380 h ≈ 6 months continuous at rated load — aligned with industry
--   deep-groove ball bearing L10 life estimates at moderate radial load.
-- Ea = 0.80 eV: Lubricant viscosity breakdown activates at moderate temperatures;
--   lower Ea than insulation because it is not purely thermal (mechanical shear also).
(
    1,                              -- component_id
    'Bearing',                      -- component_name
    1,                              -- position_in_chain (most upstream)
    'Rolling-element fatigue; lubricant breakdown under load and temperature',
    2.5,                            -- weibull_beta_min  (β lower bound)
    3.5,                            -- weibull_beta_max  (β upper bound)
    3.0,                            -- weibull_beta_mid  (2.5+3.5)/2 = 3.0
    4380.0,                         -- weibull_eta_hours (η ≈ 6 months)
    0.65,                           -- activation_energy_ev (Ea = 0.65 eV)
    'PM'                            -- maintenance_strategy (Preventive Maintenance)
),

-- ── Component 2: Shaft ───────────────────────────────────────────────────────
-- Failure mode: Fatigue cracking from cyclic torsional stress and rotational
--               imbalance-induced bending moments.
-- β ∈ [1.5, 2.0]: Moderate wear-out; fatigue failures accumulate with cycles
--   but are less sharply concentrated than rolling-contact fatigue.
-- η = 8760 h ≈ 1 year: Shafts are robust; main failure driver is imbalance
--   buildup, not intrinsic material fatigue at normal load levels.
-- Ea = NULL: Fatigue crack growth is mechanically driven (stress intensity factor).
--   Temperature has second-order effect only. Arrhenius model does not apply.
(
    2,
    'Shaft',
    2,
    'Fatigue cracking from torsional stress and rotational imbalance',
    1.5,                            -- weibull_beta_min
    2.0,                            -- weibull_beta_max
    1.75,                           -- weibull_beta_mid  (1.5+2.0)/2 = 1.75
    8760.0,                         -- weibull_eta_hours (η ≈ 1 year)
    NULL,                           -- activation_energy_ev — NULL: Arrhenius excluded
    'CBM'                           -- Condition-Based Maintenance (vibration monitoring)
),

-- ── Component 3: Motor Housing ───────────────────────────────────────────────
-- Failure mode: Winding insulation degradation — Class F (155 °C rated) or
--               Class B (130 °C rated) thermal ageing per IEC 60085.
-- β ∈ [1.8, 2.5]: Moderate-to-strong wear-out; thermal cumulative damage.
-- η = 6570 h ≈ 9 months: Motor insulation life strongly temperature-dependent;
--   η here represents nominal life at the rated winding temperature.
-- Ea = 1.00 eV: Polymer insulation degradation has high Ea — consistent with
--   IEC 60216 / Montsinger rule (≈2× life reduction per +10 °C above rated temp).
(
    3,
    'Motor Housing',
    3,
    'Winding insulation thermal ageing; Class B/F degradation per IEC 60085',
    1.8,
    2.5,
    2.15,                           -- weibull_beta_mid  (1.8+2.5)/2 = 2.15
    8000.0,                         -- weibull_eta_hours (η ≈ 9 months)
    0.85,                           -- activation_energy_ev (Ea = 0.85 eV — insulation)
    'CBM'
),

-- ── Component 4: Coupling ────────────────────────────────────────────────────
-- Failure mode: Elastomer (rubber/polyurethane spider) ageing from combined
--               thermal cycling, ozone exposure, and cyclic compression fatigue.
-- β ∈ [1.5, 2.0]: Similar to Shaft — moderate wear-out; elastomers age
--   gradually until a tearing threshold is crossed.
-- η = 5256 h ≈ 7 months: Standard flexible coupling replacement interval at
--   moderate torque and ambient temperature.
-- Ea = 0.60 eV: Lower Ea reflects that elastomer ageing is partly driven by
--   mechanical fatigue cycles, not purely thermal activation.
(
    4,
    'Coupling',
    4,
    'Elastomer ageing from thermal cycling and misalignment-induced fatigue',
    1.5,
    2.0,
    1.75,                           -- weibull_beta_mid  (1.5+2.0)/2 = 1.75
    5256.0,                         -- weibull_eta_hours (η ≈ 7 months)
    0.60,                           -- activation_energy_ev (Ea = 0.60 eV)
    'CBM'
),

-- ── Component 5: Gearbox ─────────────────────────────────────────────────────
-- Failure mode: Gear-tooth pitting (contact fatigue on pitch line) and
--               oil oxidation (lubricant breakdown under load and temperature).
-- β ∈ [2.0, 3.0]: Strong wear-out — gear-tooth pitting concentrates at end-of-life.
-- η = 4380 h ≈ 6 months: Same as Bearing; gearboxes in continuous duty are
--   serviced on similar intervals (oil change + inspection).
-- Ea = 0.70 eV: Oil oxidation Arrhenius Ea from MIL-HDBK-217F estimates for
--   mineral and PAO gear lubricants.
(
    5,
    'Gearbox',
    5,                              -- position_in_chain (most downstream)
    'Gear-tooth pitting (contact fatigue) and oil oxidation under sustained load',
    2.0,
    3.0,
    2.5,                            -- weibull_beta_mid  (2.0+3.0)/2 = 2.5
    4380.0,                         -- weibull_eta_hours (η ≈ 6 months)
    0.70,                           -- activation_energy_ev (Ea = 0.70 eV — oil oxidation)
    'PM_CBM'                        -- Combined Preventive + Condition-Based
);


-- =============================================================================
-- SECTION 2: sensors table
-- =============================================================================
-- Each component has one PRIMARY sensor (its diagnostic signal) plus secondary
-- sensors where applicable.  All ISO 10816-3 thresholds are set on vibration
-- sensors; temperature and other sensor types use component-specific limits.
--
-- ISO 10816-3 vibration zone thresholds (locked Day 1):
--   Zone C onset (alarm):  4.5 mm/s RMS  → iso_alarm_threshold
--   Zone D onset (danger): 7.1 mm/s RMS  → iso_danger_threshold
--
-- Temperature thresholds (component-specific):
--   Motor Housing: alarm = 130 °C (Class B rated limit), danger = 155 °C (Class F)
--   Bearing:       alarm =  80 °C (grease degradation onset), danger = 100 °C
--   Gearbox:       alarm =  90 °C (oil degradation), danger = 110 °C
--
-- sensor_id assignment (manual, consistent with component_id × 10 scheme):
--   10x: Bearing sensors (11 = vibration, 12 = temperature)
--   20x: Shaft sensors   (21 = vibration 1× harmonic, 22 = RPM)
--   30x: Motor Housing   (31 = temperature, 32 = vibration)
--   40x: Coupling        (41 = vibration 2× harmonic, 42 = load)
--   50x: Gearbox         (51 = vibration envelope, 52 = oil debris, 53 = temperature)
-- =============================================================================

INSERT OR IGNORE INTO sensors (
    sensor_id,
    component_id,
    sensor_type,
    unit_of_measure,
    iso_alarm_threshold,
    iso_danger_threshold,
    sample_rate_hz,
    is_active
) VALUES

-- ──────────────────────────────────────────────────────────────────────────────
-- Bearing Sensors (component_id = 1)
-- ──────────────────────────────────────────────────────────────────────────────

-- Sensor 11: Bearing Vibration RMS (PRIMARY — ISO 10816-3 classification)
-- Dominant diagnostic for rolling-element fatigue and lubrication state.
-- Alarm at 4.5 mm/s (Zone C onset), Danger at 7.1 mm/s (Zone D onset).
(
    11, 1,
    'vibration', 'mm/s_rms',
    4.5,                    -- iso_alarm_threshold  (Zone C onset — ISO 10816-3)
    7.1,                    -- iso_danger_threshold (Zone D onset — ISO 10816-3)
    1.0,                    -- sample_rate_hz
    1                       -- is_active
),

-- Sensor 12: Bearing Temperature
-- Lubricant degradation accelerates above 80 °C; seizure risk above 100 °C.
-- Thresholds based on typical anti-friction bearing grease (NLGI Grade 2).
(
    12, 1,
    'temperature', 'degC',
    80.0,                   -- iso_alarm_threshold  (grease degradation onset)
    100.0,                  -- iso_danger_threshold (thermal seizure risk)
    1.0,
    1
),

-- ──────────────────────────────────────────────────────────────────────────────
-- Shaft Sensors (component_id = 2)
-- ──────────────────────────────────────────────────────────────────────────────

-- Sensor 21: Shaft Vibration — 1× Running Speed Harmonic
-- Imbalance manifests as a dominant 1× harmonic peak in the frequency spectrum.
-- Same ISO 10816-3 amplitude thresholds apply.
(
    21, 2,
    'vibration', 'mm/s_rms',
    4.5,
    7.1,
    1.0,
    1
),

-- Sensor 22: Shaft RPM
-- RPM is both a process variable and a Performance KPI input.
-- No ISO alarm threshold for RPM (machine-specific rated speed).
-- Thresholds set to NULL — anomaly detection uses ±10% of rated_rpm instead.
(
    22, 2,
    'rpm', 'rpm',
    NULL,                   -- no universal ISO threshold for RPM
    NULL,
    1.0,
    1
),

-- ──────────────────────────────────────────────────────────────────────────────
-- Motor Housing Sensors (component_id = 3)
-- ──────────────────────────────────────────────────────────────────────────────

-- Sensor 31: Motor Housing Temperature (PRIMARY — winding insulation monitoring)
-- IEC 60085 Class B insulation: rated 130 °C, danger above 155 °C (Class F limit).
-- Sustained operation above alarm threshold triggers corrective CBM inspection.
(
    31, 3,
    'temperature', 'degC',
    130.0,                  -- iso_alarm_threshold  (IEC 60085 Class B limit)
    155.0,                  -- iso_danger_threshold (IEC 60085 Class F limit)
    1.0,
    1
),

-- Sensor 32: Motor Housing Vibration (SECONDARY — structure-borne noise)
-- Stator eccentricity and looseness manifest as elevated overall vibration.
(
    32, 3,
    'vibration', 'mm/s_rms',
    4.5,
    7.1,
    1.0,
    1
),

-- ──────────────────────────────────────────────────────────────────────────────
-- Coupling Sensors (component_id = 4)
-- ──────────────────────────────────────────────────────────────────────────────

-- Sensor 41: Coupling Vibration — 2× Running Speed Harmonic (PRIMARY)
-- Angular and parallel misalignment produce a characteristic 2× harmonic.
-- This is the standard CBM trigger for flexible coupling condition assessment.
(
    41, 4,
    'vibration', 'mm/s_rms',
    4.5,
    7.1,
    1.0,
    1
),

-- Sensor 42: Coupling Load (% of rated)
-- Elastomer loading above design capacity accelerates fatigue ageing.
-- Alert at 90% rated load; danger at 100% (rated design maximum).
(
    42, 4,
    'load', 'pct',
    90.0,                   -- iso_alarm_threshold  (90% rated load)
    100.0,                  -- iso_danger_threshold (100% rated — elastic limit)
    1.0,
    1
),

-- ──────────────────────────────────────────────────────────────────────────────
-- Gearbox Sensors (component_id = 5)
-- ──────────────────────────────────────────────────────────────────────────────

-- Sensor 51: Gearbox Vibration — Envelope Analysis (PRIMARY)
-- Gear-tooth pitting raises sidebands and tooth-mesh frequency harmonics.
-- Envelope (demodulated) vibration is more sensitive to pitting than raw RMS.
(
    51, 5,
    'vibration', 'mm/s_rms',
    4.5,
    7.1,
    1.0,
    1
),

-- Sensor 52: Gearbox Oil Debris Count (per mL, 15-minute rolling window)
-- Wear particle count from online oil debris monitor (ODM).
-- Threshold based on ISO 4406 / NAS 1638 cleanliness target for gear oils.
-- Alarm at 50 particles/mL, Danger at 200 particles/mL.
(
    52, 5,
    'oil_debris', 'count',
    50.0,                   -- iso_alarm_threshold  (50 particles/mL — early wear)
    200.0,                  -- iso_danger_threshold (200 particles/mL — severe wear)
    1.0,
    1
),

-- Sensor 53: Gearbox Sump Temperature
-- Gear oil oxidation accelerates above 90 °C; flash point risk above 110 °C.
(
    53, 5,
    'temperature', 'degC',
    90.0,                   -- iso_alarm_threshold  (oil oxidation onset)
    110.0,                  -- iso_danger_threshold (oil flash-point risk zone)
    1.0,
    1
);


-- =============================================================================
-- VERIFICATION QUERIES (run manually after seed to confirm row counts)
-- =============================================================================
--
-- Expected output:
--   SELECT COUNT(*) FROM components;  → 5
--   SELECT COUNT(*) FROM sensors;     → 9
--
-- Sanity check — all sensor thresholds valid (alarm < danger):
--   SELECT sensor_id, iso_alarm_threshold, iso_danger_threshold
--   FROM sensors
--   WHERE iso_alarm_threshold IS NOT NULL
--     AND iso_danger_threshold IS NOT NULL
--     AND iso_alarm_threshold >= iso_danger_threshold;
--   → 0 rows (all good)
--
-- Component chain order check:
--   SELECT component_id, component_name, position_in_chain
--   FROM components
--   ORDER BY position_in_chain;
--   → 1 Bearing, 2 Shaft, 3 Motor Housing, 4 Coupling, 5 Gearbox
--
-- =============================================================================
-- END OF seed.sql
-- =============================================================================
