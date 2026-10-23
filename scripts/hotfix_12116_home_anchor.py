"""Offline, one-class Home anchor hotfix for the exact audited 1.21.16 recipe."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rc2vi.hud_capsule import PROFILE_ENTRY
from rc2vi.hud_tools import HudTools, sha256_file
from scripts.build_12116_menu_recipe import SOURCE_SHA256, _dex_dump, _method, _short_windows_path, normalize_smali_encoding
from scripts.build_feature_candidate import run

PREVIOUS_RECIPE = 'b8df8c71949f43ac5582f41144e0b46dcc73663a96a43bd59b26680117d350a1'
TYPE = 'Llocal/rc2/hud/ScreenRoles;'
ANCHOR = 'go_fly_connection_disconnect_button'
HOME = ['main_page_ui_state_startfly_btn', 'main_page_ui_device_disconnect_state_button',
        'direct_enter_fpv_view', 'layout_direct_enter_fpv', 'connection_guide_enter_fpv_button']
DUMP_TOOL = '''import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import com.android.tools.smali.dexlib2.iface.ClassDef;
public final class Menu12116DexTool {
 public static void main(String[] args)throws Exception {
  if(args.length!=2)throw new IllegalArgumentException();
  Path out=Path.of(args[1]);Files.createDirectory(out);
  ArrayList<String> rows=new ArrayList<>();int n=0;
  for(Map.Entry<String,ClassDef> e:AdaptiveHudTool.classes(Path.of(args[0])).entrySet()) {
   String name="class-"+(n++)+".smali";
   Files.writeString(out.resolve(name),AdaptiveHudTool.dump(e.getValue()),StandardCharsets.UTF_8);
   rows.add(e.getKey()+"\\t"+name);
  }
  Files.write(out.resolve("classes.tsv"),rows,StandardCharsets.UTF_8);System.out.print(n);
 }
}'''


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def patch_screen_roles(text: str) -> str:
    """Extend only the HOME initializer, using existing 16 local registers."""
    if text.splitlines()[0] != '.class final ' + TYPE or ANCHOR in text:
        raise ValueError('Unexpected or already patched ScreenRoles')
    body = _method(text, '<clinit>()V')
    old_values = [('v0', HOME[3]), ('v1', HOME[4]), ('v2', HOME[0]), ('v3', HOME[1]), ('v4', HOME[2])]
    old = '\n\n'.join('    const-string ' + reg + ', "' + name + '"' for reg, name in old_values)
    old += '\n\n    filled-new-array {v2, v3, v4, v0, v1}, [Ljava/lang/String;'
    if body.count('    .registers 16\n') != 1 or body.count(old) != 1:
        raise ValueError('Exact HOME initializer anchor differs')
    new = '\n\n'.join('    const-string v' + str(index) + ', "' + name + '"'
                       for index, name in enumerate(HOME + [ANCHOR]))
    # Six elements require the range encoding; v0..v5 are all dead until HOME
    # is stored. The following HUD initializer redefines every register it uses.
    new += '\n\n    filled-new-array/range {v0 .. v5}, [Ljava/lang/String;'
    patched_body = body.replace(old, new, 1)
    if patched_body.replace(new, old, 1) != body:
        raise ValueError('Unexpected initializer edit')
    return text.replace(body, patched_body, 1)


def build(work: Path, java_home: Path, port: Path, source: Path, previous_assets: Path) -> dict:
    work, port, source = work.resolve(), port.resolve(), source.resolve()
    assets = ROOT / 'assets/advanced12116'
    if work.exists() or sha256_file(source) != SOURCE_SHA256:
        raise ValueError('Need a new work directory and the pinned immutable source')
    work.mkdir(parents=True)
    previous = work / 'previous'
    previous.mkdir()
    originals = {name: (previous_assets.resolve() / name).read_bytes() for name in ('manifest.json', 'recipe.zip')}
    publication_snapshot = {name: (assets / name).read_bytes() for name in originals}
    manifest = json.loads(originals['manifest.json'])
    if digest(originals['recipe.zip']) != PREVIOUS_RECIPE or manifest['recipe_sha256'] != PREVIOUS_RECIPE:
        raise ValueError('Previous recipe pin differs')
    for name, data in originals.items():
        (previous / name).write_bytes(data)
    other_assets = {str(path.relative_to(ROOT)): sha256_file(path)
                    for version in ('advanced1218', 'advanced12110')
                    for path in sorted((ROOT / 'assets' / version).iterdir()) if path.is_file()}
    with ZipFile(previous / 'recipe.zip') as archive:
        if archive.testzip() is not None or len(set(archive.namelist())) != len(archive.namelist()):
            raise ValueError('Previous archive integrity failed')
        payloads = {name: archive.read(name) for name in archive.namelist()}
    if set(payloads) != set(manifest['entries']):
        raise ValueError('Previous payload inventory differs')
    for name, data in payloads.items():
        if manifest['entries'][name] != {'sha256': digest(data), 'bytes': len(data)}:
            raise ValueError('Previous payload pin differs: ' + name)
    source_java = ROOT / 'android-hud/src/local/rc2/hud/ScreenRoles.java'
    java_text = source_java.read_text('utf-8')
    source_home = re.search(r'(?s)String\[\] HOME = \{(.*?)\};', java_text)
    if source_home is None or re.findall(r'"([^"\n]+)"', source_home[1]) != HOME + [ANCHOR]:
        raise ValueError('Java HOME array and patched DEX would differ')
    tools = HudTools(ROOT / 'assets', _short_windows_path(port) / 't')
    bundle = tools.prepare()
    java = java_home.resolve() / 'bin/java.exe'
    classes = work / 'tools'
    classes.mkdir()
    dump_source = work / 'Menu12116DexTool.java'
    dump_source.write_text(DUMP_TOOL, encoding='utf-8')
    libcp = os.pathsep.join(str(path) for path in (bundle / 'lib/apktool.jar', bundle / 'lib/apksigner.jar'))
    run(java.with_name('javac.exe'), '-encoding', 'UTF-8', '-cp', libcp, '-d', classes,
        ROOT / 'android-hud/AdaptiveHudTool.java', ROOT / 'android-hud/FeatureAssemblyTool.java',
        ROOT / 'android-hud/FeatureAuditTool.java', dump_source)
    cp = str(classes) + os.pathsep + libcp
    bridge, feature = work / 'previous-classes23.dex', work / 'classes24.dex'
    bridge.write_bytes(payloads['additions/classes23.dex'])
    feature.write_bytes(payloads['additions/classes24.dex'])
    before = _dex_dump(java, cp, bridge, work / 'before')
    if len(before) != 253 or TYPE not in before:
        raise ValueError('Bridge inventory differs')
    expected = {**before, TYPE: patch_screen_roles(before[TYPE])}
    smali = work / 'smali'
    smali.mkdir()
    for index, (typ, text) in enumerate(expected.items()):
        (smali / ('class-' + str(index) + '.smali')).write_text(text, encoding='utf-8', newline='\n')
    candidate = work / 'classes23.dex'
    count = int(run(java, '-Xmx2560m', '-cp', cp, 'FeatureAssemblyTool', 'assemble', candidate, smali))
    after = _dex_dump(java, cp, candidate, work / 'after')
    if count != 253 or set(before) != set(after):
        raise ValueError('Rebuilt bridge class inventory differs')
    if any(before[typ] != after[typ] for typ in before if typ != TYPE):
        raise ValueError('An unrelated bridge class changed')
    if normalize_smali_encoding(expected[TYPE]) != normalize_smali_encoding(after[TYPE]):
        raise ValueError('Rebuilt ScreenRoles differs from its exact expected edit')
    signatures = re.findall(r'(?m)^\.method [^\n]* (\S+\([^\n]+)$', before[TYPE])
    if any(_method(before[TYPE], signature) != _method(after[TYPE], signature)
           for signature in signatures if signature != '<clinit>()V'):
        raise ValueError('A ScreenRoles method outside its initializer changed')
    # Bind the retained stock/host DEX set to the source and previous recipe.
    audit = port / 'audit-dex'
    audit_hashes = {}
    with ZipFile(source) as archive:
        names = [name for name in archive.namelist() if re.fullmatch(r'classes(?:[0-9]+)?\.dex', name)]
        if len(names) != 22:
            raise ValueError('Expected 22 original source DEX entries')
        for name in names:
            data = payloads.get('replacements/' + name, archive.read(name))
            expected_hash = digest(data)
            if sha256_file(audit / name) != expected_hash:
                raise ValueError('Retained source/host DEX binding differs: ' + name)
            audit_hashes[name] = expected_hash
    run(java, '-Xmx2560m', '-cp', cp, 'FeatureAuditTool', 'check', work / 'dependencies.tsv', audit, candidate, feature)
    if (work / 'dependencies.tsv').read_text('utf-8').strip():
        raise ValueError('Unresolved helper dependency')
    if any(sha256_file(audit / name) != value for name, value in audit_hashes.items()):
        raise ValueError('An audit input changed during validation')
    profile_name = 'additions/' + PROFILE_ENTRY
    profile = json.loads(payloads[profile_name])
    proof = {'revision': 'r14.6.1-home-anchor', 'anchor': ANCHOR, 'class': TYPE,
             'previous_recipe_sha256': PREVIOUS_RECIPE, 'source_java_sha256': sha256_file(source_java),
             'changed_method': '<clinit>()V', 'other_252_bridge_classes_exactly_preserved': True,
             'all_other_screen_roles_methods_exactly_preserved': True}
    profile['home_anchor_hotfix'] = proof
    profile['runtime_verified'] = False
    payloads['additions/classes23.dex'] = candidate.read_bytes()
    payloads[profile_name] = json.dumps(profile, sort_keys=True, ensure_ascii=False).encode('utf-8')
    recipe = work / 'recipe.zip'
    with ZipFile(recipe, 'x', ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            entry = ZipInfo(name, date_time=(2026, 10, 23, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, data, compresslevel=9)
    with ZipFile(recipe) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(payloads):
            raise ValueError('New recipe ZIP integrity failed')
        if any(archive.read(name) != data for name, data in payloads.items()):
            raise ValueError('New recipe bytes differ from audited inputs')
    with ZipFile(previous / 'recipe.zip') as archive:
        changed = sorted(name for name, data in payloads.items() if archive.read(name) != data)
    if changed != sorted(['additions/classes23.dex', profile_name]):
        raise ValueError('Changes extend beyond bridge and profile')
    result = copy.deepcopy(manifest)
    result['recipe_sha256'] = sha256_file(recipe)
    result['entries'] = {name: {'sha256': digest(data), 'bytes': len(data)} for name, data in payloads.items()}
    write_json(work / 'manifest.json', result)
    if sha256_file(source) != SOURCE_SHA256 or any((assets / name).read_bytes() != data for name, data in publication_snapshot.items()):
        raise ValueError('An original changed before publication')
    if any(sha256_file(ROOT / name) != value for name, value in other_assets.items()):
        raise ValueError('Another version recipe changed')
    report = {**proof, 'status': 'PASS_STATIC_HOME_ANCHOR_HOTFIX', 'recipe_sha256': result['recipe_sha256'],
              'changed_payloads': changed, 'bridge_classes': 253, 'feature_classes': 430, 'unresolved_dependencies': 0,
              'source_sha256': SOURCE_SHA256, 'other_version_assets_sha256': other_assets,
              'all_host_dex_and_feature_dex_unchanged': True, 'runtime_verified': False, 'device_commands_sent': False}
    write_json(work / 'report.json', report)
    if digest(publication_snapshot['recipe.zip']) not in (PREVIOUS_RECIPE, result['recipe_sha256']):
        raise ValueError('Refusing to overwrite a different published recipe')
    # Root serializes consumers while this two-file recipe update is published.
    # Keep exact previous bytes available for rollback if the metadata replace fails.
    recipe_tmp, manifest_tmp = assets / 'recipe.zip.home-anchor.new', assets / 'manifest.json.home-anchor.new'
    with recipe_tmp.open('xb') as stream:
        stream.write(recipe.read_bytes())
    with manifest_tmp.open('xb') as stream:
        stream.write((work / 'manifest.json').read_bytes())
    os.replace(recipe_tmp, assets / 'recipe.zip')
    try:
        os.replace(manifest_tmp, assets / 'manifest.json')
    except BaseException:
        recipe_tmp.write_bytes(publication_snapshot['recipe.zip'])
        os.replace(recipe_tmp, assets / 'recipe.zip')
        raise
    if sha256_file(assets / 'recipe.zip') != result['recipe_sha256']:
        raise ValueError('Published recipe hash differs')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--port', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--previous-assets', type=Path, required=True,
                        help='Directory holding the exact reviewed r14.6 recipe/manifest, obtainable from that Git tag')
    args = parser.parse_args()
    build(args.work, args.java_home, args.port, args.source, args.previous_assets)
