"""Private, bounded recovery archives; all device operations use injected fakes."""
import hashlib
import io
import os
from pathlib import Path
import shlex
import tarfile

import pytest


def test_backup_excludes_only_fixed_transient_crashlytics_directories(tmp_path):
    from rc2vi.hud_backup import HudBackup,PRIVATE_ROOTS,PACKAGE
    backup=HudBackup(tmp_path,lambda *a:None)
    command=backup._archive_command('/data/local/tmp/test/data.tar')
    for root in PRIVATE_ROOTS:
        assert '--exclude='+root+'/files/.com.google.firebase.crashlytics.files.v2:'+PACKAGE in command
    assert '--exclude=files' not in command and '--exclude=*' not in command

from rc2vi import hud_backup as backend


def archive_bytes(entries=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        for name, kind, data in (entries or [
            ('data/user/0/dji.go.v5', 'dir', b''),
            ('data/user/0/dji.go.v5/files/state', 'file', b'synthetic-state'),
            ('data/user_de/0/dji.go.v5', 'dir', b''),
            ('data/media/0/Android/data/dji.go.v5', 'dir', b''),
        ]):
            entry = tarfile.TarInfo(name)
            entry.uid = entry.gid = 10029
            if name.startswith('data/media/'):
                entry.uid = entry.gid = 1023
            if kind == 'dir':
                entry.type = tarfile.DIRTYPE
            elif kind in {'link', 'hardlink'}:
                entry.type = tarfile.SYMTYPE if kind == 'link' else tarfile.LNKTYPE
                entry.linkname = data.decode()
            else:
                entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data) if kind == 'file' else None)
    return output.getvalue()


class BackupAdb:
    serial = 'RC2TEST'

    def __init__(self, raw=None):
        self.raw = raw if raw is not None else archive_bytes()
        self.files = {'/data/app/dji.go.v5/base.apk': b'prior-apk'}
        self.calls = []
        self.disconnect = False
        self.bad_size = False
        self.bad_hash = False
        self.pull_fail = False
        self.labels = 'u:object_r:app_data_file:s0:c1,c2'
        self.find_failed = False
        self.stage_owner = '0'
        self.external_owner = '1023:1023'
        self.external_label = 'u:object_r:media_rw_data_file:s0'
        self.stage_inode = '8:77'
        self.stage_symlink = False

    def bind(self, target):
        owner = self
        class Bound:
            serial = target
            def shell(self, cmd, **kwargs):
                # Simulate the physical-serial guard in one remote shell session.
                if cmd.startswith('if [ "$(getprop ro.serialno)"'):
                    expected, cmd = cmd.split('; fi; ', 1)
                    physical = getattr(owner, 'physical', owner.serial)
                    if physical != shlex.split(expected)[4]:
                        return 'RC2VI_HUD_WRONG_DEVICE'
                return owner.shell(cmd, **kwargs)
            def command(self, *args, **kwargs):
                return owner.command(*args, **kwargs)
        return Bound()

    def command(self, *args, **kwargs):
        self.calls.append(args)
        if self.disconnect or self.pull_fail:
            raise ConnectionError('synthetic-disconnection')
        if args[0] == 'pull':
            Path(args[2]).write_bytes(self.files[args[1]])
        elif args[0] == 'push':
            self.files[args[2]] = Path(args[1]).read_bytes()
        return ''

    def shell(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.disconnect:
            raise ConnectionError('synthetic-disconnection')
        words = shlex.split(cmd)
        if (self.stage_symlink and cmd.startswith('[ -d /data/local/tmp/rc2vi-hud-data-')):
            return ''
        if words[0] == 'cd' and '$(stat -c %d:%i .)' in words:
            index = words.index('$(stat -c %d:%i .)')
            if words[index + 2] != self.stage_inode:
                return ''
        if cmd == 'getprop ro.serialno':
            return self.serial
        if cmd == 'id':
            return 'uid=0(root)'
        if cmd.startswith('if [ ! -e /data/local/tmp/rc2vi-hud-data-') and 'RC2VI_HUD_ABSENT' in cmd:
            remote = words[4]
            return 'RC2VI_HUD_ABSENT' if not any(name.startswith(remote + '/') for name in self.files) else ''
        if cmd.startswith('stat -c %u:%a'):
            return self.stage_owner + ':700'
        if cmd.startswith('stat -c %u:%g'):
            return self.external_owner
        if cmd.startswith('stat -c %d:%i'):
            return self.stage_inode
        if cmd.startswith('stat -c %u'):
            return self.stage_owner if '/data/local/tmp/rc2vi-hud-data-' in cmd else '10031'
        if cmd.startswith('ls -Zd '):
            return self.external_label if '/data/media/' in cmd else self.labels
        if words[0] == 'stat':
            data = self.files.get(words[-1], self.raw)
            return str(len(data) + (512 if self.bad_size else 0))
        if words[0] == 'sha256sum':
            data = self.files.get(words[1], self.raw)
            return checksum(cmd, '0' * 64 if self.bad_hash else hashlib.sha256(data).hexdigest())
        if words[0] == 'tar' and '-cpf' in words:
            self.files[words[words.index('-cpf') + 1]] = self.raw
        if words[0] == 'cp':
            self.files[words[2]] = self.files[words[1]]
        if words[0] == 'dd':
            values = dict(word.split('=', 1) for word in words[1:] if '=' in word)
            size = int(values['bs'])
            start = int(values['skip']) * size
            self.files[values['of']] = self.files[values['if']][start:start + int(values['count']) * size]
        if words[0] == 'umask' and ': >' in cmd:
            self.files[words[words.index('>') + 1]] = b''
        if 'cat' in words and '>>' in words:
            self.files[words[words.index('>>') + 1]] += self.files[words[words.index('cat') + 1]]
        if 'rm' in words:
            start = words.index('rm')
            for name in words[start + 1:words.index('&&', start)]:
                if not name.startswith('-'):
                    if words[0] == 'cd':
                        name = words[1] + '/' + name
                    self.files.pop(name, None)
            root = words[words.index('rmdir') + 2]
            if any(name.startswith(root + '/') for name in self.files):
                return ''
        if cmd.startswith('find '):
            return '' if self.find_failed else 'RC2VI_HUD_OK'
        if cmd.startswith('wc -l '):
            return '0'
        return 'RC2VI_HUD_OK'


def backup(tmp_path, adb=None):
    adb = adb or BackupAdb()
    service = backend.HudBackup(tmp_path, lambda *event: None)
    state = {'serial': adb.serial, 'apk_path': '/data/app/dji.go.v5/base.apk',
             'digest': hashlib.sha256(b'prior-apk').hexdigest(), 'uid': 10029}
    return service, adb, state


@pytest.mark.parametrize('entry', [
    ('data/user/0/other/files/x', 'file', b'x'),
    ('/data/user/0/dji.go.v5/files/x', 'file', b'x'),
    ('data/user/0/dji.go.v5/../other/x', 'file', b'x'),
    ('data/user/0/dji.go.v5/files/link', 'link', b'/etc/passwd'),
    ('data/user/0/dji.go.v5/files/link', 'hardlink', b'data/user/0/other/x'),
    ('data/user/0/dji.go.v5/lib', 'link', b'/data/app/lib'),
    ('data/user/0/dji.go.v5/code_cache/x', 'file', b'x'),
    ('data/user/0/dji.go.v5\\files\\x', 'file', b'x'),
])
def test_archive_rejects_paths_links_and_excluded_native_cache(tmp_path, entry):
    path = tmp_path / 'data.tar'
    path.write_bytes(archive_bytes([entry]))
    with pytest.raises(ValueError):
        backend.validate_archive(path)


def test_archive_rejects_truncation_and_hidden_trailing_archive(tmp_path):
    path = tmp_path / 'data.tar'
    raw = archive_bytes()
    for value in [raw[:-512] + b'x' * 512, raw[:512], raw + archive_bytes()]:
        path.write_bytes(value)
        with pytest.raises(ValueError):
            backend.validate_archive(path)


def test_backup_stops_app_and_retains_verified_apk_privately(tmp_path):
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    service.verify(result)
    assert Path(result['archive']).read_bytes() == adb.raw
    assert Path(result['apk']).read_bytes() == b'prior-apk'
    commands = [item for item in adb.calls if isinstance(item, str)]
    assert next(i for i, cmd in enumerate(commands) if 'force-stop' in cmd) < next(
        i for i, cmd in enumerate(commands) if cmd.startswith('tar '))
    tar = next(cmd for cmd in commands if cmd.startswith('tar '))
    assert 'code_cache' in tar and '/lib' in tar and ' -C / ' in tar
    assert 'chmod 700' in ' '.join(commands) and 'chmod 600' in ' '.join(commands)
    assert not any('uninstall' in cmd or 'pm clear' in cmd for cmd in commands)
    if os.name != 'nt':
        assert Path(result['archive']).stat().st_mode & 0o777 == 0o600
        assert Path(result['directory']).stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('flag', ['bad_size', 'bad_hash', 'pull_fail'])
def test_backup_failure_never_produces_verified_recovery(tmp_path, flag):
    service, adb, state = backup(tmp_path)
    setattr(adb, flag, True)
    with pytest.raises((ValueError, RuntimeError, ConnectionError)):
        service.create(adb, state)


def test_chunked_download_is_complete_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'CHUNK_SIZE', 1024)
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    assert Path(result['archive']).read_bytes() == adb.raw
    assert any(isinstance(cmd, str) and cmd.startswith('dd ') for cmd in adb.calls)
    assert not list(Path(result['directory']).glob('*.part'))


def test_backup_tampering_is_rejected_before_restore(tmp_path):
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    Path(result['archive']).write_bytes(archive_bytes([('data/user/0/dji.go.v5', 'dir', b'')]))
    with pytest.raises(ValueError):
        service.verify(result)


def test_restore_stops_before_extract_maps_ownership_and_restores_labels(tmp_path):
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    helper = tmp_path / 'restore-owner'
    helper.write_bytes(b'synthetic-native-helper')
    adb.calls.clear()
    service.restore(adb, result, 10031, helper, hashlib.sha256(helper.read_bytes()).hexdigest())
    calls = [cmd for cmd in adb.calls if isinstance(cmd, str)]
    assert next(i for i, cmd in enumerate(calls) if 'force-stop' in cmd) < next(
        i for i, cmd in enumerate(calls) if cmd.startswith('tar -x'))
    assert any('restore-owner 10029 10031' in cmd for cmd in calls)
    assert any('restorecon -RF' in cmd for cmd in calls)
    assert not any('chown -R' in cmd or 'pm clear' in cmd for cmd in calls)


def test_restore_disconnection_never_reports_restored(tmp_path):
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    adb.disconnect = True
    with pytest.raises(ConnectionError):
        service.restore(adb, result, 10031, tmp_path / 'restore-owner', 'a' * 64)


def test_freshness_rejects_userdata_changed_after_confirmation(tmp_path):
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    adb.raw = archive_bytes([
        ('data/user/0/dji.go.v5', 'dir', b''),
        ('data/user/0/dji.go.v5/files/changed', 'file', b'changed'),
        ('data/user_de/0/dji.go.v5', 'dir', b''),
        ('data/media/0/Android/data/dji.go.v5', 'dir', b''),
    ])
    with pytest.raises(ValueError):
        service.check_fresh(adb, result)
    assert not any(isinstance(cmd, str) and 'uninstall' in cmd for cmd in adb.calls)


@pytest.mark.parametrize('unsafe', ['find_failed', 'labels'])
def test_restore_requires_successful_link_scan_and_selinux_verification(tmp_path, unsafe):
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    helper = tmp_path / 'restore-owner'
    helper.write_bytes(b'synthetic-native-helper')
    setattr(adb, unsafe, True if unsafe == 'find_failed' else 'u:object_r:wrong_label:s0')
    with pytest.raises((ValueError, RuntimeError)):
        service.restore(adb, result, 10031, helper, hashlib.sha256(helper.read_bytes()).hexdigest())


@pytest.mark.parametrize('uid', [-1, 0, 9999, 20000, True, '10029'])
def test_uid_mapping_rejects_non_app_and_non_numeric_uid(uid):
    with pytest.raises(ValueError):
        backend.valid_uid(uid)


def test_large_restore_archive_upload_uses_verified_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'CHUNK_SIZE', 1024)
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    helper = tmp_path / 'restore-owner'
    helper.write_bytes(b'synthetic-native-helper')
    adb.calls.clear()
    service.restore(adb, result, 10031, helper, hashlib.sha256(helper.read_bytes()).hexdigest())
    assert not any(isinstance(call, tuple) and call[0] == 'push' and call[1] == result['archive']
                   for call in adb.calls)
    assert adb.files[result['remote'] + '/restore.tar'] == adb.raw


def test_non_root_owned_remote_recovery_stage_is_rejected_before_upload(tmp_path):
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    helper = tmp_path / 'restore-owner'
    helper.write_bytes(b'synthetic-native-helper')
    adb.stage_owner = '10029'
    adb.calls.clear()
    with pytest.raises(ValueError):
        service.restore(adb, result, 10031, helper, hashlib.sha256(helper.read_bytes()).hexdigest())
    assert not any(isinstance(cmd, tuple) and cmd[0] == 'push' for cmd in adb.calls)


@pytest.mark.parametrize('missing', backend.DATA_ROOTS)
def test_archive_requires_all_three_app_roots(tmp_path, missing):
    path = tmp_path / 'data.tar'
    path.write_bytes(archive_bytes([(root, 'dir', b'') for root in backend.DATA_ROOTS if root != missing]))
    with pytest.raises(ValueError):
        backend.validate_archive(path)


def test_guard_rejects_junction_metadata_without_following_target(monkeypatch, tmp_path):
    from types import SimpleNamespace
    target = tmp_path / 'junction' / 'data.tar'
    original = Path.lstat
    def metadata(path, *args, **kwargs):
        if path == target.parent:
            return SimpleNamespace(st_file_attributes=0x400, st_mode=0o40700)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', metadata)
    with pytest.raises(ValueError):
        backend.guard_path(target)


@pytest.mark.parametrize('value', ['a' * 64 + ' file\nerror', 'a' * 64 + ' file\n' + 'b' * 64 + ' file', 'bad file'])
def test_checksum_record_must_be_unambiguous_and_successful(value):
    class Adb:
        def shell(self, *args, **kwargs):
            return value
    with pytest.raises(ValueError):
        backend.remote_digest(Adb(), '/data/local/tmp/file')


def checksum(cmd, digest):
    output = digest + '  ' + shlex.split(cmd)[1]
    return output + ('\nRC2VI_HUD_OK' if 'RC2VI_HUD_OK' in cmd else '')


def test_real_transport_binding_uses_fixed_transport_id_and_remote_serial_guard(monkeypatch):
    import sys
    from types import SimpleNamespace
    calls = []
    physical = ['RC2TEST']
    retarget, owner = [False], [None]
    class NativeAdb:
        def __init__(self, binary, port=5037, serial=''):
            self.binary, self.port, self.serial = binary, port, serial
        def command(self, *args, **kwargs):
            calls.append((self.serial, args))
            if args == ('get-transport-id',):
                raise RuntimeError('adb.exe: unknown command get-transport-id')
            if args == ('devices', '-l'):
                return 'List of devices attached\nRC2TEST device product:rc331 transport_id:41\nOTHER device transport_id:19\n'
            assert args[:2] == ('-t', '41') and self.serial == ''
            if retarget[0]:
                owner[0].serial = 'OTHER'
                retarget[0] = False
            if args[2] == 'shell':
                return 'RC2VI_HUD_WRONG_DEVICE' if physical[0] != 'RC2TEST' else 'Success'
            return ''
        def shell(self, command, **kwargs):
            return self.command('shell', '-x', command, **kwargs)
    monkeypatch.setitem(sys.modules, 'rc2vi.transport', SimpleNamespace(Adb=NativeAdb))
    original = NativeAdb('synthetic-adb', 5040, 'RC2TEST')
    owner[0] = original
    bound = backend.PinnedAdb(original, 'RC2TEST')
    retarget[0] = True
    assert bound.shell('pm uninstall --user 0 dji.go.v5') == 'Success'
    assert '$(getprop ro.serialno)' in calls[-1][1][-1]
    assert calls[-1][0] == '' and calls[-1][1][:2] == ('-t', '41')
    assert original.serial == 'OTHER'  # Delegate retargeted after _bound; fixed ID still won.
    original.serial = 'RC2TEST'
    physical[0] = 'OTHER'
    with pytest.raises(ValueError):
        bound.shell('pm uninstall --user 0 dji.go.v5')


@pytest.mark.parametrize('listing', [
    '', 'OTHER device transport_id:41\n', 'RC2TEST offline transport_id:41\n',
    'RC2TEST unauthorized transport_id:41\n', 'RC2TEST device\n',
    'RC2TEST device transport_id:0\n', 'RC2TEST device transport_id:-1\n',
    'RC2TEST device transport_id:18446744073709551616\n',
    'RC2TEST device transport_id:41 transport_id:42\n',
    'RC2TEST device transport_id:41\nRC2TEST device transport_id:42\n',
])
def test_native_adb_list_binding_rejects_missing_ambiguous_or_unready_target(listing):
    with pytest.raises(ValueError):
        backend.transport_id_from_devices(listing, 'RC2TEST')


def test_native_adb_list_binding_selects_exact_loopback_target_and_transport_id():
    listing = ('List of devices attached\n127.0.0.1:34567 device product:rc331 '
               'model:DJI_RC_2 device:rc331 transport_id:71\n'
               '127.0.0.1:3456 device transport_id:19\n')
    assert backend.transport_id_from_devices(listing, '127.0.0.1:34567') == '71'


@pytest.mark.parametrize('separator', ['\n', '\n\n'])
def test_remote_digest_accepts_toybox_newline_before_completion_marker(separator):
    class NativeSha:
        def shell(self, command, **kwargs):
            return 'a' * 64 + '  /data/app/test/base.apk' + separator + backend.MARKER
    assert backend.remote_digest(NativeSha(), '/data/app/test/base.apk') == 'a' * 64


@pytest.mark.parametrize('output', [
    'a' * 64 + '  /data/app/other/base.apk\n\n' + backend.MARKER,
    'a' * 64 + '  /data/app/test/base.apk\n\nwrong-marker',
    'warning\n' + 'a' * 64 + '  /data/app/test/base.apk\n\n' + backend.MARKER,
])
def test_remote_digest_keeps_strict_path_marker_and_extra_output_guards(output):
    class NativeSha:
        def shell(self, command, **kwargs):
            return output
    with pytest.raises(ValueError):
        backend.remote_digest(NativeSha(), '/data/app/test/base.apk')


@pytest.mark.parametrize('external_uid',[10029,10031])
def test_external_app_owned_metadata_requires_same_app_uid(tmp_path,external_uid):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for root in backend.DATA_ROOTS:
            member = tarfile.TarInfo(root)
            member.type, member.uid, member.gid = tarfile.DIRTYPE, 10029, 10029
            if root==backend.DATA_ROOTS[2]:member.uid=member.gid=external_uid
            archive.addfile(member)
    service, adb, state = backup(tmp_path, BackupAdb(stream.getvalue()))
    if external_uid==10029:
        recovery=service.create(adb,state);service.verify(recovery)
        adb.external_owner='10031:10031'
        helper=tmp_path/'helper';helper.write_bytes(b'helper')
        service.restore(adb,recovery,10031,helper,hashlib.sha256(b'helper').hexdigest())
    else:
        with pytest.raises(ValueError):service.create(adb,state)


@pytest.mark.parametrize('attribute,value', [('external_owner', '10029:10029'),
                                            ('external_label', 'u:object_r:wrong_data:s0')])
def test_external_tree_ownership_and_labels_are_verified(tmp_path, attribute, value):
    service, adb, state = backup(tmp_path)
    result = service.create(adb, state)
    helper = tmp_path / 'restore-owner'
    helper.write_bytes(b'synthetic-native-helper')
    setattr(adb, attribute, value)
    with pytest.raises(ValueError):
        service.restore(adb, result, 10031, helper, hashlib.sha256(helper.read_bytes()).hexdigest())


def test_windows_private_directory_dacl_is_protected_and_owner_system_only(tmp_path):
    if os.name != 'nt':
        return  # chmod behavior is exercised by the cross-platform backup test.
    import ctypes
    directory = tmp_path / 'private'
    directory.mkdir()
    backend.make_private(directory, directory=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    get = advapi.GetNamedSecurityInfoW
    get.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.POINTER(ctypes.c_void_p)]
    convert = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                       ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    descriptor, string = ctypes.c_void_p(), ctypes.c_void_p()
    assert get(str(directory), 1, 4, None, None, None, None, ctypes.byref(descriptor)) == 0
    try:
        assert convert(descriptor, 1, 4, ctypes.byref(string), None)
        sddl = ctypes.wstring_at(string)
        assert sddl.startswith('D:P') and sddl.count('(A;') == 2
        assert ';;;SY)' in sddl and ';;;OW)' in sddl
        assert ';;;WD)' not in sddl and ';;;BU)' not in sddl
    finally:
        if string:
            kernel.LocalFree(string)
        kernel.LocalFree(descriptor)


def test_windows_dacl_failure_cannot_continue_with_public_recovery(tmp_path, monkeypatch):
    if os.name != 'nt':
        return
    class Function:
        def __call__(self, *args):
            return 0
    class Library:
        def __getattr__(self, name):
            return Function()
    monkeypatch.setattr(backend.ctypes, 'WinDLL', lambda *args, **kwargs: Library())
    path = tmp_path / 'private'
    path.mkdir()
    with pytest.raises(RuntimeError):
        backend.make_private(path, directory=True)


def test_system_ce_alias_is_the_only_permitted_link_exception():
    command = backend.safe_roots_command()
    assert command.count('readlink ') == 1
    assert '"$(readlink /data/user/0)" = /data/data' in command
    assert '[ ! -L /data/data ]' in command
    assert '[ ! -L /data/user/0/dji.go.v5 ]' in command
    assert '[ ! -L /data/user_de/0/dji.go.v5 ]' in command


def test_backup_user_error_hides_private_path_and_does_not_claim_success(tmp_path, monkeypatch):
    service, adb, state = backup(tmp_path)
    def failure(*args, **kwargs):
        raise PermissionError(13, 'denied', 'PRIVATE_ACCOUNT_PATH/recovery/data.tar')
    monkeypatch.setattr(backend, 'make_private', failure)
    with pytest.raises(RuntimeError) as error:
        service.create(adb, state)
    assert 'Không thể' in str(error.value) and 'HUD_IO' in str(error.value)
    assert 'PRIVATE_ACCOUNT_PATH' not in str(error.value)


def remote_cleanup_calls(adb):
    return [cmd for cmd in adb.calls if isinstance(cmd, str) and 'rm -f -- ' in cmd
            and 'rc2vi-hud-data-' in cmd]


def test_remote_cleanup_is_scoped_nonrecursive_and_keeps_pc_recovery(tmp_path):
    service, adb, state = backup(tmp_path)
    recovery = service.create(adb, state)
    result = service.cleanup_remote(adb, recovery)
    assert result['status'] == 'hud_remote_cleaned' and result['cleaned'] is True
    assert not any(name.startswith(recovery['remote'] + '/') for name in adb.files)
    assert Path(recovery['archive']).is_file() and Path(recovery['apk']).is_file()
    assert all('-r' not in shlex.split(cmd) and '-rf' not in shlex.split(cmd)
               and recovery['remote'] in cmd for cmd in remote_cleanup_calls(adb))


@pytest.mark.parametrize('change', ['path', 'serial', 'owner', 'uncertain'])
def test_remote_cleanup_rejects_unsafe_scope_or_preserves_uncertain_state(tmp_path, change):
    service, adb, state = backup(tmp_path)
    recovery = service.create(adb, state)
    if change == 'path':
        recovery = {**recovery, 'remote': '/data/local/tmp/../user/0/dji.go.v5'}
    elif change == 'serial':
        adb.serial = 'OTHER'
    elif change == 'owner':
        adb.stage_owner = '10029'
    else:
        service.report(recovery, 'hud_recovery_required', 'recovery_incomplete')
    adb.calls.clear()
    if change == 'uncertain':
        result = service.cleanup_remote(adb, recovery)
        assert result['cleaned'] is False and not adb.calls
    else:
        with pytest.raises((ValueError, RuntimeError)):
            service.cleanup_remote(adb, recovery)
    assert not remote_cleanup_calls(adb)


def test_failed_backup_cleans_remote_partial_archive_and_keeps_pc_files(tmp_path):
    service, adb, state = backup(tmp_path)
    adb.pull_fail = True
    with pytest.raises((ValueError, RuntimeError, ConnectionError)):
        service.create(adb, state)
    assert remote_cleanup_calls(adb)
    assert not any('rc2vi-hud-data-' in name for name in adb.files)
    assert list((tmp_path / 'recovery').glob('*/recovery.json'))


def test_cleanup_with_unknown_file_preserves_it_and_reports_retained(tmp_path):
    service, adb, state = backup(tmp_path)
    recovery = service.create(adb, state)
    unknown = recovery['remote'] + '/unowned'
    adb.files[unknown] = b'unowned'
    result = service.cleanup_remote(adb, recovery)
    assert result['cleaned'] is False and adb.files[unknown] == b'unowned'


@pytest.mark.parametrize('change', ['inode', 'symlink'])
def test_cleanup_does_not_unlink_after_remote_directory_identity_changes(tmp_path, change):
    service, adb, state = backup(tmp_path)
    recovery = service.create(adb, state)
    if change == 'inode':
        adb.stage_inode = '8:78'
    else:
        adb.stage_symlink = True
    before = dict(adb.files)
    result = service.cleanup_remote(adb, recovery)
    assert result['cleaned'] is False and adb.files == before
    assert Path(recovery['archive']).is_file()
