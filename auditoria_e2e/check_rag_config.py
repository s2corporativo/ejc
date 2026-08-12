import re, sys
src = open('/home/ubuntu/ejc/backend/app/core/config.py').read()
# print all settings with defaults mentioning rag, ai, embed, ollama, model
for m in re.finditer(r'class Settings.*?(?=\n\n\n|\Z)', src, re.S):
    block = m.group(0)
    for line in block.splitlines():
        if re.search(r'rag|embed|ai_|MODEL|ollama', line, re.I):
            print(line)
