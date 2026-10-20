"""Build RC2 r14.4 with USB authorization retries and existing Animation ZIPs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.stage_advanced_assets import stage_assets
from rc2vi.hud_tools import sha256_file
from rc2vi.auto_patch import TRANSLATION_SHA256
from rc2vi.fly_versions import FLY_1218, SUPPORTED


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-root', type=Path, required=True)
    args = parser.parse_args()
    build = args.build_root.absolute()
    build.mkdir(parents=True, exist_ok=True)
    stage = build / 'assets'
    inventory = stage_assets(ROOT / 'assets', stage)
    recipe_target = stage / FLY_1218.recipe_directory
    recipe_target.mkdir()
    for name in ('manifest.json', 'recipe.zip'):
        shutil.copy2(ROOT / 'assets' / FLY_1218.recipe_directory / name, recipe_target / name)
        inventory.append(FLY_1218.recipe_directory + '/' + name)
    target = stage / 'auto12110'
    target.mkdir()
    for name in ('manifest.json', 'vietnamese.arsc'):
        shutil.copy2(ROOT / 'assets/auto12110' / name, target / name)
        inventory.append('auto12110/' + name)
    assert sha256_file(target / 'vietnamese.arsc') == TRANSLATION_SHA256
    assert not any(p.suffix.lower() in {'.p12', '.jks', '.keystore', '.dpapi'} for p in stage.rglob('*'))
    assert all(p.stat().st_size < 64 * 1024**2 for p in stage.rglob('*.apk'))
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
                    '--name', 'RC2-TuDong-Patch-r14.4', '--specpath', str(build / 'spec'),
                    '--workpath', str(build / 'work'), '--distpath', str(ROOT / 'dist'),
                    '--version-file', str(ROOT / 'packaging/usb-retry-windows-version.txt'),
                    '--hidden-import', 'PIL.ImageTk', '--hidden-import', 'PIL.ImageGrab',
                    '--collect-data', 'customtkinter',
                    '--copy-metadata', 'customtkinter', '--copy-metadata', 'darkdetect',
                    '--add-data', str(stage) + ';assets', str(ROOT / 'auto_patch_app.py')], cwd=ROOT, check=True)
    exe = ROOT / 'dist/RC2-TuDong-Patch-r14.4.exe'
    from rc2vi.animation import EFFECTS, LOOP_EFFECTS, PRESETS
    report = {'exe': str(exe), 'sha256': sha256_file(exe), 'bytes': exe.stat().st_size,
              'full_fly_apk_embedded': False, 'private_signing_key_embedded': False,
              'python_install_required': False, 'java_install_required': False,
              'network_required': False, 'embedded_vietnamese': True,
              'animation_editor': True, 'animation_effects': dict(EFFECTS),
              'animation_loop_effects': dict(LOOP_EFFECTS), 'animation_presets': dict(PRESETS),
              'animation_projects_portable': True, 'animation_device_tested_this_release': False,
              'desktop_style': 'rounded-dark-mint', 'desktop_ui_revision': 'r14.4',
              'usb_manual_authorization_retry': True, 'usb_pending_retry_seconds': 10,
              'animation_existing_zip_install': True,
              'animation_single_window': True, 'animation_back_preserves_draft': True,
              'animation_upload_permissions': 'reassert-and-verify-after-push',
              'animation_preview_update': 'frame-coalesced', 'idle_button_updates': 'idempotent',
              'desktop_ui_toolkit': 'CustomTkinter 5.2.2',
              'translation_revision': 'r13.1-resource-initialization-wording',
              'menu_features': ['Đèn càng', 'Chạm 2 lần để ẩn HUD', 'Xuất hình', 'FCC', 'EC / gốc',
                                'Nâng cao', 'Hiệu chỉnh gimbal'],
              'recipes': {p.version: json.loads((stage / p.recipe_directory / 'manifest.json').read_text('utf-8'))['recipe_sha256']
                          for p in SUPPORTED},
              'asset_inventory': {name: sha256_file(stage / name) for name in sorted(inventory)}}
    (build / 'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'asset_inventory'}))


if __name__ == '__main__':
    main()
