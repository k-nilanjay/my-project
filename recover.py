import os, json, re

filepath = r'C:\Users\Hement Kitukale\.gemini\antigravity-ide\brain\0f0e057f-f2b1-4aa4-8c33-4757cbe3c1ed\.system_generated\logs\transcript_full.jsonl'
if not os.path.exists(filepath):
    print("Transcript not found")
    exit(1)

with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# The original view_file had: Total Lines: 777
start_idx = text.find('Total Lines: 777')
if start_idx == -1:
    print("Not found")
    exit(1)

# Find the start of the file content in that string
content_start = text.find('1: # UX Implementation Guide', start_idx)
content_end = text.find('The above content shows the entire', content_start)

if content_start != -1 and content_end != -1:
    content = text[content_start:content_end]
    content = content.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
    
    lines = content.split('\n')
    out = []
    for l in lines:
        m = re.match(r'^\d+:\s?(.*)$', l)
        if m: out.append(m.group(1))
        else: out.append(l)
    
    with open(r'c:\Users\Hement Kitukale\Desktop\Resume project\docs\ux_implementation_guide.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))
    print('Restored original 777-line file. Final length: ' + str(len(out)))
else:
    print('Not found content start/end')
