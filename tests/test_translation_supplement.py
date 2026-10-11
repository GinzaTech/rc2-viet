"""Supplemental export data never overrides newer context or invents lost markup."""
import json
import pytest
from scripts.import_translation_memory import import_memory
from rc2vi.translation_catalog import _canonical
import xml.etree.ElementTree as ET


def export_fixture(tmp_path):
    root=tmp_path/'export/translation';(root/'rc-1.21.10/res/values').mkdir(parents=True)
    rows=[{'kind':'string','name':'old','texts':['Old text']},
          {'kind':'string','name':'new','texts':['New text']},
          {'kind':'string','name':'broken','texts':['Value %s']},
          {'kind':'string-array','name':'array','texts':['One']}]
    (root/'translation-catalog.json').write_text(json.dumps(rows),'utf-8')
    (root/'rc-1.21.10/res/values/strings.xml').write_text(
        '<resources><string name="old">Văn bản cũ</string><string name="new">Văn bản mới</string>'
        '<string name="broken">Giá trị %d</string><string-array name="array"><item>Một</item></string-array></resources>','utf-8')
    return root.parent


def test_import_keeps_current_pairs_and_checks_new_pairs(tmp_path):
    folder=export_fixture(tmp_path);before={p:p.read_bytes() for p in folder.rglob('*') if p.is_file()}
    el=ET.Element('string',name='old');el.text='Old text'
    current={'schema':1,'entries':[{'kind':'string','name':'old','source':_canonical(el),
                                  'translation_xml':'<string name="old">Bản hiện tại</string>'}]}
    result,provenance=import_memory(folder,[current])
    assert [e['name'] for e in result['entries']]==['new']
    assert result['report']=={'matched':1,'skipped':3,'total':4,'reasons':{
        'already_in_current_memory':1,'incompatible_contract':1,'missing_source_shape_or_translation':1}}
    assert provenance['runtime_tested'] is False
    assert all(p.read_bytes()==data for p,data in before.items())


@pytest.mark.parametrize('change',[{'kind':{}},{'name':'../escape'},{'name':'old','texts':['again']}])
def test_invalid_or_duplicate_legacy_identity_is_rejected(tmp_path,change):
    folder=export_fixture(tmp_path);p=folder/'translation/translation-catalog.json'
    rows=json.loads(p.read_text('utf-8'));rows[1]={**rows[1],**change};p.write_text(json.dumps(rows),'utf-8')
    with pytest.raises(ValueError):import_memory(folder,[])
