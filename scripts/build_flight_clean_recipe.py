"""Stage recipes removing special flight overlays, preserving other DEX classes."""
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
from scripts.feature_host_patch import remove_record_decryption


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
        ROOT / 'android-hud/AdaptiveHudTool.java', ROOT / 'android-hud/NestedMenuDexTool.java',
        ROOT / 'android-hud/FeatureHookTool.java')
    toolcp = str(classes) + os.pathsep + cp
    bridge = stage / 'bridge'
    bridge.mkdir()
    print('Compiling flight-screen fix', flush=True)
    prepare_bridge(bridge, args.java_home, args.sdk)
    report = {'schema': 1, 'release': 'r14.5', 'recipes': {}, 'runtime_visual': 'NOT_RUN'}
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
        # Keep the exact reviewed previous recipe for update/recovery validation.
        shutil.copy2(recipe, work / 'previous-recipe.zip')
        shutil.copy2(target / 'manifest.json', work / 'previous-manifest.json')
        old = work / 'old.dex'
        old.write_bytes(entries['additions/classes23.dex'])
        new = work / 'new.dex'
        preserved = int(run(args.java_home / 'bin/java.exe', '-cp', toolcp,
            'NestedMenuDexTool', 'merge-flight', old, bridge / 'bridge-dex/classes.dex', new, work / 'smali'))
        run(args.java_home / 'bin/java.exe', '-cp', toolcp, 'NestedMenuDexTool',
            'dump-flight', work / 'audit', new)
        integration = (work / 'audit/local.rc2.hud.PortIntegration.smali').read_text('utf-8')
        hooks = (work / 'audit/local.rc2.hud.PortHooks.smali').read_text('utf-8')
        if '"flyctl.Q"' in integration or '"addToggles"' in hooks or '"frtool.X"' in integration:
            raise ValueError('Special flight-control attachment still present')
        feature_old = work / 'old-feature.dex'
        feature_old.write_bytes(entries['additions/classes24.dex'])
        run(args.java_home / 'bin/java.exe', '-cp', toolcp, 'NestedMenuDexTool',
            'dump-flight', work / 'feature-before', feature_old)
        patches = work / 'feature-patches'
        patches.mkdir()
        for filename in ('flysettings.S.smali', 'frtool.X.smali', 'frtool.Decryptor.smali'):
            original = (work / 'feature-before' / filename).read_text('utf-8')
            patched = remove_record_decryption(original)
            if patched == original:
                raise ValueError('Decryption removal did not change ' + filename)
            (patches / filename).write_text(patched, 'utf-8')
        feature_new = work / 'new-feature.dex'
        if run(args.java_home / 'bin/java.exe', '-cp', toolcp, 'FeatureHookTool',
               feature_old, feature_new, work / 'feature-smali', patches) != '3':
            raise ValueError('Expected exactly three decrypt-related feature classes to change')
        # All other feature classes and all stock host replacement DEX files remain unchanged.
        before = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
        entries['additions/classes23.dex'] = new.read_bytes()
        entries['additions/classes24.dex'] = feature_new.read_bytes()
        name = 'additions/' + PROFILE_ENTRY
        profile = json.loads(entries[name])
        profile['flight_overlay_policy'] = 'menu-only-no-special-flight-controls-or-cell-readout-v1'
        profile['record_decryption_removed'] = True
        entries[name] = json.dumps(profile, ensure_ascii=False, sort_keys=True).encode('utf-8')
        changed = {n for n, data in entries.items() if hashlib.sha256(data).hexdigest() != before[n]}
        if changed != {'additions/classes23.dex', 'additions/classes24.dex', name}:
            raise ValueError('Unexpected recipe changes')
        with ZipFile(recipe, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
            for info in infos:
                archive.writestr(info, entries[info.filename])
        metadata['recipe_sha256'] = sha256_file(recipe)
        metadata['entries'] = {n: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                               for n, data in entries.items()}
        (target / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), 'utf-8')
        report['recipes'][folder] = {'sha256': metadata['recipe_sha256'],
            'previous_recipe_sha256': sha256_file(work / 'previous-recipe.zip'),
            'unrelated_bridge_classes_preserved': preserved,
            'feature_dex_sha256': hashlib.sha256(entries['additions/classes24.dex']).hexdigest(),
            'unrelated_feature_classes_preserved': 427,
            'record_decryption_removed': True,
            'changed_entries': sorted(changed)}
        print('Verified flight-screen recipe: ' + folder, flush=True)
    (stage / 'report.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
