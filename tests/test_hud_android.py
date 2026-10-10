"""Runnable JVM behavior tests; these do not claim an Android device UI pass."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_triple_tap_delegation_led_frames_transport_and_cancellation(tmp_path):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    files = [source / 'TouchDispatch.java']
    files.extend(ROOT / 'android-hud/test/legacy' / (name + '.java') for name in
                 ('TripleTap', 'LedProtocol', 'LedClient'))
    files.append(ROOT / 'android-hud/test/local/rc2/hud/HudInteractionTest.java')
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                    *map(str, files)], check=True, capture_output=True)
    result = subprocess.run(['java', '-cp', str(tmp_path),
                             'local.rc2.hud.HudInteractionTest'], check=True,
                            capture_output=True, text=True, timeout=30)
    assert 'hud_interactions_passed' in result.stdout


def test_double_tap_requires_two_short_nearby_preview_taps(tmp_path):
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                    str(ROOT / 'android-hud/src/local/rc2/hud/DoubleTap.java'),
                    str(ROOT / 'android-hud/test/local/rc2/hud/DoubleTapTest.java')],
                   check=True, capture_output=True)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.DoubleTapTest'],
                            check=True, capture_output=True, text=True)
    assert 'double_tap_passed' in result.stdout


def test_led_gate_blocks_airborne_armed_stale_and_unknown_state(tmp_path):
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                    str(ROOT / 'android-hud/src/local/rc2/hud/GroundGate.java'),
                    str(ROOT / 'android-hud/test/local/rc2/hud/GroundGateTest.java')], check=True, capture_output=True)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.GroundGateTest'],
                            check=True, capture_output=True, text=True)
    assert 'ground_gate_passed' in result.stdout


def test_native_led_transaction_readback_timeout_and_lifecycle(tmp_path):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                    str(source / 'GroundGate.java'), str(source / 'LedJob.java'),
                    str(ROOT / 'android-hud/test/local/rc2/hud/LedJobTest.java')],
                   check=True, capture_output=True)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.LedJobTest'],
                            check=True, capture_output=True, text=True, timeout=15)
    assert 'led_job_passed' in result.stdout


def test_reflective_sdk_bridge_preserves_fields_and_rejects_unknown_values(tmp_path):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    fixtures = sorted((ROOT / 'android-hud/test/sdk-fixture').rglob('*.java'))
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                    *map(str, fixtures), str(source / 'GroundGate.java'),
                    str(source / 'LedJob.java'), str(source / 'FlySdk.java'),
                    str(ROOT / 'android-hud/test/local/rc2/hud/FlySdkTest.java')],
                   check=True, capture_output=True)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.FlySdkTest'],
                            check=True, capture_output=True, text=True, timeout=15)
    assert 'fly_sdk_passed' in result.stdout


def test_menu_centers_on_full_anchor_even_when_visible_rect_is_clipped(tmp_path):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                    str(source / 'MenuPlacement.java'),
                    str(ROOT / 'android-hud/test/local/rc2/hud/MenuPlacementTest.java')],
                   check=True, capture_output=True)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.MenuPlacementTest'],
                            check=True, capture_output=True, text=True, timeout=15)
    assert 'menu_placement_passed' in result.stdout


def test_every_flight_state_callback_respects_cancellation_and_duplicates(tmp_path):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    fixtures = sorted((ROOT / 'android-hud/test/sdk-fixture').rglob('*.java'))
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                    *map(str, fixtures), *[str(source / (name + '.java')) for name in
                    ('GroundGate', 'LedJob', 'FlySdk', 'NativeAircraft')],
                    str(ROOT / 'android-hud/test/local/rc2/hud/NativeAircraftTest.java')],
                   check=True, capture_output=True)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.NativeAircraftTest'],
                            check=True, capture_output=True, text=True, timeout=15)
    assert 'native_aircraft_passed' in result.stdout


def test_unresolved_led_write_is_excluded_across_activity_recreation(tmp_path):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    fixtures = sorted((ROOT / 'android-hud/test/sdk-fixture').rglob('*.java'))
    fixtures += sorted((ROOT / 'android-hud/test/forearm-fixture').rglob('*.java'))
    fixtures += sorted((ROOT / 'android-hud/test/forearm-write-fixture').rglob('*.java'))
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                    *map(str, fixtures), *[str(source / (name + '.java')) for name in
                    ('GroundGate', 'LedJob', 'FlySdk', 'NativeAircraft', 'MutationFence', 'NativeLed',
                     'ForearmLedJob', 'NativeForearmLed', 'ForearmParamProbe')],
                    str(ROOT / 'android-hud/test/local/rc2/hud/NativeLedFenceTest.java')],
                   check=True, capture_output=True)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.NativeLedFenceTest'],
                            check=True, capture_output=True, text=True, timeout=15)
    assert 'native_led_fence_passed' in result.stdout


def test_full_hud_source_compiles_against_android_11(tmp_path):
    sdk = Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk'
    sources = sorted((ROOT / 'android-hud/src').rglob('*.java'))
    subprocess.run(['javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8',
                    '-cp', str(sdk / 'platforms/android-30/android.jar'),
                    '-d', str(tmp_path), *map(str, sources)], check=True,
                   capture_output=True)
    dex = tmp_path / 'dex'
    dex.mkdir()
    r8 = sdk / 'build-tools/36.1.0/lib/d8.jar'
    if not r8.is_file():
        r8 = sdk / 'build-tools/36.1.0/lib/r8.jar'
    subprocess.run(['java', '-cp', str(r8), 'com.android.tools.r8.D8', '--min-api', '30',
                    '--lib', str(sdk / 'platforms/android-30/android.jar'), '--output', str(dex),
                    *map(str, sorted(tmp_path.rglob('*.class')))], check=True, capture_output=True)
    assert (dex / 'classes.dex').read_bytes() == (ROOT / 'assets/hud/classes23.dex').read_bytes()
    assert b'LedClient' not in (dex / 'classes.dex').read_bytes()
    assert b'LedProtocol' not in (dex / 'classes.dex').read_bytes()
