import sqlite3
db = sqlite3.connect('data/manufacturing.db')
tables = db.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
print("Tables:", tables)

for t in tables:
    table_name = t[0]
    count = db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    print(f"Table {table_name} has {count} rows")
    if table_name == 'sensor_readings' or table_name == 'component_readings':
        if 'is_anomaly' in [col[1] for col in db.execute(f"PRAGMA table_info({table_name})").fetchall()]:
            anomaly_count = db.execute(f"SELECT COUNT(*) FROM {table_name} WHERE is_anomaly=1").fetchone()[0]
            print(f"  Anomalies in {table_name}: {anomaly_count}")
