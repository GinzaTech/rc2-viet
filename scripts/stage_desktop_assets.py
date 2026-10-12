"""Stage desktop public assets without retired, version-specific translation APKs."""
from pathlib import Path
import shutil
import stat
import tempfile
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rc2vi.hud_tools import LEGACY_HUD_PAYLOADS, sha256_file
RETIRED = {'vietnamese-resources.apk', 'phone-vietnamese-resources.apk'}

TOP_LEVEL={'manifest.json','FREEFCC_LICENSE.txt','LAWNCHAIR_LICENSE.txt',
           'freefcc.apk','home-bridge.apk','rc-launcher.apk','lawnchair.apk'}
ADB={'adb.exe','AdbWinApi.dll','AdbWinUsbApi.dll'}
HUD={'classes23.dex','payload.json','restore-owner','toolchain.json','toolchain.zip',
     'source-recovery.zip','source-recovery-1.21.10.zip'}
TRANSLATION={'catalog.json','engine.json','memories.json','overrides.json','wording.json'}
MEMORY={'phone.json','rc12110-supplement.json','rc12110-supplement.provenance.json'}

def public_asset(path, relative):
    parts=relative.parts
    if len(parts)==1:return parts[0] in TOP_LEVEL
    if len(parts)==2 and parts[0]=='adb':return parts[1] in ADB
    if len(parts)==2 and parts[0]=='hud':return parts[1] in HUD
    if len(parts)==2 and parts[0]=='translation':return parts[1] in TRANSLATION
    if len(parts)==3 and parts[:2]==('translation','memory'):return parts[2] in MEMORY
    if len(parts)==3 and parts[:2]==('hud','history') and parts[2].endswith('.dex'):
        digest=parts[2][:-4]
        return digest in LEGACY_HUD_PAYLOADS and sha256_file(path)==digest
    return False

def stage_assets(source, target):
    target.mkdir()
    for path in source.rglob('*'):
        if path.lstat().st_file_attributes & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
            raise ValueError('Public asset source contains a reparse point.')
        if not path.is_file():continue
        relative=path.relative_to(source)
        if not public_asset(path,relative):continue
        if path.suffix=='.dex' and any(marker in path.read_bytes() for marker in
            (b'AdvancedMenu',b'AdvancedSdk',b'AdvancedJob',b'PortIntegration',b'PortHooks')):
            raise ValueError('Private experiment found in a public helper.')
        destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,destination)


def main():
    base = (ROOT / 'build').resolve()
    base.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='desktop-assets-', dir=base)).resolve()
    if not stage.is_relative_to(base):
        raise ValueError('Asset staging path escaped the build directory.')
    source = ROOT / 'assets'
    stage_assets(source,stage/'assets')
    print(stage / 'assets')


if __name__ == '__main__':
    main()
