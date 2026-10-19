package local.rc2.hud;

import android.app.Activity;

final class Air3sFeaturePanel {
    static int opens;
    private Air3sFeaturePanel() { }
    static void open(Activity activity) { opens++; }
}
