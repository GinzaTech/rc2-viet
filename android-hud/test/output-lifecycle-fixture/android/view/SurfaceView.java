package android.view;
import android.content.Context;
import android.graphics.Rect;
import java.util.ArrayList;
import java.util.List;
public class SurfaceView extends View {
    public final Holder holder=new Holder();
    private SurfaceControl control=new SurfaceControl();
    public SurfaceView(Context context){super(context);}
    public SurfaceHolder getHolder(){return holder;}
    public SurfaceControl getSurfaceControl(){return control;}
    public void attach(int w,int h){super.attach(w,h);holder.frame=new Rect(0,0,w,h);holder.create();}
    public void detach(){holder.destroy();}
    public static final class Holder implements SurfaceHolder {
        private final Surface surface=new Surface();
        public Rect frame=new Rect(0,0,640,360);
        public final List<Callback> callbacks=new ArrayList<>();
        public Surface getSurface(){return surface;}public Rect getSurfaceFrame(){return frame;}
        public void addCallback(Callback callback){callbacks.add(callback);}
        public void removeCallback(Callback callback){callbacks.remove(callback);}
        public void create(){surface.valid=true;for(Callback c:new ArrayList<>(callbacks))c.surfaceCreated(this);}
        public void destroy(){surface.valid=false;for(Callback c:new ArrayList<>(callbacks))c.surfaceDestroyed(this);}
        public void resize(int w,int h){frame=new Rect(0,0,w,h);for(Callback c:new ArrayList<>(callbacks))c.surfaceChanged(this,0,w,h);}
    }
}
