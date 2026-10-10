package local.rc2.hud;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.SharedPreferences;
import android.hardware.display.DisplayManager;
import android.os.Handler;
import android.os.Looper;
import android.os.Bundle;
import android.view.Display;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.widget.FrameLayout;
import java.util.ArrayList;
import java.util.List;

/** Direct external-display modes. A saved choice never implies that HDMI is connected. */
final class ExternalOutput implements DisplayManager.DisplayListener,SurfaceHolder.Callback,ViewTreeObserver.OnGlobalLayoutListener {
    interface Cancel { void cancel(); }
    private final DisplayManager manager;
    private final SharedPreferences options;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final List<Runnable> listeners=new ArrayList<>();
    private volatile Activity activity;
    private FrameLayout root;
    private volatile SurfaceView preview;
    private CleanPresentation clean;
    private long generation;
    private final OutputProbe probe=new OutputProbe();
    private boolean closed;
    private String text="Chưa kết nối màn hình ngoài.";
    ExternalOutput(Application application) {
        manager=(DisplayManager)application.getSystemService(Context.DISPLAY_SERVICE);
        options=application.getSharedPreferences("local_rc2_hud",0);
        if(manager!=null)manager.registerDisplayListener(this,main);
        update();
    }
    boolean withHud() { return options.getBoolean("output_with_hud",true); }
    void setWithHud(boolean value) { options.edit().putBoolean("output_with_hud",value).apply();update(); }
    String statusText() { return text; }
    Bundle probe(boolean start) {
        if(start)main.post(()->{if(!closed)probe.start(activity,preview);});
        SurfaceView observed=preview;Bundle value=probe.status();value.putBoolean("has_activity",activity!=null);
        value.putBoolean("has_preview",observed!=null);
        value.putBoolean("surface_valid",observed!=null && observed.getHolder().getSurface().isValid());return value;
    }
    Cancel observe(Runnable callback) {
        listeners.add(callback);callback.run();return ()->listeners.remove(callback);
    }
    private Display external() {
        if(manager==null)return null;
        for(Display display:manager.getDisplays(DisplayManager.DISPLAY_CATEGORY_PRESENTATION))
            if(display.getDisplayId()!=Display.DEFAULT_DISPLAY && display.isValid() && display.getState()!=Display.STATE_OFF)return display;
        return null;
    }
    private void status(String value) {
        if(closed || value.equals(text))return;
        text=value;
        for(Runnable callback:new ArrayList<>(listeners)) {
            try { callback.run(); } catch(RuntimeException | LinkageError error) { listeners.remove(callback); }
        }
    }
    void resume(Activity owner,FrameLayout root) {
        pause(activity);activity=owner;this.root=root;
        root.getViewTreeObserver().addOnGlobalLayoutListener(this);
        locatePreview();update();
    }
    private boolean locatePreview() {
        if(closed || activity==null || root==null)return false;
        int id=activity.getResources().getIdentifier("view_surface","id","dji.go.v5");
        SurfaceView found=id==0?null:find(root.findViewById(id));
        if(found==preview)return false;
        probe.stop();stopClean();if(preview!=null)preview.getHolder().removeCallback(this);
        preview=found;if(preview!=null)preview.getHolder().addCallback(this);
        return true;
    }
    public void onGlobalLayout() { if(locatePreview())update(); }
    private static SurfaceView find(View view) {
        if(view instanceof SurfaceView)return (SurfaceView)view;
        if(view instanceof ViewGroup) {
            ViewGroup group=(ViewGroup)view;
            for(int index=0;index<group.getChildCount();index++) {
                SurfaceView result=find(group.getChildAt(index));if(result!=null)return result;
            }
        }
        return null;
    }
    void pause(Activity owner) {
        if(owner!=null && owner!=activity)return;
        if(root!=null && root.getViewTreeObserver().isAlive())root.getViewTreeObserver().removeOnGlobalLayoutListener(this);
        probe.stop();stopClean();if(preview!=null)preview.getHolder().removeCallback(this);
        preview=null;activity=null;root=null;update();
    }
    private void stopClean() {
        ++generation;CleanPresentation value=clean;clean=null;
        if(value!=null)value.dismiss();
    }
    private void update() {
        if(closed)return;
        Display display=external();
        if(display==null) { stopClean();status("Chưa kết nối màn hình ngoài.");return; }
        if(withHud()) { stopClean();status("Màn ngoài: phản chiếu có HUD.");return; }
        if(activity==null || preview==null || !preview.getHolder().getSurface().isValid()) {
            stopClean();status("Màn ngoài: chờ màn hình bay.");return;
        }
        if(clean!=null && clean.isShowing() && clean.getDisplay().getDisplayId()==display.getDisplayId()) {
            clean.sourceChanged();return;
        }
        stopClean();
        final long version=++generation;
        try {
            CleanPresentation opened=new CleanPresentation(activity,display,preview,value->{
                if(!closed && version==generation && clean!=null)status(value);
            });
            clean=opened;
            opened.setOnDismissListener(ignored->{
                if(clean!=opened || version!=generation)return;
                clean=null;++generation;main.post(()->{if(!closed)update();});
            });
            status("Đang mở video không HUD…");opened.show();
        } catch(RuntimeException | LinkageError error) {
            stopClean();status("Không mở được màn hình ngoài.");
            android.util.Log.w("RC2Hud","external_presentation_unavailable");
        }
    }
    public void onDisplayAdded(int id) { update(); }
    public void onDisplayRemoved(int id) { update(); }
    public void onDisplayChanged(int id) {
        if(clean!=null && clean.getDisplay().getDisplayId()==id)stopClean();
        update();
    }
    public void surfaceCreated(SurfaceHolder holder) { update(); }
    public void surfaceChanged(SurfaceHolder holder,int format,int width,int height) { update(); }
    public void surfaceDestroyed(SurfaceHolder holder) { stopClean(); }
    void close() {
        closed=true;if(manager!=null)manager.unregisterDisplayListener(this);
        if(root!=null && root.getViewTreeObserver().isAlive())root.getViewTreeObserver().removeOnGlobalLayoutListener(this);
        probe.stop();stopClean();if(preview!=null)preview.getHolder().removeCallback(this);
        preview=null;activity=null;root=null;listeners.clear();
    }
}
