import sqlite3

conn = sqlite3.connect(r'c:\Users\Hement Kitukale\Desktop\Resume project\data\manufacturing.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print('TABLES:', tables)
for t in tables:
    c.execute(f"PRAGMA table_info({t})")
    cols = [(r[1], r[2]) for r in c.fetchall()]
    print(f"\n{t}: {cols}")
    c.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  rows: {c.fetchone()[0]}")
conn.close()
