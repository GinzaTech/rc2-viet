"""Structural menu patch contracts, with no Android device or version allowlist."""
import hashlib
from pathlib import Path
import struct
from zipfile import ZipFile, ZIP_DEFLATED

import pytest


def manifest_fixture(application='example.Boot', version='92.7', code=927, package='dji.go.v5'):
    strings = ['manifest', 'application', 'package', 'name', 'versionName', 'versionCode',
               'http://schemas.android.com/apk/res/android', 'android', package, application, version]
    data, offsets = bytearray(), []
    for value in strings:
        offsets.append(len(data)); encoded = value.encode()
        data.extend(bytes([len(value), len(encoded)]) + encoded + b'\0')
    data.extend(bytes(-len(data) % 4))
    pool = struct.pack('<HH6I', 1, 28, 28 + len(offsets)*4 + len(data), len(offsets), 0,
                       256, 28 + len(offsets)*4, 0)
    pool += struct.pack('<'+'I'*len(offsets), *offsets)+data
    def start(tag, attrs):
        values = b''.join(struct.pack('<iiIHBBI', ns, key, raw, 8, 0, kind, value)
                          for ns, key, raw, kind, value in attrs)
        return struct.pack('<HHIii', 0x102, 16, 36+len(values), 1, -1)+struct.pack('<ii6H', -1, tag, 20, 20, len(attrs), 0, 0, 0)+values
    def end(tag): return struct.pack('<HHIiiii', 0x103, 16, 24, 1, -1, -1, tag)
    resources=[0,0,0,0x01010003,0x0101021c,0x0101021b]
    mapping=struct.pack('<HHI',0x180,8,8+len(resources)*4)+struct.pack('<'+'I'*len(resources),*resources)
    namespace=struct.pack('<HHIiiii',0x100,16,24,1,-1,7,6)
    nodes=start(0,[(-1,2,8,3,8),(6,4,10,3,10),(6,5,0xffffffff,16,code)])
    nodes+=start(1,[(6,3,9,3,9)])+end(1)+end(0)
    nodes+=struct.pack('<HHIiiii',0x101,16,24,1,-1,7,6)
    body=pool+mapping+namespace+nodes
    return struct.pack('<HHI',3,8,8+len(body))+body


def apk_fixture(path, extra_dex=False):
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        z.writestr('AndroidManifest.xml',manifest_fixture())
        z.writestr('classes.dex',b'original dex')
        z.writestr('resources.arsc',b'original resources')
        z.writestr('assets/original.bin',b'untouched'*120)
        if extra_dex: z.writestr('classes23.dex',b'unrelated dex')
    return path


def test_generic_manifest_reads_application_and_version_without_appguard_template():
    from scripts.hud_manifest import inspect_application, add_adaptive_provider
    source=manifest_fixture()
    assert inspect_application(source)=={'package':'dji.go.v5','application':'example.Boot','version':'92.7','code':927}
    result=add_adaptive_provider(source)
    assert inspect_application(result)==inspect_application(source)
    with pytest.raises(ValueError): add_adaptive_provider(result)


@pytest.mark.parametrize('name',['.Boot','Boot','example.NewBoot'])
def test_application_normalization(name):
    from scripts.hud_manifest import inspect_application
    actual=inspect_application(manifest_fixture(application=name))['application']
    assert actual==('dji.go.v5'+name if name.startswith('.') else 'dji.go.v5.'+name if '.' not in name else name)


def test_generic_capsule_recovers_exact_input_with_dynamic_dex_slot(tmp_path):
    from rc2vi.hud_capsule import build_capsule, recover_capsule
    from scripts.hud_apk import repack_apk, validate_apk_change
    source=apk_fixture(tmp_path/'source.apk',True); capsule=tmp_path/'capsule.zip'
    build_capsule(source,capsule,{'AndroidManifest.xml','classes.dex'})
    candidate=tmp_path/'patched.apk'
    replacements={'AndroidManifest.xml':b'patched manifest','classes.dex':b'patched dex'}
    additions={'classes24.dex':b'helper','assets/rc2-menu/recovery.zip':capsule.read_bytes()}
    repack_apk(source,candidate,replacements=replacements,additions=additions)
    validate_apk_change(source,candidate,replacements=replacements,additions=additions)
    output=tmp_path/'restored.apk'
    recover_capsule(candidate,capsule,output,additions.keys())
    assert output.read_bytes()==source.read_bytes()
    with pytest.raises(FileExistsError): recover_capsule(candidate,capsule,output,additions.keys())


def test_capsule_rejects_mutation_of_unchanged_payload(tmp_path):
    from rc2vi.hud_capsule import build_capsule, recover_capsule
    from scripts.hud_apk import repack_apk
    source=apk_fixture(tmp_path/'source.apk'); capsule=tmp_path/'capsule.zip'
    build_capsule(source,capsule,{'AndroidManifest.xml'})
    candidate=tmp_path/'bad.apk'
    repack_apk(source,candidate,replacements={'resources.arsc':b'altered'})
    with pytest.raises(ValueError): recover_capsule(candidate,capsule,tmp_path/'output.apk',[])
    assert not (tmp_path/'output.apk').exists()


def test_streamed_loader_signature_retention_matches_reference_bytes(tmp_path):
    from test_hud_build import signing_block
    from scripts.hud_signing_block import V2,block_entries_path,preserve_v2_file,replace_v2_block
    source=apk_fixture(tmp_path/'source.apk');signed=apk_fixture(tmp_path/'signed.apk')
    signing_block(source,[(V2,b'original-v2')]);signing_block(signed,[(V2,b'new-v2'),(0xf05368c0,b'new-v3')])
    output=tmp_path/'output.apk';preserve_v2_file(source,signed,output)
    assert output.read_bytes()==replace_v2_block(source.read_bytes(),signed.read_bytes())
    assert block_entries_path(output)[V2]==b'original-v2'


def test_cine_memory_and_overrides_use_slow_speed_wording():
    from rc2vi.translation_memory import load_memories
    root=Path(__file__).resolve().parents[1]
    catalogs,overrides,_=load_memories(root/'assets')
    assert overrides['Cine mode (slow speed)']=='Chế độ C (Tốc độ chậm)'
    matched=[e for c in catalogs for e in c['entries'] if e['name']=='fpv_basic_flight_cinesmooth_mode_toast']
    assert matched and all('Chế độ C (Tốc độ chậm)' in e['translation_xml'] for e in matched)
    assert 'D-Cinelike' not in overrides or 'Chế độ C' not in overrides['D-Cinelike']


def test_explicit_correction_wins_over_an_older_exact_memory(tmp_path):
    import xml.etree.ElementTree as ET
    from rc2vi.translation_catalog import _canonical
    from rc2vi.translation_complete import compose_complete
    target=tmp_path/'res/values'; target.mkdir(parents=True)
    el=ET.Element('string',name='mode'); el.text='Cine mode (slow speed)'
    root=ET.Element('resources');root.append(el)
    (target/'strings.xml').write_bytes(ET.tostring(root))
    catalog={'schema':1,'entries':[{'kind':'string','name':'mode','source':_canonical(el),
             'translation_xml':'<string name="mode">Chế độ sin (tiểu thức chậm)</string>'}]}
    values,report=compose_complete(target.parent,[catalog],lambda texts:pytest.fail('Correction must not need model'),
                                  corrections={'Cine mode (slow speed)':'Chế độ C (Tốc độ chậm)'})
    assert values[0].text=='Chế độ C (Tốc độ chậm)' and report['complete']


@pytest.fixture
def adaptive_builder(tmp_path, monkeypatch):
    from rc2vi import hud_build
    from test_hud_build import FakeTools, FakeKeys
    class Tools(FakeTools):
        def inspect_bootstrap(self, dex, application):
            return {'found':True,'class_count':2,'mode':'provider','superclass':'Landroid/app/Application;'}
        def resource_names(self, apk, stage):
            return {'main_page_ui_state_startfly_btn','view_surface','top_bar_shell_layout','osd_shell_layout'}
    monkeypatch.setattr(hud_build,'HudTools',Tools)
    monkeypatch.setattr(hud_build,'HudKeyStore',FakeKeys)
    source=apk_fixture(tmp_path/'new-version.apk',True)
    from scripts.hud_apk import repack_apk
    actual=tmp_path/'input.apk'
    repack_apk(source,actual,replacements={'classes.dex':b'dex\n035\0 Lexample/Boot; original'})
    builder=hud_build.HudBuilder(tmp_path/'assets',tmp_path/'work',lambda *args:None)
    return builder,actual


def test_new_build_has_no_version_pin_and_selects_next_dex_slot(adaptive_builder):
    import json
    builder,source=adaptive_builder
    result=builder.build(source)
    assert result['source_digest']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert result['source_identity']['version']=='92.7'
    receipt=json.loads(Path(result['receipt']).read_text('utf-8'))
    assert receipt['schema']==2 and receipt['plan']['helper_entry']=='classes24.dex'
    assert builder.verify(result['receipt'])==result
    assert builder.latest()==result
    assert builder.verify_device_apk(result['apk'],source)['source_digest']==result['source_digest']


def test_adaptive_receipt_replay_rejects_changed_identity(adaptive_builder):
    import json
    builder,source=adaptive_builder;result=builder.build(source)
    path=Path(result['receipt']);value=json.loads(path.read_text('utf-8'))
    value['plan']['identity']['version']='forged-version';path.write_text(json.dumps(value),'utf-8')
    with pytest.raises(ValueError):builder.verify(path)


def test_adaptive_build_rejects_missing_runtime_ui_contract(adaptive_builder):
    builder,source=adaptive_builder
    builder.tools.resource_names=lambda *args:{'view_surface'}
    with pytest.raises(ValueError):builder.build(source)
    assert builder.latest() is None


def test_embedded_capsule_restores_new_version_without_external_stock_file(adaptive_builder,tmp_path):
    from rc2vi.hud_device_source import source_kind,recover_adaptive
    builder,source=adaptive_builder; result=builder.build(source)
    assert source_kind(result['apk'])=='adaptive' and source_kind(source)=='stock'
    restored=tmp_path/'restored.apk';recover_adaptive(result['apk'],restored)
    assert restored.read_bytes()==source.read_bytes()
    assert not (restored.parent/'recovery.zip').exists()
    assert builder.verify_device_apk(result['apk'],restored)['source_digest']==result['source_digest']


def test_default_application_bootstrap_uses_provider(adaptive_builder,tmp_path):
    from scripts.hud_apk import repack_apk
    builder,source=adaptive_builder
    simple=tmp_path/'simple.apk'
    repack_apk(source,simple,replacements={'AndroidManifest.xml':manifest_fixture(application='android.app.Application')})
    result=builder.build(simple)
    import json
    plan=json.loads(Path(result['receipt']).read_text('utf-8'))['plan']
    assert plan['bootstrap']['mode']=='provider' and plan['bootstrap']['entry'] is None


def test_source_kind_rejects_partial_capsule(tmp_path):
    from rc2vi.hud_device_source import source_kind
    p=apk_fixture(tmp_path/'partial.apk')
    with ZipFile(p,'a') as z:z.writestr('assets/rc2-menu/profile.json',b'{}')
    with pytest.raises(ValueError):source_kind(p)


def test_generic_provider_attributes_are_private_and_have_framework_ids():
    from scripts.hud_manifest import add_adaptive_provider,_chunks,_attributes,inspect_strings,ANDROID,ATTR_IDS
    output=add_adaptive_provider(manifest_fixture());strings=inspect_strings(output)
    providers=[]
    for kind,_,chunk in _chunks(output):
        if kind==0x102 and strings[struct.unpack_from('<I',chunk,20)[0]]=='provider':
            providers.append(_attributes(chunk,strings))
    assert len(providers)==1 and providers[0][ANDROID,'exported']==(18,0)
    assert providers[0][ANDROID,'name']==(3,'local.rc2.hud.HudProvider')
    mapping=next(chunk for kind,_,chunk in _chunks(output) if kind==0x180)
    ids=struct.unpack('<'+'I'*((len(mapping)-8)//4),mapping[8:])
    assert all(ids[strings.index(name,len(strings)-7)]==value for name,value in ATTR_IDS.items())
