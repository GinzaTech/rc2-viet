"""Apply reviewed wording fixes to the embedded Vietnamese resource table."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rc2vi.resource_embed import Table


WORDING = {
    'account_email_transfer_register_input_hint_title': 'Nhập Gmail',
    'account_guide_input_box_hint_subtitle': 'Nhập số điện thoại hoặc Gmail',
    'account_guide_subtitle': 'Nhập số điện thoại hoặc Gmail',
    'ABC_app_launch_data_transition_initial_title_storage_optimize': 'Đang chuyển dữ liệu…',
    'ABC_app_launch_storage_freeup_initial_title_storage_optimize': 'Đang giải phóng bộ nhớ…',
    'ABC_fly_launch_download_resource_fail_check_local_storage_title':
        'Không đủ dung lượng lưu trữ. Hãy giải phóng bộ nhớ rồi thử lại.',
    'ABC_fly_launch_download_resource_fail_check_network_title':
        'Không thể tải tệp tài nguyên. Kiểm tra kết nối mạng rồi thử lại.',
    'ABC_fly_launch_download_resource_success_initial_success_starting_title':
        'Đã khởi tạo xong dữ liệu tài nguyên. Đang mở DJI Fly…',
    'ABC_fly_launch_download_resource_success_initial_title': 'Đang khởi tạo dữ liệu tài nguyên…',
    'ABC_fly_launch_resource_lack_quit_download_dialog_content':
        'Thiếu tệp tài nguyên nên DJI Fly không thể khởi động. Bạn có muốn thoát và dừng tải xuống không?',
}


def update_catalog(path):
    value = json.loads(path.read_text('utf-8'))
    entries = {row['name']: row for row in value['entries']}
    if not set(WORDING) <= set(entries):
        raise ValueError('Translation catalog is missing reviewed resources')
    for name, text in WORDING.items():
        xml = entries[name]['translation_xml']
        opening = re.fullmatch(r'(<string name="' + re.escape(name) + r'">)(.*)(</string>)', xml, re.S)
        if not opening:
            raise ValueError('Unexpected catalog XML for ' + name)
        entries[name]['translation_xml'] = opening.group(1) + text + opening.group(3)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), 'utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def update_arsc(path):
    table = Table(path.read_bytes())
    pending = dict(WORDING)
    for key, config, positions in table.entries():
        kind, name = key
        if kind != 'string' or name not in pending or any(config[4:]):
            continue
        if set(positions) != {None}:
            raise ValueError('Expected one simple string value for ' + name)
        position = positions[None]
        if table.data[position + 3] != 3:
            raise ValueError('Expected a compiled string for ' + name)
        current = table.pool.strings[struct.unpack_from('<I', table.data, position + 4)[0]]
        if current == pending[name]:
            pending.pop(name)
            continue
        index = len(table.pool.strings)
        table.pool.strings.append(pending.pop(name))
        table.pool.styles.append(())
        struct.pack_into('<I', table.data, position + 4, index)
    if pending:
        raise ValueError('Embedded resource table is missing: ' + ', '.join(sorted(pending)))
    output = table.build()
    rebuilt = Table(output)
    observed = {}
    for key, config, positions in rebuilt.entries():
        if key[0] == 'string' and key[1] in WORDING and not any(config[4:]):
            value_type, index = rebuilt.values(positions)[None]
            if value_type != 3:
                raise ValueError('Updated value is not a string: ' + key[1])
            observed[key[1]] = rebuilt.pool.strings[index]
    if observed != WORDING:
        raise ValueError('Compiled wording verification failed')
    path.write_bytes(output)
    return hashlib.sha256(output).hexdigest(), len(output)


def main():
    catalog_digest = update_catalog(ROOT / 'assets/translation/catalog.json')
    memories_path = ROOT / 'assets/translation/memories.json'
    memories = json.loads(memories_path.read_text('utf-8'))
    memories['files']['catalog.json']['sha256'] = catalog_digest
    memories_path.write_text(json.dumps(memories, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    memories_digest = hashlib.sha256(memories_path.read_bytes()).hexdigest()
    memory_source = ROOT / 'rc2vi/translation_memory.py'
    source = memory_source.read_text('utf-8')
    source, count = re.subn(r"MEMORY_MANIFEST_SHA256 = '[0-9a-f]{64}'",
                            "MEMORY_MANIFEST_SHA256 = '" + memories_digest + "'", source)
    if count != 1:
        raise ValueError('Translation memory manifest pin was not unique')
    memory_source.write_text(source, 'utf-8')
    arsc = ROOT / 'assets/auto12110/vietnamese.arsc'
    digest, size = update_arsc(arsc)
    manifest_path = arsc.with_name('manifest.json')
    manifest = json.loads(manifest_path.read_text('utf-8'))
    manifest.update(resource_sha256=digest, bytes=size,
                    translation_revision='r13.1-resource-initialization-wording',
                    translation_semantics_match_reviewed_apk=False,
                    manual_overrides=sorted(WORDING))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'sha256': digest, 'bytes': size, 'catalog_sha256': catalog_digest,
                      'memory_manifest_sha256': memories_digest,
                      'updated': sorted(WORDING)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
