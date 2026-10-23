import pytest
from rc2vi.fly_versions import FLY_1218, FLY_12110, FLY_12116, SUPPORTED, for_identity, for_source


@pytest.mark.parametrize('profile', SUPPORTED)
def test_identity_and_source_select_the_same_separate_recipe(profile):
    assert for_identity(profile.version, profile.code) is profile
    assert for_source(profile.source_sha256) is profile


@pytest.mark.parametrize('version,code', [
    ('1.21.8', 3115981), ('1.21.10', 3115809), ('1.21.9', 3115900),
    ('1.21.8', '3115809'), ('1.21.10', True), ('1.21.10-phone', 3115981),
    ('1.21.16', 3115981), ('1.21.16', '3132286'), ('1.21.16-phone', 3132286),
])
def test_mixed_or_unknown_identity_does_not_select_any_recipe(version, code):
    with pytest.raises(ValueError):
        for_identity(version, code)


@pytest.mark.parametrize('digest', [None, 'f6c11267', '0' * 64])
def test_unreviewed_source_hash_is_not_authorized(digest):
    with pytest.raises(ValueError):
        for_source(digest)


def test_new_version_cannot_share_an_older_build_or_translation_cache():
    assert len({profile.build_directory for profile in SUPPORTED}) == len(SUPPORTED)
    assert FLY_12116.translation_directory not in {FLY_1218.translation_directory, FLY_12110.translation_directory}
    assert FLY_12116.translation_sha256
    assert FLY_12116.translation_count > FLY_12110.translation_count
