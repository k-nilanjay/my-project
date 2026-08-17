import os
import re

def grep_file(filepath, pattern):
    results = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if re.search(pattern, line, re.IGNORECASE):
                    results.append(f"{i+1}: {line.strip()}")
    except Exception as e:
        pass
    return results

files = [
    'python/reliability.py',
    'python/kpi.py',
    'python/graph_centrality.py',
    'python/composite_criticality.py',
    'python/simulate.py'
]

patterns = ['MTBF', 'MTTR', 'Arrhenius', 'OEE', 'centrality', 'criticality', 'Availability', 'Performance', 'Quality']

with open('audit_extract.txt', 'w', encoding='utf-8') as out:
    for f in files:
        out.write(f"\n--- {f} ---\n")
        for p in patterns:
            res = grep_file(f, p)
            if res:
                out.write(f"\nPattern: {p}\n")
                out.write("\n".join(res[:15]) + "\n")
