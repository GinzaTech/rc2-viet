from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from scripts import build_android_direct_apk as direct


ROOT = Path(__file__).resolve().parents[1]


def test_android_12112_assets_are_pinned_and_current():
    manifest = json.loads((ROOT / 'assets/android12112/manifest.json').read_text('utf-8'))
    translated = direct.translation_asset()
    helper = direct.menu_payload()
    assert manifest['target']['source_sha256'] == direct.SOURCE_SHA256
    assert manifest['resource_sha256'] == sha256(translated).hexdigest()
    assert manifest['translation_revision'] == 'r13.1-resource-initialization-wording'
    assert sha256(helper).hexdigest() == direct.HELPER_SHA256


def test_android_output_name_is_distinct_from_rc2_installer():
    assert direct.OUTPUT_NAME.startswith('DJI-Fly-Android-1.21.12-')
    assert direct.OUTPUT_NAME.endswith('.apk')
