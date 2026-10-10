package android.view;
import android.graphics.Rect;
import java.util.ArrayList;
import java.util.List;
/** Records native operations and injects a resize-time transaction failure. */
public class SurfaceControl {
    public static boolean mirrorFails,failNextGeometry;
    public static int geometries,transactionsClosed,mirrorCalls;
    public static Rect lastCrop,lastDestination;
    public static final List<SurfaceControl> mirrors=new ArrayList<>();
    private boolean released;
    public static SurfaceControl mirrorSurface(SurfaceControl source){
        mirrorCalls++;
        if(mirrorFails)throw new IllegalStateException("injected mirror denied");
        SurfaceControl value=new SurfaceControl();mirrors.add(value);return value;
    }
    public boolean isValid(){return !released;}
    public void release(){released=true;}
    public static int liveMirrors(){int n=0;for(SurfaceControl c:mirrors)if(!c.released)n++;return n;}
    public static void reset(){mirrorFails=false;failNextGeometry=false;geometries=0;transactionsClosed=0;mirrorCalls=0;lastCrop=null;lastDestination=null;mirrors.clear();}
    public static class Transaction implements AutoCloseable {
        private Rect crop,destination;
        public Transaction reparent(SurfaceControl child,SurfaceControl parent){if(!child.isValid())throw new IllegalArgumentException("released control");return this;}
        public Transaction setLayer(SurfaceControl control,int layer){return this;}
        public Transaction setGeometry(SurfaceControl control,Rect src,Rect dst,int rotation){
            if(failNextGeometry){failNextGeometry=false;throw new IllegalStateException("injected later geometry failure");}
            crop=new Rect(src);destination=new Rect(dst);return this;
        }
        public Transaction setVisibility(SurfaceControl control,boolean visible){return this;}
        public Transaction remove(SurfaceControl control){return this;}
        public void apply(){if(crop!=null){geometries++;lastCrop=crop;lastDestination=destination;}}
        public void close(){transactionsClosed++;}
    }
}
