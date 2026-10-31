"""A menu patch plan derived from the input manifest, root DEX and resource IDs."""
from pathlib import Path
import re
from zipfile import ZipFile

from .hud_backup import guard_path
from .hud_tools import check_cancel, sha256_file
from .hud_stock import entries
from .hud_capsule import CAPSULE_ENTRY, PROFILE_ENTRY
from scripts.hud_manifest import inspect_application, inspect_strings

REVISION = 'structural-menu-v1'
HOME_IDS = ('main_page_ui_state_startfly_btn', 'main_page_ui_device_disconnect_state_button',
            'direct_enter_fpv_view', 'layout_direct_enter_fpv', 'connection_guide_enter_fpv_button')
HUD_IDS = ('top_bar_shell_layout', 'osd_shell_top_layout', 'osd_shell_layout',
           'left_bar_shell_layout', 'right_bar_shell_layout', 'map_shell_layout',
           'radar_shell_layout', 'histogram_shell_layout', 'zoom_focus_layer_layout',
           'right_bottom_shell_layout', 'attitude_bar_shell_layout',
           'osd_shell_top_child_layout', 'portrait_right_bar_shell_layout',
           'metering_shell_layout', 'gimbal_shell_layout')
DEX = re.compile(r'classes(?:[2-9]|[1-9][0-9]+)?\.dex\Z')


def analyze(source: Path, tools, stage: Path, cancel=None) -> dict:
    source = guard_path(source)
    if not 0 < source.stat().st_size <= 1536 * 1024 * 1024:
        raise ValueError('Kích thước APK menu vượt giới hạn.')
    digest = sha256_file(source, cancel)
    with ZipFile(source) as archive:
        all_entries = entries(archive)
        names = set(archive.namelist())
        if (not {'AndroidManifest.xml', 'resources.arsc', 'classes.dex'} <= names
                or CAPSULE_ENTRY in names or PROFILE_ENTRY in names):
            raise ValueError('Đầu vào menu thiếu tài nguyên hoặc chưa phục hồi patch cũ.')
        if archive.getinfo('AndroidManifest.xml').file_size > 4*1024*1024:
            raise ValueError('Manifest quá lớn.')
        manifest = archive.read('AndroidManifest.xml')
        identity = inspect_application(manifest)
        if identity['package'] != 'dji.go.v5':
            raise ValueError('APK menu phải thuộc DJI Fly dji.go.v5.')
        if 'local.rc2.hud.HudProvider' in inspect_strings(manifest):
            raise ValueError('APK đã có menu; cần phục hồi đúng đầu vào trước.')
        dex_entries = sorted((e for e in all_entries if DEX.fullmatch(e.filename)),
                             key=lambda e: 1 if e.filename=='classes.dex' else int(e.filename[7:-4]))
        if len(dex_entries) > 128 or any(e.file_size > 256*1024*1024 for e in dex_entries):
            raise ValueError('DEX vượt giới hạn phân tích menu.')
        maximum = max(1 if e.filename=='classes.dex' else int(e.filename[7:-4]) for e in dex_entries)
        if maximum >= 999: raise ValueError('Không thể cấp vị trí DEX menu.')
        application = 'L'+identity['application'].replace('.','/')+';'
        found = []
        for i, entry in enumerate(dex_entries):
            check_cancel(cancel)
            raw = archive.read(entry)
            if b'local/rc2/hud/HudController' in raw:
                raise ValueError('Đầu vào chứa helper menu chưa được phục hồi.')
            if application.encode() not in raw: continue
            dex = stage / ('inspect-'+str(i)+'.dex'); dex.write_bytes(raw)
            try:
                value = tools.inspect_bootstrap(dex, application)
            finally:
                dex.unlink(missing_ok=True)
            if value['found']: found.append((entry.filename, value))
        if identity['application']=='android.app.Application':
            if found: raise ValueError('Unexpected framework Application in source')
            bootstrap = {'entry': None, 'mode': 'provider', 'class_count': 0, 'descriptor':application}
        elif len(found) == 1:
            name, value = found[0]
            bootstrap = {'entry': name, 'mode': value['mode'], 'class_count': value['class_count'], 'descriptor':application}
            ancestor, seen = value['superclass'], {application}
            while ancestor != 'Landroid/app/Application;':
                if ancestor in seen or len(seen) >= 16: raise ValueError('Application inheritance is cyclic or excessive')
                seen.add(ancestor); matches = []
                for i, entry in enumerate(dex_entries):
                    check_cancel(cancel); raw = archive.read(entry)
                    if ancestor.encode() not in raw: continue
                    dex=stage/('ancestor-'+str(i)+'.dex');dex.write_bytes(raw)
                    try: item=tools.inspect_bootstrap(dex,ancestor)
                    finally: dex.unlink(missing_ok=True)
                    if item['found']: matches.append((entry.filename,item))
                if len(matches)!=1: raise ValueError('Cannot resolve Application inheritance uniquely')
                name,item=matches[0]
                if item['mode']=='context_swap':
                    if bootstrap['mode']=='context_swap':raise ValueError('Ambiguous nested context swap')
                    bootstrap={'entry':name,'mode':item['mode'],'class_count':item['class_count'],'descriptor':ancestor}
                ancestor=item['superclass']
        else:
            raise ValueError('Không xác định duy nhất Application trong DEX; chưa patch menu.')
    ids = tools.resource_names(source, stage)
    homes = [name for name in HOME_IDS if name in ids]
    hud = [name for name in HUD_IDS if name in ids]
    if not homes or 'view_surface' not in ids or len(hud) < 2:
        raise ValueError('Chưa nhận diện đủ điểm vào màn hình bay, preview và lớp HUD trong tài nguyên.')
    if sha256_file(source, cancel) != digest: raise ValueError('APK thay đổi khi phân tích menu.')
    return {'revision': REVISION, 'source_digest': digest, 'identity': identity,
            'application_descriptor': application, 'bootstrap': bootstrap,
            'helper_entry': 'classes'+str(maximum+1)+'.dex',
            'retain_loader_v2': bootstrap['mode']=='context_swap',
            'ui': {'home': homes, 'preview': ['view_surface'], 'hud': hud},
            'device_runtime_verified': False, 'aircraft_api_runtime_verification_required': True}
