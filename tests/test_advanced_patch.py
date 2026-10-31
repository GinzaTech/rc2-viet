"""Private recipe contracts: small synthetic APKs, no real keys/device/APKs."""
import hashlib
import json
import shutil
import struct
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from rc2vi import advanced_patch as core
from rc2vi.hud_capsule import CAPSULE_ENTRY, PROFILE_ENTRY
from rc2vi.hud_tools import HudCancelled
from rc2vi.hud_backup import HudCancelled as InstallCancelled
from scripts.hud_apk import repack_apk, _compressed_digest
from scripts.hud_signing_block import V2, block_entries_path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sign_block(path, values):
    raw = path.read_bytes()
    end = raw.rfind(b'PK\x05\x06')
    central = struct.unpack_from('<I', raw, end + 16)[0]
    pairs = b''.join(struct.pack('<QI', len(value) + 4, key) + value for key, value in values)
    size = len(pairs) + 24
    block = struct.pack('<Q', size) + pairs + struct.pack('<Q', size) + b'APK Sig Block 42'
    value = bytearray(raw[:central] + block + raw[central:])
    struct.pack_into('<I', value, end + len(block) + 16, central + len(block))
    path.write_bytes(value)


class Tools:
    archive_sha256, manifest_sha256 = 'a' * 64, 'b' * 64
    certificate = 'c' * 64

    def __init__(self, *args):
        self.sign = Mock(side_effect=self._sign)

    def prepare(self):
        return Path('unused')

    def align(self, source, target):
        shutil.copyfile(source, target)

    def _sign(self, source, target, *args):
        shutil.copyfile(source, target)
        sign_block(target, [(V2, b'new signer'), (0xf05368c0, b'v3 signer')])

    def verify(self, path):
        return self.certificate


class Keys:
    def __init__(self, *args):
        self.ensure = Mock(side_effect=self.load)

    def load(self):
        return SimpleNamespace(keyfile=Path('never-created.p12'), alias='test',
                               password='fixture-only', certificate_sha256='c' * 64)


def save_recipe(assets, values, manifest):
    root = assets / 'advanced12110'
    root.mkdir(parents=True, exist_ok=True)
    with ZipFile(root / 'recipe.zip', 'w', ZIP_DEFLATED) as archive:
        for name, data in values.items():
            archive.writestr(name, data)
    result = {**manifest, 'recipe_sha256': digest((root / 'recipe.zip').read_bytes()),
              'entries': {name: {'sha256': digest(data), 'bytes': len(data)}
                          for name, data in values.items()}}
    (root / 'manifest.json').write_text(json.dumps(result), encoding='utf-8')
    return result


@pytest.fixture
def context(tmp_path, monkeypatch):
    identity = {'package': 'dji.go.v5', 'application': 'com.AppGuard.AppGuard.QLVRK',
                'version': '1.21.10', 'code': 3115981}
    monkeypatch.setattr(core, 'inspect_application', lambda raw: dict(identity))
    monkeypatch.setattr(core, 'HudTools', Tools)
    monkeypatch.setattr(core, 'HudKeyStore', Keys)
    # Synthetic fixture has no real V2 signature. Native stock verification is
    # covered independently and against the actual pinned APK in the release probe.
    monkeypatch.setattr(core, 'verify_stock_apk', lambda *a, **kw: core.SOURCE_CERTIFICATE_SHA256)
    source = tmp_path / 'stock.apk'
    stock = {name: ('original-' + name).encode() for name in core.REPLACEMENT_ENTRIES}
    stock.update({'resources.arsc': b'resources', 'classes2.dex': b'PROTOCOL\0\xff' * 500,
                  'lib/armeabi-v7a/protocol.so': b'unchanged native protocol'})
    with ZipFile(source, 'w', ZIP_DEFLATED) as archive:
        for name, data in stock.items():
            archive.writestr(name, data)
    sign_block(source, [(V2, b'original-loader-v2')])
    pinned = digest(source.read_bytes())
    monkeypatch.setattr(core, 'SOURCE_SHA256', pinned)
    profile = {'schema': 1, 'kind': 'rc2-advanced-12110', 'source_sha256': pinned,
               'helper_entry': 'classes23.dex', 'feature_entry': 'classes24.dex',
               'feature_classes': 430, 'localized_ui_sites': 1150,
               'plan': {'identity': dict(identity), 'source_digest': pinned,
                        'helper_entry': 'classes23.dex', 'retain_loader_v2': True,
                        'bootstrap': {'entry': 'classes.dex'}}}
    values = {'replacements/' + name: data + b':patched' for name, data in stock.items()
              if name in core.REPLACEMENT_ENTRIES}
    values.update({'additions/classes23.dex': b'dex\n035\0helper',
                   'additions/classes24.dex': b'dex\n035\0feature',
                   'additions/' + PROFILE_ENTRY: json.dumps(profile).encode()})
    manifest = {'schema': 1, 'version': '1.21.10', 'code': 3115981,
                'source_sha256': pinned, 'profile_kind': 'rc2-advanced-12110',
                'compatible_installed': {}}
    assets, work = tmp_path / 'assets', tmp_path / 'work'
    manifest = save_recipe(assets, values, manifest)
    builder = core.AdvancedBuilder(assets, work, lambda *args: None)
    return builder, source, values, manifest, identity


def test_real_source_pin():
    assert core.SOURCE_SHA256 == 'f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98'


def test_roundtrip_replay_loader_and_protocol_preserved(context):
    builder, source, _, _, identity = context
    result = builder.build(source)
    assert result['status'] == 'hud_built'
    assert result['source_identity'] == identity
    assert builder.latest() == builder.verify_historical(result)
    assert block_entries_path(Path(result['apk']))[V2] == block_entries_path(source)[V2]
    with ZipFile(source) as old, ZipFile(result['apk']) as new:
        for name in ('classes2.dex', 'lib/armeabi-v7a/protocol.so'):
            assert old.read(name) == new.read(name)
            assert _compressed_digest(old, old.getinfo(name)) == _compressed_digest(new, new.getinfo(name))
        profile = json.loads(new.read(PROFILE_ENTRY))
        assert profile['kind'] == core.PROFILE_KIND
        assert profile['recipe_sha256'] == json.loads((builder.assets / 'advanced12110/manifest.json').read_text())['recipe_sha256']
    builder.keys.load = Mock(side_effect=AssertionError('no keys during device verification'))
    assert builder.verify_device_apk(result['apk'], source)['digest'] == result['digest']
    assert builder.verify_device_apk(source, source)['source_digest'] == result['source_digest']


@pytest.mark.parametrize('mode', ['missing', 'wronghash', 'version', 'code', 'package'])
def test_bad_source_rejected_before_any_writes_or_signing(context, mode):
    builder, source, _, _, identity = context
    if mode == 'missing':
        source = source.with_name('missing.apk')
    elif mode == 'wronghash':
        source.write_bytes(b'not stock')
    elif mode == 'version':
        identity['version'] = '1.21.9'
    elif mode == 'code':
        identity['code'] = 1
    else:
        identity['package'] = 'evil.package'
    with pytest.raises((ValueError, OSError)):
        builder.build(source)
    assert not builder.work.exists()
    builder.keys.ensure.assert_not_called()
    builder.tools.sign.assert_not_called()


@pytest.mark.parametrize('mode', ['ziphash', 'entryhash', 'size', 'escape', 'backslash',
                                  'extra', 'missing', 'wrongkind', 'sourcepin', 'schema'])
def test_recipe_tamper_fails_closed(context, mode):
    builder, source, values, manifest, _ = context
    root = builder.assets / 'advanced12110'
    if mode == 'ziphash':
        with (root / 'recipe.zip').open('ab') as stream:
            stream.write(b'tamper')
    elif mode in ('entryhash', 'size', 'sourcepin', 'schema'):
        if mode == 'entryhash':
            manifest['entries']['replacements/classes.dex']['sha256'] = '0' * 64
        elif mode == 'size':
            manifest['entries']['replacements/classes.dex']['bytes'] += 1
        elif mode == 'sourcepin':
            manifest['source_sha256'] = '1' * 64
        else:
            manifest['schema'] = True
        (root / 'manifest.json').write_text(json.dumps(manifest))
    else:
        values = dict(values)
        if mode in ('escape', 'backslash', 'extra'):
            values[{'escape': 'additions/../escape', 'backslash': 'additions/evil\\name',
                    'extra': 'additions/recovery.zip'}[mode]] = b'untrusted'
        elif mode == 'missing':
            del values['replacements/classes10.dex']
        else:
            profile = json.loads(values['additions/' + PROFILE_ENTRY])
            profile['kind'] = 'basic'
            values['additions/' + PROFILE_ENTRY] = json.dumps(profile).encode()
        save_recipe(builder.assets, values, manifest)
    with pytest.raises(ValueError):
        builder.build(source)
    assert not builder.work.exists()
    builder.keys.ensure.assert_not_called()


@pytest.mark.parametrize('name', ['classes24.dex', CAPSULE_ENTRY, PROFILE_ENTRY])
def test_device_missing_inventory_rejected(context, name):
    builder, source, _, _, _ = context
    result = builder.build(source)
    broken = source.with_name('missing-entry.apk')
    with ZipFile(result['apk']) as archive, ZipFile(broken, 'w', ZIP_DEFLATED) as target:
        for info in archive.infolist():
            if info.filename != name:
                target.writestr(info, archive.read(info))
    with pytest.raises((ValueError, KeyError)):
        builder.verify_device_apk(broken, source)


@pytest.mark.parametrize('mode', ['kind', 'recipe', 'feature', 'extra', 'protocol'])
def test_device_replay_rejects_changed_payloads(context, mode):
    builder, source, _, _, _ = context
    built = builder.build(source)
    wrong = source.with_name('modified.apk')
    replacements, additions = {}, {}
    with ZipFile(built['apk']) as archive:
        profile = json.loads(archive.read(PROFILE_ENTRY))
    if mode in ('kind', 'recipe'):
        profile['kind' if mode == 'kind' else 'recipe_sha256'] = 'wrong'
        replacements[PROFILE_ENTRY] = json.dumps(profile).encode()
    elif mode == 'feature':
        replacements['classes24.dex'] = b'bad feature'
    elif mode == 'extra':
        additions['assets/extra'] = b'extra'
    else:
        replacements['classes2.dex'] = b'tampered protocol'
    repack_apk(Path(built['apk']), wrong, replacements=replacements, additions=additions)
    sign_block(wrong, [(V2, b'original-loader-v2'), (0xf05368c0, b'v3 signer')])
    with pytest.raises(ValueError):
        builder.verify_device_apk(wrong, source)


def test_legacy_requires_full_hash_and_certificate_and_exact_recovery(context):
    builder, source, values, manifest, _ = context
    built = builder.build(source)
    legacy = source.with_name('legacy.apk')
    profile = json.loads(values['additions/' + PROFILE_ENTRY])
    profile['kind'] = 'redfly-feature-candidate'
    repack_apk(Path(built['apk']), legacy, replacements={PROFILE_ENTRY: json.dumps(profile).encode()})
    sign_block(legacy, [(V2, b'original-loader-v2'), (0xf05368c0, b'v3 signer')])
    with pytest.raises(ValueError):
        builder.verify_device_apk(legacy, source)
    manifest['compatible_installed'] = {digest(legacy.read_bytes()): {'certificate_sha256': 'd' * 64}}
    save_recipe(builder.assets, values, manifest)
    with pytest.raises(ValueError):
        builder.verify_device_apk(legacy, source)
    manifest['compatible_installed'] = {digest(legacy.read_bytes()): {'certificate_sha256': 'c' * 64}}
    save_recipe(builder.assets, values, manifest)
    assert builder.verify_device_apk(legacy, source)['digest'] == digest(legacy.read_bytes())


def test_receipt_escape_tamper_and_cancellation(context):
    builder, source, _, _, _ = context
    with pytest.raises(ValueError):
        builder.verify(source.parent / 'receipt.json')
    event = threading.Event()
    event.set()
    builder.cancel = event
    with pytest.raises(HudCancelled):
        builder.build(source)
    assert not builder.work.exists()
    event.clear()
    result = builder.build(source)
    receipt = Path(result['receipt'])
    value = json.loads(receipt.read_text())
    value['apk'] = '../escape.apk'
    receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        builder.verify(result)


def legacy_basic(context, tmp_path):
    from rc2vi.hud_capsule import build_capsule
    builder, source, _, manifest, identity = context
    capsule = tmp_path / 'basic-recovery.zip'
    build_capsule(source, capsule, {'AndroidManifest.xml', 'classes.dex'})
    profile = {'revision': 'structural-menu-v1', 'variant': 'basic',
               'source_digest': core.SOURCE_SHA256, 'helper_entry': 'classes23.dex',
               'identity': dict(identity), 'retain_loader_v2': True}
    additions = {'classes23.dex': b'old basic helper', CAPSULE_ENTRY: capsule.read_bytes(),
                 PROFILE_ENTRY: json.dumps(profile).encode()}
    legacy = tmp_path / 'basic.apk'
    with ZipFile(source) as archive:
        replacements = {name: archive.read(name) + b':basic' for name in ('AndroidManifest.xml', 'classes.dex')}
    repack_apk(source, legacy, replacements=replacements, additions=additions)
    sign_block(legacy, [(V2, b'original-loader-v2'), (0xf05368c0, b'v3 signer')])
    return legacy, manifest, profile


def test_known_basic_recovery_has_no_feature_entry(context, tmp_path):
    builder, source, values, _, _ = context
    legacy, manifest, _ = legacy_basic(context, tmp_path)
    manifest['compatible_installed'] = {digest(legacy.read_bytes()): {'certificate_sha256': 'c' * 64}}
    save_recipe(builder.assets, values, manifest)
    target = tmp_path / 'basic-restored.apk'
    assert builder.recover_profile(legacy, target) == target
    assert target.read_bytes() == source.read_bytes()
    builder.keys.load = Mock(side_effect=AssertionError('no keys on import'))
    assert builder.verify_device_apk(legacy, target)['digest'] == digest(legacy.read_bytes())
    with pytest.raises(FileExistsError):
        builder.recover_profile(legacy, target)


@pytest.mark.parametrize('mode', ['unknownkind', 'feature', 'variant', 'source', 'unlisted', 'badcert'])
def test_basic_migration_is_explicitly_bounded(context, tmp_path, mode):
    builder, source, values, _, _ = context
    legacy, manifest, profile = legacy_basic(context, tmp_path)
    if mode == 'unknownkind':
        profile['kind'] = 'some-other-old-profile'
    elif mode == 'feature':
        profile['feature_entry'] = 'classes24.dex'
    elif mode == 'variant':
        profile['variant'] = 'advanced'
    elif mode == 'source':
        profile['source_digest'] = 'f' * 64
    changed = tmp_path / 'basic-changed.apk'
    repack_apk(legacy, changed, replacements={PROFILE_ENTRY: json.dumps(profile).encode()})
    sign_block(changed, [(V2, b'original-loader-v2'), (0xf05368c0, b'v3 signer')])
    manifest['compatible_installed'] = {} if mode == 'unlisted' else {
        digest(changed.read_bytes()): {'certificate_sha256': ('d' if mode == 'badcert' else 'c') * 64}}
    save_recipe(builder.assets, values, manifest)
    target = tmp_path / 'should-not-recover.apk'
    with pytest.raises(ValueError):
        builder.recover_profile(changed, target)
    assert not target.exists()
    with pytest.raises(ValueError):
        builder.verify_device_apk(changed, source)


def test_recover_new_profile_and_no_retained_intermediates(context, tmp_path):
    builder, source, _, _, _ = context
    result = builder.build(source)
    directory = Path(result['receipt']).parent
    assert {p.name for p in directory.iterdir()} == {'receipt.json', 'source.apk', 'hud.apk'}
    target = tmp_path / 'recovered.apk'
    builder.recover_profile(result['apk'], target)
    assert target.read_bytes() == source.read_bytes()


def test_insufficient_disk_is_readonly_with_clear_work_advice(context, monkeypatch):
    builder, source, _, _, _ = context
    monkeypatch.setattr(core.shutil, 'disk_usage', lambda p: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match='--work'):
        builder.build(source)
    assert not builder.work.exists()
    builder.keys.ensure.assert_not_called()


def test_sign_failure_removes_only_current_invocation(context):
    builder, source, _, _, _ = context
    retained = builder.work / 'builds' / ('f' * 32)
    retained.mkdir(parents=True)
    earlier = retained / 'keep.apk'
    earlier.write_bytes(b'other-agent-artifact')
    builder.tools.sign.side_effect = RuntimeError('sign failed')
    with pytest.raises(RuntimeError, match='sign failed'):
        builder.build(source)
    assert earlier.read_bytes() == b'other-agent-artifact'
    assert list((builder.work / 'builds').iterdir()) == [retained]
    assert not (builder.work / 'latest.json').exists()


@pytest.mark.parametrize('mode', ['profile', 'capsule', 'cert', 'tools', 'digest', 'source', 'extra'])
def test_receipt_metadata_strict(context, mode):
    builder, source, _, _, _ = context
    result = builder.build(source)
    path = Path(result['receipt'])
    value = json.loads(path.read_text())
    if mode == 'profile':
        value['profile']['recipe_sha256'] = 'e' * 64
    elif mode == 'capsule':
        value['capsule_sha256'] = 'e' * 64
    elif mode == 'cert':
        value['certificate_sha256'] = 'e' * 64
    elif mode == 'tools':
        value['tool_manifest_sha256'] = 'e' * 64
    elif mode == 'digest':
        value['digest'] = 'e' * 64
    elif mode == 'source':
        value['source_digest'] = 'e' * 64
    else:
        value['extra'] = True
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        builder.verify(result)


@pytest.mark.parametrize('mode', ['escape', 'schema', 'duplicate'])
def test_latest_pointer_fail_closed(context, mode):
    builder, _, _, _, _ = context
    assert builder.latest() is None
    builder.work.mkdir()
    raw = json.dumps({'schema': 1, 'receipt': '../receipt.json' if mode == 'escape'
                     else 'builds/' + 'a' * 32 + '/receipt.json'})
    if mode == 'schema':
        raw = raw.replace('"schema": 1', '"schema": true')
    elif mode == 'duplicate':
        raw = raw.replace('{', '{"schema": 1,', 1)
    (builder.work / 'latest.json').write_text(raw)
    with pytest.raises(ValueError):
        builder.latest()


class Device:
    """Injected immutable transport, real base serial/root/version guards."""
    serial = 'TEST_RC2'

    def __init__(self, apk):
        self.apk = apk
        self.calls = []
        self.model, self.device, self.sdk = 'DJI RC 2', 'rc331', '30'
        self.physical, self.root = self.serial, 'uid=0(root)'
        self.version, self.code = '1.21.10', 3115981
        self.foreground = 'mResumedActivity: app.launcher/.Launcher'
        self.after_pull = None
        self.pull_corrupt = False

    def bind(self, serial):
        assert serial == self.serial
        return self

    def command(self, *args, **kwargs):
        self.calls.append(args)
        if args == ('get-state',):
            return 'device'
        if args[0] == 'pull':
            Path(args[2]).write_bytes(b'bad pull' if self.pull_corrupt else self.apk.read_bytes())
            if self.after_pull:
                self.after_pull()
            return '1 file pulled'
        raise AssertionError(args)

    def shell(self, cmd, **kwargs):
        # PinnedAdb wraps each shell command with the physical serial check.
        self.calls.append(cmd)
        if cmd.startswith('if [ "$(getprop ro.serialno)"'):
            cmd = cmd.split('; fi; ', 1)[-1]
        props = {'ro.product.model': self.model, 'ro.product.device': self.device,
                 'ro.build.version.sdk': self.sdk, 'ro.serialno': self.physical}
        if cmd.startswith('getprop '):
            return props.get(cmd[8:], '')
        if cmd == 'id':
            return self.root
        if cmd.startswith('dumpsys activity'):
            return self.foreground
        if cmd == 'pm path dji.go.v5':
            return 'package:/data/app/dji.go.v5/base.apk'
        if cmd == 'dumpsys package dji.go.v5':
            return f'userId=10023\nversionName={self.version}\nversionCode={self.code}'
        if cmd.startswith('sha256sum '):
            from rc2vi.hud_backup import MARKER
            return digest(self.apk.read_bytes()) + '  /data/app/dji.go.v5/base.apk\n' + MARKER
        raise AssertionError(cmd)


@pytest.mark.parametrize('modded', [False, True])
def test_installer_self_pull_verified_before_registration(context, modded):
    builder, source, _, _, _ = context
    installed = Path(builder.build(source)['apk']) if modded else source
    adb = Device(installed)
    installer = core.AdvancedInstaller(builder.assets, builder.work / 'installer', lambda *a: None, builder)
    result = installer.pull_source(adb, adb.serial)
    assert result.read_bytes() == source.read_bytes()
    pulled, stock = installer._device_sources[digest(installed.read_bytes())]
    assert stock == result
    snapshot = json.loads((pulled.parent / 'snapshot.json').read_text())
    assert snapshot['device']['serial'] == adb.serial
    assert snapshot['device']['uid'] == 10023
    assert snapshot['verified']['source_digest'] == core.SOURCE_SHA256
    assert not any('install ' in str(c) or 'force-stop' in str(c) for c in adb.calls)


@pytest.mark.parametrize('attribute,value', [('model', 'DJI RC'), ('device', 'wrong'), ('sdk', '31'),
                                            ('root', 'uid=2000(shell)'), ('physical', 'OTHER'),
                                            ('version', '1.21.8'), ('code', 42),
                                            ('foreground', 'mResumedActivity: dji.go.v5/.FPV')])
def test_installer_base_guards_prevent_pull(context, attribute, value):
    builder, source, _, _, _ = context
    adb = Device(source)
    setattr(adb, attribute, value)
    installer = core.AdvancedInstaller(builder.assets, builder.work / 'installer', lambda *a: None, builder)
    with pytest.raises(ValueError):
        installer.pull_source(adb, adb.serial)
    assert not any(isinstance(c, tuple) and c[0] == 'pull' for c in adb.calls)
    assert not installer._device_sources


@pytest.mark.parametrize('mode', ['corrupt', 'changedversion', 'cancel', 'verifyfail'])
def test_installer_failed_pull_never_registers(context, mode):
    builder, source, _, _, _ = context
    adb = Device(source)
    event = threading.Event()
    installer = core.AdvancedInstaller(builder.assets, builder.work / 'installer', lambda *a: None, builder, event)
    if mode == 'corrupt':
        adb.pull_corrupt = True
    elif mode == 'changedversion':
        adb.after_pull = lambda: setattr(adb, 'version', '1.21.8')
    elif mode == 'cancel':
        adb.after_pull = event.set
    else:
        builder.verify_device_apk = Mock(side_effect=ValueError('unverified'))
    with pytest.raises((ValueError, HudCancelled, InstallCancelled)):
        installer.pull_source(adb, adb.serial)
    assert installer._device_sources == {}
    assert list((installer.work / 'imports').iterdir()) == []


@pytest.mark.parametrize('failure', [None, 'settings', 'foreground', 'stopped'])
def test_stage_settings_after_parent_push_with_cleanup(context, monkeypatch, failure):
    builder, _, _, _, _ = context
    calls = []
    monkeypatch.setattr(core.HudInstaller, '_stage', lambda *a: calls.append('parent-push') or '/stage/candidate.apk')
    monkeypatch.setattr(core, 'assert_stopped', lambda adb: calls.append('stopped') if failure != 'stopped'
                        else (_ for _ in ()).throw(ValueError('not stopped')))
    installer = core.AdvancedInstaller(builder.assets, builder.work, lambda *a: None, builder)
    installer._cleanup_stage = Mock()
    installer._device = Mock()
    def shell(cmd, **kwargs):
        calls.append(cmd)
        if cmd.startswith('am start'):
            return 'Error' if failure == 'settings' else 'Status: ok\nComplete'
        if cmd.startswith('dumpsys'):
            return 'mResumedActivity: dji.go.v5/.FPV' if failure == 'foreground' else 'mResumedActivity: com.android.settings/.Settings'
        return ''
    adb = SimpleNamespace(shell=shell)
    if failure:
        with pytest.raises(ValueError):
            installer._stage(adb, {'apk': 'candidate'})
        installer._cleanup_stage.assert_called_once_with(adb, '/stage/candidate.apk')
    else:
        assert installer._stage(adb, {'apk': 'candidate'}) == '/stage/candidate.apk'
        installer._cleanup_stage.assert_not_called()
    assert calls[0] == 'parent-push'
    assert calls[1].startswith('am start -W -n com.android.settings')


def test_pinned_stock_signature_uses_v2_verifier_not_modded_v3(context, monkeypatch):
    builder, source, _, _, _ = context
    stock_certificate = '01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4'
    verifier = Mock(return_value=stock_certificate)
    monkeypatch.setattr(core, 'verify_stock_apk', verifier, raising=False)
    builder.tools.verify = Mock(side_effect=RuntimeError('HUD tool execution failed.'))
    assert builder.verify_apk(source) == stock_certificate
    verifier.assert_called_once_with(builder.tools, source, source_digest=core.SOURCE_SHA256,
                                     certificate_digest=stock_certificate)
    builder.tools.verify.assert_not_called()


def test_original_stock_self_pull_succeeds_with_v2_only_signer(context, monkeypatch):
    builder, source, _, _, _ = context
    certificate = '01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4'
    monkeypatch.setattr(core, 'verify_stock_apk', Mock(return_value=certificate), raising=False)
    builder.tools.verify = Mock(side_effect=RuntimeError('HUD tool execution failed.'))
    adb = Device(source)
    installer = core.AdvancedInstaller(builder.assets, builder.work / 'installer', lambda *a: None, builder)
    result = installer.pull_source(adb, adb.serial)
    pulled, stock = installer._device_sources[core.SOURCE_SHA256]
    assert result == stock and pulled == stock
    snapshot = json.loads((pulled.parent / 'snapshot.json').read_text('utf-8'))
    assert snapshot['verified']['certificate_sha256'] == certificate
    assert not any('install ' in str(c) or 'uninstall' in str(c) for c in adb.calls)
    builder.tools.verify.assert_not_called()


def test_other_apk_hash_still_requires_v3(context, monkeypatch):
    builder, source, _, _, _ = context
    other = source.with_name('other-v2.apk')
    other.write_bytes(source.read_bytes() + b'changed')
    verifier = Mock(side_effect=AssertionError('Never accept another hash as stock'))
    monkeypatch.setattr(core, 'verify_stock_apk', verifier, raising=False)
    builder.tools.verify = Mock(side_effect=RuntimeError('SDK30 V3 required'))
    with pytest.raises(RuntimeError):
        builder.verify_apk(other)
    verifier.assert_not_called()
    builder.tools.verify.assert_called_once_with(other)
