import pytest
from rc2vi.fly_versions import FLY_1218, FLY_12110, for_identity, for_source


@pytest.mark.parametrize('profile', [FLY_1218, FLY_12110])
def test_identity_and_source_select_the_same_separate_recipe(profile):
    assert for_identity(profile.version, profile.code) is profile
    assert for_source(profile.source_sha256) is profile


@pytest.mark.parametrize('version,code', [
    ('1.21.8', 3115981), ('1.21.10', 3115809), ('1.21.9', 3115900),
    ('1.21.8', '3115809'), ('1.21.10', True), ('1.21.10-phone', 3115981),
])
def test_mixed_or_unknown_identity_does_not_select_any_recipe(version, code):
    with pytest.raises(ValueError):
        for_identity(version, code)


@pytest.mark.parametrize('digest', [None, 'f6c11267', '0' * 64])
def test_unreviewed_source_hash_is_not_authorized(digest):
    with pytest.raises(ValueError):
        for_source(digest)
