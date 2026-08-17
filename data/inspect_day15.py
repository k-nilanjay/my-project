import sqlite3, pandas as pd
conn = sqlite3.connect('data/manufacturing.db')
cols = pd.read_sql_query('PRAGMA table_info(components)', conn)
print(cols[['name','type']].to_string())
print()
print(pd.read_sql_query('SELECT * FROM components LIMIT 5', conn).to_string())
conn.close()
