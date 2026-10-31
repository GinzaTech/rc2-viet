from pathlib import Path
import json
from unittest.mock import Mock
import pytest
from rc2vi import embedded_install as api


@pytest.fixture
def deployment(tmp_path,monkeypatch):
    apk=tmp_path/'reviewed.apk';apk.write_bytes(b'APK fixture')
    monkeypatch.setattr(api,'sha256_file',lambda p:api.SUPPORTED_APK)
    return api.Deployment(apk,tmp_path/'assets',tmp_path/'work','RC2-TEST-A',
                          grounded=True,allow_data_reset=True)


def test_install_requires_explicit_ground_confirmation(tmp_path):
    with pytest.raises(ValueError,match='xác nhận'):
        api.Deployment(tmp_path/'apk',tmp_path,tmp_path/'work','RC2')


@pytest.mark.parametrize('failure', ['INSTALL_FAILED_UPDATE_INCOMPATIBLE',
    'INSTALL_FAILED_SHARED_USER_INCOMPATIBLE', 'INSTALL_FAILED_VERSION_DOWNGRADE'])
def test_data_preserving_update_never_uninstalls_without_consent(deployment,failure):
    deployment.allow_data_reset=False
    deployment.status['original']={'digest':'0'*64}
    deployment.snapshot=Mock(return_value=deployment.status['original'])
    deployment.shell=Mock(side_effect=[deployment.digest+' candidate.apk','Failure ['+failure+']'])
    with pytest.raises(api.DeploymentValidationError,match='chưa được phép xóa dữ liệu'):
        deployment.install()
    assert deployment.shell.call_count==2
    assert not deployment.status.get('uninstall_authorized_started')


def test_same_signer_update_does_not_require_data_reset_consent(deployment):
    job=api.Deployment(deployment.apk,deployment.assets,deployment.work/'preserve',deployment.serial,
                       grounded=True,expected_digest=deployment.digest)
    assert not job.allow_data_reset
    job.status['original']={'digest':'0'*64}
    job.snapshot=Mock(side_effect=[job.status['original'],{'digest':job.digest}])
    job.shell=Mock(side_effect=[job.digest+' candidate.apk','Success'])
    job.install()
    assert job.shell.call_count==2
    assert not job.status.get('uninstall_authorized_started')


def test_wrong_apk_rejected_before_usb_or_chunk_publication(tmp_path,monkeypatch):
    monkeypatch.setattr(api,'sha256_file',lambda p:'0'*64)
    with pytest.raises(ValueError,match='APK không đúng'):
        api.Deployment(tmp_path/'apk',tmp_path,tmp_path/'work','RC2',grounded=True,allow_data_reset=True)
    assert not list((tmp_path/'work').glob('part-*'))


def test_explicit_builder_digest_is_checked_and_not_replaced_with_release_pin(tmp_path):
    import hashlib
    apk=tmp_path/'built.apk';apk.write_bytes(b'fresh locally built APK')
    digest=hashlib.sha256(apk.read_bytes()).hexdigest()
    job=api.Deployment(apk,tmp_path,tmp_path/'work','RC2',grounded=True,allow_data_reset=True,
                       expected_digest=digest,source_digest='a'*64)
    assert job.digest==digest and job.source_digest=='a'*64
    with pytest.raises(ValueError):
        api.Deployment(apk,tmp_path,tmp_path/'bad','RC2',grounded=True,allow_data_reset=True,
                       expected_digest='0'*64)


def test_changed_source_is_rejected_before_upload_or_package_install(deployment):
    deployment.source_digest='a'*64
    deployment.retry=lambda operation,label:operation()
    deployment.snapshot=Mock(return_value={'digest':'b'*64})
    deployment.push_part=Mock();deployment.install=Mock();deployment.close=Mock()
    with pytest.raises(api.DeploymentValidationError,match='đã đổi'):
        deployment.run()
    deployment.push_part.assert_not_called();deployment.install.assert_not_called()


def test_windowed_exe_has_no_stdout_and_still_can_emit(monkeypatch):
    monkeypatch.setattr(api.sys,'stdout',None)
    api.emit('ready','Completed')


@pytest.mark.parametrize('marker',['RC2_FOREGROUND_UNKNOWN','RC2_WAIT_ANDROID_SETTINGS_FLY_IS_OPEN'])
def test_transient_foreground_guard_failure_is_distinct_from_transport_failure(deployment,marker):
    deployment.root=Mock();deployment.root.shell.return_value=marker
    with pytest.raises(api.DeviceUiWait,match=marker):deployment.shell('printf UNUSED')


@pytest.mark.parametrize('marker,power,wakes',[
    ('RC2_FOREGROUND_UNKNOWN','mWakefulness=Awake',0),
    ('RC2_FOREGROUND_UNKNOWN','mWakefulness=Asleep',1),
    ('RC2_WAIT_ANDROID_SETTINGS_FLY_IS_OPEN','mWakefulness=Asleep',0),
])
def test_ui_wait_keeps_usb_and_only_wakes_asleep_device_then_rechecks_guard(deployment,monkeypatch,marker,power,wakes):
    monkeypatch.setattr(api.time,'sleep',lambda seconds:None)
    deployment.root=Mock();deployment.root.shell.return_value=power
    deployment.connect=Mock();deployment.close=Mock()
    operation=Mock(side_effect=[api.DeviceUiWait(marker),'GUARD_PASSED'])
    assert deployment.retry(operation,'upload_part-0011')=='GUARD_PASSED'
    assert operation.call_count==2
    deployment.close.assert_not_called()
    calls=[c.args[0] for c in deployment.root.shell.call_args_list]
    assert sum('input keyevent 224' in c for c in calls)==wakes
    assert all('RC2-TEST-A' in c and 'rc331' in c and 'id -u' in c for c in calls)
    assert not any('settings put' in c or 'pm install' in c or 'keyevent 82' in c for c in calls)


def test_stage_cleanup_requires_verified_final_hash_and_only_removes_owned_parts(deployment):
    deployment.shell=Mock()
    with pytest.raises(api.DeploymentValidationError):deployment.cleanup_verified_stage()
    deployment.shell.assert_not_called()
    deployment.status.update(installed_verified=True,final={'digest':deployment.digest})
    deployment.cleanup_verified_stage()
    command=deployment.shell.call_args.args[0]
    assert 'cd -- '+deployment.remote in command and 'for rc2part in part-0000;' in command
    assert 'candidate.apk candidate.apk.tmp' in command and '"$rc2part.upload"' in command
    assert 'rm -rf' not in command and '/data/app/' not in command
    assert not any(path.exists() for _,path,_ in deployment.parts)
    assert deployment.status['staging_cleanup']=='PASS'


def test_full_31_part_cleanup_fits_legacy_shell_service_and_preserves_scoping(deployment):
    deployment.parts=[]
    for number in range(31):
        name=f'part-{number:04d}'
        path=deployment.work/name;path.write_bytes(b'verified part')
        deployment.parts.append((name,path,'a'*64))
    deployment.status.update(installed_verified=True,final={'digest':deployment.digest})
    calls=[]
    def limited_shell(command,**kwargs):
        calls.append(command)
        if len(command.encode('utf-8'))>=4096:raise RuntimeError('Shell service request exceeds limit')
        return 'RC2_EMBED_COMMAND_OK\n'
    deployment.root=Mock();deployment.root.shell.side_effect=limited_shell
    deployment.cleanup_verified_stage()
    assert deployment.status['staging_cleanup']=='PASS'
    assert 'cd -- '+deployment.remote in calls[0] and '0:700' in calls[0]
    assert all(not path.exists() for _,path,_ in deployment.parts)


def test_cleanup_failure_does_not_report_successful_install_as_failed(deployment):
    deployment.status.update(installed_verified=True,final={'digest':deployment.digest})
    deployment.shell=Mock(side_effect=ConnectionError('USB disconnected after install'))
    deployment.cleanup_verified_stage()
    assert deployment.status['installed_verified'] and deployment.status['staging_cleanup']=='DEFERRED'
    assert all(path.exists() for _,path,_ in deployment.parts)


def test_stop_after_uninstall_prevents_next_install_dispatch_and_keeps_recovery_marker(deployment):
    import threading
    deployment.cancel=threading.Event()
    original={'digest':'0'*64};deployment.status['original']=original
    deployment.snapshot=Mock(return_value=original)
    commands=[]
    def shell(command,**kwargs):
        commands.append(command)
        if 'sha256sum ' in command:result=deployment.digest+' candidate.apk'
        elif 'pm install -r ' in command:result='Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]'
        elif 'pm uninstall dji.go.v5' in command:
            deployment.cancel.set();result='Success'
        else:raise AssertionError('Unexpected dispatch after Stop: '+command)
        return result+'\nRC2_EMBED_COMMAND_OK\n'
    deployment.root=Mock();deployment.root.shell.side_effect=shell
    with pytest.raises(InterruptedError):deployment.install()
    assert deployment.status['uninstall_authorized_started']
    assert len(commands)==3 and not any('pm install --user' in command for command in commands)


def test_external_stop_file_prevents_any_shell_command(deployment):
    deployment.stop_file=deployment.work/'parent-stop'
    deployment.stop_file.write_text('RC2-AUTO-PATCH-STOP')
    deployment.root=Mock()
    with pytest.raises(InterruptedError):deployment.shell('pm uninstall dji.go.v5')
    deployment.root.shell.assert_not_called()


def test_model_guard_accepts_underscore_and_space_variants(deployment):
    command=deployment.root_guard(True)
    assert "tr _ ' '" in command and "'DJI RC 2'" in command
    assert 'RC2-TEST-A' in command and 'rc331' in command and 'sdk)' in command
    assert '*dji.go.v5/*)' in command and 'RC2_WAIT_ANDROID_SETTINGS' in command


def test_upload_failure_never_reaches_package_install(deployment):
    deployment.snapshot=Mock(return_value={'digest':'0'*64})
    deployment.connect=Mock();deployment.close=Mock()
    deployment.retry=lambda operation,label:operation()
    deployment.push_part=Mock(side_effect=RuntimeError('USB disconnected'))
    deployment.install=Mock()
    with pytest.raises(RuntimeError,match='USB disconnected'):
        deployment.run()
    deployment.install.assert_not_called()


def test_incompatible_signature_then_install_has_lost_reply_recovery_marker(deployment):
    original={'digest':'0'*64};deployment.status['original']=original
    deployment.snapshot=Mock(side_effect=[original,{'digest':api.SUPPORTED_APK}])
    deployment.shell=Mock(side_effect=[api.SUPPORTED_APK+' candidate.apk',
        'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]', 'Success','Success'])
    deployment.install()
    assert deployment.status['uninstall_authorized_started'] is True
    calls=[c.args[0] for c in deployment.shell.call_args_list]
    assert 'pm uninstall dji.go.v5' in calls
    assert any('(pm install -r' in c and '; true)' in c for c in calls)
    assert all('other.package' not in c for c in calls)


def test_restart_retains_only_same_serial_and_digest_recovery_state(deployment):
    deployment.status.update(original={'digest':'0'*64},uninstall_authorized_started=True)
    deployment.save()
    again=api.Deployment(deployment.apk,deployment.assets,deployment.work,deployment.serial,
                         grounded=True,allow_data_reset=True)
    assert again.status['original']=={'digest':'0'*64}
    assert again.status['uninstall_authorized_started']
    foreign=api.Deployment(deployment.apk,deployment.assets,deployment.work,'OTHER-RC2',
                           grounded=True,allow_data_reset=True)
    assert 'original' not in foreign.status


def test_already_installed_apk_is_verified_without_upload_or_uninstall(deployment):
    deployment.retry=lambda operation,label:operation()
    deployment.snapshot=Mock(return_value={'digest':api.SUPPORTED_APK})
    deployment.push_part=Mock();deployment.install=Mock();deployment.close=Mock()
    deployment.run()
    assert deployment.status['installed_verified']
    deployment.push_part.assert_not_called();deployment.install.assert_not_called()


def package_dump(version,code):
    return ('Packages:\n  Package [dji.go.v5] (123):\n'
            f'    versionCode={code} minSdk=23 targetSdk=30\n    versionName={version}\n'
            'Hidden system packages:\n  Package [dji.go.v5] (456):\n'
            '    versionCode=3115981 minSdk=23\n    versionName=1.21.10\n')


@pytest.mark.parametrize('version,code',[('1.17.6',117600),('1.21.10',3115981),('2.0.0',4000000)])
def test_snapshot_reads_actual_active_version_instead_of_requiring_target(deployment,version,code):
    deployment.shell=Mock(side_effect=['package:/data/app/fly/base.apk','0'*64+' base.apk',package_dump(version,code)])
    result=deployment.snapshot()
    assert result=={'path':'/data/app/fly/base.apk','digest':'0'*64,'version':version,'code':code}
    assert deployment.status['observed_package']['version']==version
    assert (deployment.work/'package-version.txt').is_file()
    command=deployment.shell.call_args.args[0]
    assert command.startswith('dumpsys package dji.go.v5 | grep -E ')
    assert '^[^[:space:]]' in command


@pytest.mark.parametrize('dump',[
    'versionCode=3115981\nversionName=1.21.10',
    package_dump('',123),package_dump('null',123),
    package_dump('1.17.6',123).replace('    versionName=1.17.6','    versionName=1.17.6\n    versionName=2.0.0'),
    package_dump('1.17.6',123).replace('versionCode=123','versionCode=unknown'),
])
def test_package_metadata_must_be_unambiguous(dump):
    with pytest.raises(api.DeploymentValidationError):api.package_version(dump)


def test_target_hash_still_requires_exact_target_version(deployment):
    deployment.shell=Mock(side_effect=['package:/data/app/fly/base.apk',api.SUPPORTED_APK+' base.apk',package_dump('1.17.6',123)])
    with pytest.raises(api.DeploymentValidationError,match='phiên bản đọc lại khác'):
        deployment.snapshot()


@pytest.mark.parametrize('version,code', [('1.21.8',3115809),('1.21.10',3115981)])
def test_target_readback_uses_selected_version_including_1218(tmp_path, version, code):
    import hashlib
    apk=tmp_path/'candidate.apk';apk.write_bytes(b'candidate')
    digest=hashlib.sha256(apk.read_bytes()).hexdigest()
    job=api.Deployment(apk,tmp_path/'assets',tmp_path/'work','RC2-A',
                       grounded=True,allow_data_reset=True,expected_digest=digest,
                       target_version=version,target_code=code)
    job.shell=Mock(side_effect=['package:/data/app/fly/base.apk',digest+' base.apk',package_dump(version,code)])
    assert job.snapshot()['version']==version
    wrong_version,wrong_code=('1.21.10',3115981) if code==3115809 else ('1.21.8',3115809)
    job.shell=Mock(side_effect=['package:/data/app/fly/base.apk',digest+' base.apk',package_dump(wrong_version,wrong_code)])
    with pytest.raises(api.DeploymentValidationError):job.snapshot()


def test_confirmed_package_validation_failure_does_not_loop_usb_pairing(deployment,monkeypatch):
    deployment.connect=Mock();operation=Mock(side_effect=api.DeploymentValidationError('invalid metadata'))
    sleep=Mock();monkeypatch.setattr(api.time,'sleep',sleep)
    with pytest.raises(api.DeploymentValidationError,match='invalid metadata'):
        deployment.retry(operation,'read_original')
    operation.assert_called_once();deployment.connect.assert_called_once();sleep.assert_not_called()
    assert deployment.status['phase']=='read_original' and deployment.status['last_error']=='invalid metadata'


def test_newer_installed_version_can_be_replaced_after_verified_candidate(deployment):
    original={'digest':'0'*64,'version':'2.0.0','code':4000000};deployment.status['original']=original
    deployment.snapshot=Mock(side_effect=[original,{'digest':api.SUPPORTED_APK}])
    deployment.shell=Mock(side_effect=[api.SUPPORTED_APK+' candidate.apk',
        'Failure [INSTALL_FAILED_VERSION_DOWNGRADE]', 'Success','Success'])
    deployment.install()
    assert deployment.status['uninstall_authorized_started'] is True
    calls=[call.args[0] for call in deployment.shell.call_args_list]
    assert 'sha256sum ' in calls[0]
    assert calls[2]=='pm uninstall dji.go.v5'


def test_apk_upload_disables_compression_and_verifies_before_commit(deployment):
    deployment.stage=Mock();deployment.root=Mock()
    deployment.shell=Mock(side_effect=['','SAFE','a'*64+' part.upload',''])
    deployment.push_part('part-0000',deployment.apk,'a'*64)
    deployment.root.command.assert_called_once_with('push','-Z',str(deployment.apk),
        deployment.remote+'/part-0000.upload',timeout=90)
    assert 'sha256sum ' in deployment.shell.call_args_list[2].args[0]
    assert 'mv -f ' in deployment.shell.call_args_list[3].args[0]


@pytest.mark.parametrize('foreground,navigate',[
    ('dji.go.v5/com.dji.mainpageui.device.DJIDeviceActivity',True),
    ('dji.go.v5/com.dji.fpv.FlightActivity',False),
    ('com.android.settings/.Settings',False),
])
def test_settings_navigation_is_limited_to_ground_consented_fly_home(deployment,monkeypatch,foreground,navigate):
    connection=Mock();connection.alive.return_value=False
    root=Mock();root.shell.side_effect=['RC2_ID_OK',foreground,'Started\nRC2_EMBED_COMMAND_OK\n']
    monkeypatch.setattr(api,'discover_rc2',lambda:[Mock(serial=deployment.serial)])
    monkeypatch.setattr(api,'private_connection',lambda *args:connection)
    monkeypatch.setattr(api,'pin_adb',lambda *args:root)
    deployment.connect()
    starts=[c.args[0] for c in root.shell.call_args_list if 'am start' in c.args[0]]
    assert len(starts)==int(navigate)
