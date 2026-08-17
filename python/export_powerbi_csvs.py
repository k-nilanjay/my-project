import os
import sqlite3
import pandas as pd

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, 'data', 'manufacturing.db')
    processed_dir = os.path.join(base_dir, 'data', 'processed')
    
    os.makedirs(processed_dir, exist_ok=True)
    
    tables_to_export = {
        'sensor_readings': 'sensor_readings_export.csv',
        'components': 'components_export.csv',
        'production_shifts': 'production_shifts_export.csv',
        'downtime_events': 'downtime_events_export.csv',
        'failure_log': 'failure_log_export.csv',
        'production_counts': 'production_counts_export.csv',
        'sensors': 'sensors_export.csv'
    }
    
    conn = sqlite3.connect(db_path)
    
    for table, filename in tables_to_export.items():
        print(f"Exporting {table} to {filename}...")
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        out_path = os.path.join(processed_dir, filename)
        df.to_csv(out_path, index=False)
        print(f"Saved {out_path} ({len(df)} rows)")
        
    conn.close()
    print("All exports completed.")

if __name__ == "__main__":
    main()
