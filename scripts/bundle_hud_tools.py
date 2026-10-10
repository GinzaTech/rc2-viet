"""Package only public runtime/tools/payload. Never copy signing material or Fly APKs."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def run(*args):
    result=subprocess.run([str(arg) for arg in args],capture_output=True,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace')[:1500])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--java-home',type=Path,required=True)
    parser.add_argument('--sdk-tools',type=Path,required=True)
    parser.add_argument('--apktool',type=Path,required=True)
    args=parser.parse_args()
    stage=ROOT/'build/hud-toolchain-stage';stage.mkdir(parents=True,exist_ok=True)
    runtime=ROOT/'build/hud-jre-desktop'
    if not (runtime/'bin/java.exe').is_file():
        run(args.java_home/'bin/jlink.exe','--add-modules','java.base,java.logging,java.xml,java.desktop,jdk.crypto.ec,jdk.unsupported',
            '--strip-debug','--no-header-files','--no-man-pages','--compress=2','--output',runtime)
    shutil.copytree(runtime,stage/'java',dirs_exist_ok=True)
    (stage/'lib').mkdir(exist_ok=True);(stage/'bin').mkdir(exist_ok=True);(stage/'licenses').mkdir(exist_ok=True)
    shutil.copy2(args.apktool,stage/'lib/apktool.jar')
    shutil.copy2(args.sdk_tools/'lib/apksigner.jar',stage/'lib/apksigner.jar')
    shutil.copy2(args.sdk_tools/'zipalign.exe',stage/'bin/zipalign.exe')
    shutil.copy2(args.sdk_tools/'NOTICE.txt',stage/'licenses/ANDROID_BUILD_TOOLS_NOTICE.txt')
    for path in (ROOT/'build/hud-licenses').glob('*'):
        shutil.copy2(path,stage/'licenses'/path.name)
    classes=ROOT/'build/hud-java-classes';classes.mkdir(exist_ok=True)
    cp=os.pathsep.join(map(str,[args.apktool,args.sdk_tools/'lib/apksigner.jar']))
    run(args.java_home/'bin/javac.exe','-encoding','UTF-8','-cp',cp,'-d',classes,ROOT/'android-hud/HudTool.java')
    run(args.java_home/'bin/jar.exe','--create','--file',stage/'lib/hud-tool.jar','-C',classes,'.')
    assets=ROOT/'assets/hud';assets.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'android-hud/dex/classes.dex',assets/'classes23.dex')
    files={}
    with zipfile.ZipFile(assets/'toolchain.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for path in sorted(stage.rglob('*')):
            if not path.is_file():continue
            name=path.relative_to(stage).as_posix()
            if any(part in {'private-signing','device-backups'} for part in path.parts) or path.suffix.lower() in {'.jks','.p12','.pfx','.apk'}:
                raise RuntimeError('Private/app input file in public toolchain stage')
            content=path.read_bytes();files[name]=hashlib.sha256(content).hexdigest()
            info=zipfile.ZipInfo(name,(2026,10,8,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            output.writestr(info,content)
    archive_hash=hashlib.sha256((assets/'toolchain.zip').read_bytes()).hexdigest()
    (assets/'toolchain.json').write_text(json.dumps({'schema':1,'archive_sha256':archive_hash,'files':files},indent=2),encoding='utf-8')
    payload={'schema':1,'sha256':hashlib.sha256((assets/'classes23.dex').read_bytes()).hexdigest()}
    owner=assets/'restore-owner'
    if owner.is_file():payload['restore_owner_sha256']=hashlib.sha256(owner.read_bytes()).hexdigest()
    (assets/'payload.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps({'archive_sha256':archive_hash,'files':len(files),'archive_bytes':(assets/'toolchain.zip').stat().st_size,'payload':payload}))


if __name__=='__main__':main()
