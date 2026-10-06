import pytest
from rc2vi.developer import enable_developer_options,COMPONENT

class FakeAdb:
    def __init__(self,device='rc331',root=True,sdk='30',saved='1',launch_ok=True):
        self.device=device;self.root=root;self.sdk=sdk;self.saved=saved;self.launch_ok=launch_ok;self.changes=[]
    def shell(self,command,timeout=20):
        if command=='getprop ro.product.device':return self.device
        if command=='getprop ro.build.version.sdk':return self.sdk
        if command=='id':return 'uid=0(root)' if self.root else 'uid=2000(shell)'
        if command.startswith('cmd package resolve-activity'):return COMPONENT
        if command=='settings get global development_settings_enabled':return self.saved
        self.changes.append(command)
        if command.startswith('pm enable'):return 'new state: enabled'
        if command.startswith('am start'):return 'Status: ok' if self.launch_ok else 'Error: Activity not found'
        return ''

@pytest.mark.parametrize('args',[{'device':'mondrian'},{'root':False},{'sdk':'35'}])
def test_wrong_device_or_privilege_does_not_change_settings(args):
    adb=FakeAdb(**args)
    with pytest.raises(ValueError):enable_developer_options(adb)
    assert adb.changes==[]

def test_enable_and_open_uses_existing_system_component():
    adb=FakeAdb()
    result=enable_developer_options(adb)
    assert result['status']=='developer_enabled'
    assert any(COMPONENT in command for command in adb.changes)
    assert not any('adb_enabled' in command or 'adb_allowed_connection_time' in command or 'install' in command for command in adb.changes)

def test_failed_readback_is_not_reported_as_success():
    with pytest.raises(RuntimeError,match='xác nhận'):enable_developer_options(FakeAdb(saved='0'))

def test_launch_error_is_reported():
    with pytest.raises(RuntimeError,match='mở'):enable_developer_options(FakeAdb(launch_ok=False))
