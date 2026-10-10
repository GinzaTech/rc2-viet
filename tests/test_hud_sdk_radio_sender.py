"""Stock SDK radio writes are guarded and verified; fixtures never contact hardware."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_sdk_radio_roundtrip_baseline_cancel_and_no_false_ack_success(tmp_path):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    files = sorted((ROOT / 'android-hud/test/radio-sdk-fixture').rglob('*.java'))
    fixtures = ROOT / 'android-hud/test/forearm-fixture/uav/midware'
    files += [fixtures / 'interfaces/UAVDataCallBack.java', fixtures / 'data/config/P3/Ccode.java']
    files += [source / (name + '.java') for name in
              ('GroundGate', 'NativeAircraft', 'FlySdk', 'LedJob', 'MutationFence',
               'RadioProtocol', 'RadioDiagnostics', 'RadioTransport', 'NativeRadio',
               'SdrRadioProbe', 'SdkRadioSender')]
    files.append(ROOT / 'android-hud/test/local/rc2/hud/SdkRadioSenderTest.java')
    result = subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                             *map(str, files)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.SdkRadioSenderTest'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'sdk_radio_sender_passed' in result.stdout
