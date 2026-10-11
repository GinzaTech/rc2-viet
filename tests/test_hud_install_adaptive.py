"""The installer binds current metadata instead of a numerical version allowlist."""
from test_hud_install import context


def test_prepare_accepts_future_version_when_it_matches_the_verified_source(context):
    installer,adb,builder,_=context
    adb.version,adb.code='99.8.7',9987
    builder.result['source_identity']={**builder.result['source_identity'],'version':adb.version,'code':adb.code}
    result=installer.prepare(adb,adb.serial)
    assert result['status']=='hud_confirmation_required'
