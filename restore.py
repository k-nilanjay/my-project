import json
import re

transcript_path = r'C:\Users\Hement Kitukale\.gemini\antigravity-ide\brain\0f0e057f-f2b1-4aa4-8c33-4757cbe3c1ed\.system_generated\logs\transcript_full.jsonl'
found = False

def extract_from_dict(d):
    global found
    if isinstance(d, dict):
        for k, v in d.items():
            if k == 'output' and isinstance(v, str) and 'Total Lines: 777' in v:
                lines = v.split('\n')
                original_lines = []
                capture = False
                for l in lines:
                    if l.startswith('1: # UX Implementation Guide'):
                        capture = True
                    if l.startswith('The above content shows the entire'):
                        capture = False
                    if capture:
                        m = re.match(r'^\d+:\s?(.*)$', l)
                        if m:
                            original_lines.append(m.group(1))
                        else:
                            original_lines.append(l)
                with open(r'c:\Users\Hement Kitukale\Desktop\Resume project\docs\ux_implementation_guide.md', 'w', encoding='utf-8') as out_f:
                    out_f.write('\n'.join(original_lines))
                print('Restored', len(original_lines), 'lines.')
                found = True
                return
            extract_from_dict(v)
    elif isinstance(d, list):
        for i in d:
            extract_from_dict(i)

with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        extract_from_dict(data)
        if found: break

if not found: print('Not found')
