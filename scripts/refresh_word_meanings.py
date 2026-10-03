#!/usr/bin/env python3
"""Offline, identity-preserving source-footer repair. Dry-run unless --apply.

Supports the repository's single-sheet XLSX vocabulary format with textual
单词/词性/中文 columns. Rejects formulas and ambiguous workbook structure.
No runtime settings, Redis, or model clients are loaded.
"""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.wordlist_cleanup import clean_meaning

NS = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read_source(path):
    """Read text cells only; do not evaluate formulas or alter original bytes."""
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheets = workbook.findall('x:sheets/x:sheet', NS)
        if len(sheets) != 1:
            raise ValueError('Expected exactly one vocabulary worksheet')
        rel_id = sheets[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        matches = [r for r in rels if r.get('Id') == rel_id and r.get('TargetMode') != 'External']
        if len(matches) != 1:
            raise ValueError('Invalid worksheet relationship')
        target = matches[0].get('Target', '')
        sheet_path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(si.itertext()) for si in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('x:si', NS)]
        rows = []
        for row in ET.fromstring(archive.read(sheet_path)).findall('x:sheetData/x:row', NS):
            values = {}
            for cell in row.findall('x:c', NS):
                address = cell.get('r', '')
                match = re.fullmatch(r'([A-Z]+)[1-9][0-9]*', address)
                if not match or match[1] in values or cell.find('x:f', NS) is not None:
                    raise ValueError('Invalid, duplicated or formula cell: ' + address)
                kind = cell.get('t')
                v = cell.find('x:v', NS)
                if kind == 'inlineStr':
                    inline = cell.find('x:is', NS)
                    value = ''.join(inline.itertext()) if inline is not None else ''
                elif kind == 's' and v is not None:
                    index = int(v.text)
                    if not 0 <= index < len(strings):
                        raise ValueError('Invalid shared string index')
                    value = strings[index]
                elif kind == 'str' and v is not None:
                    value = v.text or ''
                elif v is None and kind in (None, 'n'):
                    value = ''
                else:
                    raise ValueError('Expected text cell: ' + address)
                values[match[1]] = value.strip()
            if any(values.values()):
                rows.append(values)
    if not rows:
        raise ValueError('Empty workbook')
    header = rows[0]
    columns = {}
    for name in ('单词', '词性', '中文'):
        found = [column for column, value in header.items() if value == name]
        if len(found) != 1:
            raise ValueError('Missing or duplicate column: ' + name)
        columns[name] = found[0]
    result = []
    for row in rows[1:]:
        word = row.get(columns['单词'], '')
        meaning = row.get(columns['中文'], '')
        if not word or not meaning:
            raise ValueError('Missing word or meaning')
        result.append({'hangul': word, 'meaning': meaning})
    return result


def plan_refresh(data, source):
    if not isinstance(data, dict) or not isinstance(data.get('words'), list):
        raise ValueError('Expected vocabulary object with words array')
    words = data['words']
    if len(words) != len(source) or data.get('total_words') != len(words):
        raise ValueError('Source and vocabulary word counts differ')
    updated = copy.deepcopy(data)
    changes = []
    seen = set()
    for position, (word, original, corrected) in enumerate(zip(words, source, updated['words']), 1):
        if not isinstance(word, dict) or type(word.get('id')) is not int:
            raise ValueError('Invalid word ID type')
        identity = word['id']
        if identity in seen or identity != position or word.get('hangul') != original['hangul']:
            raise ValueError(f'Word identity or position mismatch at {position}')
        seen.add(identity)
        old = word.get('primary_meaning')
        new = clean_meaning(original['meaning'])
        # This repair never reconciles unrelated translation edits silently.
        if clean_meaning(old) != new:
            raise ValueError(f'Source meaning mismatch at ID {identity}')
        if old != new:
            corrected['primary_meaning'] = new
            changes.append({'id': identity, 'hangul': word['hangul'], 'before': old, 'after': new})
    return updated, changes


def refresh(source_path, target_path, apply=False):
    target = Path(target_path)
    if target.is_symlink():
        raise ValueError('Refusing symlink target')
    before = target.read_bytes()
    source = read_source(source_path)
    updated, changes = plan_refresh(json.loads(before), source)
    after = (json.dumps(updated, ensure_ascii=False, indent=2) + ('\n' if before.endswith(b'\n') else '')).encode() if changes else before
    if apply and changes:
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.' + target.name + '.', delete=False) as stream:
                temp_name = stream.name
                os.fchmod(stream.fileno(), target.stat().st_mode & 0o777)
                stream.write(after)
                stream.flush()
                os.fsync(stream.fileno())
            if target.read_bytes() != before:
                raise ValueError('Vocabulary changed during refresh; refusing overwrite')
            os.replace(temp_name, target)
            temp_name = None
        finally:
            if temp_name is not None:
                os.unlink(temp_name)
    return {'applied': bool(apply and changes), 'word_count': len(source), 'change_count': len(changes),
            'before_sha256': hashlib.sha256(before).hexdigest(), 'after_sha256': hashlib.sha256(after).hexdigest(), 'changes': changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='data/common_words.xlsx')
    parser.add_argument('--target', default='data/common_words.json')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(refresh(args.source, args.target, args.apply), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
