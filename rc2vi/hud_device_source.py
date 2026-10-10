"""Pull only the selected controller's Fly APK; recover exact pinned stock if modded."""
from pathlib import Path
import uuid

from .core import SUPPORTED_APK
from .hud_backup import PinnedAdb, guard_path, make_private, sha256_file


def recover_stock(pulled,template,target,cancel=None):
    from .hud_stock import recover_stock as restore
    return restore(pulled,template,target,cancel=cancel)


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
    if before['digest']==SUPPORTED_APK:return pulled
    installer.emit('applying','Đang khôi phục đầu vào Fly gốc từ APK trên tay…')
    stock=directory/'source.apk'
    recover_stock(pulled,installer.assets/'hud/source-recovery.zip',stock,cancel=installer.cancel)
    installer._check_cancel();guard_path(stock);make_private(stock)
    if sha256_file(stock,installer.cancel)!=SUPPORTED_APK:
        raise ValueError('Không khôi phục được APK gốc đã kiểm chứng; chưa patch hoặc cài.')
    verified=installer.builder.verify_device_apk(pulled,stock)
    installer._check_cancel()
    if verified['digest']!=before['digest']:
        raise ValueError('APK trên tay thay đổi trong bước kiểm chứng; chưa patch hoặc cài.')
    installer._device_sources[before['digest']]=(pulled,stock)
    return stock
