package local.rc2.hud;

import android.app.Presentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Display;
import android.view.PixelCopy;
import android.view.SurfaceControl;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.ImageView;

/** A presentation of the owned preview surface only. Never changes local HUD/video. */
final class CleanPresentation extends Presentation implements SurfaceHolder.Callback {
    interface Status { void changed(String message); }
    private final SurfaceView source;
    private final Status status;
    private final boolean preferMirror;
    private final Handler main=new Handler(Looper.getMainLooper());
    private SurfaceView sink;
    private ImageView copied;
    private SurfaceControl mirror;
    private Bitmap first,second,next;
    private boolean alive,inFlight,fallback;
    private int failures;
    private final Runnable startup=this::startPicture;
    CleanPresentation(Context context,Display display,SurfaceView source,Status status) {
        this(context,display,source,status,true);
    }
    CleanPresentation(Context context,Display display,SurfaceView source,Status status,boolean preferMirror) {
        super(context,display);this.source=source;this.status=status;this.preferMirror=preferMirror;
    }
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN
            |WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE|WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE);
        FrameLayout frame=new FrameLayout(getContext());frame.setBackgroundColor(Color.BLACK);
        sink=new SurfaceView(getContext());frame.addView(sink,new FrameLayout.LayoutParams(-1,-1));
        copied=new ImageView(getContext());copied.setScaleType(ImageView.ScaleType.FIT_CENTER);
        copied.setVisibility(android.view.View.INVISIBLE);frame.addView(copied,new FrameLayout.LayoutParams(-1,-1));
        setContentView(frame);alive=true;sink.getHolder().addCallback(this);
    }
    public void surfaceCreated(SurfaceHolder holder) { main.removeCallbacks(startup);main.post(startup); }
    public void surfaceChanged(SurfaceHolder holder,int format,int width,int height) {
        sourceChanged();
    }
    public void surfaceDestroyed(SurfaceHolder holder) { removeMirror(); }
    private void startPicture() {
        if(!alive)return;
        if(!source.getHolder().getSurface().isValid()) { status.changed("Chưa có video để xuất.");return; }
        if(mirror!=null || fallback) { sourceChanged();return; }
        if(!preferMirror) { startFallback();return; }
        try {
            mirror=(SurfaceControl)SurfaceControl.class.getMethod("mirrorSurface",SurfaceControl.class)
                .invoke(null,source.getSurfaceControl());
            if(mirror==null || !mirror.isValid()) throw new IllegalStateException("Preview mirror unavailable");
            positionMirror();status.changed("Màn ngoài: video không HUD.");
            android.util.Log.i("RC2Hud","external_clean renderer=surface_mirror display="+getDisplay().getDisplayId());
        } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
            startFallback();
        }
    }
    void sourceChanged() {
        if(!alive)return;
        try { if(mirror!=null)positionMirror(); }
        catch(RuntimeException | LinkageError error) { startFallback(); }
        if(fallback && !inFlight) { main.removeCallbacks(copyFrame);main.post(copyFrame); }
    }
    private void startFallback() {
        removeMirror();fallback=true;
        sink.setVisibility(android.view.View.INVISIBLE);copied.setVisibility(android.view.View.VISIBLE);
        main.removeCallbacks(copyFrame);main.post(copyFrame);
    }
    private boolean sizeCopies() {
        Rect frame=source.getHolder().getSurfaceFrame();
        if(frame.width()<=0 || frame.height()<=0)return false;
        int[] size=OutputGeometry.copySize(frame.width(),frame.height());
        if(first!=null && first.getWidth()==size[0] && first.getHeight()==size[1])return true;
        copied.setImageDrawable(null);recycle();
        first=Bitmap.createBitmap(size[0],size[1],Bitmap.Config.ARGB_8888);
        second=Bitmap.createBitmap(size[0],size[1],Bitmap.Config.ARGB_8888);next=first;
        android.util.Log.i("RC2Hud","external_clean renderer=pixel_copy width="+size[0]+" height="+size[1]+" max_fps=5");
        return true;
    }
    private void positionMirror() {
        Rect frame=source.getHolder().getSurfaceFrame();
        if(!alive || mirror==null || sink.getWidth()<=0 || sink.getHeight()<=0 || frame.width()<=0 || frame.height()<=0)return;
        int[] rect=OutputGeometry.fit(frame.width(),frame.height(),sink.getWidth(),sink.getHeight());
        try(SurfaceControl.Transaction transaction=new SurfaceControl.Transaction()) {
            transaction.reparent(mirror,sink.getSurfaceControl()).setLayer(mirror,1)
                .setGeometry(mirror,new Rect(0,0,frame.width(),frame.height()),
                    new Rect(rect[0],rect[1],rect[0]+rect[2],rect[1]+rect[3]),0)
                .setVisibility(mirror,true).apply();
        }
    }
    private final Runnable copyFrame=new Runnable() {
        public void run() {
            if(!alive || !fallback || inFlight)return;
            if(!source.getHolder().getSurface().isValid()) { status.changed("Video chưa sẵn sàng.");main.postDelayed(this,1000);return; }
            try {
                if(!sizeCopies()) { main.postDelayed(this,1000);return; }
                Bitmap destination=next;inFlight=true;
                PixelCopy.request(source,destination,result->{
                inFlight=false;
                if(!alive) { recycle();return; }
                if(result==PixelCopy.SUCCESS) {
                    failures=0;copied.setImageBitmap(destination);next=destination==first?second:first;
                    status.changed("Màn ngoài: video không HUD (5 fps).");
                } else {
                    failures++;
                    if(failures>=5) status.changed("Chưa lấy được video để xuất.");
                }
                main.postDelayed(this,failures>=5?1000:200);
            },main); } catch(RuntimeException | LinkageError error) {
                inFlight=false;status.changed("Không lấy được lớp video.");
                main.postDelayed(this,1000);
            }
        }
    };
    private void removeMirror() {
        SurfaceControl value=mirror;mirror=null;
        if(value==null)return;
        try(SurfaceControl.Transaction transaction=new SurfaceControl.Transaction()) {
            if(value.isValid()) {
                try { SurfaceControl.Transaction.class.getMethod("remove",SurfaceControl.class).invoke(transaction,value); }
                catch(ReflectiveOperationException error) { transaction.setVisibility(value,false).reparent(value,null); }
                transaction.apply();
            }
        } catch(RuntimeException | LinkageError error) {
            android.util.Log.w("RC2Hud","external_mirror_cleanup_failed");
        } finally { value.release(); }
    }
    private void recycle() {
        if(inFlight)return;
        if(first!=null)first.recycle();if(second!=null)second.recycle();
        first=null;second=null;next=null;
    }
    public void dismiss() {
        alive=false;main.removeCallbacks(startup);main.removeCallbacks(copyFrame);
        if(sink!=null)sink.getHolder().removeCallback(this);
        if(copied!=null)copied.setImageDrawable(null);
        removeMirror();recycle();super.dismiss();
    }
}
