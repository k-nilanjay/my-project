import sqlite3
conn = sqlite3.connect('data/manufacturing.db')
r = conn.execute("SELECT start_ts, component_name, downtime_category FROM downtime_events WHERE downtime_category='unplanned_failure' LIMIT 10").fetchall()
print("unplanned_failure samples:", r)
cats = conn.execute("SELECT DISTINCT downtime_category FROM downtime_events").fetchall()
print("categories:", cats)
conn.close()
