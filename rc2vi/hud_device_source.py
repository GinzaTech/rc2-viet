"""Pull only the selected controller's Fly APK; recover exact pinned stock if modded."""
from pathlib import Path
import uuid

from .core import SUPPORTED_APK, RC_12110_APK
from .hud_backup import PinnedAdb, guard_path, make_private, sha256_file
from zipfile import ZipFile
from .hud_capsule import CAPSULE_ENTRY, PROFILE_ENTRY, MAX_LITERAL, recover_capsule
from .hud_tools import _json_object
from .hud_plan import DEX
from scripts.hud_manifest import inspect_application, inspect_strings


def recover_stock(pulled,template,target,cancel=None,expected_digest=None):
    from .hud_stock import recover_stock as restore
    return restore(pulled,template,target,cancel=cancel,expected_digest=expected_digest)


def source_kind(pulled):
    with ZipFile(pulled) as archive:
        names = archive.namelist()
        if len(names)!=len(set(names)): raise ValueError('APK lấy từ tay có entry trùng.')
        capsule, profile = CAPSULE_ENTRY in names, PROFILE_ENTRY in names
        if capsule != profile: raise ValueError('APK menu thiếu dữ liệu phục hồi.')
        if capsule: return 'adaptive'
        if archive.getinfo('AndroidManifest.xml').file_size>4*1024*1024: raise ValueError('Manifest quá lớn.')
        manifest=archive.read('AndroidManifest.xml')
        if 'local.rc2.hud.HudProvider' in inspect_strings(manifest): return 'legacy'
        if inspect_application(manifest)['package']!='dji.go.v5': raise ValueError('Đầu vào không phải DJI Fly.')
        return 'stock'


def recover_adaptive(pulled,target,cancel=None):
    capsule=target.parent/'recovery.zip'
    try:
        with ZipFile(pulled) as archive:
            if (archive.getinfo(CAPSULE_ENTRY).file_size>MAX_LITERAL
                    or archive.getinfo(PROFILE_ENTRY).file_size>128*1024):
                raise ValueError('Dữ liệu phục hồi menu quá lớn.')
            profile=_json_object(archive.read(PROFILE_ENTRY)); helper=profile.get('helper_entry')
            if not isinstance(helper,str) or not DEX.fullmatch(helper) or helper=='classes.dex':
                raise ValueError('Vị trí DEX trong menu không hợp lệ.')
            with capsule.open('xb') as output: output.write(archive.read(CAPSULE_ENTRY))
        return recover_capsule(pulled,capsule,target,{helper,CAPSULE_ENTRY,PROFILE_ENTRY},cancel)
    finally:
        capsule.unlink(missing_ok=True)


def acquire_source(installer,adb,serial):
    installer._check_cancel()
    bound=PinnedAdb(adb,serial)
    installer._device(bound)
    before=dict(installer._installed(bound))
    root=guard_path(Path(installer.work)/'imports')
    root.mkdir(parents=True,exist_ok=True);make_private(root,directory=True)
    directory=guard_path(root/uuid.uuid4().hex)
    directory.mkdir();make_private(directory,directory=True)
    try:return _pull(installer,bound,before,directory)
    except BaseException:
        # Delete only this invocation's two known files; never other imports/data.
        guard_path(directory)
        for name in ('installed.apk','source.apk'):
            guard_path(directory/name).unlink(missing_ok=True)
        directory.rmdir()
        raise


def _pull(installer,bound,before,directory):
    pulled=directory/'installed.apk'
    installer.emit('applying','Đang lấy APK DJI Fly từ RC 2…')
    bound.command('pull',before['apk_path'],str(pulled),timeout=300)
    installer._check_cancel();guard_path(pulled);make_private(pulled)
    if sha256_file(pulled,installer.cancel)!=before['digest']:
        raise ValueError('SHA-256 của APK lấy từ tay không khớp; chưa patch hoặc cài.')
    installer._device(bound)
    if dict(installer._installed(bound))!=before:
        raise ValueError('DJI Fly hoặc thiết bị đã thay đổi trong lúc lấy APK; chưa patch hoặc cài.')
    installer._check_cancel()
    if before['digest'] in {SUPPORTED_APK,RC_12110_APK}:return pulled
    kind=source_kind(pulled)
    if kind=='stock':return pulled
    installer.emit('applying','Đang khôi phục đầu vào Fly gốc từ APK trên tay…')
    stock=directory/'source.apk'
    if kind=='adaptive': recover_adaptive(pulled,stock,cancel=installer.cancel)
    else:
        current=before.get('version')=='1.21.10' and before.get('code')==3115981
        expected=RC_12110_APK if current else SUPPORTED_APK
        template='source-recovery-1.21.10.zip' if current else 'source-recovery.zip'
        if current:recover_stock(pulled,installer.assets/'hud'/template,stock,cancel=installer.cancel,expected_digest=expected)
        else:recover_stock(pulled,installer.assets/'hud'/template,stock,cancel=installer.cancel)
    installer._check_cancel();guard_path(stock);make_private(stock)
    if kind=='legacy' and sha256_file(stock,installer.cancel) not in {SUPPORTED_APK,RC_12110_APK}:
        raise ValueError('Không khôi phục được APK gốc đã kiểm chứng; chưa patch hoặc cài.')
    verified=installer.builder.verify_device_apk(pulled,stock)
    installer._check_cancel()
    if verified['digest']!=before['digest']:
        raise ValueError('APK trên tay thay đổi trong bước kiểm chứng; chưa patch hoặc cài.')
    installer._device_sources[before['digest']]=(pulled,stock)
    return stock
