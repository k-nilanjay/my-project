# Viva Preparation Guide — All 77 Q&As
## Manufacturing & Industrial Analytics FYP
### Reliability & Maintenance Intelligence System

**Project:** Manufacturing Analytics — Reliability & Maintenance Intelligence
**Student:** Hement Kitukale
**Date Compiled:** 2026-08-15 (Day 35 — Final Consolidation)
**Coverage:** Q1-Q77 across all 35 project days

> This document consolidates every viva Q&A recorded throughout the 35-day build.
> Questions are grouped by theme. Each answer is the definitive locked response.
> Read this document end-to-end before your viva session.

---

## Part 1 — Foundations & Methodology (Q1-Q13)

---

**Q1: Why did you not use Machine Learning for predictive maintenance? Wouldn't LSTM or a Random Forest give better results?**

**A:** Three reasons justify descriptive/diagnostic analytics over ML:
1. Data volume constraint: LSTMs require tens of thousands of labelled failure events. Our simulated dataset covers 35 days of 5-component telemetry. A model trained on this would overfit immediately and produce statistically meaningless RUL predictions.
2. Explainability mandate: In industrial maintenance, a maintenance engineer cannot act on a "black box" prediction. Our system flags anomalies with a specific sensor reading, a specific threshold, and a specific physical reason (e.g., "Bearing vibration RMS exceeded 7.5 mm/s for 3 consecutive hours — indicative of race-way spalling per ISO 10816-3"). Weibull analysis and control charts give full traceability. LSTM does not.
3. Standards compliance: Industrial reliability systems operate under ISO 13381 (Condition Monitoring), ISO 55000 (Asset Management), and IEC 60812 (FMEA). Descriptive/statistical methods map directly to these standards. ML approaches require separate validation frameworks outside our FYP scope.

---

**Q2: Is Condition-Based Monitoring just a simpler version of Predictive Maintenance? Why differentiate?**

**A:** CBM and PdM differ in their output, not just complexity:
- CBM answers: "Is the component degraded right now?" — a threshold-crossing decision at the present moment.
- PdM answers: "When will the component fail if current degradation continues?" — requires a model of the degradation trajectory.
We implement CBM with trend analysis (regression lines on rolling KPIs), which gives a visual approximation of degradation trajectory in Power BI. Full PdM with confidence intervals on RUL would require a physics-based degradation model or a trained ML model — both are explicitly scoped as future work.

---

**Q3: Why did you choose the Weibull distribution over simpler exponential failure modelling?**

**A:** The exponential model assumes a constant failure rate (beta=1), valid only for the "useful life" phase of the bathtub curve. Our components — particularly Bearing (fatigue wear-out, beta=2.5-3.5) and Gearbox (tooth pitting, beta=2.0-3.0) — have increasing failure rates with age. Using exponential modelling would underestimate failure probability at high hours-in-service, leading to dangerous under-maintenance. Weibull's shape parameter beta captures the actual failure physics. It is the industry standard for mechanical component reliability (MIL-HDBK-189C, ReliaSoft industry practice), and scipy.stats.weibull_min provides a direct Python implementation.

---

**Q4: How do you validate your system without a real industrial dataset?**

**A:** Simulation fidelity is the validation strategy, structured in three layers:
1. Physics-grounded generation: The Python simulator uses Weibull failure distributions, the Arrhenius temperature model, and ISO 10816-3 vibration severity classes to constrain all synthetic sensor values to physically plausible ranges.
2. Cross-validation with published case studies: KPI threshold decisions are benchmarked against published industrial standards (SKF bearing handbooks, ISO standards). Every threshold can be cited to a published source.
3. Internal consistency checks: SQL schema enforces referential integrity; Python pipeline enforces unit and range validation; Power BI dashboards include data-quality KPI tiles that flag implausible readings.

---

**Q5: Why do you use the minimum operator for system Availability and Performance rather than the average?**

**A:** Our pipeline is a series reliability block: [Bearing]->[Shaft]->[Motor Housing]->[Coupling]->[Gearbox]. The system can only produce output if ALL components are available simultaneously. If any one component is down, the entire pipeline stops. Therefore:
- System Availability = min(A_i) — the component with worst availability dictates system uptime (series block principle, R_sys = product of R_i).
- System Performance = min(P_i) — Goldratt's Theory of Constraints: system throughput equals throughput of the bottleneck.
Using an average would mask the bottleneck and give a falsely optimistic system OEE figure.

---

**Q6: Why is Quality aggregated as a product rather than a minimum?**

**A:** Quality defects accumulate independently through the pipeline. If Bearing produces 2% defects and Gearbox produces 3% defects, the final output quality is approximately (1-0.02) x (1-0.03) = 0.9506 — a multiplicative degradation, not a min(). The formula Q_sys = product(Q_i) is the independent probability multiplication rule: P(all pass) = product(P_i(pass)). The min() rule applies only where the weakest single component's constraint completely determines the system output. For quality, every component contributes its own defect rate to the final yield.

---

**Q7: Your kpi.py has a compute_performance_rpm fallback. Doesn't using RPM as a Performance proxy introduce significant inaccuracy?**

**A:** Yes — RPM-based Performance (P_rpm = actual_rpm / rated_rpm) is an approximation. It assumes linear relationship between rotational speed and throughput, valid only when: (a) no product changeover has occurred and (b) the machine is not operating in reduced-speed mode due to quality constraints. The fallback is clearly documented with a performance_method flag column that tags every Power BI row as 'unit_count' (primary) or 'rpm_proxy' (fallback). This is a data lineage column — Power BI can suppress "precise" percentage formatting when the fallback is in use, signalling to the analyst that the figure is an estimate.

---

**Q8: What is the fundamental difference between diagnostic analytics and prognostic analytics in the context of PHM?**

**A:** In the PHM (Prognostics & Health Management) spectrum:
- Descriptive analytics — "What happened?" (historical KPI summaries, failure counts, OEE tables)
- Diagnostic analytics — "Why did it happen?" (root-cause attribution, anomaly flagging, correlation analysis)
- Prognostic analytics — "When will it happen again?" (Remaining Useful Life estimation, degradation trajectory modelling)
Our FYP delivers Descriptive + Diagnostic. Prognostic capability would require a physics-based degradation model or a data-driven model (LSTM, Bayesian filter) trained on historical failure trajectories. We explicitly scope this out and instead use Weibull MTBF as a stationary reliability estimate.

---

**Q9: Why is the Weibull MTBF calculation in reliability.py not sufficient for prognostics?**

**A:** MTBF is a population-level statistic — it is the mean time to failure averaged over many components of the same type under nominal conditions. It does not track the current degradation state of a specific component. A prognostic model requires: (1) a health state estimate (e.g., current damage fraction, crack depth), (2) a degradation rate model (how fast the health state is declining), (3) a failure threshold (what health state value constitutes failure), (4) confidence intervals on the predicted time-to-threshold crossing. Weibull MTBF provides none of these — it is a maintenance scheduling reference, not a real-time RUL estimator.

---

**Q10: How would you validate consistency between empirical and Weibull MTBF, and what if they diverge?**

**A:** Consistency check: compute the ratio (empirical_MTBF / Weibull_MTBF). Acceptable range for sample sizes n=4 to 7: ratio between 0.80 and 1.25. Our results: Bearing 0.736, Motor Housing 0.809, Gearbox 1.138, Coupling 1.090 — all within acceptable bounds except Bearing (borderline). If they diverge significantly (ratio outside 0.70-1.40): (1) Check model specification — is beta correct? (2) Check sample size — with n<5, empirical MTBF has too-wide confidence intervals. (3) Check censoring — if failures were not recorded, empirical MTBF is an overestimate. Action: use empirical value for maintenance scheduling (observed reality) and flag the divergence as a calibration issue for Phase 2.

---

**Q11: How does your SQL implementation identify the bottleneck component when using MIN(Performance)?**

**A:** In oee_system_series.sql, three CTEs identify bottlenecks independently for each OEE factor. The availability bottleneck: SELECT component_name WHERE shift_availability = MIN(shift_availability) within the shift GROUP. Performance bottleneck: SELECT component_name WHERE performance_ratio = MIN(performance_ratio). A CASE WHEN chain produces bottleneck_component_name and bottleneck_factor columns in the final SELECT. If two components tie at the same minimum, the CASE WHEN returns the first match (lowest component_id in seed.sql order). Viva answer: "In the event of a tie, the upstream component is reported as the bottleneck, consistent with the cascade failure model."

---

**Q12: How do the seven wastes of Lean Manufacturing map onto the OEE framework?**

**A:** OEE quantifies Lean's value-stream efficiency numerically. The mapping:
| Waste | OEE Pillar | Example in our system |
|---|---|---|
| Defects | Quality | Gearbox torque variation producing out-of-spec output |
| Waiting | Availability | Idle time during upstream component failure (cascade downtime) |
| Motion/Overproduction | Performance | Running at excess speed to compensate for downstream slow component |
| Extra-processing (8th waste) | Quality | Rework units = Loss 6 |
The Six Big Losses from TPM/OEE are a precise reformulation of Lean waste categories specifically for equipment: Losses 1-2 are Availability losses, Losses 3-4 are Performance losses, Losses 5-6 are Quality losses.

---

**Q13: Your seed.sql uses ISO 10816-3 Zone C (4.5 mm/s) as the alarm threshold for all vibration sensors. Would you apply the same threshold to the Shaft's 1x harmonic as to the Bearing's overall RMS?**

**A:** Technically, no — ISO 10816-3 broadband RMS thresholds are designed for overall vibration, not for individual frequency components. The 1x harmonic (shaft rotation frequency) is typically assessed using ISO 7919 (shaft vibration) or by comparing to baseline signatures. However, for this FYP, we use ISO 10816-3 as a consistent, standardised proxy because: (a) we do not have frequency-resolved (FFT) spectral data — our vibration readings are broadband RMS, (b) a single standard simplifies the threshold enforcement DDL and Power BI conditional formatting, (c) the alarm threshold is a precursor for CBM triggering, not a definitive fault diagnosis. In a real system, Shaft would have its own baseline-derived envelope alarm threshold.

---

## Part 2 — Simulation & Data Generation (Q14-Q16)

---

**Q14: You use the inverse-CDF method to sample Weibull failure times. Why not just use numpy.random.weibull?**

**A:** numpy.random.weibull(beta) generates samples from a Weibull distribution with scale=1. To use our calibrated eta (characteristic life in hours), we would need to multiply: TTF = eta * numpy.random.weibull(beta). The inverse-CDF method (TTF = eta * (-ln(U))^(1/beta), U ~ Uniform(0,1)) is mathematically identical but is: (1) More transparent — the formula is directly auditable against the Weibull quantile function definition. (2) More flexible — U can be seeded or constrained to specific probability ranges for scenario testing. (3) Easier to document for viva: the formula derives directly from inverting R(t) = exp(-(t/eta)^beta).

---

**Q15: How does the Arrhenius model change the Weibull distribution shape vs the scale?**

**A:** The Arrhenius model affects ONLY the scale parameter eta, not the shape parameter beta.
- eta_stressed = eta_nominal / AF, where AF = exp[(Ea/k) * (1/T_use - 1/T_stress)]
- Higher temperature (T_stress > T_use) gives AF > 1, which reduces eta_stressed.
- A smaller eta means the Weibull CDF shifts left (failures occur sooner), but the shape (beta-governed curvature) is unchanged.
- Physical interpretation: Arrhenius accelerates the rate of the underlying failure mechanism but does not change the mechanism's statistical nature. This is the core assumption of the Arrhenius-Weibull model used in accelerated life testing (JEDEC standards, MIL-HDBK-217).

---

**Q16: Your topology.py uses a pure-Python adjacency list rather than a library like networkx. Justify this.**

**A:** Five reasons: (1) Graph size: 5 nodes, 4 directed edges, linear chain — trivially representable as a Python dict. (2) Zero additional dependencies: networkx adds ~20 MB to the environment for no analytical benefit on a 5-node graph. (3) O(1) lookup: get_downstream_components(name) is a dict.get() call — constant time. (4) DAG property is guaranteed physically: The pipeline's physical constraints guarantee no cycles. No cycle-detection algorithm is needed. (5) Viva transparency: Any examiner can read PIPELINE_GRAPH = {"Bearing": ["Shaft"], ...} and immediately understand the dependency structure without knowledge of networkx API.


---

## Part 3 — Schema, ETL & Python Pipeline (Q17-Q25)

---

**Q17: What is Third Normal Form and can you give an example of a 3NF violation you deliberately avoided?**

**A:** 3NF: Every non-key attribute must depend on the whole primary key, nothing but the key, and nothing but the primary key. A 3NF violation (transitive dependency): if downtime_events stored component_name derived from component_id, and component_name determined iso_alarm_threshold, then iso_alarm_threshold would transitively depend on component_id via component_name — a 3NF violation. We avoided this by storing component-specific thresholds only in the sensors and components tables, not in downtime_events. The component_name column in downtime_events is a deliberate denormalization (documented in erd.md as a reporting convenience), not a transitive dependency — it carries no functionally dependent attributes.

---

**Q18: Why do you use surrogate integer primary keys rather than natural keys in your schema?**

**A:** Four reasons: (1) Immutability: component_name could change; component_id (integer PK) never changes. (2) Join performance: INTEGER equality joins are faster than VARCHAR equality joins (no collation comparison). (3) DAX compatibility: Power BI active relationships require numeric or text keys; INTEGER keys avoid ambiguity in SELECTEDVALUE() patterns. (4) FK enforcement: SQLite and SQL Server handle INTEGER FK constraints with better index support than TEXT FK constraints.

---

**Q19: How does your schema enforce the cascade failure rule at the database layer?**

**A:** Two DDL constraints in downtime_events: (1) CHECK ((downtime_category != 'cascade_upstream') OR (root_cause_component_id IS NOT NULL)) — forces every cascade_upstream row to name the causing component. A cascade event with no attribution cannot be inserted. (2) CHECK (root_cause_component_id != component_id) — prevents a component from being its own root cause. These constraints implement the Day 2 cascade tagging rule at the database layer, not just at application layer. A bug in etl.py that fails to set root_cause_component_id will raise a SQLite constraint violation — the error is caught at the storage boundary, not silently propagated into analytics.

---

**Q20: What is an ETL pipeline, and what are its three stages in the context of your project?**

**A:**
- Extract: Read raw CSV files from data/processed/ (multi_failure_telemetry.csv, ttf_samples.csv) generated by python/data_generator.py.
- Transform: Validate column types, compute derived columns (is_anomaly, iso_zone, health_score), enforce range constraints, handle nulls, cast datatypes to match SQL schema.
- Load: INSERT OR IGNORE rows into SQLite tables (sensor_readings, failure_log, components, sensors) via Python sqlite3. The INSERT OR IGNORE pattern makes the ETL idempotent.

---

**Q21: Why do you use INSERT OR IGNORE instead of a plain INSERT in your ETL pipeline?**

**A:** INSERT OR IGNORE skips any row whose primary key already exists in the target table. This provides idempotency — the ETL can be re-run multiple times without creating duplicate rows (provided the source data and PKs are unchanged). In development, the schema can be preserved while re-running data generation. For production: if the DB is not cleared between runs and new data uses different PKs, INSERT OR IGNORE would still insert the new rows correctly. The trade-off: if source data changes but the PK is the same, INSERT OR IGNORE silently skips the update — acceptable for our simulation where source data is regenerated from scratch each run.

---

**Q22: How does your ETL pipeline compute is_anomaly and iso_zone, and what are they used for?**

**A:** is_anomaly: Computed in Python during Transform phase. For each row, if sensor_value > sensor.iso_alarm threshold (joined from sensors table), is_anomaly = 1; else 0. Stored as INTEGER in SQLite (not BOOLEAN, which SQLite does not natively support). iso_zone: Derived from ISO 10816-3 zone boundaries: A (0-2.3), B (2.3-4.5), C (4.5-7.1), D (>7.1) for vibration sensors. For temperature/other sensors, zone thresholds use component-specific alarm/danger values from the sensors table. Usage: is_anomaly drives the Power BI E-01 [Total Active Alerts] measure. iso_zone drives KPI card conditional formatting and the Violation Rate Matrix (Panel C on Page 3). Both are pre-computed at ETL time (not in DAX) to reduce Power BI semantic layer complexity.

---

**Q23: Why does your MTBF differ between the empirical estimate and the Weibull parametric formula?**

**A:** The empirical MTBF (mean of TTF samples) and the Weibull parametric MTBF (eta * Gamma(1 + 1/beta)) are different estimators. The empirical MTBF is the MLE estimate for the exponential distribution. When beta > 1 (wear-out), the arithmetic mean converges to the true Weibull mean only with large sample sizes. With n=6 (Bearing) or n=7 (Motor Housing), the empirical mean has wide confidence intervals. The Weibull parametric MTBF accounts for distribution shape via the Gamma function — theoretically more accurate for small samples when the model is correctly specified. The ratio (empirical/Weibull) is the sanity check: 0.80-1.25 acceptable for n=4-7. Our results: Bearing 0.736, Motor Housing 0.809, Gearbox 1.138, Coupling 1.090.

---

**Q24: What is Coefficient of Variation (CoV) and what does it tell you about your failure data?**

**A:** CoV = sigma/mu (standard deviation / mean TTF). Dimensionless dispersion measure. For exponential (beta=1): CoV=1.0 exactly. For Weibull with beta>1 (wear-out): CoV<1.0 — failures are more predictable. All our components have beta>1 (Bearing beta=3.0, Motor Housing beta=2.15, Gearbox beta=2.5, Coupling beta=1.75). Results: Bearing 0.20, Motor Housing 0.29, Coupling 0.20, Gearbox 0.16. All <1.0, confirming wear-out behaviour and validating the Weibull model choice. Low CoV means maintenance intervals can be predicted with reasonable confidence — the basis for PM scheduling.

---

**Q25: Why do Gearbox and Coupling vibration sensors show 91% anomaly rates? Does that mean 91% of the time the plant was in an alarm state?**

**A:** No — this is a consequence of cascade failure simulation design. The multi-failure simulation injects cascade vibration boosts starting from each upstream failure event. In a 365-day window, Bearing and Motor Housing fail multiple times (6 and 7 cycles). Each failure triggers elevated vibration signals on all downstream sensors from that point forward. The cumulative effect is that Gearbox and Coupling vibration channels spend a large fraction of total observation hours above ISO alarm threshold. The cascade_anomalies column shows 100% of Gearbox vibration anomalies are cascade-caused (upstream propagation), not intrinsic to the Gearbox itself. This is an important diagnostic finding: apparent Gearbox alarm escalation is a lagging indicator of upstream events, preventing misdiagnosed Gearbox replacement.

---

## Part 4 — SQL Analytics (Q26-Q31)

---

**Q26: What is the difference between ROW_NUMBER(), RANK(), and NTILE() in SQL?**

**A:**
- ROW_NUMBER(): Assigns unique sequential integers (1, 2, 3...) to every row within the partition. Ties broken arbitrarily by ORDER BY direction. Result: always unique row numbers.
- RANK(): Like ROW_NUMBER but tied values receive the same rank. Next rank skips tied positions (e.g., 1, 2, 2, 4). Also called "skip rank" or "competition rank".
- DENSE_RANK(): Like RANK() but no gaps — tied values receive same rank and next rank is consecutive (e.g., 1, 2, 2, 3).
- NTILE(n): Divides partition into n equal-sized buckets, assigns bucket number 1-n to each row. Used for quartile/decile classification. Unequal partition sizes: SQL adds extra rows to lower-numbered buckets.
In our Day 11 SQL: ROW_NUMBER() for unique shift ranking within component; NTILE(4) for quartile labelling of OEE scores; RANK() DENSE for failure-frequency ranking by component.

---

**Q27: What does a 7-shift rolling average of downtime tell you that a raw downtime value does not?**

**A:** The raw downtime value for a single shift is highly volatile — a single unplanned failure can spike it to 480 minutes (full shift). A 7-shift rolling average (~2-3 calendar days of 3-shift operation) smooths out individual spike noise and reveals the trend: is downtime systematically increasing (indicator of developing degradation), systematically decreasing (indicator that a PM action was effective), or stationary (system is at steady-state)? The rolling average also enables control chart analysis — we can establish a baseline (mean + 2 sigma bounds) and flag when the rolling average itself exceeds control limits, indicating a structural change in the process rather than an isolated event.

---

**Q28: Why does Motor Housing have the lowest OEE despite not being the most frequent failure component?**

**A:** Motor Housing's low OEE is driven by Performance loss, not Availability. Its primary failure mode is thermal winding insulation degradation — it does not fail completely (sudden stop), but instead causes a sustained thermal derating: the motor runs at 60-75% of rated speed to prevent overheating. This reduces Performance continuously across many shifts even when Availability=100%. Bearing, by contrast, has fewer operating hours at reduced speed (it runs at full speed until it fails suddenly). The OEE formula A x P x Q means that a sustained Performance hit of 25-40% has a larger cumulative impact than infrequent but complete Availability failures. This is why the OEE waterfall chart shows Motor Housing with a dominant Loss 4 (Reduced Speed) bar.

---

**Q29: What is the difference between a CTE and a subquery, and when did you use each?**

**A:** CTE (WITH clause): Named temporary result set defined before the main SELECT. Readable, reusable within the same query, and helps the optimiser recognise the computation as a unit. Best for: multi-step transformations, self-referencing (recursive CTEs), and logic referenced more than once. Subquery: Inline SELECT within FROM, WHERE, or SELECT clause. Evaluated once per context reference. Best for: simple one-off filters or existence checks (EXISTS, IN). In our Day 12 composite OEE query (oee_composite.sql): 4 CTEs (downtime_agg, shift_run_time, rpm_avg, oee_factors) because each stage builds on the previous — flattening into subqueries would make the SQL unreadable. In anomaly_rate_by_sensor.sql: correlated subquery in SELECT to count cascade_anomalies, because it is a one-off column derivation.

---

**Q30: In query P7, why did you need a self-join on the components table rather than a simple join?**

**A:** Query P7 traces cascade failure attribution: it needs to display both the component that experienced the downtime (the victim) AND the component that caused it (the root cause, identified by root_cause_component_id). Since both victim and root cause are rows in the same components table, two references to the same table are needed — a self-join (alias c1 for victim, c2 for root cause). A simple join would only resolve the victim's name, leaving root_cause_component_id as a bare integer. The INNER JOIN on c2 = root_cause_component_id (filtered to cascade_upstream rows only) resolves the root cause component name for readable cascade attribution in the report.

---

**Q31: Why does the time-series query (T1) use ROWS BETWEEN 3 PRECEDING AND CURRENT ROW rather than RANGE BETWEEN INTERVAL?**

**A:** SQLite does not support RANGE BETWEEN INTERVAL syntax — it requires ROWS or RANGE with numeric offsets only. More importantly, ROWS BETWEEN counts a fixed number of physical rows, while RANGE BETWEEN counts rows within a value range. In our time-series queries, shifts are not evenly spaced (weekends may have fewer shifts), so RANGE BETWEEN a fixed interval could include varying numbers of rows depending on data density. ROWS BETWEEN 3 PRECEDING AND CURRENT ROW always includes exactly the current row plus the 3 most recent rows — predictable, consistent behaviour regardless of date gaps. For Power BI time-intelligence functions, the DAX layer handles calendar-aware rolling windows; the SQL layer uses row-based windows for simplicity and SQLite compatibility.

---

## Part 5 — EDA & Statistical Analysis (Q32-Q43)

---

**Q32: Why does the pooled value column show extreme right skew (+2.80) when individual sensor types look more normal?**

**A:** Mixing sensor types (vibration in mm/s, temperature in degC, load in %, oil_debris in count/mL) into a single pooled column creates a mixture distribution. Each sensor type has a different mean and standard deviation, and the combined distribution's shape is driven by the heaviest-tailed component. The oil_debris sensor (count/mL, with values ranging 0-300+ during cascade events) contributes extreme right-tail values that inflate the pooled skewness. This is not a data quality issue — it is the expected behaviour of a heterogeneous mixture. The EDA correctly reports this as a caveat in eda_full_report.txt: "Do not use pooled statistics for threshold-setting; use per-sensor-type statistics."

---

**Q33: arrhenius_factor has zero variance and triggered a Shapiro-Wilk "range zero" warning. Is this a bug?**

**A:** Not a bug — it is a deliberate simulation characteristic. In our simulation, arrhenius_factor is computed once per component per day and applied uniformly to all readings in that window. Within a single EDA window, if temperature does not vary, AF is a constant. The Shapiro-Wilk test correctly identifies this as a degenerate distribution (all values identical — range=0). The warning is caught in our EDA code and logged as "Shapiro-Wilk skipped: range=0 (constant variable)". This is correct statistical practice — normality testing is meaningless on a constant.

---

**Q34: Downtime mean (75.7 min) is 3x the median (23.7 min). What is the reporting implication?**

**A:** Mean >> median indicates a right-skewed distribution driven by a few very long downtime events (e.g., Bearing seizure requiring 8+ hour repair). Using the mean as the representative downtime for PM scheduling would lead to over-provisioning of maintenance windows. The median is a better central tendency measure for skewed data — it is robust to extreme repair events. In our MTTR calculations in reliability.py, we report both median and mean with a flag: "Use median for scheduling; use mean for availability calculations (A = MTBF/(MTBF+MTTR), which uses mean MTTR by definition)."

---

**Q35: You computed Pearson and Spearman for every domain. When would you choose one over the other in a real industrial context?**

**A:** Pearson r: Measures linear relationship strength between two continuous variables. Assumes both variables are normally distributed and the relationship is linear. Use when: comparing two sensor readings under steady-state conditions where linear proportionality is expected (e.g., motor current vs. load). Spearman rho: Measures monotonic relationship strength using rank-transformed values. Distribution-free. Use when: data is not normally distributed (oil_debris is right-skewed), or when the relationship is expected to be monotonic but nonlinear (e.g., vibration vs. bearing age follows a nonlinear degradation curve), or when outliers are present (Spearman is outlier-robust; Pearson is not). In our EDA: Pearson for within-shift steady-state sensor pairs; Spearman as a robustness check. Divergence between Pearson r and Spearman rho signals nonlinearity or outlier influence.

---

**Q36: What is the difference between a Pearson correlation matrix and a covariance matrix, and why is the correlation matrix preferred?**

**A:** Covariance matrix: cov(X,Y) = E[(X-mu_X)(Y-mu_Y)]. Values are in the product of X and Y units (e.g., mm/s * degC), making cross-variable comparison impossible. Correlation matrix: corr(X,Y) = cov(X,Y) / (sigma_X * sigma_Y). Dividing by both standard deviations scales the result to [-1, +1], making it dimensionless and comparable across all sensor pairs regardless of unit differences. In our system: vibration (mm/s) x temperature (degC) x oil_debris (count/mL) x load (%) x rpm (rpm) — comparing covariances across these would be meaningless. The correlation matrix is the correct tool for multi-domain sensor relationship analysis.

---

**Q37: Gearbox oil_debris shows r=+0.99 with Gearbox temperature (Pearson) but r=+0.74 with Motor Housing vibration (Spearman). What does this divergence tell you?**

**A:** The Pearson r=+0.99 with Gearbox temperature is expected: oil_debris increases monotonically and near-linearly with oil temperature (Arrhenius-governed oxidation mechanism). The relationship is linear, normally distributed, with no outliers — ideal for Pearson. The Spearman rho=+0.74 with Motor Housing vibration indicates a moderate monotonic but nonlinear relationship. Motor Housing vibration influences Gearbox oil contamination through the cascade mechanism (high Motor Housing vibration → increased load on Coupling → increased gear mesh irregularity → oil contamination), but this is a multi-hop causal chain with nonlinear threshold effects. Pearson r would likely show a lower value (nonlinearity reduces linear correlation). This divergence justifies using ISO zone step-change thresholds rather than a linear regression alert model.

---

**Q38: Why did you choose a 7-day and a 14-day rolling window rather than a 3-day or 30-day?**

**A:** The choice reflects the operational cycle of the simulated system. 7-day window: Aligns with the weekly maintenance cycle (weekend PM windows are common in manufacturing). A 7-day rolling average captures a full work-week of degradation signal and smooths shift-to-shift noise. 14-day window: Doubles the 7-day window to capture slower-moving trends (Motor Housing thermal degradation has a multi-week onset; Gearbox oil oxidation accumulates over 2-3 weeks). Why not 3-day: Too short — a single unplanned failure event would dominate the 3-day average, creating a spike-and-decay artefact that mimics a trend. Why not 30-day: Too long — a Bearing failure (TTF ~180 days) would only begin to appear as a rising 30-day average in its last 3-4 weeks. The 7-day window provides earlier warning.

---

**Q39: Your Plot 1 uses a twin-axis (twinx) layout. What is the risk of a dual y-axis chart, and how did you mitigate it?**

**A:** The main risk of dual y-axis charts is visual deception: by independently scaling the two y-axes, the analyst can make any two series appear correlated or anti-correlated, regardless of the actual relationship. Mitigation in our plots: (1) Both axes are explicitly labelled with units in the same colour as their corresponding series. (2) The left axis is vibration (mm/s RMS), right axis is temperature (degC) — both have ISO-defined thresholds marked as horizontal reference lines. (3) The chart title explicitly states "Vibration (left axis) vs Temperature (right axis) — scales are independent." (4) In the Power BI version, we avoid dual-axis charts entirely for exactly this reason — all KPI trend lines use consistent normalised scales.

---

**Q40: Plot 3 shows stacked downtime categories as an area chart, not a line chart. Justify that choice and describe one weakness.**

**A:** Justification: A stacked area chart visually represents the composition (partition-to-whole relationship) of total downtime. The area between each band represents the contribution of each downtime category. A stacked line chart would require the reader to mentally subtract lower series from upper series to assess individual category magnitudes — cognitively demanding. Weakness: The stacked area chart makes individual category trends difficult to read for lower-stack series. If cascade_upstream increases while idle decreases by the same amount, the total area remains constant and both changes are invisible. A Pareto chart or a faceted small-multiples layout would make individual category trends more readable.

---

**Q41: You built a dedicated synthesis document before writing any Phase 2 or Phase 3 code. Is that not over-engineering for an FYP?**

**A:** The synthesis document is the bridge between Phase 1 (descriptive) and Phase 2 (diagnostic). Without it, Phase 2 code would be written without a clear prioritization of which findings to investigate further. The EDA produced ~45 statistical findings across sensor types, components, and correlations. The synthesis document applies the 80/20 rule: identifies the 3-4 findings with the highest diagnostic value (Motor Housing thermal pattern, Gearbox cascade rate, Bearing vibration-temperature coupling) and explicitly de-scopes the remaining findings. This is standard data science practice (phase-gate analysis). For the FYP, it is evidence of analytical rigour and systematic prioritization — not over-engineering.

---

**Q42: Your EDA reports that first_pass_yield is highly left-skewed (skewness = -5.18, kurtosis = +48.29). How will this affect your Phase 3 Quality dashboard?**

**A:** Left-skew in first_pass_yield means most shifts have high yield (concentrated near 100%), but a small number of shifts have catastrophic yield failures (values close to 0%). For the Power BI Quality dashboard: (1) The mean yield (97.1%) is a misleading summary — it is dragged up by the dominant high-yield mode. (2) Conditional formatting thresholds must account for the heavy left tail: a yield below 90% is several standard deviations from the mean, but the extreme tail extends to near-zero. (3) The most appropriate summary statistic is the P5 (5th percentile) yield, not the mean — "95% of shifts achieve at least X% yield." This is reported in the E-09 DAX measure [P5 Yield]. (4) The kurtosis of +48.29 indicates extreme peakedness — the distribution is driven by a bimodal pattern (normal operation vs. cascade-failure operation), which the waterfall chart decomposition surfaces.

---

**Q43: The Pearson vs Spearman divergence for mean_vibration vs anomaly_rate (0.92 vs 0.76) justifies using ISO zone step-change thresholds. Explain how.**

**A:** Pearson r=0.92 indicates a strong linear relationship on average; Spearman rho=0.76 indicates the rank-order relationship is weaker. When Pearson > Spearman, it typically means a small number of (x,y) pairs with very high x and very high y are inflating the Pearson correlation (leverage points). In our case: extreme vibration values (Zone D > 7.1 mm/s) cause disproportionately high anomaly rates (near 100%), while moderate vibration (Zone B, 2.3-4.5 mm/s) causes near-zero anomaly rates. The relationship has a threshold character — not a linear one. This justifies the ISO zone step-change model: alarm does not increase proportionally with vibration; it crosses a step threshold at Zone C (4.5 mm/s) and another at Zone D (7.1 mm/s). A linear regression model would under-alarm at moderate vibration and over-smooth the danger zone boundary.

---

## Part 6 — Graph Analysis & Criticality (Q44-Q49)

---

**Q44: Motor Housing ranks first in Structural Risk Score but only second in Cascade Reach. How can a node with fewer downstream targets be more dangerous than Bearing?**

**A:** Cascade Reach is only one component of the Structural Risk Score (SRS). The SRS formula is: SRS = 0.50 * cascade_reach_normalised + 0.30 * edge_weight_normalised + 0.20 * failure_frequency_normalised. Motor Housing outranks Bearing in the composite SRS because: (1) Its edge weight to Coupling is the highest in the graph (Pearson r=+0.94, vs Bearing->Shaft r=+0.79). High edge weight means Motor Housing degradation strongly predicts Coupling degradation. (2) Its failure_frequency (7 cycles in 365 days) is the highest of all components. (3) Bearing's cascade_reach=4 (can affect Shaft, Motor Housing, Coupling, Gearbox), but its edge_weight to Shaft is lower (r=+0.79) and its failure_frequency is lower (6 cycles). The weighting (50/30/20) deliberately down-weights structural reach relative to actual operational impact.

---

**Q45: You used Pearson r values from Day 15 as edge weights. These are correlation coefficients between sensor readings — not failure propagation probabilities. Is that a valid encoding?**

**A:** It is a pragmatic approximation, not a theoretically exact encoding. True failure propagation probabilities would require conditional failure frequency data: P(B fails | A fails within 48h). We do not have enough failure events (n=19 total in failure_log) to estimate this conditional probability reliably. Pearson r between sensor readings is used as a proxy for "influence strength" — a high correlation between Bearing vibration and Shaft vibration (r=+0.87) indicates that Bearing's mechanical state strongly co-varies with Shaft's state, which is a reasonable proxy for cascade influence. The limitation (noted in SRS documentation): correlation does not imply causation, and the edge weight does not account for temporal lag. This is explicitly documented as a model simplification.

---

**Q46: The SRS formula uses fixed weights (0.50, 0.30, 0.20). How were those chosen and how sensitive is the ranking to those weights?**

**A:** The weights were chosen based on domain reasoning: cascade reach is the primary driver of system-level risk (50%), sensor correlation edge weight captures influence propagation strength (30%), and raw failure frequency captures historical reliability (20%). Sensitivity analysis: we tested three alternative weight schemes (equal 33/33/33; reach-dominant 70/20/10; frequency-dominant 20/20/60). In all schemes, Motor Housing ranked 1st or 2nd and Bearing ranked 1st or 2nd. The top-2 ranking is robust to weight variation. Coupling and Shaft swap positions between 3rd and 4th depending on the weight scheme — this is noted in the SRS documentation as a boundary case where the two-component distinction is not statistically significant given the model's precision.

---

**Q47: Motor Housing was ranked first in Structural Risk Score (Day 18) but fell to Rank 3 in the Composite Criticality Index. Does this mean the Day 18 analysis was wrong?**

**A:** No — SRS and CCI answer different questions. SRS is a graph-structural metric: "which component's failure has the broadest systemic impact based on dependency topology and sensor correlations?" CCI is an operational metric: "which component is currently causing the most actual maintenance burden, considering OEE impact, threshold breach frequency, and downtime?" Motor Housing fell in CCI ranking because its threshold breach rate is lower (it operates mostly in Zone B for temperature, not Zone C/D) and its OEE Availability contribution is acceptable (it rarely causes complete stoppages — it causes speed reduction, not shutdown). Bearing ranks higher in CCI because it combines high threshold breach frequency with higher unplanned downtime contribution. The two metrics are complementary: SRS guides where to invest in redundancy; CCI guides where to prioritise maintenance budget now.

---

**Q48: Why use max-normalisation instead of min-max scaling?**

**A:** Max-normalisation (x / max(x)) preserves proportionality: a component with twice the cascade reach of another will have exactly twice the normalised score. Min-max scaling (x - min(x)) / (max(x) - min(x)) compresses all values to [0,1] but destroys proportionality: the lowest component always scores 0 regardless of its absolute value. In our CCI, we want the scores to reflect relative magnitudes, not just relative ranks. If Bearing has 3x the anomaly rate of Gearbox, the normalised anomaly rate should reflect that 3x factor. Min-max would compress this to a difference that depends on the range, potentially hiding a factor-of-3 disparity. Additionally, max-normalisation is simpler to explain in a viva: "Bearing's normalised cascade reach = Bearing_reach / 4 = 1.0 (maximum possible reach in a 5-node series chain)."

---

**Q49: The threshold breach rates are derived from simulated data. How does that affect the validity of the CCI?**

**A:** The CCI's validity rests on the validity of the simulation. Three mitigations: (1) Physics-grounded thresholds: ISO 10816-3 vibration zones and IEC 60085 temperature class limits are real-world standards. Breach rates against these thresholds are meaningful even for simulated data. (2) Relative ranking is robust: Even if absolute breach rates differ from real-world values, the relative ranking reflects the actual physical failure mode hierarchy. (3) Explicit disclaimer: The CCI is documented as "calibrated to simulation parameters; real-world calibration requires historical failure data from the specific plant." This is the standard practice in model-based reliability analysis (ISO 31000 risk management principle: all risk models require real-world validation before operational use).


---

## Part 7 — Power BI Data Model (Q50-Q64)

---

**Q50: Walk me through how the pipeline stages connect to each other.**

**A:** Stage 1 (data_generator.py) generates multi_failure_telemetry.csv and ttf_samples.csv using Weibull TTF sampling, Arrhenius temperature modulation, and cascade failure injection. Stage 2 (ingest.py, which wraps etl.py) reads these CSVs, performs Transform (is_anomaly, iso_zone, health_score derivation, type casting) and Loads them into data/manufacturing.db via INSERT OR IGNORE. Stage 3a-3c (eda_summary_stats.py, eda_trends.py, eda_correlation.py) reads from data/manufacturing.db and produces CSV summaries, trend plots, and correlation matrices to data/processed/. Power BI Desktop then connects to data/manufacturing.db (the SQLite source) and the data/processed/ CSVs (for pre-computed scores) to build the semantic model.

---

**Q51: Why does the EDA run after SQL ingestion rather than reading the CSV directly?**

**A:** Three reasons: (1) Schema enforcement: The SQL database enforces all CHECK constraints, FK relationships, and NOT NULL rules on ingestion. Running EDA against the raw CSV would bypass these constraints and produce statistics on potentially invalid data. (2) Derived columns: is_anomaly, iso_zone, and health_score are computed during ETL and stored in the DB. The EDA needs these derived columns — they are not in the raw CSV. (3) Single source of truth: Running EDA against the DB ensures the statistical summaries are consistent with what Power BI will see. If a CSV were re-generated between EDA and Power BI refresh, the two layers would diverge.

---

**Q52: What happens if Stage 1 (data generation) is re-run? Is it safe to re-run the pipeline multiple times?**

**A:** Stage 1 re-run generates new random samples (different U ~ Uniform(0,1) draws), producing a new multi_failure_telemetry.csv with different (but Weibull-consistent) sensor values and failure times. If Stage 2 is then re-run: INSERT OR IGNORE skips all rows with matching PKs (reading_id). If the CSV regeneration produced new PKs (auto-incremented by data_generator.py from where the previous run left off), the new rows ARE inserted. If PKs are reset from 1 (fresh start), the old rows are skipped and the DB retains stale data. Safe practice: if re-running Stage 1 from scratch (new simulation window), also DROP and RECREATE the DB tables before Stage 2. The --skip-generation and --skip-ingestion flags allow re-running only specific stages.

---

**Q53: How does run_pipeline.py know the pipeline succeeded?**

**A:** Three independent success signals are checked: (1) subprocess.run() return code: each stage must exit with returncode=0. (2) File-level artefact checks in validate_pipeline_outputs(): checks file existence, CSV row counts (>= threshold), and DB file size (>= 3 MB). (3) Database row-count verification in _verify_db_tables(): opens SQLite directly via sqlite3 and issues SELECT COUNT(*) queries — sensor_readings >= 47,000 and failure_log >= 15. All three must pass for the pipeline to report overall success. A stage that exits 0 but produces no output files or insufficient DB rows is caught by checks 2 and 3.

---

**Q54: The criticality_index_plot.png and criticality_scores.csv are in data/processed/, not docs/. Why not copy them to docs/ for the viva?**

**A:** data/processed/ is the designated output directory for all Python pipeline artefacts — it is the "data layer" output consumed by Power BI. docs/ is reserved for documentation artefacts: ERD, test logs, this viva guide, architecture diagrams. Mixing pipeline output files (Python-generated) into docs/ would blur the architecture boundary between data layer and documentation layer. For the viva, the criticality_scores.csv is presented directly from data/processed/ in Power BI (dim_criticality table is loaded from this path) and the plot is presented from the pipeline log. If an examiner wants to see the plot standalone, it can be opened directly from its path — no docs/ copy is needed.

---

**Q55: What is a Star Schema and why did you choose it for Power BI?**

**A:** A star schema organises data into one central fact table (containing measurable events: sensor readings, one row per reading_id) surrounded by dimension tables (containing descriptive attributes: dim_components, dim_sensors, dim_calendar). Reasons for choosing star schema for Power BI: (1) DAX optimisation: Power BI's DAX engine (VertiPaq columnar store) is optimised for star schemas. Relationship traversal between fact and dimension tables uses VertiPaq join operations that run in-memory at high speed. (2) Simple relationships: All relationships are 1-to-many from dimension to fact, with a single active relationship per dimension. (3) Report filter performance: Slicers on dimension columns filter the fact table directly through the active relationship — no complex DAX FILTER() expressions required.

---

**Q56: What is the difference between a Fact table and a Dimension table?**

**A:** Fact table (fact_sensor_readings): Contains measurable, quantitative events. One row per measurement instance. Has many rows (47,957 in our system). Contains foreign keys to all related dimensions. Contains the numerical measures used in aggregations (sensor_value, is_anomaly, health_score). Dimension table (dim_components, dim_sensors, dim_calendar): Contains descriptive, categorical attributes. One row per entity (5 components, 11 sensors, ~365 calendar dates). Contains the primary keys that fact tables reference. Used for filtering, grouping, and labelling in reports. Key rule: facts are aggregated; dimensions are filtered. "Total anomalies by component" = aggregate(fact) grouped by filter(dim_components).

---

**Q57: You have 9 active and 2 inactive relationships. What is an inactive relationship and when do you use it?**

**A:** An inactive relationship is a defined relationship between two tables that Power BI does not automatically apply for cross-table filtering. It is activated on-demand using USERELATIONSHIP() inside a DAX measure. In our model: the relationship between dim_components[component_id] and fact_sensor_readings[root_cause_component_id] is inactive (R-10). It is the same table pair as the active R-01 relationship (on sr.component_id), but targets a different column. If both were active, Power BI would error with "ambiguous relationship." The inactive R-10 is activated in D-07 [Root Cause Downtime Min] to calculate downtime attributable to root-cause events — using a different column than the default active relationship.

---

**Q58: Why is the relationship between dim_production_shifts and dim_production_counts a 1:1 with Both cross-filter directions?**

**A:** By design, there is exactly one production_counts row per (component_id, shift_id) pair (enforced by UNIQUE constraint in schema.sql). This makes the relationship structurally 1:1. Both cross-filter directions are enabled because: when you filter dim_production_shifts (e.g., select "DAY shift"), you want fact_sensor_readings to filter (to show only sensor readings during day shifts), AND when you filter dim_production_counts (e.g., select shifts with quality < 95%), you want to see which production shifts those correspond to. Both tables need to filter each other — bidirectional filtering is appropriate for 1:1 relationships. Note: for 1-to-many relationships, bidirectional filtering can cause DAX ambiguity and is avoided.

---

**Q59: How does dim_criticality connect to the operational data? What does that relationship enable?**

**A:** dim_criticality contains the Composite Criticality Index (CCI) scores and Structural Risk Scores (SRS) computed by python/composite_criticality.py. It joins to dim_components on component_id. This relationship enables: (1) filtering operational data (sensor readings, downtime events) by criticality tier (CRITICAL/HIGH/MEDIUM/LOW); (2) the radar chart on Page 2 (Panel B) shows CCI score alongside MTBF for the selected component — requiring both dim_criticality and the MTBF measure to be computable for the same component_id filter context; (3) the Page 3 scatter chart (Panel B) uses CCI as the X-axis, requiring dim_criticality to participate in the cross-filter from the Component slicer.

---

**Q60: What is cardinality in a data model and why does it matter?**

**A:** Cardinality describes the uniqueness of values in a relationship column. One-to-many (1:*): One row in the dimension matches many rows in the fact table. Example: one component_id in dim_components matches 47,957/5 ~= 9,591 rows in fact_sensor_readings. This is the standard star schema relationship. Many-to-many (M:*): Multiple rows in both tables can match each other. Power BI supports M:M relationships using bridge tables, but they complicate DAX filter context and are avoided in our model. One-to-one (1:1): Each row in one table matches exactly one row in the other. Used for dim_production_shifts <-> dim_production_counts. Cardinality matters because it determines how filters propagate. A 1:* relationship propagates filters from "one" side (dimension) to "many" side (fact) automatically.

---

**Q61: Walk me through how OEE Availability would be calculated in DAX using your model.**

**A:** Step by step: (1) CALCULATE(SUM(fact_downtime_events[duration_min]), fact_downtime_events[downtime_category] <> "planned_maintenance") — total unplanned downtime minutes in current filter context. (2) CALCULATE(SUM(dim_production_shifts[planned_duration_min])) — total planned production time in current filter context. (3) [OEE Availability] = DIVIDE(([Planned Duration] - [Unplanned Downtime]), [Planned Duration]) — protected by DIVIDE() which returns BLANK() on zero denominator. The current filter context is determined by the slicers (Date Range, Component) and any active visual-level filters. CALCULATE() creates a new filter context by applying the category filter to the existing context. DIVIDE() is safer than the "/" operator because it handles division-by-zero gracefully.

---

**Q62: What is DAX filter context and how does it differ from row context?**

**A:** Filter context: The set of filters currently active on the data model, established by slicers, visual-level filters, report-level filters, and CALCULATE() expressions. Filter context operates on tables — it restricts which rows are visible to an aggregation. Example: selecting "Bearing" in the Component slicer sets a filter context WHERE dim_components[component_name] = "Bearing". Row context: The context of a single row during a calculated column or EARLIER()/SUMMARIZE() iteration. Row context applies to the current row being evaluated, not to a filter on the whole table. Example: in a calculated column [is_above_alarm] = IF([sensor_value] > RELATED(dim_sensors[iso_alarm]), 1, 0), the row context provides [sensor_value] and RELATED() follows the active relationship to get the alarm threshold for that row's sensor. Confusing the two is a common DAX error: using a measure (which operates in filter context) inside an iterator (which needs row context) requires CALCULATE() to convert filter context correctly.

---

**Q63: Why is health_score implemented as a Power Query M derived column rather than a DAX calculated column?**

**A:** health_score = R(t) = exp(-(t/eta)^beta) uses component-specific beta and eta parameters that must be looked up from dim_components. In DAX: a calculated column on fact_sensor_readings would need RELATED(dim_components[eta]) and RELATED(dim_components[weibull_beta_mid]) — these RELATED() lookups work but run at table refresh time on every row (47,957 rows). The M query pre-computes health_score during data load (before the VertiPaq model is built), storing the result as a static column. This means: (1) no RELATED() overhead at report render time, (2) health_score values are available for use in other M steps or as a Power Query filter, (3) the Weibull formula is computed once at load, not re-evaluated on every DAX query. The trade-off: if eta or beta changes, the report must be refreshed (not just the DAX model recalculated).

---

**Q64: Explain why [OEE Composite] returns BLANK() rather than 0 when production count data is missing for a shift.**

**A:** OEE = A x P x Q. If production_counts data is missing for a shift, Q (Quality = good_units/total_units) is BLANK (DIVIDE returns BLANK on zero denominator or no matching rows). BLANK() propagates through multiplication: BLANK * A * P = BLANK, not 0. This is intentional: 0 would mean OEE = 0%, which implies the shift produced no good output — a false assertion. BLANK() means "no data available for this shift" — Power BI shows it as an empty cell, and it is excluded from averages (AVERAGE() ignores BLANK). The design principle: distinguish "measured zero" from "unmeasured." A 0% OEE is a real result; BLANK() means the measurement does not exist.

---

## Part 8 — Power BI Visuals & UX (Q65-Q74)

---

**Q65: Why do you use a waterfall chart for the Six Big Losses decomposition rather than a Pareto chart?**

**A:** A waterfall chart shows additive decomposition from a starting value (100% planned time) to a final value (OEE%). Each waterfall bar represents a loss category reducing the total. The visual communicates "OEE = 100% minus these losses" — a partition-to-whole story that directly matches the mathematical structure: OEE = 1 - Loss1 - Loss2 - ... - Loss6. A Pareto chart ranks individual loss frequencies or magnitudes but does not show the cumulative effect on OEE — it would answer "which loss is largest?" not "how do losses stack to produce this OEE?". For maintenance prioritization, the waterfall gives engineers the OEE decomposition they need to understand which loss category to attack first.

---

**Q66: Why do you use a line chart rather than a bar chart for MTBF trends?**

**A:** Line charts are appropriate for continuous time-series data where the value at any point in time is interpretable (interpolation between data points is meaningful). MTBF is computed per time window and represents a continuously changing reliability characteristic — a line chart conveys the temporal trend (is MTBF increasing or decreasing over time?). A bar chart would imply discrete, independent categories — appropriate for comparing MTBF across different components side by side (a grouped bar) or for showing MTBF in specific time buckets without implying continuity. The Page 2 Panel A chart uses a line for MTBF and MTTR on the same axis to show the widening or narrowing gap (MTBF increasing while MTTR is stable = reliability improving).

---

**Q67: Why use SELECTEDVALUE() for CCI Score in the radar chart rather than AVERAGE()?**

**A:** The CCI is a component-level static score — each component has exactly one CCI value in dim_criticality. There is no meaningful aggregation (average/sum) of CCI across components. SELECTEDVALUE(dim_criticality[cci_score]) returns the single CCI value for the currently selected component (via the drill-through filter from Page 1). If multiple components were somehow selected, SELECTEDVALUE() returns BLANK — a safe failure mode that signals the radar chart needs a single-component context. AVERAGE() would return a numeric value even for multi-component selections, potentially misleading the analyst into thinking they are seeing a meaningful aggregate when they are seeing a nonsensical blend of different components' CCI scores.

---

**Q68: Explain the semantic difference between [Root Cause Downtime Min] (D-07) and [Total Downtime Min] (B-02).**

**A:** [Total Downtime Min] (B-02): All downtime minutes for the currently filtered component, regardless of cause. Includes unplanned failures, cascade_upstream events, changeover, and idle time. This is the Total Corrective Time metric from ISO 13306. [Root Cause Downtime Min] (D-07): Downtime minutes where the filtered component is the ROOT CAUSE (not the victim) of a cascade. Uses USERELATIONSHIP() to activate R-10 (the inactive relationship on root_cause_component_id). If Bearing fails and Motor Housing receives a cascade_upstream downtime event, D-07 for Bearing includes Motor Housing's cascade downtime; D-07 for Motor Housing does not include its own cascade_upstream events (those are attributed to Bearing). D-07 drives the Pareto chart ranking — it ranks components by the total systemic damage they cause, not just their own downtime.

---

**Q69: Why are three separate tooltip pages used rather than the default Power BI tooltip?**

**A:** The default Power BI tooltip (auto-generated from the visual's data fields) shows a plain text list of field=value pairs with no formatting control. Custom tooltip pages enable: (1) KPI cards with large fonts, conditional formatting, and branded colours — readable at a glance during a hover. (2) Layout control — our T-1 tooltip shows four KPI cards arranged in a 2x2 grid with specific card sizes. (3) Dark canvas matching — T-2 has a #0D1117 background matching Page 3's dark canvas, preventing jarring colour discontinuity. (4) Multiple measure types — the T-3 Waterfall Loss tooltip shows three percentage-point values (Availability/Performance/Quality loss) that cannot be auto-formatted in a default tooltip. The investment in custom tooltip pages provides systematic, formatted evidence that the dashboard was designed with user experience in mind.

---

**Q70: Why is the Component slicer synced-but-hidden on Page 2 rather than simply absent?**

**A:** Drill-through from Page 1 automatically navigates to Page 2 AND passes the selected component as a filter. Power BI drill-through requires a field in the "Drill through" well of the destination page — we use dim_components[component_id]. When drill-through fires, Power BI sets a filter context on Page 2 for that component_id. If the Component slicer were absent from Page 2, the drill-through filter would still apply (it is a page-level filter, not a slicer filter), but there would be no visual indicator showing which component is currently selected. By syncing the Component slicer (Sync=ON) but hiding it (Visible=OFF), the slicer holds the drill-through filter state invisibly, ensuring all Page 2 DAX measures (D-01 through D-16) resolve SELECTEDVALUE() correctly. A visible slicer on Page 2 would allow the analyst to accidentally change the component filter after drill-through, breaking the drill-through context.

---

**Q71: The Day 22 DAX uses SELECTEDVALUE() for the Radar chart measures. Why does the UX implementation guide specifically warn about the slicer on Page 2?**

**A:** SELECTEDVALUE(dim_components[component_id]) returns a single value only when exactly one component_id is in the current filter context. If the Component slicer on Page 2 were visible and the analyst selected "ALL" or multiple components, SELECTEDVALUE() returns BLANK, making the entire radar chart blank. The UX guide warning: "Do not make the Component slicer on Page 2 visible — users selecting 'ALL' will get blank radar charts and file a bug report." The hidden slicer ensures the filter context always contains exactly one component_id (the one passed by drill-through), guaranteeing SELECTEDVALUE() returns a non-BLANK value.

---

**Q72: Why are all 5 KPI cards placed at Y=0 specifically, rather than distributed across the page?**

**A:** Y=0 is the top edge of the Power BI canvas. Placing all KPI cards in a horizontal strip at Y=0 implements the Z-pattern reading principle: the user's eye enters at the top-left (KPI Card 1), scans right across the five cards, then drops to the main analytical visuals below. This is the standard dashboard layout pattern from Nielsen Norman Group and Stephen Few's "Now You See It." Distributing KPI cards across the page breaks this scanning pattern — the user must hunt for summary metrics between visual elements. The consistent Y=0 strip also enables the "persistent summary bar" pattern: as the user navigates between pages (all three pages use the same card strip layout), the key metrics are always in the same visual location, reducing cognitive load.

---

**Q73: Why is Panel B (horizontal bar) the drill-through trigger for Page 2, rather than Panel A (line chart)?**

**A:** Drill-through in Power BI requires the user to right-click on a specific data point. Line chart data points are small circles that are difficult to right-click precisely — they require hover to highlight and then a careful right-click without moving the cursor. A horizontal bar chart has large, wide bars that are easy to right-click anywhere along their length. This is a UX decision, not a data decision: the same drill-through destination works from any visual on the page. Panel B (Health Score bar chart) was chosen as the primary trigger because: (1) it is the most naturally "clickable" visual, (2) each bar represents exactly one component — the drill-through filter (component_id) is unambiguous, (3) it is placed prominently in the Z-pattern primary reading area (top-left quadrant).

---

**Q74: Why does the Waterfall chart use Percentage Point (PP) losses rather than raw OEE percentage?**

**A:** The waterfall starts at 100% (full planned time) and each bar subtracts the loss for one of the Six Big Losses categories. The final bar shows the resulting OEE%. Each loss is expressed as a Percentage Point (PP) deduction: "Loss 1 (Unplanned Failures) = 8.3 PP" means 8.3% of planned production time was lost to this category. Using raw OEE percentage would require the viewer to mentally compute the subtraction chain (100% - 8.3% - 3.1% - ...). Using PP makes the decomposition additive: sum(Loss PPs) = 100% - OEE%. This matches the mathematical structure of OEE. The PP waterfall is the industry-standard way to communicate loss attribution (TPM/OEE practitioners universally use PP decomposition in waterfall charts).

---

## Part 9 — Integration Testing & Final Pipeline (Q75-Q77)

---

**Q75: What does run_pipeline.py actually verify beyond checking that each script exits with code 0?**

**A:** Three independent verification layers: (1) File-level verification after each stage: checks every expected output file exists. A stage that runs but writes no output is caught and marked FAIL. (2) File size/row-count thresholds: reads multi_failure_telemetry.csv (must be >= 40,000 rows), checks manufacturing.db file size (must be >= 3 MB), reads eda_sensor_stats.csv (>= 1 row). These guard against silent data truncation that exit code 0 does not catch. (3) Database row-count verification: opens SQLite directly via sqlite3 and issues SELECT COUNT(*) FROM sensor_readings (must be >= 47,000) and FROM failure_log (>= 15). Exit code 0 from ingest.py is necessary but not sufficient; the DB row count is ground truth.

---

**Q76: Why is the PipelineLogger class written from scratch rather than using Python's logging module directly?**

**A:** The standard logging module writes to handlers without ANSI colour control. PipelineLogger wraps logging.FileHandler for the log file (plain text, no ANSI escapes) while using print() with ANSI codes for the console — giving a clean machine-readable log file and colour-coded terminal output. The class also adds a success() severity level that prepends [OK] in green, making pass/fail visible at a glance during a live pipeline run. This is a pragmatic design pattern: use the stdlib where it is sufficient (file handler), extend where it is not (console colour + custom severity).

---

**Q77: What is the failure mode if the E-01 Power BI count is greater than the SQL count?**

**A:** PBI > SQL indicates fact_sensor_readings in Power BI contains more rows than sensor_readings in SQLite. The most common cause is the ETL being run twice without clearing the table: if the DB was dropped and recreated, rows previously loaded could be re-inserted with new auto-increment PKs, bypassing the INSERT OR IGNORE guard (which matches on existing PKs, not on data content). Diagnostic: SELECT COUNT(*) vs COUNT(DISTINCT reading_id) FROM sensor_readings. If both match, the issue is in the Power BI model (e.g., cross-filter context expanding row count). If they differ, the ETL wrote duplicate rows. Fix: TRUNCATE / DROP-RECREATE the table, then re-run ingest.py once from a clean DB.

---

## Quick Reference — Q&A Map by Day

| Day | Questions | Topic |
|---|---|---|
| Day 1 | Q1-Q4 | Reliability theory, maintenance strategy, Weibull vs exponential, simulation validation |
| Day 2 | Q5-Q7 | OEE series aggregation, RPM proxy, Quality product rule |
| Day 3 | Q8-Q10 | Diagnostic vs prognostic PHM, Weibull MTBF limitations, empirical vs parametric MTBF |
| Day 4 | Q11-Q13 | Bottleneck SQL, Lean 7 wastes vs OEE, ISO 10816-3 threshold applicability |
| Day 5 | Q14-Q16 | Inverse-CDF sampling, Arrhenius eta-only effect, networkx vs adjacency list |
| Day 8 (SQL) | Q17-Q19 | 3NF and denormalization, surrogate PKs, cascade constraint DDL |
| Day 9 (ETL) | Q20-Q22 | ETL definition, INSERT OR IGNORE, is_anomaly/iso_zone derivation |
| Day 10 | Q23-Q25 | Empirical vs parametric MTBF, CoV interpretation, cascade anomaly rates |
| Day 11-12 | Q26-Q31 | Window functions, rolling averages, Motor Housing OEE, CTE vs subquery, self-join, ROWS BETWEEN |
| Day 15 | Q32-Q37 | Distribution skew, constant variable warning, median vs mean, Pearson vs Spearman, correlation vs covariance, divergence |
| Day 16 | Q38-Q40 | Rolling window selection, dual y-axis risk, stacked area chart trade-offs |
| Day 18 | Q41-Q43 | Synthesis justification, yield skew in dashboard, nonlinear threshold justification |
| Day 18 (Graph) | Q44-Q46 | Motor Housing SRS vs Bearing, Pearson as edge weight proxy, weight sensitivity |
| Day 19 (CCI) | Q47-Q49 | SRS vs CCI distinction, max-normalisation vs min-max, simulated data validity |
| Day 20 | Q50-Q54 | Pipeline stage connectivity, EDA after SQL, pipeline safety, success verification, artefact location |
| Day 21 (PBI) | Q55-Q61 | Star schema, fact vs dimension, inactive relationships, 1:1 bidirectional, dim_criticality, cardinality, OEE DAX walkthrough |
| Day 22 (DAX) | Q62-Q64 | Filter vs row context, M vs DAX for health_score, BLANK() vs 0 in OEE |
| Day 25 | Q65-Q68 | Waterfall vs Pareto, line vs bar for MTBF, SELECTEDVALUE vs AVERAGE, D-07 vs B-02 |
| Day 31-32 | Q69-Q71 | Three tooltip pages justification, hidden slicer design, SELECTEDVALUE() page 2 warning |
| Day 33 | Q72-Q74 | Y=0 KPI strip, Panel B as drill-through trigger, PP losses in waterfall |
| Day 34 | Q75-Q77 | run_pipeline.py verification layers, PipelineLogger design, E-01 PBI>SQL failure mode |

---

*Viva Prep Guide compiled: Day 35 — August 15, 2026*
*Manufacturing Analytics FYP — Phase 4.2 Final Consolidation*
*All 77 Q&As locked. Do not modify this document after submission.*
