"""Build a local experimental feature APK, retaining the user's stock as the base.

No device connection or aircraft action. Reference feature code stays in ignored
work directories; the published source contains only the extraction/bridge recipe.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rc2vi.hud_tools import HudTools,_tool_environment,sha256_file
from rc2vi.hud_keys import HudKeyStore
from rc2vi.hud_capsule import build_capsule,recover_capsule,CAPSULE_ENTRY,PROFILE_ENTRY
from rc2vi.hud_plan import analyze
from scripts.hud_apk import repack_apk,validate_apk_change
from scripts.hud_manifest import add_adaptive_provider
from scripts.hud_signing_block import preserve_v2_file
from scripts.feature_host_patch import feature_adjustments,prepare_hosts,ui_const_sites

REFERENCE_SHA='3e7a657ae4193789b59fedc6fb0274642756b3735e6469b52c010ecce0e363fe'
STOCK_SHA='cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e'


def reviewed_menu_words():
    path=ROOT/'android-hud/feature-port/menu-vi-review.json'
    if path.stat().st_size>512*1024:raise ValueError('Oversized feature wording review')
    value=json.loads(path.read_text('utf-8'));words=value.get('strings')
    if (value.get('schema')!=1 or value.get('reference_sha256')!=REFERENCE_SHA or not isinstance(words,dict)
            or len(words)>5000 or any(not re.fullmatch('[0-9a-f]{64}',k) or not isinstance(v,str) or not v or len(v)>16000 for k,v in words.items())):
        raise ValueError('Invalid reviewed feature wording')
    return words


def feature_payload(reference_dex,toolcp,java,stage,bindings,texts):
    smali=stage/'feature-smali';smali.mkdir()
    count=int(run(java/'bin/java.exe','-cp',toolcp,'FeatureAssemblyTool','extract',smali,*sorted(reference_dex.glob('*.dex'))))
    reviewed=reviewed_menu_words();ids=set();remapped=0;translated=0;changes=[]
    for p in smali.glob('*.smali'):
        s=p.read_text('utf-8')
        def resource(m):
            nonlocal remapped
            value=int(m[0],16)
            if value==0x7fffffff:return m[0]
            if value not in bindings:raise ValueError('Feature resource lacks a matching source name: '+m[0])
            ids.add(value)
            if bindings[value]!=value:remapped+=1
            return hex(bindings[value])
        s=re.sub(r'(?<![A-Za-z0-9])0x7f[0-9a-fA-F]{6}\b',resource,s)
        s,adjustments=feature_adjustments(s)
        if adjustments:changes.append({'class':s.splitlines()[0],'changes':adjustments})
        sites=ui_const_sites(s)
        def wording(m):
            nonlocal translated
            try:raw=json.loads(m[2].replace("\\'","'"))
            except json.JSONDecodeError:return m[0]
            if m.start() not in sites:return m[0]
            target=reviewed.get(hashlib.sha256(raw.encode()).hexdigest(),texts.get(raw,raw))
            if target==raw:return m[0]
            translated+=1
            return m[1]+json.dumps(target,ensure_ascii=True)
        s=re.sub(r'(?m)^(    const-string(?:/jumbo)? [vp]\d+, )("(?:[^"\\]|\\.)*")$',wording,s)
        p.write_text(s,'utf-8')
    output=stage/'features.dex'
    if int(run(java/'bin/java.exe','-cp',toolcp,'FeatureAssemblyTool','assemble',output,smali))!=count:
        raise ValueError('Feature class count changed during assembly')
    return output,{'feature_classes':count,'resource_ids_remapped':remapped,'resource_ids_validated':len(ids),
                   'translated_constants':translated,'feature_adjustments':changes}


def run(*args):
    r=subprocess.run(list(map(str,args)),capture_output=True,text=True,encoding='utf-8',errors='replace',
                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=_tool_environment(),timeout=300)
    if r.returncode:raise RuntimeError((r.stdout+r.stderr)[-4000:])
    return r.stdout.strip()


def parse_resource_dump(text):
    rows=re.findall(r'\bresource\s+(0x[0-9a-fA-F]{8})\s+(?:[A-Za-z0-9_.]+:)?([a-zA-Z0-9_]+)/([A-Za-z0-9_.]+)',text)
    if not rows:raise ValueError('No resource inventory from AAPT2')
    result={}
    for value,kind,name in rows:
        key=(kind,name)
        if key in result and result[key]!=int(value,16):raise ValueError('Ambiguous resource identity')
        result[key]=int(value,16)
    return result


def resource_bindings(reference,stock,bundle,stage):
    aapt=stage/'resource-aapt2.exe'
    with ZipFile(bundle/'lib/apktool.jar') as z:aapt.write_bytes(z.read('prebuilt/windows/aapt2_64.exe'))
    try:
        a=parse_resource_dump(run(aapt,'dump','resources','--no-values',reference))
        b=parse_resource_dump(run(aapt,'dump','resources','--no-values',stock))
        return {old:b[key] for key,old in a.items() if key in b}
    finally:aapt.unlink(missing_ok=True)


def prepare_bridge(directory,java,sdk):
    source=directory/'source';source.mkdir()
    for original in (ROOT/'android-hud/src').rglob('*.java'):
        target=source/original.relative_to(ROOT/'android-hud/src');target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original,target)
    for original in (ROOT/'android-hud/feature-port').rglob('*.java'):
        target=source/original.relative_to(ROOT/'android-hud/feature-port')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
    p=source/'local/rc2/hud/HudController.java';s=p.read_text('utf-8')
    s=s.replace('app.registerActivityLifecycleCallbacks(created);','app.registerActivityLifecycleCallbacks(created);\n            PortIntegration.install(app);')
    s=s.replace('int role=ScreenRoles.select(activity.getClass().getName(),views);','int role=ScreenRoles.select(activity.getClass().getName(),views);\n        PortIntegration.resumed(activity,role);')
    s=s.replace('@Override public void onActivityPaused(Activity activity) {','@Override public void onActivityPaused(Activity activity) {\n        PortIntegration.paused(activity);')
    s=s.replace('@Override public void onActivityDestroyed(Activity activity) {','@Override public void onActivityDestroyed(Activity activity) {\n        PortIntegration.paused(activity);')
    s=s.replace('hidden = changedCount > 0;','changedCount += PortIntegration.hideExtras(root,original);\n            hidden = changedCount > 0;\n            if(hidden) PortIntegration.hudHidden(activity,root,true);')
    s=s.replace('original.clear();\n            hidden = false;','original.clear();\n            hidden = false;\n            if(alive) PortIntegration.hudHidden(activity,root,false);')
    p.write_text(s,'utf-8')
    p=source/'local/rc2/hud/DeviceMenu.java';s=p.read_text('utf-8')
    marker='content.addView(scroll,new LinearLayout.LayoutParams(-1,-2));'
    if marker not in s:raise ValueError('Menu insertion point changed')
    s=s.replace(marker,'PortIntegration.addMenu(activity,panel);\n        '+marker);p.write_text(s,'utf-8')
    marker='radio.request(fcc,(ok,message)->activity.runOnUiThread(()->{'
    if s.count(marker)!=1:raise ValueError('Radio completion point changed')
    s=s.replace(marker,marker+'\n                    if(ok) PortIntegration.radioUpdated(activity,fcc);');p.write_text(s,'utf-8')
    classes=directory/'classes';classes.mkdir();dex=directory/'bridge-dex';dex.mkdir()
    android=sdk/'platforms/android-30/android.jar';r8=sdk/'build-tools/36.1.0/lib/d8.jar'
    if not r8.exists():r8=sdk/'build-tools/36.1.0/lib/r8.jar'
    run(java/'bin/javac.exe','-source','8','-target','8','-encoding','UTF-8','-cp',android,'-d',classes,*sorted(source.rglob('*.java')))
    run(java/'bin/java.exe','-cp',r8,'com.android.tools.r8.D8','--min-api','30','--lib',android,'--output',dex,*sorted(classes.rglob('*.class')))
    return (dex/'classes.dex').read_bytes()


def build(source,reference,java,sdk,work,menu_translations=None):
    if sha256_file(source)!=STOCK_SHA:raise ValueError('Candidate currently requires the verified stock1.21.8 input')
    if sha256_file(reference)!=REFERENCE_SHA:raise ValueError('Reference APK checksum differs')
    work=work.resolve();work.mkdir(parents=True,exist_ok=True)
    stage=work/uuid.uuid4().hex;stage.mkdir()
    tools=HudTools(ROOT/'assets',work/'tools');bundle=tools.prepare()
    cp=os.pathsep.join(str(bundle/'lib'/n) for n in ['apktool.jar','apksigner.jar'])
    classes=stage/'tool-classes';classes.mkdir()
    run(java/'bin/javac.exe','-encoding','UTF-8','-cp',cp,'-d',classes,
        *[ROOT/'android-hud'/(name+'.java') for name in ['AdaptiveHudTool','FeatureAssemblyTool','FeatureHookTool','FeatureAuditTool']])
    refdex=stage/'reference-dex';refdex.mkdir()
    with ZipFile(reference) as z:
        names=sorted(n for n in z.namelist() if re.fullmatch(r'classes(?:[2-9]|[1-9][0-9]+)?\.dex',n))
        for n in names:(refdex/n).write_bytes(z.read(n))
    toolcp=str(classes)+os.pathsep+cp
    texts=json.loads(menu_translations.read_text('utf-8')) if menu_translations else {}
    if not isinstance(texts,dict) or any(not isinstance(k,str) or not isinstance(v,str) or not k or not v for k,v in texts.items()):
        raise ValueError('Menu translation input must be an exact text dictionary')
    bindings=resource_bindings(reference,source,bundle,stage)
    feature_dex,payload=feature_payload(refdex,toolcp,java,stage,bindings,texts)
    count=payload['feature_classes'];patched_ids=payload['resource_ids_remapped']
    translated_constants=payload['translated_constants'];feature_changes=payload['feature_adjustments']
    stockdex=stage/'stock-dex';stockdex.mkdir()
    with ZipFile(source) as z:
        for name in z.namelist():
            if re.fullmatch(r'classes(?:[2-9]|[1-9][0-9]+)?\.dex',name):(stockdex/name).write_bytes(z.read(name))
    refhosts=stage/'reference-hosts'
    run(java/'bin/java.exe','-Xmx1536m','-cp',toolcp,'FeatureAuditTool','hosts',refhosts,*sorted(refdex.glob('*.dex')))
    typefile=stage/'host-types.txt'
    host_types={line.split('\t')[2] for line in (refhosts/'hosts.tsv').read_text('utf-8').splitlines()}
    host_types.add('Lcom/uav/component/fpv/widget/setting/ui/safety/SettingAltitudeLimitViewModel;')
    typefile.write_text('\n'.join(sorted(host_types)),'utf-8')
    stockhosts=stage/'stock-hosts'
    run(java/'bin/java.exe','-Xmx1536m','-cp',toolcp,'FeatureAuditTool','dump',stockhosts,typefile,*sorted(stockdex.glob('*.dex')))
    hostpatch=stage/'host-patches';method_hooks=prepare_hosts(stockhosts,hostpatch)
    planstage=stage/'plan';planstage.mkdir();plan=analyze(source,tools,planstage)
    with ZipFile(source) as z:
        replacements={'AndroidManifest.xml':add_adaptive_provider(z.read('AndroidManifest.xml'))}
        inp=stage/'bootstrap.dex';inp.write_bytes(z.read(plan['bootstrap']['entry']))
    patched=stage/'bootstrap-patched.dex';tools.patch_adaptive(inp,patched,stage/'smali',plan['bootstrap']['descriptor'])
    replacements[plan['bootstrap']['entry']]=patched.read_bytes()
    class_index={line.split('\t')[0]:line.split('\t')[2] for line in (stockhosts/'classes.tsv').read_text('utf-8').splitlines()}
    targets=['Lcom/uav/fpv/leftbar/component/takeoffandland/LandAndGoHomeVM;',
             'Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandView;',
             'Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandViewModel;']
    host_hooks=[]
    dexnames={class_index[name] for name in targets}|{row['dex'] for row in method_hooks}
    for entry in sorted(dexnames):
        inp=stage/('host-'+entry);out=stage/('hooked-'+entry)
        with ZipFile(source) as z:inp.write_bytes(z.read(entry))
        changed=int(run(java/'bin/java.exe','-Xmx1536m','-cp',toolcp,'FeatureHookTool',inp,out,stage/('host-smali-'+entry),hostpatch))
        replacements[entry]=out.read_bytes();host_hooks.append({'dex':entry,'classes_patched':changed})
    bridge=prepare_bridge(stage,java,sdk)
    run(java/'bin/java.exe','-Xmx1536m','-cp',toolcp,'FeatureAuditTool','check',stage/'dependencies.tsv',stockdex,feature_dex,stage/'bridge-dex/classes.dex')
    if (stage/'dependencies.tsv').read_text('utf-8').strip():raise ValueError('Unresolved feature API dependencies; inspect dependencies.tsv')
    capsule=stage/'recovery.zip';build_capsule(source,capsule,set(replacements))
    helper=plan['helper_entry'];slot=int(helper[7:-4]);addon='classes'+str(slot+1)+'.dex'
    profile={'schema':1,'kind':'redfly-feature-candidate','source_sha256':STOCK_SHA,'reference_sha256':REFERENCE_SHA,
             'helper_entry':helper,'feature_entry':addon,'feature_classes':count,'resource_ids_remapped':patched_ids,
             'resource_ids_validated':payload['resource_ids_validated'],
             'runtime_verified':False,'host_hooks':host_hooks,'method_hooks':method_hooks,
             'translated_constants':translated_constants,'feature_adjustments':feature_changes,
             'unported':['login-limit native/activation changes'],
             'host_method_hooks_complete':False,'plan':plan}
    additions={helper:bridge,addon:feature_dex.read_bytes(),CAPSULE_ENTRY:capsule.read_bytes(),PROFILE_ENTRY:json.dumps(profile,sort_keys=True).encode()}
    unsigned,aligned,signed,output=[stage/(n+'.apk') for n in ['unsigned','aligned','signed','candidate']]
    repack_apk(source,unsigned,replacements=replacements,additions=additions)
    tools.align(unsigned,aligned);keys=HudKeyStore(tools);key=keys.ensure()
    tools.sign(aligned,signed,key.keyfile,key.alias,key.password);preserve_v2_file(source,signed,output)
    changes=validate_apk_change(source,output,replacements=replacements,additions=additions)
    if tools.verify(output)!=key.certificate_sha256:raise ValueError('Candidate signer check failed')
    restored=stage/'restored.apk';recover_capsule(output,capsule,restored,additions.keys())
    if sha256_file(restored)!=STOCK_SHA:raise ValueError('Source round-trip failed')
    report={'status':'feature_candidate_built','apk':str(output),'sha256':sha256_file(output),'bytes':output.stat().st_size,
            'certificate_sha256':key.certificate_sha256,'source_sha256':STOCK_SHA,'reference_sha256':REFERENCE_SHA,
            'feature_classes':count,'resource_ids_remapped':patched_ids,'changes':changes,'runtime_verified':False,
            'host_hooks':host_hooks,'method_hooks':method_hooks,'translated_constants':translated_constants,
            'host_method_hooks_complete':False,'all_features_verified':False,'profile':profile}
    (stage/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--java-home',type=Path,required=True);parser.add_argument('--sdk',type=Path,required=True)
    parser.add_argument('--work',type=Path,default=ROOT/'phone-work/feature-candidate')
    parser.add_argument('--menu-translations',type=Path)
    args=parser.parse_args();print(json.dumps(build(args.source,args.reference,args.java_home,args.sdk,args.work,args.menu_translations),ensure_ascii=False))


if __name__=='__main__':main()
