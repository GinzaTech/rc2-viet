"""Exact asset inventory for the local Advanced EXE; never copy an entire workspace."""
from pathlib import Path
import json
import shutil
import stat
import tempfile

ROOT=Path(__file__).resolve().parents[1]
TOP={'manifest.json','home-bridge.apk','lawnchair.apk','freefcc.apk',
     'FREEFCC_LICENSE.txt','LAWNCHAIR_LICENSE.txt'}
ADB={'adb.exe','AdbWinApi.dll','AdbWinUsbApi.dll'}
HUD={'classes23.dex','payload.json','restore-owner','toolchain.json','toolchain.zip'}
TRANSLATION={'catalog.json','engine.json','memories.json','overrides.json','wording.json'}
MEMORY={'phone.json','rc12110-supplement.json','rc12110-supplement.provenance.json'}
ADVANCED={'manifest.json','recipe.zip'}


def allowed(relative):
    parts=relative.parts
    if len(parts)==1:return parts[0] in TOP
    if len(parts)==2:
        return parts[1] in {'adb':ADB,'hud':HUD,'translation':TRANSLATION,'advanced12110':ADVANCED}.get(parts[0],set())
    if len(parts)==3 and parts[:2]==('translation','memory'):return parts[2] in MEMORY
    return False


def stage_assets(source,target):
    target.mkdir()
    copied=[]
    for path in source.rglob('*'):
        if not path.is_file():continue
        if path.lstat().st_file_attributes & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
            raise ValueError('Advanced asset source contains reparse point')
        relative=path.relative_to(source)
        if not allowed(relative):continue
        destination=target/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,destination);copied.append(relative.as_posix())
    required={'advanced12110/manifest.json','advanced12110/recipe.zip','hud/toolchain.json','hud/toolchain.zip',
              'hud/classes23.dex','hud/payload.json','hud/restore-owner',
              *('adb/'+name for name in ADB),*('translation/'+name for name in TRANSLATION)}
    if not required <= set(copied):raise ValueError('Missing Advanced runtime asset')
    return copied


def main():
    base=ROOT/'build/advanced-desktop';base.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='assets-',dir=base))
    copied=stage_assets(ROOT/'assets',stage/'assets')
    (stage/'inventory.json').write_text(json.dumps(copied,indent=2),'utf-8')
    print(stage/'assets')


if __name__=='__main__':main()
