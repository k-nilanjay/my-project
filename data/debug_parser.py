"""Debug: what blocks does split_sql_file find for downtime_pareto.sql?"""
import pathlib
import re

_HRULE_PATTERN = re.compile(r"^--\s*={10,}\s*$", re.MULTILINE)

def split_sql_file(sql_text):
    hr_positions = [m.start() for m in _HRULE_PATTERN.finditer(sql_text)]
    if not hr_positions:
        return [{"label": "MAIN", "sql": sql_text}]

    sections = []
    for i, pos in enumerate(hr_positions):
        next_pos  = hr_positions[i + 1] if i + 1 < len(hr_positions) else len(sql_text)
        section   = sql_text[pos:next_pos]
        sections.append(section)

    label_pat = re.compile(r"^--\s*([A-Z][0-9]+)\s*[:\.\s—\-]", re.MULTILINE)
    result = []
    seen = set()
    for section in sections:
        m = label_pat.search(section)
        if m:
            label = m.group(1)
            if label in seen:
                label = label + "_b"
            seen.add(label)
            result.append({"label": label, "sql": section[:100]})

    if not result:
        return [{"label": "MAIN", "sql": sql_text}]
    return result

for fname in ["downtime_pareto.sql", "downtime_timeseries.sql", "oee_window_analytics.sql"]:
    sql = pathlib.Path(f"sql/queries/{fname}").read_text(encoding="utf-8")
    # Check horizontal rules
    hrs = [m.start() for m in _HRULE_PATTERN.finditer(sql)]
    print(f"\n{fname}:")
    print(f"  Horizontal rules found: {len(hrs)}")
    
    # Show first few HRs
    for i, pos in enumerate(hrs[:5]):
        line_start = sql.rfind("\n", 0, pos) + 1
        line_end = sql.find("\n", pos)
        print(f"  HR[{i}] at char {pos}: {repr(sql[line_start:line_end+1])}")

    blocks = split_sql_file(sql)
    print(f"  Blocks extracted: {len(blocks)}")
    for b in blocks[:5]:
        print(f"    label={b['label']}: {b['sql'][:80].replace(chr(10), ' ')}")
