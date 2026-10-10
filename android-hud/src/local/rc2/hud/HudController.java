package local.rc2.hud;

import android.app.Activity;
import android.app.Application;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.graphics.Rect;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewConfiguration;
import android.view.Window;
import android.widget.FrameLayout;
import android.util.Log;
import java.util.LinkedHashMap;
import java.util.IdentityHashMap;
import java.util.Map;

/** In-process double-tap HUD and the home-page menu. */
public final class HudController implements Application.ActivityLifecycleCallbacks {
    private static final String TAG = "RC2Hud";
    private static final String[] TARGETS = {
        "top_bar_shell_layout", "osd_shell_top_layout", "osd_shell_layout",
        "left_bar_shell_layout", "right_bar_shell_layout", "map_shell_layout",
        "radar_shell_layout", "histogram_shell_layout", "zoom_focus_layer_layout",
        "right_bottom_shell_layout", "attitude_bar_shell_layout",
        "osd_shell_top_child_layout", "portrait_right_bar_shell_layout",
        "metering_shell_layout", "gimbal_shell_layout"
    };
    private static HudController instance;
    private final Application application;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final NativeRadio radio;
    private final ExternalOutput output;
    private final Map<Activity, State> states = new IdentityHashMap<>();
    private final Map<Activity, DeviceMenu> menus = new IdentityHashMap<>();

    private HudController(Application app) { application = app; radio=new NativeRadio(app.getClassLoader()); output=new ExternalOutput(app); }

    public static synchronized String install(Application app) {
        if (!"dji.go.v5".equals(app.getPackageName())) return "wrong_package";
        if (instance != null) return "already_installed";
        final HudController created = new HudController(app);
        instance = created;
        Runnable register = () -> {
            app.registerActivityLifecycleCallbacks(created);
            Log.i(TAG, "registered");
        };
        if (Looper.myLooper() == Looper.getMainLooper()) register.run();
        else created.main.post(register);
        return "registered_or_scheduled";
    }

    public static synchronized String uninstall() {
        if (instance == null) return "not_installed";
        final HudController old = instance;
        instance = null;
        old.main.post(() -> {
            old.application.unregisterActivityLifecycleCallbacks(old);
            old.radio.close();
            old.output.close();
            for (State state : old.states.values()) state.dispose();
            old.states.clear();
            for (DeviceMenu menu : old.menus.values()) menu.dispose();
            old.menus.clear();
            Log.i(TAG, "uninstalled_restored");
        });
        return "uninstall_scheduled";
    }
    static synchronized Bundle outputProbe(boolean start) {
        if(instance!=null) return instance.output.probe(start);
        Bundle value=new Bundle();value.putString("result","not_installed");return value;
    }

    @Override public void onActivityResumed(Activity activity) {
        if(activity.getClass().getName().equals("com.dji.mainpageui.device.DJIDeviceActivity")) {
            if(menus.containsKey(activity)) return;
            View content=activity.findViewById(android.R.id.content);
            if(content instanceof FrameLayout) {
                DeviceMenu menu=new DeviceMenu(activity,(FrameLayout)content,radio,output);
                try { menu.attach(); menus.put(activity,menu); }
                catch(RuntimeException | LinkageError failure) { menu.dispose(); Log.e(TAG,"menu_attach_failed",failure); }
            }
            return;
        }
        if (!activity.getClass().getName().endsWith(".FpvComponentActivity")) return;
        if (states.containsKey(activity)) return;
        try {
            View content = activity.findViewById(android.R.id.content);
            if (!(content instanceof FrameLayout)) {
                Log.w(TAG, "unsupported_content");
                return;
            }
            State state = new State(activity, (FrameLayout) content);
            try { state.attach(); states.put(activity, state); output.resume(activity,(FrameLayout)content); }
            catch (RuntimeException failure) { state.dispose(); throw failure; }
        } catch (RuntimeException exception) {
            Log.e(TAG, "attach_failed", exception);
        }
    }

    @Override public void onActivityPaused(Activity activity) {
        output.pause(activity);
        DeviceMenu menu=menus.remove(activity); if(menu!=null) menu.dispose();
        State state = states.remove(activity);
        if (state != null) state.dispose();
    }
    @Override public void onActivityDestroyed(Activity activity) {
        output.pause(activity);
        DeviceMenu menu=menus.remove(activity); if(menu!=null) menu.dispose();
        State state = states.remove(activity);
        if (state != null) state.dispose();
    }
    @Override public void onActivityCreated(Activity a, Bundle b) { }
    @Override public void onActivityStarted(Activity a) { }
    @Override public void onActivityStopped(Activity a) { }
    @Override public void onActivitySaveInstanceState(Activity a, Bundle b) { }

    private static final class State {
        final Activity activity;
        final FrameLayout root;
        final Map<View, Integer> original = new LinkedHashMap<>();
        final Rect hit = new Rect();
        final DoubleTap taps;
        final SharedPreferences options;
        final Window window;
        Window.Callback originalCallback, wrappedCallback;
        TouchDispatch dispatch;
        int previewId;
        boolean alive;
        boolean hidden;

        State(Activity activity, FrameLayout root) {
            this.activity = activity;
            this.root = root;
            window = activity.getWindow();
            options=activity.getSharedPreferences("local_rc2_hud",0);
            taps = new DoubleTap(ViewConfiguration.get(activity).getScaledTouchSlop(), dp(36));
            previewId = activity.getResources().getIdentifier("view_surface", "id", "dji.go.v5");
        }
        int dp(int value) { return Math.round(value * activity.getResources().getDisplayMetrics().density); }
        void attach() {
            alive = true;
            originalCallback = window.getCallback();
            dispatch = new TouchDispatch(new TouchDispatch.Observer() {
                public void before(Object event) { observeBefore((MotionEvent)event); }
                public void after(Object event) { observeAfter((MotionEvent)event); }
                public void focusChanged(boolean focused) { if (!focused) taps.reset(); }
                public void failed(RuntimeException error) { taps.reset(); Log.w(TAG, "touch_observer_failed", error); }
            });
            wrappedCallback = dispatch.wrap(Window.Callback.class, originalCallback);
            window.setCallback(wrappedCallback);
            Log.i(TAG, "double_tap_attached");
        }
        void observeBefore(MotionEvent event) {
            if (!alive || event == null) return;
            int action = event.getActionMasked();
            if (action == MotionEvent.ACTION_DOWN) {
                taps.down(event.getEventTime(), event.getRawX(), event.getRawY(),
                    eligible(event.getRawX(), event.getRawY()), event.getPointerCount());
            } else if (action == MotionEvent.ACTION_MOVE) {
                taps.move(event.getRawX(), event.getRawY(), event.getPointerCount());
            } else if (action == MotionEvent.ACTION_CANCEL || action == MotionEvent.ACTION_POINTER_DOWN) taps.reset();
        }
        void observeAfter(MotionEvent event) {
            if (!alive || event == null) return;
            if (!root.hasWindowFocus()) { taps.reset(); return; }
            if (event.getActionMasked() == MotionEvent.ACTION_UP
                    && taps.up(event.getEventTime(), event.getRawX(), event.getRawY(), event.getPointerCount())
                    && DoubleTap.enabled(options.getBoolean("double_tap",true),hidden)) toggle();
        }
        boolean eligible(float x, float y) {
            if (!root.hasWindowFocus() || previewId == 0) return false;
            View preview = root.findViewById(previewId);
            if (preview == null || !preview.isShown() || !preview.getGlobalVisibleRect(hit)
                    || !hit.contains((int)x, (int)y)) return false;
            return !controlAt(root, preview, (int)x, (int)y, 0);
        }
        boolean controlAt(View view, View preview, int x, int y, int depth) {
            if (!view.isShown() || !view.getGlobalVisibleRect(hit) || !hit.contains(x, y)) return false;
            if (depth > 48) return true; // Fail closed on an unexpected hierarchy.
            if (view == preview) return false;
            if (view instanceof ViewGroup) {
                ViewGroup group = (ViewGroup)view;
                for (int index = group.getChildCount() - 1; index >= 0; index--)
                    if (controlAt(group.getChildAt(index), preview, x, y, depth + 1)) return true;
                if (group.findViewById(previewId) != null) return false;
            }
            return view.isClickable() || view.isLongClickable();
        }
        void toggle() { if (hidden) restore(); else hide(); }
        void hide() {
            original.clear();
            int changedCount = 0;
            for (String name : TARGETS) {
                int id = activity.getResources().getIdentifier(name, "id", "dji.go.v5");
                View view = id == 0 ? null : root.findViewById(id);
                if (view == null || view == root) continue;
                // Never hide a selected ancestor if it contains the preview surface.
                if (view instanceof ViewGroup && previewId != 0 && view.findViewById(previewId) != null) continue;
                int visibility = view.getVisibility();
                original.put(view, visibility);
                if (visibility == View.VISIBLE) {
                    view.setVisibility(View.INVISIBLE);
                    changedCount++;
                }
            }
            hidden = changedCount > 0;
            Log.i(TAG, "hud_hidden changed=" + changedCount + " tracked=" + original.size());
        }
        void restore() {
            for (Map.Entry<View, Integer> entry : original.entrySet()) entry.getKey().setVisibility(entry.getValue());
            original.clear();
            hidden = false;
            Log.i(TAG, "hud_restored");
        }
        void dispose() {
            alive = false; taps.reset();
            if (dispatch != null) dispatch.stop();
            if (wrappedCallback != null && window.getCallback() == wrappedCallback) window.setCallback(originalCallback);
            restore();
        }
    }
}
