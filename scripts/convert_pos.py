import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(BASE_DIR, 'data', 'topik_ii_words.json')

if not os.path.exists(path):
    print(f"File not found: {path}")
    exit(1)

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

mapping = {
    '명사': '名词',
    '대명사': '代词',
    '수사': '数词',
    '동사': '动词',
    '형용사': '形容词',
    '관형사': '冠形词',
    '부사': '副词',
    '감탄사': '感叹词',
    '조사': '助词',
    '접사': '词缀',
    '접미사': '后缀',
    '접두사': '前缀',
    '의존명사': '依存名词',
    '상태동사': '状态动词',
    '지명': '地名',
    '단위명사': '量词',

    # Abbreviated / Traditional
    '名': '名词',
    '動': '动词', '动': '动词',
    '形': '形容词',
    '副': '副词',
    '冠': '冠形词',
    '代': '代词',
    '數': '数词', '数': '数词',
    '感': '感叹词'
}

count = 0
for word in data['words']:
    pos = word.get('pos', '')
    if not pos:
        continue

    # Split by comma or space
    parts = [p.strip() for p in re.split(r'[, ]+', pos) if p.strip()]
    new_parts = []

    changed = False
    for p in parts:
        if p in mapping:
            new_parts.append(mapping[p])
            changed = True
        else:
            new_parts.append(p)
            print(f"Warning: Unknown POS tag '{p}' in word '{word['hangul']}'")

    if changed:
        word['pos'] = '，'.join(new_parts)  # Using full-width comma for Chinese context
        count += 1

print(f"Updated {count} words.")

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
