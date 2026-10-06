"""Install FreeFCC only; no connection, activation or radio commands."""
from .apk_install import BundledAPK,install_bundled_apk
from .core import FREEFCC_APK_HASH

FREEFCC_COMPONENT='com.freefcc.app/com.freefcc.app.MainActivity'


def install_freefcc(adb,assets,emit):
    app=BundledAPK('FreeFCC','freefcc.apk','com.freefcc.app',
                   FREEFCC_COMPONENT,FREEFCC_APK_HASH,'freefcc')
    return install_bundled_apk(adb,assets,app,emit)
