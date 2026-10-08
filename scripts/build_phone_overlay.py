"""Build phone translations only when old and current English source agree."""
from pathlib import Path
import copy
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from rc2vi.phone_resources import compatible_resources

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'phone-work/fly-source/res'
PREVIOUS=Path(os.environ['RC2VI_PREVIOUS_SOURCE'])/'res/values'
KEYS=Path(os.environ['RC2VI_SIGNING_DIR'])
BUILD=ROOT/'phone-work/overlay'
TOOLS=Path(os.environ['LOCALAPPDATA'])/'Android/Sdk/build-tools/36.1.0'
ANDROID=TOOLS.parents[1]/'platforms/android-34/android.jar'


def run(*args):
    result=subprocess.run([str(a) for a in args],capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))


def main():
    report={};total=0
    reviewed={
        'account_guide_privacy_tips_subtitle_user':'Điều khoản sử dụng',
        'gdpr_legal_term_user_agreement_top_bar_title':'Điều khoản sử dụng',
        'terms_update_notification_terms_of_use':'Điều khoản sử dụng',
        'account_guide_privacy_tips_subtitle_privacy':'Thông báo về quyền riêng tư',
        'gdpr_legal_term_privac_agreement_top_bar_title':'Thông báo về quyền riêng tư',
        'terms_update_notification_privacy_notice':'Thông báo về quyền riêng tư',
        'gdpr_legal_term_disagree_btn':'Không đồng ý',
        'fpv_basic_flight_topbar_panel_tof_obstacle_avoid_state':'Hệ thống cảm biến',
    }
    locales=['values','values-vi','values-en','values-en-rUS','values-en-rGB','values-en-rAU','values-en-rCA','values-en-rIN']
    for filename in ['strings.xml','plurals.xml','arrays.xml']:
        old=ET.parse(PREVIOUS/filename).getroot();new=ET.parse(SOURCE/'values'/filename).getroot()
        vi=ET.parse(ROOT/'translation/review-round2/overlay/res/values'/filename).getroot()
        accepted,rejected=compatible_resources(old,new,vi)
        # A regional English override with changed text must also be excluded.
        current={e.get('name'):e for e in new}
        conflicts=set()
        from rc2vi.phone_resources import identity
        for locale in locales:
            file=SOURCE/locale/filename
            if locale.startswith('values-en') and file.exists():
                for e in ET.parse(file).getroot():
                    name=e.get('name')
                    if name in current and identity(e)!=identity(current[name]):conflicts.add(name)
        final=[e for e in accepted if e.get('name') not in conflicts]
        for element in final:
            if element.get('name') in reviewed:element.text=reviewed[element.get('name')]
        for locale in locales:
            path=BUILD/'res'/locale/filename;path.parent.mkdir(parents=True,exist_ok=True)
            tree=ET.Element('resources');tree.extend(copy.deepcopy(final));ET.ElementTree(tree).write(path,encoding='utf-8',xml_declaration=True)
        total+=len(final);report[filename]={'accepted':len(final),'source_changed_or_absent':rejected,'regional_conflicts':sorted(conflicts)}
    report['reviewed_visible_labels']=reviewed
    manifest='''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="local.dji.fly.phone.vietnamese" android:versionCode="3" android:versionName="1.21.12-vi3"><uses-sdk android:minSdkVersion="35" android:targetSdkVersion="35"/><overlay android:targetPackage="dji.go.v5" android:targetName="DJIFlyPhoneTranslation" android:isStatic="false" android:priority="999"/><application android:hasCode="false" android:label="Tiếng Việt DJI Fly Android"/></manifest>'''
    (BUILD/'AndroidManifest.xml').write_text(manifest,encoding='utf-8')
    run(TOOLS/'aapt2.exe','compile','--dir',BUILD/'res','-o',BUILD/'resources.zip')
    run(TOOLS/'aapt2.exe','link','--manifest',BUILD/'AndroidManifest.xml','-I',ANDROID,'-R',BUILD/'resources.zip',
        '--auto-add-overlay','--no-resource-deduping','--no-resource-removal','-o',BUILD/'unsigned.apk')
    run(TOOLS/'zipalign.exe','-f','4',BUILD/'unsigned.apk',BUILD/'aligned.apk')
    config=json.loads((KEYS/'local-signing.json').read_text())
    os.environ['RC2VI_SIGN_PASS']=config['password']
    target=ROOT/'assets/phone-vietnamese-resources.apk'
    try:
        run(TOOLS/'apksigner.bat','sign','--ks',KEYS/'local-vietnamese-draft.jks','--ks-key-alias',config['alias'],
            '--ks-pass','env:RC2VI_SIGN_PASS','--key-pass','env:RC2VI_SIGN_PASS','--out',target,BUILD/'aligned.apk')
    finally:os.environ.pop('RC2VI_SIGN_PASS',None)
    run(TOOLS/'apksigner.bat','verify',target)
    report['active_resources']=total;report['overlay_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    report['target_sha256']=hashlib.sha256((ROOT/'phone-work/DJI-Fly-official-real.apk').read_bytes()).hexdigest()
    (ROOT/'docs/phone-resource-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if not isinstance(v,dict)}))


if __name__=='__main__':main()
