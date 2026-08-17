# E-01 Cross-Validation Script
# Run from: c:\Users\Hement Kitukale\Desktop\Resume project\
import sqlite3
import pandas as pd

DB_PATH = r"c:\Users\Hement Kitukale\Desktop\Resume project\data\manufacturing.db"

conn = sqlite3.connect(DB_PATH)

# Main count
sql_total = pd.read_sql_query(
    "SELECT COUNT(*) AS total_anomaly_count FROM sensor_readings WHERE is_anomaly = 1",
    conn
)
print(f"SQL total anomaly count: {sql_total['total_anomaly_count'].iloc[0]}")

# Per-component breakdown
sql_by_component = pd.read_sql_query("""
    SELECT sr.component_id, c.component_name, COUNT(*) AS anomaly_count
    FROM sensor_readings sr
    JOIN components c ON sr.component_id = c.component_id
    WHERE sr.is_anomaly = 1
    GROUP BY sr.component_id, c.component_name
    ORDER BY anomaly_count DESC
""", conn)
print("\nPer-component breakdown:")
print(sql_by_component.to_string(index=False))

conn.close()
