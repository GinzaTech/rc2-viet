package local.rc2.hud;

import android.app.Activity;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.SurfaceView;
import java.nio.ByteBuffer;

/** Root-only caller's bounded compositor check. No files, sockets or video export. */
final class OutputProbe {
    private final Handler main=new Handler(Looper.getMainLooper());
    private volatile String result="idle";
    private volatile int frames,nonBlack;
    private ImageReader reader;
    private VirtualDisplay display;
    private CleanPresentation window;
    private boolean active;
    void start(Activity activity,SurfaceView preview) {
        if(active) return;
        frames=0;nonBlack=0;result="starting";
        if(activity==null || preview==null || !preview.getHolder().getSurface().isValid()) {
            result="no_preview";return;
        }
        active=true;
        try {
            reader=ImageReader.newInstance(640,360,PixelFormat.RGBA_8888,2);
            reader.setOnImageAvailableListener(value->{
                try(Image image=value.acquireLatestImage()) {
                    if(image==null || !active)return;
                    Image.Plane plane=image.getPlanes()[0];ByteBuffer buffer=plane.getBuffer();
                    int count=0;
                    for(int y=0;y<image.getHeight();y+=30)for(int x=0;x<image.getWidth();x+=40) {
                        int offset=y*plane.getRowStride()+x*plane.getPixelStride();
                        if(offset+2<buffer.limit() && ((buffer.get(offset)&255)+(buffer.get(offset+1)&255)+(buffer.get(offset+2)&255))>24)count++;
                    }
                    frames++;nonBlack=Math.max(nonBlack,count);
                } catch(RuntimeException | LinkageError error) { result="image_read_error"; }
            },main);
            DisplayManager manager=(DisplayManager)activity.getSystemService(Activity.DISPLAY_SERVICE);
            // A private OWN_CONTENT_ONLY display is not picked by the physical-output selector.
            display=manager.createVirtualDisplay("RC2-Preview-Probe",640,360,160,reader.getSurface(),
                DisplayManager.VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY);
            if(display==null) throw new IllegalStateException("Virtual display unavailable");
            window=new CleanPresentation(activity,display.getDisplay(),preview,message->{
                android.util.Log.i("RC2Hud","output_probe_renderer "+message);
            },false);
            window.show();main.postDelayed(finish,4000);
        } catch(RuntimeException | LinkageError error) { result="presentation_unavailable";stop(); }
    }
    private final Runnable finish=()->{
        result=frames>=2 && nonBlack>0?"clean_buffers_received":"no_clean_picture";
        android.util.Log.i("RC2Hud","output_probe result="+result+" frames="+frames+" non_black_samples="+nonBlack);
        stop();
    };
    void stop() {
        active=false;main.removeCallbacks(finish);
        if(window!=null){window.dismiss();window=null;}
        if(display!=null){display.release();display=null;}
        if(reader!=null){reader.setOnImageAvailableListener(null,null);reader.close();reader=null;}
    }
    Bundle status() {
        Bundle value=new Bundle();value.putString("result",result);
        value.putInt("frames",frames);value.putInt("non_black_samples",nonBlack);return value;
    }
}
