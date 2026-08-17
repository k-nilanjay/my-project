"""Apply Day 13 performance indexes to manufacturing.db"""
import sqlite3
import pathlib
import re

db  = pathlib.Path("data/manufacturing.db")
idx = pathlib.Path("sql/schema/indexes.sql")

print(f"Connecting to: {db}")
conn = sqlite3.connect(str(db))
conn.execute("PRAGMA foreign_keys = ON;")

sql_text = idx.read_text(encoding="utf-8")

# Extract CREATE INDEX statements with a regex
# Handles partial indexes (WHERE clause) and multi-line definitions
index_pattern = re.compile(
    r"(CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+\S+\s+ON\s+\S+\s*\([^;]+?\)(?:\s*WHERE[^;]+?)?)\s*;",
    re.IGNORECASE | re.DOTALL,
)

statements = index_pattern.findall(sql_text)
created = 0

for stmt in statements:
    stmt_clean = stmt.strip()
    try:
        conn.execute(stmt_clean + ";")
        created += 1
        name_match = re.search(r"idx_\w+", stmt_clean, re.IGNORECASE)
        name = name_match.group(0) if name_match else stmt_clean[:40]
        print(f"  OK: {name}")
    except sqlite3.Error as e:
        print(f"  WARN: {e} | stmt: {stmt_clean[:60]}")

conn.commit()

query = "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%' ORDER BY name"
rows  = conn.execute(query).fetchall()
print(f"\nIndexes in DB ({len(rows)} total):")
for r in rows:
    print(f"  {r[0]}")

conn.close()
print(f"\nDone. {created} index(es) applied.")
