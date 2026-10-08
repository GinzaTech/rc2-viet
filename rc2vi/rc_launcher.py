"""The small RC dashboard is a separate app; Lawnchair remains available."""
from .apk_install import BundledAPK,install_bundled_apk

RC_LAUNCHER_HASH='4c6f914531a74158ae62fd12c3957bd245ca3054e7e0a34f57f04b9a5622e05d'
RC_LAUNCHER_COMPONENT='dev.rclauncher.rc2.debug/dev.rclauncher.rc2.RCLauncher'


def install_rc_launcher(adb,assets,emit):
    app=BundledAPK('RC Launcher','rc-launcher.apk','dev.rclauncher.rc2.debug',
                   RC_LAUNCHER_COMPONENT,RC_LAUNCHER_HASH,'rc_launcher',upgrade_hashes=(
                       '8a14c16c18bc16f9ed0567598ffa6d9d96d0a9ba0c0a60e77637661e008560a7',
                       '9ccfcac7a2f1f3b18e13d8bdcfd4a532b41d7a1aa0004f2bcee41444f4ae5834',
                       '89a7bf6d6c99657cc8b9233039fd1b57dba8b5d7eae26cd092315ef1ec187dfe'))
    return install_bundled_apk(adb,assets,app,emit)
