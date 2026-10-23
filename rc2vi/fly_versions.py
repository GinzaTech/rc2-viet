"""Exact RC Fly inputs with independently built menu recipes."""
from dataclasses import dataclass


@dataclass(frozen=True)
class FlyVersion:
    version: str
    code: int
    source_sha256: str
    recipe_directory: str
    profile_kind: str
    auto_kind: str
    certificate_sha256: str = '01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4'
    translation_directory: str = 'auto12110'
    translation_sha256: str | None = None
    translation_count: int = 11313
    replacement_entries: tuple[str, ...] | None = None

    @property
    def build_directory(self):
        # Retain the r3 location so pending 1.21.10 jobs remain resumable.
        return 'build' if self.version == '1.21.10' else 'build-' + self.version.replace('.', '')


FLY_1218 = FlyVersion(
    '1.21.8', 3115809,
    'cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e',
    'advanced1218', 'rc2-advanced-1218', 'rc2-advanced-1218-vietnamese-auto-v1')
FLY_12110 = FlyVersion(
    '1.21.10', 3115981,
    'f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98',
    'advanced12110', 'rc2-advanced-12110', 'rc2-advanced-12110-vietnamese-auto-v1')
FLY_12116 = FlyVersion(
    '1.21.16', 3132286,
    '9bec52ed4c43aad6c615b0a7a0650f0d35e842c4bf8a5e59d5da005a50d56b6a',
    'advanced12116', 'rc2-advanced-12116', 'rc2-advanced-12116-vietnamese-auto-v1',
    translation_directory='auto12116',
    translation_sha256='60381bce71f307f92c847f2abb0025e66a6cab351ee510a92052077bc579c509',
    translation_count=11994,
    replacement_entries=(
        'AndroidManifest.xml', 'classes.dex', 'classes10.dex', 'classes11.dex',
        'classes13.dex', 'classes14.dex', 'classes15.dex', 'classes20.dex',
        'classes21.dex', 'classes22.dex', 'classes4.dex', 'classes5.dex',
        'classes6.dex', 'classes7.dex', 'classes9.dex'))
SUPPORTED = (FLY_1218, FLY_12110, FLY_12116)


def for_identity(version, code):
    for profile in SUPPORTED:
        if version == profile.version and type(code) is int and code == profile.code:
            return profile
    raise ValueError('Chỉ hỗ trợ đúng DJI Fly RC 1.21.8 (3115809), 1.21.10 (3115981) hoặc 1.21.16 (3132286).')


def for_source(digest):
    for profile in SUPPORTED:
        if digest == profile.source_sha256:
            return profile
    raise ValueError('APK nguồn không thuộc bản RC 1.21.8, 1.21.10 hoặc 1.21.16 đã kiểm chứng.')
