import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

HERE=Path(__file__).parent
SDK=Path(os.environ['LOCALAPPDATA'])/'Android/Sdk'
TOOLS=SDK/'build-tools/36.1.0'
KEYS=Path(os.environ['RC2VI_SIGNING_DIR'])

def run(*args):
    result=subprocess.run([str(a) for a in args],capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode: raise RuntimeError(result.stderr)
    return result.stdout.strip()

def main():
    run(TOOLS/'aapt2.exe','compile','--dir',HERE/'overlay/res','-o',HERE/'compiled.zip')
    run(TOOLS/'aapt2.exe','link','-o',HERE/'unsigned.apk','--manifest',HERE/'overlay/AndroidManifest.xml',
        '-I',SDK/'platforms/android-30/android.jar','--auto-add-overlay','-R',HERE/'compiled.zip')
    run(TOOLS/'zipalign.exe','-f','4',HERE/'unsigned.apk',HERE/'aligned.apk')
    config=json.loads((KEYS/'local-signing.json').read_text())
    os.environ['RC2VI_SIGN_PASS']=config['password']
    apk=HERE/'DJI_Fly_Vietnamese_Reviewed5.apk'
    run(TOOLS/'apksigner.bat','sign','--ks',KEYS/'local-vietnamese-draft.jks',
        '--ks-key-alias',config['alias'],'--ks-pass','env:RC2VI_SIGN_PASS','--key-pass','env:RC2VI_SIGN_PASS','--out',apk,HERE/'aligned.apk')
    del os.environ['RC2VI_SIGN_PASS']
    verified=run(TOOLS/'apksigner.bat','verify','--verbose','--print-certs',apk)
    with zipfile.ZipFile(apk) as archive:
        if any(n.endswith(('.dex','.so')) for n in archive.namelist()): raise ValueError('Unexpected executable payload')
    result={'apk':str(apk),'sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),
            'size':apk.stat().st_size,'versionCode':7,'signature_verified':True,'has_dex_or_native':False}
    (HERE/'build-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
