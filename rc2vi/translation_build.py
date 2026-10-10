"""Build a resource-only Vietnamese RRO against the installed Fly resources."""
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from .hud_keys import HudKeyStore
from .hud_tools import (HudTools, _check_ancestors, _physical_stat, _safe_relative, _tool_environment,
                        check_cancel, load_json, run_process, sha256_file)

CATALOG_SHA256 = 'f8efb85dc2b8920db255297e0fe225c2a5c0be70916701d5b49ebdf145a02ddd'
MAX_APK_BYTES = 1536 * 1024 * 1024
MAX_RESOURCE_BYTES = 512 * 1024 * 1024
PREFIX = 'local.dji.fly.vi.auto.'


def resource_snapshot(source: Path, destination: Path, cancel=None) -> None:
    """Strip code/assets before parsing; bound and validate every copied entry."""
    _check_ancestors(source.parent)
    _physical_stat(source)
    _check_ancestors(destination.parent)
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_APK_BYTES:
        raise ValueError('Kích thước APK không hợp lệ để đọc tài nguyên.')
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            names = [i.filename for i in members]
            if (len(members) > 150000 or len(set(names)) != len(names)
                    or not {'AndroidManifest.xml', 'resources.arsc'} <= set(names)):
                raise ValueError('APK thiếu tài nguyên hoặc có entry trùng.')
            selected = []
            for info in members:
                check_cancel(cancel)
                name = info.filename
                if (info.orig_filename != name or name.startswith(('/', '\\'))
                        or '\\' in name or '..' in name.split('/')):
                    raise ValueError('Đường dẫn trong APK không an toàn.')
                if name in {'AndroidManifest.xml', 'resources.arsc'} or name.startswith('res/'):
                    if info.is_dir():
                        continue
                    _safe_relative(name)
                    if (info.flag_bits & 1 or info.file_size > 96 * 1024 * 1024
                            or (info.external_attr >> 16) & 0o170000 == 0o120000):
                        raise ValueError('Entry tài nguyên APK không hợp lệ.')
                    selected.append(info)
            if sum(i.file_size for i in selected) > MAX_RESOURCE_BYTES:
                raise ValueError('Tài nguyên APK vượt giới hạn xử lý.')
            with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as output:
                for info in selected:
                    check_cancel(cancel)
                    with archive.open(info) as src, output.open(info.filename, 'w') as dst:
                        while chunk := src.read(1024 * 1024):
                            check_cancel(cancel)
                            dst.write(chunk)
    except zipfile.BadZipFile:
        raise ValueError('APK không phải ZIP tài nguyên hợp lệ.') from None


class TranslationBuilder:
    def __init__(self, assets: Path, work: Path, emit=lambda *args: None, cancel=None, sdk=30):
        if type(sdk) is not int or sdk not in (30, 35):
            raise ValueError('Chưa hỗ trợ định dạng overlay của SDK này.')
        self.assets = Path(assets)
        self.work = Path(work).absolute()
        self.emit = emit
        self.cancel = cancel
        self.sdk = sdk
        self.target_name = 'DJIFlyPhoneTranslation' if sdk == 35 else 'DJIFlyLocalTranslation'
        self.tools = HudTools(self.assets, self.work / 'tools', cancel)

    def _run(self, *args):
        return run_process(args, cancel=self.cancel, env=_tool_environment())

    def _utilities(self, stage):
        root = self.tools.prepare()
        jar = root / 'lib/apktool.jar'
        with zipfile.ZipFile(jar) as archive:
            aapt = stage / 'aapt2.exe'
            framework = stage / 'framework.apk'
            aapt.write_bytes(archive.read('prebuilt/windows/aapt2_64.exe'))
            framework.write_bytes(archive.read('prebuilt/android-framework.jar'))
        return root / 'java/bin/java.exe', jar, aapt, framework

    def _cached(self, folder, source_hash, package, certificate):
        _check_ancestors(folder)
        receipt = load_json(folder / 'receipt.json')
        apk = folder / 'overlay.apk'
        _check_ancestors(apk.parent)
        _physical_stat(apk)
        if (receipt.get('source_digest') != source_hash or receipt.get('package') != package
                or receipt.get('profile_sdk') != self.sdk
                or receipt.get('catalog_digest') != CATALOG_SHA256
                or receipt.get('digest') != sha256_file(apk, self.cancel)
                or self.tools.verify(apk) != certificate):
            raise ValueError('Cache bản dịch bị thay đổi; không cài gói này.')
        self._resource_only(apk)
        return dict(receipt, apk=apk)

    @staticmethod
    def _resource_only(apk):
        with zipfile.ZipFile(apk) as archive:
            names = archive.namelist()
            if (len(names) != len(set(names)) or not {'AndroidManifest.xml', 'resources.arsc'} <= set(names)
                    or any(n not in {'AndroidManifest.xml', 'resources.arsc'}
                           and not n.startswith('META-INF/') for n in names)):
                raise ValueError('Gói dịch phải chỉ chứa manifest và bảng tài nguyên.')

    def build(self, source_apk: Path) -> dict:
        from .translation_catalog import select_resources
        source_apk = Path(source_apk).absolute()
        _check_ancestors(source_apk.parent)
        _physical_stat(source_apk)
        source_hash = sha256_file(source_apk, self.cancel)
        catalog_path = self.assets / 'translation/catalog.json'
        if sha256_file(catalog_path, self.cancel) != CATALOG_SHA256:
            raise ValueError('Từ điển bản dịch không khớp gói EXE.')
        catalog = load_json(catalog_path)
        _check_ancestors(self.work)
        self.work.mkdir(parents=True, exist_ok=True)
        key = HudKeyStore(self.tools, root=self.work / 'private-signing').ensure()
        profile = hashlib.sha256((CATALOG_SHA256 + ':' + str(self.sdk)).encode()).hexdigest()[:8]
        package = PREFIX + 'r' + source_hash[:16] + 'c' + profile + 's' + key.certificate_sha256[:8]
        folder = self.work / 'builds' / package
        _check_ancestors(folder)
        if folder.exists():
            return self._cached(folder, source_hash, package, key.certificate_sha256)
        self.emit('applying', 'Đang đọc tài nguyên DJI Fly và đối chiếu từ điển tiếng Việt…')
        with tempfile.TemporaryDirectory(prefix='translation-', dir=self.work) as temporary:
            stage = Path(temporary)
            java, jar, aapt, framework = self._utilities(stage)
            snapshot = stage / 'resources.apk'
            resource_snapshot(source_apk, snapshot, self.cancel)
            if sha256_file(source_apk, self.cancel) != source_hash:
                raise ValueError('APK nguồn thay đổi trong lúc đọc tài nguyên.')
            badging = self._run(aapt, 'dump', 'badging', snapshot)
            identity = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'", badging, re.M)
            if not identity or identity[1] != 'dji.go.v5':
                raise ValueError('APK không thuộc DJI Fly dji.go.v5.')
            decoded = stage / 'decoded'
            self._run(java, '-jar', jar, 'd', '-s', '--no-assets', '-j', '1',
                      '-p', stage / 'frameworks', '-o', decoded, snapshot)
            elements, report = select_resources(catalog, decoded / 'res')
            if not elements:
                raise ValueError('Phiên bản này chưa có câu khớp trong từ điển tiếng Việt.')
            samples = [{'name': e.get('name'), 'value': e.text} for e in elements
                       if e.tag == 'string' and not len(e) and e.text and e.text == e.text.strip()
                       and not any(c in e.text for c in '\\%\n\r\t\"\'@?')][:3]
            if not samples:
                raise ValueError('Không có câu độc lập để đọc lại và xác nhận bản dịch.')
            self.emit('applying', f"Đang dựng gói tiếng Việt: {len(elements)} tài nguyên phù hợp…")
            res = stage / 'overlay/res'
            for qualifier in ('values', 'values-en', 'values-en-rUS', 'values-vi'):
                directory = res / qualifier
                directory.mkdir(parents=True)
                xml = ET.Element('resources')
                xml.extend(copy.deepcopy(elements))
                ET.ElementTree(xml).write(directory / 'translations.xml', encoding='utf-8', xml_declaration=True)
            manifest = stage / 'overlay/AndroidManifest.xml'
            manifest.write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="' + package +
                '" android:versionCode="1" android:versionName="adaptive-1">'
                '<uses-sdk android:minSdkVersion="30" android:targetSdkVersion="' + str(self.sdk) + '"/>'
                '<overlay android:targetPackage="dji.go.v5" android:targetName="' + self.target_name + '" '
                'android:isStatic="false" android:priority="999"/>'
                '<application android:hasCode="false" android:label="Tiếng Việt DJI Fly"/></manifest>', encoding='utf-8')
            compiled, unsigned, aligned, signed = (stage / n for n in ('compiled.zip', 'unsigned.apk', 'aligned.apk', 'overlay.apk'))
            self._run(aapt, 'compile', '--dir', res, '-o', compiled)
            self._run(aapt, 'link', '-o', unsigned, '--manifest', manifest, '-I', framework,
                      '--auto-add-overlay', '--no-resource-deduping', '--no-resource-removal', '-R', compiled)
            self.tools.align(unsigned, aligned)
            self.tools.sign(aligned, signed, key.keyfile, key.alias, key.password)
            if self.tools.verify(signed) != key.certificate_sha256:
                raise ValueError('Chữ ký bản dịch không khớp khóa trên PC.')
            self._resource_only(signed)
            receipt = {'schema': 1, 'digest': sha256_file(signed, self.cancel), 'source_digest': source_hash,
                       'catalog_digest': CATALOG_SHA256, 'package': package, 'version': identity[3],
                       'version_code': int(identity[2]), 'report': report, 'samples': samples,
                       'profile_sdk': self.sdk, 'target_name': self.target_name}
            check_cancel(self.cancel)
            folder.parent.mkdir(parents=True, exist_ok=True)
            _check_ancestors(folder.parent)
            # Publish only our own small artifact directory, never the decoded Fly tree.
            publish = stage / 'publish'
            publish.mkdir()
            shutil.copyfile(signed, publish / 'overlay.apk')
            (publish / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
            publish.rename(folder)
        return dict(receipt, apk=folder / 'overlay.apk')
