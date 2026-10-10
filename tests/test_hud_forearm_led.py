"""Grounded parameter transaction tests; no aircraft commands or physical LED claims."""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name', ['ForearmLedTransactionFenceTest', 'ForearmLedToggleTest', 'MutationFenceObserverTest'])
def test_forearm_toggle_and_transaction_fence(tmp_path, name):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    files = [source / (item + '.java') for item in
             ('GroundGate', 'LedJob', 'MutationFence', 'ForearmLedJob')]
    tests = ROOT / 'android-hud/test/local/rc2/hud'
    files += [tests / 'ForearmLedJobTest.java', tests / (name + '.java')]
    result = subprocess.run(['javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8', '-d', str(tmp_path),
                             *map(str, files)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.' + name],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'passed' in result.stdout


def test_forearm_read_modify_write_guards_and_reconciliation(tmp_path):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    files = [source / (name + '.java') for name in
             ('GroundGate', 'LedJob', 'MutationFence', 'ForearmLedJob')]
    files.append(ROOT / 'android-hud/test/local/rc2/hud/ForearmLedJobTest.java')
    result = subprocess.run(['javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8', '-d', str(tmp_path),
                             *map(str, files)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.ForearmLedJobTest'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'forearm_led_job_passed' in result.stdout


def test_forearm_set_bridge_dispatch_identity_and_errors(tmp_path):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    files = sorted((ROOT / 'android-hud/test/sdk-fixture').rglob('*.java'))
    files += sorted((ROOT / 'android-hud/test/forearm-fixture').rglob('*.java'))
    files += sorted((ROOT / 'android-hud/test/forearm-write-fixture').rglob('*.java'))
    files += [source / (name + '.java') for name in
              ('GroundGate', 'LedJob', 'MutationFence', 'ForearmLedJob',
               'FlySdk', 'NativeAircraft', 'ForearmParamProbe', 'NativeForearmLed')]
    files.append(ROOT / 'android-hud/test/local/rc2/hud/ForearmSetBridgeTest.java')
    result = subprocess.run(['javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8', '-d', str(tmp_path),
                             *map(str, files)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.ForearmSetBridgeTest'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'forearm_set_bridge_passed' in result.stdout


@pytest.mark.parametrize('name', ['NativeLedToggleTest', 'NativeLedPrepFailureTest'])
def test_native_front_rear_toggle_delegates_to_fresh_parameter_and_readback(tmp_path, name):
    source = ROOT / 'android-hud/src/local/rc2/hud'
    files = sorted((ROOT / 'android-hud/test/sdk-fixture').rglob('*.java'))
    files += sorted((ROOT / 'android-hud/test/forearm-fixture').rglob('*.java'))
    files += sorted((ROOT / 'android-hud/test/forearm-write-fixture').rglob('*.java'))
    files += [source / (name + '.java') for name in
              ('GroundGate', 'LedJob', 'MutationFence', 'ForearmLedJob', 'NativeLed',
               'FlySdk', 'NativeAircraft', 'ForearmParamProbe', 'NativeForearmLed')]
    files.append(ROOT / 'android-hud/test/local/rc2/hud' / (name + '.java'))
    result = subprocess.run(['javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8', '-d', str(tmp_path),
                             *map(str, files)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.' + name],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'passed' in result.stdout
