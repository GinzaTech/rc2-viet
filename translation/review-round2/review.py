"""Audit the full catalog; apply reviewed full sentences and bounded terminology rules."""
import copy
import csv
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from user_wording import apply_user_wording

HERE=Path(__file__).parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
import localize_resources as L

FEATURES={
    'FocusTrack':'FocusTrack','Subject Scanning':'quét chủ thể','Target Scanning':'quét chủ thể',
    'AEB':'chụp bù phơi sáng (AEB)','Burst':'chụp liên tiếp','Explore':'Khám phá',
    'Night':'Ban đêm','Pano':'chụp toàn cảnh','Portrait':'khung hình dọc','Landscape':'khung hình ngang',
    'Slow Motion':'quay chậm','Enhanced Transmission':'truyền tín hiệu tăng cường',
    'SmartPhoto':'chụp ảnh thông minh (SmartPhoto)','Timed Shot':'chụp theo khoảng thời gian',
    'MasterShots':'MasterShots','QuickShots':'QuickShots','Hyperlapse':'Hyperlapse',
    'Free Hyperlapse':'Hyperlapse tự do','Circle Hyperlapse':'Hyperlapse vòng tròn',
    'Local Data':'dữ liệu cục bộ','Local Data Mode':'dữ liệu cục bộ',
}

def feature(value):
    value=value.strip()
    for suffix in (' mode',' Mode'):
        if value.endswith(suffix):
            basic=value[:-len(suffix)]
            return 'chế độ '+FEATURES[basic] if basic in FEATURES else None
    return FEATURES.get(value)

def action(value):
    match=re.fullmatch(r'shoot (\d+MP) photos',value)
    if match: return 'chụp ảnh '+match[1]
    for prefix,target in [('shoot in ','chụp/quay ở '),('shoot ','chụp '),('use ','dùng '),
                          ('enable ','bật '),('enter ','dùng '),('switch to ','chuyển sang ')]:
        if value.startswith(prefix):
            translated=feature(value[len(prefix):])
            if translated: return target+translated
    return None

def translate_sentence(source):
    normalized=L.normalize_source(source)
    patterns=[(r'Unable to (.+) when using (.+)', ' khi dùng '),
              (r'Unable to (.+) in (.+)', ' trong ')]
    for pattern,join in patterns:
        match=re.fullmatch(pattern,normalized)
        if match:
            verb=action(match[1]); context=feature(match[2])
            if verb and context: return 'Không thể '+verb+join+context
    reasons={
        'Aircraft in Attitude mode':'Máy bay đang ở chế độ ATTI',
        'Aircraft landing':'Máy bay đang hạ cánh',
        'Aircraft landing automatically':'Máy bay đang tự hạ cánh',
        'Aircraft not in flight':'Máy bay chưa bay',
        'Aircraft taking off':'Máy bay đang cất cánh',
        'RTH in progress':'Đang quay về điểm cất cánh (RTH)',
        'Satellite positioning signal weak':'Tín hiệu định vị vệ tinh yếu',
        'Wide-angle lens attached':'Đã gắn ống kính góc rộng',
    }
    match=re.fullmatch(r'(.+)\. Unable to (.+)',normalized)
    if match and match[1] in reasons:
        verb=action(match[2])
        if verb: return reasons[match[1]]+'. Không thể '+verb
    match=re.fullmatch(r'Solution: Restart your aircraft\. Contact DJI Support if the problem persists after restarting\. \(Error Code: (0x[0-9a-fA-F]+)\)',normalized)
    if match:
        return 'Giải pháp: Khởi động lại máy bay. Liên hệ bộ phận hỗ trợ DJI nếu lỗi vẫn còn sau khi khởi động lại. (Mã lỗi: '+match[1]+')'
    return None

def technical(text):
    value=L.normalize_source(text).strip()
    return bool(re.fullmatch(r'cubic-bezier\([^)]*\)',value) or
                re.fullmatch(r'(?:\d+,[A-Z]{2}\s*){2,}',value) or
                re.fullmatch(r'(?:[A-Za-z_]\w*\.){2,}[A-Za-z_]\w*',value) or
                re.fullmatch(r'(?:PhoneNumberAuthSDK|DJI_YYYYMMDDhhmmss|x{8,}(?:-x+)?)',value))

def valid(source,target):
    if L.normalize_source(source)=='Metric (km)' and target=='Hệ kilomet(Km)':
        target='Hệ kilomet(km)'
    if not isinstance(target,str) or not target.strip(): return False
    for pattern in [r'(?<!\d)'+L.FORMAT,L.TAG,L.ESCAPE,L.URL,L.UNIT,L.NUMBER]:
        if re.findall(pattern,source)!=re.findall(pattern,target): return False
    # Standalone units and URI schemes were previously unprotected.
    for pattern in [r'\b(?:km|mm|m/s|km/h|fps|GHz|MHz|dBm)\b',
                    r'(?:https?|rtmp)://[^\s<>]+']:
        if re.findall(pattern,source)!=re.findall(pattern,target): return False
    return True

def harmonize(source,target):
    rules=[]
    if re.search(r'calibrat',source,re.I): rules+= [('cân chỉnh','hiệu chuẩn')]
    if re.search(r'firmware',source,re.I):
        rules+= [('phần mềm công ty','firmware'),('phần mềm vững chắc','firmware'),
                 ('phần mềm công cụ','firmware'),('phần mềm thiết bị','firmware'),('phần cứng','firmware')]
    if re.search(r'remote controller',source,re.I): rules+= [('bộ điều khiển từ xa','tay điều khiển'),('điều khiển từ xa','tay điều khiển')]
    if re.search(r'flight record',source,re.I): rules+= [('ghi âm máy bay','nhật ký bay'),('ghi hình chuyến bay','nhật ký bay'),('ghi chép chuyến bay','nhật ký bay'),('hồ sơ chuyến bay','nhật ký bay'),('hồ sơ bay','nhật ký bay')]
    if re.search(r'(?:video|screen) record|record(?:ing)? (?:video|screen)',source,re.I): rules+= [('ghi âm','ghi hình'),('thu âm','ghi hình')]
    if 'Find My Drone' in source: rules+= [('Tìm Máy chủ của tôi','Tìm máy bay'),('Tìm kiếm Máy chủ của tôi','Tìm máy bay')]
    if re.search(r'function',source,re.I): rules+= [('hàm','chức năng')]
    if re.search(r'subject',source,re.I): rules+= [('chủ đề','chủ thể'),('đối tượng','chủ thể')]
    if re.search(r'Home Point|home point',source): rules+= [('điểm chính','điểm quay về'),('điểm Nhà','điểm quay về'),('điểm nhà','điểm quay về')]
    if re.search(r'glamour',source,re.I): rules+= [('hiệu ứng băng hà','hiệu ứng làm đẹp'),('hiệu ứng băng giá','hiệu ứng làm đẹp')]
    if re.search(r'livestream|live streaming',source,re.I): rules+= [('dòng sống','phát trực tiếp'),('chạy ngược dòng','phát trực tiếp'),('dòng trực tiếp','phát trực tiếp')]
    for old,new in rules:
        target=re.sub(re.escape(old),lambda m:new.capitalize() if m[0][0].isupper() else new,target,flags=re.I)
    return target

def load_manual():
    result=json.loads((ROOT/'terminology.json').read_text(encoding='utf-8'))
    result.update(json.loads((ROOT/'reviewed-text-overrides.json').read_text(encoding='utf-8')))
    result.update(json.loads((ROOT/'reviewed-visible-ui.json').read_text(encoding='utf-8')))
    for filename in ['clauses.tsv','phrases.tsv','diagnostics.tsv','long-sentences.tsv']:
        path=HERE/filename
        if not path.exists(): continue
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                source,target=line.split('\t',1)
                result[L.normalize_source(source.replace('\\n','\n'))]=target.replace('\\n','\n')
    result.update(json.loads((HERE/'lost-meaning-fixed.json').read_text(encoding='utf-8')))
    if (HERE/'flight-settings-fixed.json').exists():
        result.update(json.loads((HERE/'flight-settings-fixed.json').read_text(encoding='utf-8')))
    if (HERE/'remaining-fixed.json').exists():
        result.update(json.loads((HERE/'remaining-fixed.json').read_text(encoding='utf-8')))
    if (HERE/'remaining-long-fixed.json').exists():
        result.update(json.loads((HERE/'remaining-long-fixed.json').read_text(encoding='utf-8')))
    return {L.normalize_source(k):v.replace('\\n','\n') if '\n' in k else v for k,v in result.items()}

def reviewed_clauses(manual):
    clauses={}
    for source,target in manual.items():
        en=re.split(r'(?<=[.!?])\s+',source)
        vi=re.split(r'(?<=[.!?])\s+',target)
        if len(en)!=len(vi):continue
        for a,b in zip(en,vi):
            if a.strip() and b.strip():clauses[clause_key(a)]=b.strip().rstrip('.')
    return clauses

def compose_reviewed(source,clauses):
    parts=re.split(r'(?<=[.!?])\s+',L.normalize_source(source))
    if len(parts)<2:return None
    targets=[clauses.get(clause_key(p)) or diagnostic_clause(p) for p in parts]
    if any(t is None for t in targets):return None
    return '. '.join(targets)+('.' if source.endswith('.') else '')

def clause_key(text):
    return re.sub(r'\s+',' ',text.strip().rstrip('.')).casefold()

def diagnostic_clause(source):
    components={'gyroscope':'cảm biến con quay hồi chuyển','accelerometer':'cảm biến gia tốc',
                'barometer':'cảm biến áp suất','compass':'la bàn','imu':'IMU','battery':'pin',
                'gimbal':'gimbal','gimbal gyroscope':'con quay hồi chuyển gimbal','gimbal imu':'IMU gimbal',
                'esc':'bộ điều tốc (ESC)','camera':'camera','sensor':'cảm biến','aircraft':'máy bay',
                'aircraft satellite positioning':'định vị vệ tinh máy bay','recorded data':'dữ liệu đã ghi',
                'data recorder':'bộ ghi dữ liệu','remote controller':'tay điều khiển',
                'downward vision sensor calibration parameter':'thông số hiệu chuẩn cảm biến hình ảnh phía dưới',
                'backward vision sensor calibration':'hiệu chuẩn cảm biến hình ảnh phía sau',
                'downward vision sensor calibration':'hiệu chuẩn cảm biến hình ảnh phía dưới',
                'forward vision sensor calibration':'hiệu chuẩn cảm biến hình ảnh phía trước'}
    for en,vi in [('backward','phía sau'),('forward','phía trước'),('downward','phía dưới'),
                  ('upward','phía trên'),('left','bên trái'),('right','bên phải')]:
        components[en+' vision sensor']='cảm biến hình ảnh '+vi
        components[en+' tof sensor']='cảm biến ToF '+vi
    conditions={' error':'Lỗi ', ' malfunction':'Lỗi ', ' value error':'Lỗi giá trị ',
                ' initialization failed':'Khởi tạo thất bại: ', ' installation error':'Lắp không đúng: ',
                ' hardware malfunction':'Lỗi phần cứng ', ' data error':'Lỗi dữ liệu ',
                ' calibration error':'Lỗi hiệu chuẩn ', ' calibration incomplete':'Hiệu chuẩn chưa hoàn tất: ',
                ' calibration required':'Cần hiệu chuẩn ', ' connection error':'Lỗi kết nối '}
    key=clause_key(source)
    for suffix,prefix in sorted(conditions.items(),key=lambda item:len(item[0]),reverse=True):
        if key.endswith(suffix) and key[:-len(suffix)] in components:
            return prefix+components[key[:-len(suffix)]]
    return None

def main():
    manual=load_manual()
    clauses=reviewed_clauses(manual)
    roots={name:ET.parse(ROOT/'overlay-full/res/values-vi'/name).getroot()
           for name in ['strings.xml','plurals.xml','arrays.xml']}
    indices={name:{e.get('name'):e for e in root} for name,root in roots.items()}
    changes=[]; rejected=[]; removed=[]; missing=[]; audit=[]
    for filename,name,original in L.entries():
        source_slots=list(L.text_slots(original))
        source=' '.join(t for _,_,t in source_slots)
        clone=copy.deepcopy(original)
        current=indices[filename].get(name)
        if name=='country_code_2_country_str' or any(technical(t) for _,_,t in source_slots):
            if current is not None: roots[filename].remove(current); removed.append(name)
            audit.append({'name':name,'status':'technical_original_preserved'})
            continue
        if original.get('translatable')=='false' or not any(L.should_translate(name,t) for _,_,t in source_slots):
            audit.append({'name':name,'status':'excluded_original'})
            continue
        current_slots=list(L.text_slots(current)) if current is not None else []
        fully_reviewed=True; changed=False; status='reviewed_full_sentence'
        for index,(node,attr,text) in enumerate(list(L.text_slots(clone))):
            if not text.strip():
                continue
            normalized=L.normalize_source(text)
            target=manual.get(normalized) or translate_sentence(text) or diagnostic_clause(text) or compose_reviewed(text,clauses)
            contextual={'fpv_camera_osd_livephoto_format_label':'Ảnh động',
                        'fpv_setting_control_camera_mode_single_camera_title':'Một ống kính',
                        'light_editor_select_material_format_circle':'Hình tròn'}
            if name in contextual:target=contextual[name]
            if target and not re.search(r'takeoff point|take.off point',text,re.I):
                target=re.sub('quay về điểm cất cánh','quay về điểm đã đặt',target,flags=re.I)
            if target is None:
                fully_reviewed=False
                if index>=len(current_slots): break
                previous=current_slots[index][2]
                target=harmonize(text,previous)
                if target!=previous: status='terminology_only'
            target=apply_user_wording(target)
            if not valid(text,target):
                rejected.append({'name':name,'source':text,'proposed':target})
                fully_reviewed=False
                if index>=len(current_slots): break
                target=current_slots[index][2]
            escaped=L.android_escape(target)
            setattr(node,attr,escaped)
            if index>=len(current_slots) or escaped!=current_slots[index][2]: changed=True
        else:
            if current is not None or fully_reviewed:
                if changed:
                    if current is not None: roots[filename].remove(current)
                    roots[filename].append(clone)
                    changes.append({'name':name,'source':source,'old':' '.join(t for _,_,t in current_slots),
                                    'new':' '.join(t for _,_,t in L.text_slots(clone)),
                                    'review':status if fully_reviewed or status=='terminology_only' else 'existing_draft'})
                audit.append({'name':name,'status':status if fully_reviewed else 'existing_draft'})
                continue
        missing.append({'name':name,'source':source})
        audit.append({'name':name,'status':'stock_text_pending'})
    overlay=HERE/'overlay'
    for filename,root in roots.items():
        ET.indent(root,space='    ')
        for locale in ['values','values-en','values-en-rUS','values-vi']:
            path=overlay/'res'/locale/filename; path.parent.mkdir(parents=True,exist_ok=True)
            ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    report={'catalog_scanned':len(audit),'changed_resources':len(changes),
            'full_sentence_changes':sum(c['review']=='reviewed_full_sentence' for c in changes),
            'terminology_changes':sum(c['review']=='terminology_only' for c in changes),
            'technical_overrides_removed':len(removed),'rejected_candidates':len(rejected),
            'stock_resources_pending':len(missing),'active_resources':sum(len(r) for r in roots.values())}
    for name,data in [('changes',changes),('audit',audit),('rejected',rejected),('pending',missing),('removed-technical',removed),('summary',report)]:
        (HERE/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__': main()
