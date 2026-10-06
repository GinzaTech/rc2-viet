"""Pinned metadata for the previously tested Lawnchair release."""
from .apk_install import BundledAPK,install_bundled_apk
from .core import LAWNCHAIR_APK_HASH

LAWNCHAIR_COMPONENT='app.lawnchair/app.lawnchair.LawnchairLauncher'


def install_lawnchair(adb,assets,emit):
    app=BundledAPK('Lawnchair','lawnchair.apk','app.lawnchair',
                   LAWNCHAIR_COMPONENT,LAWNCHAIR_APK_HASH,'lawnchair')
    return install_bundled_apk(adb,assets,app,emit)
