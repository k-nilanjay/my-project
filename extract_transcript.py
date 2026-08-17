import os, json, re

filepath = r'C:\Users\Hement Kitukale\.gemini\antigravity-ide\brain\33bd2e3a-86ed-469e-b259-7a8bc2fab80a\.system_generated\logs\transcript_full.jsonl'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

output_text = None
for line in reversed(lines):
    if 'Total Lines: 757' in line and 'Showing lines 1 to 757' in line:
        try:
            data = json.loads(line)
            def find_output(d):
                if isinstance(d, dict):
                    for k, v in d.items():
                        if isinstance(v, str) and 'Total Lines: 757' in v:
                            return v
                        res = find_output(v)
                        if res: return res
                elif isinstance(d, list):
                    for item in d:
                        res = find_output(item)
                        if res: return res
                return None
            output_text = find_output(data)
            if output_text:
                break
        except:
            continue

if not output_text:
    print('Not found')
    exit(1)

content_lines = output_text.split('\n')
out = []
capture = False
for l in content_lines:
    if l.startswith('1: # UX Implementation Guide'):
        capture = True
    if l.startswith('The above content shows the entire'):
        capture = False
        break
    if capture:
        m = re.match(r'^\d+:\s?(.*)$', l)
        if m: out.append(m.group(1))
        else: out.append(l)

with open(r'c:\Users\Hement Kitukale\Desktop\Resume project\docs\ux_implementation_guide.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

print(f'Restored original 757-line file. Final length: {len(out)}')
