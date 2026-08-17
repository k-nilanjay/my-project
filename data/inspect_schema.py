import sqlite3
conn = sqlite3.connect('data/manufacturing.db')
for t in ['production_shifts','downtime_events','production_counts','failure_log','sensor_readings']:
    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {n}")
# Downtime category breakdown
print("\nDowntime category breakdown:")
for row in conn.execute("SELECT downtime_category, COUNT(*) FROM downtime_events GROUP BY downtime_category ORDER BY COUNT(*) DESC").fetchall():
    print(f"  {row[0]}: {row[1]}")
conn.close()
print("Day 11 verification PASSED")
