package local.rc2.hud;

import android.app.Application;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.util.Log;
import android.os.Binder;
import android.os.Bundle;
import android.os.Process;

/** Private late-init provider. Only the main Fly process registers activity callbacks. */
public final class HudProvider extends ContentProvider {
    @Override public Bundle call(String method,String arg,Bundle extras) {
        // Provider is unexported; additionally forbid every non-root/non-own-UID caller.
        int caller=Binder.getCallingUid();
        if(caller!=0 && caller!=Process.myUid()) throw new SecurityException("Private diagnostic caller required");
        if("output_probe".equals(method)) return HudController.outputProbe("start".equals(arg));
        throw new IllegalArgumentException("Unknown private diagnostic");
    }
    @Override public boolean onCreate() {
        if (!"dji.go.v5".equals(Application.getProcessName())) return true;
        try {
            Context context = getContext();
            if (context == null || !(context.getApplicationContext() instanceof Application)) return false;
            Application app = (Application) context.getApplicationContext();
            String result = HudController.install(app);
            Log.i("RC2Hud", "provider_start " + result);
            return true;
        } catch (RuntimeException | LinkageError exception) {
            Log.e("RC2Hud", "provider_init_failed", exception);
            return false;
        }
    }
    @Override public Cursor query(Uri uri, String[] projection, String selection,
            String[] selectionArgs, String sortOrder) { return null; }
    @Override public String getType(Uri uri) { return null; }
    @Override public Uri insert(Uri uri, ContentValues values) { return null; }
    @Override public int delete(Uri uri, String selection, String[] args) { return 0; }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { return 0; }
}
