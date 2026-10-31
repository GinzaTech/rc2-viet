"""Stage refreshed UI recipes, preserving every non-menu DEX class and asset."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rc2vi.hud_capsule import PROFILE_ENTRY
from rc2vi.hud_tools import HudTools, sha256_file
from scripts.build_feature_candidate import prepare_bridge, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    args = parser.parse_args()
    stage = args.work.absolute()
    stage.mkdir(parents=True, exist_ok=False)
    assets = stage / 'assets'
    shutil.copytree(ROOT / 'assets', assets)
    bundle = HudTools(assets, stage / 'tools').prepare()
    cp = os.pathsep.join(str(bundle / 'lib' / n) for n in ('apktool.jar', 'apksigner.jar'))
    classes = stage / 'classes'
    classes.mkdir()
    run(args.java_home / 'bin/javac.exe', '-encoding', 'UTF-8', '-cp', cp, '-d', classes,
        ROOT / 'android-hud/AdaptiveHudTool.java', ROOT / 'android-hud/NestedMenuDexTool.java')
    bridge = stage / 'bridge'
    bridge.mkdir()
    print('Compiling refreshed menu', flush=True)
    prepare_bridge(bridge, args.java_home, args.sdk)
    titles = ['Nâng cao', 'Hiệu chỉnh gimbal']
    hierarchy = {'parent': 'Tiện ích nâng cao', 'children': titles}
    report = {'layout': 'rc2-dual-utilities-r13', 'menu_hierarchy': hierarchy, 'recipes': {}, 'runtime_visual': 'NOT_RUN'}
    for folder in ('advanced1218', 'advanced12110'):
        target = assets / folder
        metadata = json.loads((target / 'manifest.json').read_text('utf-8'))
        recipe = target / 'recipe.zip'
        if sha256_file(recipe) != metadata['recipe_sha256']:
            raise ValueError('Recipe checksum mismatch: ' + folder)
        with ZipFile(recipe) as archive:
            infos = archive.infolist()
            entries = {info.filename: archive.read(info.filename) for info in infos}
        work = stage / folder
        work.mkdir()
        old = work / 'old.dex'
        old.write_bytes(entries['additions/classes23.dex'])
        new = work / 'new.dex'
        preserved = int(run(args.java_home / 'bin/java.exe', '-cp', str(classes) + os.pathsep + cp,
            'NestedMenuDexTool', 'merge-ui', old, bridge / 'bridge-dex/classes.dex', new, work / 'smali'))
        entries['additions/classes23.dex'] = new.read_bytes()
        name = 'additions/' + PROFILE_ENTRY
        profile = json.loads(entries[name])
        profile['layout_version'] = report['layout']
        profile['displayport_retry'] = 'hpd-retry-v1'
        profile['menu_hierarchy'] = hierarchy
        profile['visible_menu_sections'] = titles
        for row in profile.get('feature_adjustments', []):
            mapped = ['advanced_and_gimbal_menu' if c in ('full_five_section_menu',
                       'only_advanced_and_gimbal_menu') else c for c in row.get('changes', [])]
            row['changes'] = list(dict.fromkeys(mapped))
        entries[name] = json.dumps(profile, ensure_ascii=False, sort_keys=True).encode('utf-8')
        with ZipFile(recipe, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
            for info in infos:
                archive.writestr(info, entries[info.filename])
        metadata['recipe_sha256'] = sha256_file(recipe)
        metadata['menu_hierarchy'] = hierarchy
        metadata['visible_menu_sections'] = titles
        metadata['entries'] = {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                               for name, data in entries.items()}
        (target / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), 'utf-8')
        report['recipes'][folder] = {'sha256': metadata['recipe_sha256'],
            'non_menu_bridge_classes_preserved': preserved,
            'feature_dex_sha256': hashlib.sha256(entries['additions/classes24.dex']).hexdigest()}
        print('Verified UI merge: ' + folder, flush=True)
    (stage / 'report.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
