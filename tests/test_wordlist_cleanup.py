import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from scripts import excel_to_json, refresh_word_meanings
from scripts.wordlist_cleanup import SOURCE_FOOTER, clean_meaning


def test_only_exact_footer_is_removed():
    assert clean_meaning('秋天' + SOURCE_FOOTER) == '秋天'
    assert clean_meaning('TOPIK考试') == 'TOPIK考试'
    assert clean_meaning('准备 TOPIK I') == '准备 TOPIK I'
    assert clean_meaning('秋天') == '秋天'


@pytest.mark.parametrize('value', [SOURCE_FOOTER, '秋天' + SOURCE_FOOTER + '12',
                                  '秋天歷年TOPIK 最常出現的必背單字 ',
                                  '秋天历年TOPIK 最常出现的必背单字',
                                  '秋天' + SOURCE_FOOTER * 2, None, 15])
def test_unknown_footer_or_invalid_result_is_rejected(value):
    with pytest.raises(ValueError):
        clean_meaning(value)


def sample():
    return {'total_words': 1, 'version': 'preserve', 'words': [{
        'id': 1, 'hangul': '가을', 'primary_meaning': '秋天' + SOURCE_FOOTER,
        'senses': [{'meaning': '秋天', 'examples': [{'ko': '가을이에요', 'zh': '是秋天'}]}],
        'examples': ['preserve'], 'collocations': ['preserve'], 'freq_rank': 1, 'lesson_id': 1}]}


def test_plan_preserves_all_other_fields_and_is_idempotent():
    original = sample()
    unchanged = copy.deepcopy(original)
    source = [{'hangul': '가을', 'meaning': '秋天' + SOURCE_FOOTER}]
    updated, changes = refresh_word_meanings.plan_refresh(original, source)
    assert original == unchanged
    expected = copy.deepcopy(original)
    expected['words'][0]['primary_meaning'] = '秋天'
    assert updated == expected
    assert len(changes) == 1
    assert refresh_word_meanings.plan_refresh(updated, source) == (updated, [])


@pytest.mark.parametrize('field,value', [('id', 2), ('id', '1'), ('id', True), ('hangul', '겨울'), ('primary_meaning', '冬天')])
def test_identity_and_unrelated_meaning_edits_fail(field, value):
    data = sample()
    data['words'][0][field] = value
    with pytest.raises(ValueError):
        refresh_word_meanings.plan_refresh(data, [{'hangul': '가을', 'meaning': '秋天' + SOURCE_FOOTER}])


def test_duplicate_ids_fail():
    data = sample()
    data['total_words'] = 2
    data['words'].append(copy.deepcopy(data['words'][0]))
    with pytest.raises(ValueError):
        refresh_word_meanings.plan_refresh(data, [{'hangul': '가을', 'meaning': '秋天'}] * 2)


def test_atomic_refresh_dry_run_and_repeat(tmp_path, monkeypatch):
    target = tmp_path / 'words.json'
    target.write_text(json.dumps(sample()), encoding='utf-8')
    original = target.read_bytes()
    monkeypatch.setattr(refresh_word_meanings, 'read_source', lambda _: [{'hangul': '가을', 'meaning': '秋天' + SOURCE_FOOTER}])
    report = refresh_word_meanings.refresh('unused', target)
    assert report['change_count'] == 1
    assert target.read_bytes() == original
    replace = refresh_word_meanings.os.replace
    def check_replace(source, destination):
        assert target.read_bytes() == original
        assert json.loads(Path(source).read_text())['words'][0]['primary_meaning'] == '秋天'
        replace(source, destination)
    monkeypatch.setattr(refresh_word_meanings.os, 'replace', check_replace)
    assert refresh_word_meanings.refresh('unused', target, apply=True)['applied']
    corrected = target.read_bytes()
    report = refresh_word_meanings.refresh('unused', target, apply=True)
    assert report['change_count'] == 0
    assert not report['applied']
    assert target.read_bytes() == corrected


@pytest.mark.asyncio
async def test_import_reuses_enhancement_but_refreshes_meaning(tmp_path, monkeypatch):
    output = tmp_path / 'words.json'
    data = sample()
    output.write_text(json.dumps(data), encoding='utf-8')
    llm = SimpleNamespace(generate_word_content=AsyncMock(side_effect=AssertionError('No provider calls')))
    monkeypatch.setattr(excel_to_json, 'LLMService', lambda _: llm)
    monkeypatch.setattr(excel_to_json, 'get_settings', lambda: None)
    monkeypatch.setattr(excel_to_json, 'read_excel', lambda _: [{'hangul': '가을', 'pos': '名', 'meaning': clean_meaning('秋天' + SOURCE_FOOTER)}])
    await excel_to_json.build_wordlist('unused', str(output), 0)
    actual = json.loads(output.read_text())['words'][0]
    expected = copy.deepcopy(data['words'][0])
    expected['primary_meaning'] = '秋天'
    assert actual == expected
    llm.generate_word_content.assert_not_awaited()


def test_real_source_and_data_identity_and_known_footer_scope():
    root = Path(__file__).resolve().parents[1]
    source = refresh_word_meanings.read_source(root / 'data/common_words.xlsx')
    assert len(source) == 1203
    assert sum(item['meaning'].endswith(SOURCE_FOOTER) for item in source) == 76
    data = json.loads((root / 'data/common_words.json').read_text())
    updated, changes = refresh_word_meanings.plan_refresh(data, source)
    assert changes == []
    assert updated['words'][14]['hangul'] == '가을'
    assert updated['words'][14]['primary_meaning'] == '秋天'


def workbook(tmp_path, meaning_cell='<c r="C2" t="inlineStr"><is><t>秋天</t></is></c>', header='中文'):
    target = tmp_path / 'source.xlsx'
    with ZipFile(target, 'w') as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="words" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/sharedStrings.xml', '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>가을</t></si></sst>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>单词</t></is></c><c r="B1" t="inlineStr"><is><t>词性</t></is></c><c r="C1" t="inlineStr"><is><t>' + header + '</t></is></c></row><row r="2"><c r="A2" t="s"><v>0</v></c><c r="B2" t="inlineStr"><is><t>名</t></is></c>' + meaning_cell + '</row></sheetData></worksheet>')
    return target


def test_xlsx_shared_and_inline_strings(tmp_path):
    assert refresh_word_meanings.read_source(workbook(tmp_path)) == [{'hangul': '가을', 'meaning': '秋天'}]


@pytest.mark.parametrize('cell', ['<c r="C2" t="n"><v>15</v></c>', '<c r="C2" t="str"><f>1+1</f><v>秋天</v></c>', ''])
def test_xlsx_invalid_types_formulas_and_missing_meaning_fail(tmp_path, cell):
    with pytest.raises(ValueError):
        refresh_word_meanings.read_source(workbook(tmp_path, meaning_cell=cell))


@pytest.mark.parametrize('header', ['缺少中文', '单词'])
def test_xlsx_missing_or_duplicate_required_column_fails(tmp_path, header):
    with pytest.raises(ValueError):
        refresh_word_meanings.read_source(workbook(tmp_path, header=header))


def test_validation_failure_does_not_modify_target(tmp_path, monkeypatch):
    target = tmp_path / 'words.json'
    target.write_text(json.dumps(sample()), encoding='utf-8')
    original = target.read_bytes()
    monkeypatch.setattr(refresh_word_meanings, 'read_source', lambda _: [{'hangul': '다른', 'meaning': '不同'}])
    with pytest.raises(ValueError):
        refresh_word_meanings.refresh('unused', target, apply=True)
    assert target.read_bytes() == original
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.asyncio
async def test_runtime_lesson_and_whole_list_serve_corrected_file(monkeypatch):
    from app.routers import content
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(content, 'get_settings', lambda: SimpleNamespace(data_dir=str(root / 'data')))
    lesson = await content.get_lesson_words(level=0, lesson_id=1, words_per_lesson=30)
    all_words = await content.get_topik_words(level=0)
    assert lesson['wordCount'] == 30
    assert all_words['wordCount'] == 1203
    assert [w['id'] for w in lesson['words']] == list(range(1, 31))
    assert lesson['words'][14]['primaryMeaning'] == '秋天'
    assert all(clean_meaning(w['primaryMeaning']) == w['primaryMeaning'] for w in all_words['words'])


@pytest.mark.asyncio
async def test_import_rejects_unrelated_translation_change(tmp_path, monkeypatch):
    output = tmp_path / 'words.json'
    output.write_text(json.dumps(sample()), encoding='utf-8')
    original = output.read_bytes()
    llm = SimpleNamespace(generate_word_content=AsyncMock(side_effect=AssertionError('No provider calls')))
    monkeypatch.setattr(excel_to_json, 'LLMService', lambda _: llm)
    monkeypatch.setattr(excel_to_json, 'get_settings', lambda: None)
    monkeypatch.setattr(excel_to_json, 'read_excel', lambda _: [{'hangul': '가을', 'pos': '名', 'meaning': '季节'}])
    with pytest.raises(ValueError):
        await excel_to_json.build_wordlist('unused', str(output), 0)
    assert output.read_bytes() == original
    llm.generate_word_content.assert_not_awaited()
