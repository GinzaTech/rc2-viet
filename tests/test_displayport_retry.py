from pathlib import Path
import subprocess
import pytest
from rc2vi.displayport_access import enable_session, permission_command, HPD


def test_displayport_request_and_cleanup_on_jvm(tmp_path):
    root = Path(__file__).resolve().parents[1]
    files = [root / 'android-hud/src/local/rc2/hud/DisplayPortRetry.java',
             root / 'android-hud/test/local/rc2/hud/DisplayPortRetryTest.java']
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path), *map(str, files)],
                   check=True, capture_output=True, timeout=30)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.DisplayPortRetryTest'],
                            check=True, capture_output=True, text=True, timeout=15)
    assert 'displayport_retry_passed' in result.stdout


@pytest.mark.parametrize('uid', [0, 2000, 9999, 20000, True, '10023;id'])
def test_never_grants_to_unexpected_identity(uid):
    with pytest.raises(ValueError):permission_command(uid)


class Device:
    def __init__(self, digest='a'*64, identity='package:dji.go.v5 uid:10023'):
        self.digest,self.identity,self.writes=digest,identity,[]
    def snapshot(self):return {'digest':self.digest}
    def shell(self, command, mutating=True):
        if not mutating:return self.identity
        self.writes.append(command)


def test_scoped_permission_and_boot_limit():
    device=Device();result=enable_session(device,'a'*64)
    assert device.writes==[permission_command(10023)]
    assert f'chgrp 10023 {HPD}' in device.writes[0]
    assert f'chmod 660 {HPD}' in device.writes[0]
    assert result['reboot_requires_reactivation'] and not result['physical_output_verified']


@pytest.mark.parametrize('device', [Device('b'*64),Device(identity='package:dji.go.v5 uid:1000'),
                                  Device(identity='package:other uid:10023'),
                                  Device(identity='package:dji.go.v5 uid:10023\npackage:other uid:10024')])
def test_changed_apk_or_ambiguous_uid_never_grants(device):
    with pytest.raises(ValueError):enable_session(device,'a'*64)
    assert not device.writes
