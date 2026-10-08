import hashlib,json,os,subprocess,zipfile
from pathlib import Path

HERE=Path(__file__).parent
SDK=Path(os.environ['LOCALAPPDATA'])/'Android/Sdk'
TOOLS=SDK/'build-tools/36.1.0'
ANDROID=SDK/'platforms/android-30/android.jar'
KEYS=Path(os.environ['RC2VI_SIGNING_DIR'])

def run(*args):
    result=subprocess.run([str(a) for a in args],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))

def main():
    classes=HERE/'classes';classes.mkdir(exist_ok=True)
    dex=HERE/'dex';dex.mkdir(exist_ok=True)
    run('javac','-source','8','-target','8','-encoding','UTF-8','-bootclasspath',ANDROID,
        '-d',classes,*sorted((HERE/'src').rglob('*.java')))
    run(TOOLS/'d8.bat','--lib',ANDROID,'--min-api','24','--output',dex,*sorted(classes.rglob('*.class')))
    unsigned=HERE/'unsigned.apk'
    run(TOOLS/'aapt2.exe','compile','--dir',HERE/'res','-o',HERE/'resources.zip')
    run(TOOLS/'aapt2.exe','link','--manifest',HERE/'AndroidManifest.xml','-I',ANDROID,
        '-R',HERE/'resources.zip','--auto-add-overlay','-o',unsigned)
    with zipfile.ZipFile(unsigned,'a',compression=zipfile.ZIP_DEFLATED) as z:z.write(dex/'classes.dex','classes.dex')
    run(TOOLS/'zipalign.exe','-f','4',unsigned,HERE/'aligned.apk')
    config=json.loads((KEYS/'local-signing.json').read_text())
    os.environ['RC2VI_SIGN_PASS']=config['password']
    target=HERE.parent/'assets/home-bridge.apk'
    run(TOOLS/'apksigner.bat','sign','--ks',KEYS/'local-vietnamese-draft.jks','--ks-key-alias',config['alias'],
        '--ks-pass','env:RC2VI_SIGN_PASS','--key-pass','env:RC2VI_SIGN_PASS','--out',target,HERE/'aligned.apk')
    del os.environ['RC2VI_SIGN_PASS']
    run(TOOLS/'apksigner.bat','verify',target)
    print(json.dumps({'apk':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'size':target.stat().st_size}))

if __name__=='__main__':main()
