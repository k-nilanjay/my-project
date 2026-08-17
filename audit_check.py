import sqlite3, os, sys

db = r'c:\Users\Hement Kitukale\Desktop\Resume project\data\manufacturing.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

# Check tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cur.fetchall()
print('TABLES:', [t[0] for t in tables])

# Check row counts
for t in tables:
    cur.execute(f'SELECT COUNT(*) FROM {t[0]}')
    print(f'  {t[0]}: {cur.fetchone()[0]} rows')

# Check components table - verify Ea values match
cur.execute('SELECT component_id, component_name, weibull_eta_hours, weibull_beta_mid, activation_energy_ev FROM components ORDER BY component_id')
print('\nCOMPONENTS:')
for row in cur.fetchall():
    print(f'  {row}')

# Check failure_log
cur.execute('SELECT component_id, cycle_number, ttf_hours, repair_hours, beta_mid, eta_nominal_h, eta_effective_h, ea_ev FROM failure_log ORDER BY component_id, cycle_number')
print('\nFAILURE_LOG:')
for row in cur.fetchall():
    print(f'  {row}')

# Check sensor_readings basics
cur.execute('SELECT component_id, COUNT(*) as cnt, MIN(value), MAX(value), AVG(value) FROM sensor_readings GROUP BY component_id ORDER BY component_id')
print('\nSENSOR_READINGS per component (count, min_val, max_val, avg_val):')
for row in cur.fetchall():
    print(f'  component_id={row[0]}: count={row[1]}, min={row[2]:.2f}, max={row[3]:.2f}, avg={row[4]:.2f}')

# Check for negative values
cur.execute("SELECT COUNT(*) FROM sensor_readings WHERE value < 0")
print(f'\nNegative sensor values: {cur.fetchone()[0]}')

# Check anomaly count (E-01 cross-validation)
cur.execute("SELECT COUNT(*) FROM sensor_readings WHERE is_anomaly = 1")
print(f'Anomaly count (is_anomaly=1): {cur.fetchone()[0]}')

# Check sensors table
cur.execute('SELECT sensor_id, component_id, sensor_type, iso_alarm_threshold, iso_danger_threshold FROM sensors ORDER BY sensor_id')
print('\nSENSORS:')
for row in cur.fetchall():
    print(f'  {row}')

# Check production_shifts
cur.execute('SELECT COUNT(*) FROM production_shifts')
print(f'\nproduction_shifts rows: {cur.fetchone()[0]}')

cur.execute('SELECT COUNT(*) FROM downtime_events')
print(f'downtime_events rows: {cur.fetchone()[0]}')

cur.execute('SELECT COUNT(*) FROM production_counts')
print(f'production_counts rows: {cur.fetchone()[0]}')

# Check downtime categories
cur.execute("SELECT downtime_category, COUNT(*) FROM downtime_events GROUP BY downtime_category")
print('\nDowntime categories:')
for row in cur.fetchall():
    print(f'  {row}')

conn.close()
print('\nDone.')
