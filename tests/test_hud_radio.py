# SPDX-License-Identifier: AGPL-3.0-only
# Profile fixtures: doesthings/FreeFCC v1.5.5 (AGPL-3.0), commit
# 597157bd52120dfeb9677f79a8ad46b6027ce8dc; license: docs/FREEFCC_LICENSE.txt.
"""PC-only pinned-profile and JVM tests. Never contacts a controller or uses ADB."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _crc(data, seed, polynomial):
    """Independent bitwise wire checksum for the public DUML golden fixture."""
    value = seed
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (polynomial if value & 1 else 0)
    return value


@pytest.fixture(scope='module')
def radio_classes(tmp_path_factory):
    output = tmp_path_factory.mktemp('hud-radio-jvm')
    source = ROOT / 'android-hud/src/local/rc2/hud'
    files = [source / (name + '.java') for name in
             ('GroundGate', 'NativeAircraft', 'FlySdk', 'LedJob', 'MutationFence',
              'RadioProtocol', 'RadioDiagnostics', 'RadioTransport', 'NativeRadio',
              'SdkRadioSender', 'SdrRadioProbe')]
    files += sorted((ROOT / 'android-hud/test/local/rc2/hud').glob('Radio*Test.java'))
    subprocess.run(['javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8',
                    '-d', str(output), *map(str, files)], check=True,
                   capture_output=True, text=True, timeout=30)
    return output


@pytest.mark.parametrize('name', ['RadioProtocolTest', 'RadioTransportTest',
                                 'RadioNativeTest', 'RadioDiagnosticsTest', 'RadioOwnerCancellationTest'])
def test_radio_pc_behavior(radio_classes, name):
    result = subprocess.run(['java', '-cp', str(radio_classes),
                             'local.rc2.hud.' + name], check=False,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert name + '_passed' in result.stdout


def test_radio_patch_compiles_with_full_hud_to_android_30_dex(tmp_path):
    """Integration compatibility only; never replaces main's payload or installed APK."""
    sdk = Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk'
    android = sdk / 'platforms/android-30/android.jar'
    compiler = sdk / 'build-tools/36.1.0/lib/d8.jar'
    if not compiler.is_file():
        compiler = sdk / 'build-tools/36.1.0/lib/r8.jar'
    classes = tmp_path / 'classes'
    classes.mkdir()
    sources = sorted((ROOT / 'android-hud/src').rglob('*.java'))
    subprocess.run(['javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8',
                    '-cp', str(android), '-d', str(classes), *map(str, sources)],
                   check=True, capture_output=True, text=True, timeout=30)
    dex = tmp_path / 'dex'
    dex.mkdir()
    subprocess.run(['java', '-cp', str(compiler), 'com.android.tools.r8.D8',
                    '--min-api', '30', '--lib', str(android), '--output', str(dex),
                    *map(str, sorted(classes.rglob('*.class')))], check=True,
                   capture_output=True, text=True, timeout=30)
    assert (dex / 'classes.dex').read_bytes().startswith(b'dex\n')


def test_exact_public_apk_profiles_match_native_frames(radio_classes):
    apk = ROOT / 'assets/freefcc.apk'
    assert hashlib.sha256(apk.read_bytes()).hexdigest() == (
        'da2c7dd3ce389d3bd04334188e5ec0fe060070d9c4ff9cf1127aadecf133f1e4'
    )
    result = subprocess.run(['java', '-cp', str(radio_classes),
                             'local.rc2.hud.RadioProtocolTest', 'dump'], check=True,
                            capture_output=True, text=True, timeout=10)
    rows = [line.split(':') for line in result.stdout.splitlines()]
    with zipfile.ZipFile(apk) as archive:
        for fcc, filename in [('true', 'fcc.json'), ('false', 'ce_restore.json')]:
            # The public bundled APK is sufficient; no ignored/private checkout is needed.
            profile = json.loads(archive.read('assets/profiles/' + filename))
            packets = [bytes.fromhex(row[1]) for row in rows if row[0] == fcc]
            assert len(packets) == len(profile['frames']) * profile['rounds']
            for index, packet in enumerate(packets):
                frame = profile['frames'][index % len(profile['frames'])]
                assert packet[4] == profile['sender']
                assert packet[5] == frame['d']
                assert packet[8:11] == bytes([profile['cmd_type'], frame['s'], frame['i']])
                assert packet[11:-2] == bytes.fromhex(frame['p'])
                payload = bytes.fromhex(frame['p'])
                size = len(payload) + 13
                expected = bytearray([0x55, size & 255, 4 | (size >> 8), 0])
                expected[3] = _crc(expected[:3], 0x77, 0x8C)
                sequence = (0xFFF8 + index % len(profile['frames'])) & 65535
                expected.extend([profile['sender'], frame['d'], sequence & 255,
                                 sequence >> 8, profile['cmd_type'], frame['s'], frame['i']])
                expected.extend(payload)
                expected.extend(_crc(expected, 0x3692, 0x8408).to_bytes(2, 'little'))
                assert packet == expected  # full framing/sequence/CRC, not just payload
            timing = [int(value) for value in next(
                row for row in rows if row[0] == 'timing-' + fcc)[1:]]
            assert timing == [profile[key] for key in
                              ('rounds', 'inter_frame_delay_ms',
                               'inter_round_delay_ms', 'read_window_ms')]
