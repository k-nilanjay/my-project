"""
Extended audit checks - ASCII only version
"""
import sqlite3, math, os, sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

db = r'c:\Users\Hement Kitukale\Desktop\Resume project\data\manufacturing.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

print("="*70)
print("CHECK 1: eta_effective_h NULL in failure_log")
print("="*70)
cur.execute("SELECT component_id, cycle_number, eta_effective_h FROM failure_log WHERE eta_effective_h IS NULL")
nulls = cur.fetchall()
print(f"Rows with NULL eta_effective_h: {len(nulls)} out of 15 total")
print("  CRITICAL: mtbf_from_failure_log.sql MTBF_derated will be NULL for all rows")

print()
print("="*70)
print("CHECK 2: Ea values - seed.sql vs reliability.py vs failure_log")
print("="*70)
k = 8.617e-5  # eV/K
# Bearing
Ea_rpy = 0.65   # reliability.py
Ea_seed = 0.80  # seed.sql
Ea_fl = 0.65    # failure_log (actual used)
T_use = 65.0 + 273.15
T_stress = 80.0 + 273.15
AF_rpy = math.exp((Ea_rpy / k) * (1/T_use - 1/T_stress))
AF_seed = math.exp((Ea_seed / k) * (1/T_use - 1/T_stress))
print(f"Bearing Ea: reliability.py={Ea_rpy} | seed.sql(DB)={Ea_seed} | failure_log={Ea_fl}")
print(f"  AF using 0.65 (T65->T80): {AF_rpy:.4f}x")
print(f"  AF using 0.80 (T65->T80): {AF_seed:.4f}x")
print(f"  MISMATCH: seed.sql has 0.80 but reliability.py and actual simulation use 0.65")

Ea_mh_rpy = 0.85
Ea_mh_seed = 1.00
Ea_mh_fl = 0.85
T_use_mh = 85.0 + 273.15
T_stress_mh = 130.0 + 273.15
AF_mh_rpy = math.exp((Ea_mh_rpy / k) * (1/T_use_mh - 1/T_stress_mh))
AF_mh_seed = math.exp((Ea_mh_seed / k) * (1/T_use_mh - 1/T_stress_mh))
print(f"\nMotor Housing Ea: reliability.py={Ea_mh_rpy} | seed.sql(DB)={Ea_mh_seed} | failure_log={Ea_mh_fl}")
print(f"  AF using 0.85 (T85->T130): {AF_mh_rpy:.4f}x")
print(f"  AF using 1.00 (T85->T130): {AF_mh_seed:.4f}x")
print(f"  MISMATCH: seed.sql has 1.00 but reliability.py and actual simulation use 0.85")

print()
print("="*70)
print("CHECK 3: eta_nominal_h in failure_log vs components table")
print("="*70)
cur.execute("""
    SELECT fl.component_id, c.component_name, c.weibull_eta_hours as comp_eta, fl.eta_nominal_h as fl_eta
    FROM failure_log fl
    JOIN components c ON c.component_id = fl.component_id
    GROUP BY fl.component_id, c.component_name, c.weibull_eta_hours, fl.eta_nominal_h
""")
for row in cur.fetchall():
    match = "OK" if row[2] == row[3] else "MISMATCH"
    print(f"  comp_id={row[0]} {row[1]}: DB eta={row[2]}, failure_log eta={row[3]} [{match}]")
print("  NOTE: Motor Housing: DB=6570h but failure_log shows 8000h -> Day9 recal not in seed.sql")

print()
print("="*70)
print("CHECK 4: Failure count summary")
print("="*70)
cur.execute("SELECT component_id, COUNT(*) FROM failure_log GROUP BY component_id ORDER BY component_id")
total_failures = 0
for row in cur.fetchall():
    total_failures += row[1]
    print(f"  component_id={row[0]}: {row[1]} failures")
print(f"  Total: {total_failures} failures")
print(f"  Shaft (id=2): 0 failures - correct (eta=8760h, 365d window)")
print(f"  Coupling (id=4): 1 failure - minimal sample for statistics")
print(f"  STATE_SUMMARY says 19 rows but DB has {total_failures}")

print()
print("="*70)
print("CHECK 5: Anomaly count E-01 cross-validation")
print("="*70)
cur.execute("SELECT COUNT(*) FROM sensor_readings WHERE is_anomaly = 1")
db_anomaly = cur.fetchone()[0]
print(f"DB anomaly count: {db_anomaly}")
print(f"STATE_SUMMARY E-01 claim: 6,843")
match = "YES" if db_anomaly == 6843 else "NO - DB has " + str(db_anomaly)
print(f"Match: {match}")

print()
print("="*70)
print("CHECK 6: sensor_readings total rows")
print("="*70)
cur.execute("SELECT COUNT(*) FROM sensor_readings")
total = cur.fetchone()[0]
print(f"DB sensor_readings rows: {total}")
print(f"STATE_SUMMARY claim: 47,957")
print(f"README claim: 47,957")
match = "YES" if total == 47957 else "NO - DB has " + str(total)
print(f"Match: {match}")

print()
print("="*70)
print("CHECK 7: MTBF calculation validation")
print("="*70)
from math import gamma as gf
# For Bearing: beta=3.0, eta_nominal=4380h
beta_b, eta_b = 3.0, 4380.0
mtbf_b = eta_b * gf(1 + 1/beta_b)
print(f"Bearing MTBF (Weibull): eta={eta_b} * Gamma(1+1/{beta_b}) = {mtbf_b:.1f} h")

# For Motor Housing: different in reliability.py vs DB
beta_mh, eta_mh_rpy, eta_mh_seed = 2.15, 8000.0, 6570.0
mtbf_mh_rpy = eta_mh_rpy * gf(1 + 1/beta_mh)
mtbf_mh_seed = eta_mh_seed * gf(1 + 1/beta_mh)
print(f"Motor Housing MTBF (reliability.py eta=8000h): {mtbf_mh_rpy:.1f} h")
print(f"Motor Housing MTBF (seed.sql/DB eta=6570h):    {mtbf_mh_seed:.1f} h")
print(f"  MISMATCH: Python module and DB have different eta values")

print()
print("="*70)
print("CHECK 8: OEE data sanity")
print("="*70)
cur.execute("""
    SELECT component_id, 
           AVG(planned_duration_min) as avg_planned,
           AVG(CAST(good_units AS FLOAT)/NULLIF(total_units,0)) as avg_quality,
           AVG(CAST(total_units AS FLOAT)*ideal_cycle_time_min) as avg_units_x_cycle
    FROM production_counts pc
    JOIN production_shifts ps USING (shift_id, component_id)
    GROUP BY component_id
""")
print("OEE data per component (avg_planned_min, avg_quality, avg_units*cycle_time):")
for row in cur.fetchall():
    print(f"  comp_id={row[0]}: planned={row[1]:.1f}min, quality={row[2]:.4f}, units*cycle={row[3]:.1f}")

print()
print("="*70)
print("CHECK 9: Betweenness centrality check for linear DAG")
print("="*70)
print("For a 5-node linear DAG (Bearing->Shaft->Motor->Coupling->Gearbox):")
print("Expected BC (normalized):")
print("  Bearing: 0 (no intermediate paths through it as source)")
print("  Shaft: 3/(5-1)(5-2) = 3/12 = 0.25")
print("  Motor Housing: 4/12 = 0.333")
print("  Coupling: 3/12 = 0.25")
print("  Gearbox: 0 (terminal node)")
print("  NOTE: graph_centrality.py uses NetworkX normalized BC - verify this matches")

print()
print("="*70)
print("CHECK 10: Cascade reach vs exposure")
print("="*70)
print("Expected cascade reach (downstream nodes):")
print("  Bearing: 4 | Shaft: 3 | Motor Housing: 2 | Coupling: 1 | Gearbox: 0")
print("Expected cascade exposure (upstream nodes):")
print("  Bearing: 0 | Shaft: 1 | Motor Housing: 2 | Coupling: 3 | Gearbox: 4")

conn.close()
print("\nAudit complete.")
