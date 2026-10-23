"""Pinned, compact inventories for verifying upgrades from earlier auto builds.

The old payloads come from the installed APK and must match these reviewed
hashes. Recovery data alone is never sufficient to approve an installed APK.
"""
import hashlib

from .advanced_patch import REPLACEMENT_ENTRIES, ADDITION_ENTRIES
from .hud_backup import guard_path
from .hud_capsule import PROFILE_ENTRY
from .hud_tools import _json_object


PREVIOUS_RECIPES = {
    'be517b4e3de6ac99bcc6dee29bbc53616c54879520414370f3b0a1041d0f886d':
        ('r14.4-1218.json', '8739b7d5d370108007334500c770c4e2a45e8204cfcc3ce4a5722ff4bed1c24b'),
    'e8342bd9e479318bfff88fa19fcc8afedda3481e718526c9d8cce4ab7a9d6acb':
        ('r14.4-12110.json', 'a62096f32010081966df9ab91e8ac5be9a3947d4fc2a8d71ae167eb58918cb25'),
    'b8df8c71949f43ac5582f41144e0b46dcc73663a96a43bd59b26680117d350a1':
        ('r14.6-12116.json', '480c16b924cb99433d7cad7b6dc4e2d2226d42683d630e2ee033f796394a980d'),
}


def load_previous(assets, recipe_sha256, profile):
    binding = PREVIOUS_RECIPES.get(recipe_sha256)
    if binding is None:
        raise ValueError('Recipe cũ chưa được kiểm chứng; chưa thay Fly.')
    name, digest = binding
    path = guard_path(assets / 'auto-history' / name)
    if not path.is_file() or not 0 < path.stat().st_size <= 256 * 1024:
        raise ValueError('Thiếu dữ liệu kiểm chứng recipe cũ.')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Dữ liệu kiểm chứng recipe cũ bị thay đổi.')
    value = _json_object(raw)
    if set(value) != {'schema', 'manifest', 'template_json'} or value['schema'] != 1:
        raise ValueError('Invalid historical recipe inventory')
    manifest = value['manifest']
    if (not isinstance(manifest, dict) or manifest.get('recipe_sha256') != recipe_sha256
            or manifest.get('source_sha256') != profile.source_sha256
            or manifest.get('profile_kind') != profile.profile_kind
            or manifest.get('version') != profile.version or manifest.get('code') != profile.code):
        raise ValueError('Historical recipe does not match selected RC version')
    replacements = profile.replacement_entries if profile.replacement_entries is not None else REPLACEMENT_ENTRIES
    expected = {'replacements/' + name for name in replacements} | {
        'additions/' + name for name in ADDITION_ENTRIES}
    rows = manifest.get('entries')
    if not isinstance(rows, dict) or set(rows) != expected:
        raise ValueError('Historical recipe payload inventory differs')
    template_raw = value['template_json'].encode('utf-8')
    template_row = rows['additions/' + PROFILE_ENTRY]
    if (len(template_raw) != template_row['bytes']
            or hashlib.sha256(template_raw).hexdigest() != template_row['sha256']):
        raise ValueError('Historical profile template differs')
    return manifest, _json_object(template_raw)
