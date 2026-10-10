package android.view;
import android.graphics.Bitmap;
import android.os.Handler;
import java.util.ArrayList;
import java.util.List;
public class PixelCopy {
    public static final int SUCCESS=0,ERROR_SOURCE_NO_DATA=3;
    public interface OnPixelCopyFinishedListener {void onPixelCopyFinished(int result);}
    public static final List<Request> pending=new ArrayList<>();
    public static int submitted;
    public static final class Request {
        public final Bitmap destination;final OnPixelCopyFinishedListener listener;final Handler handler;
        Request(Bitmap bitmap,OnPixelCopyFinishedListener cb,Handler h){destination=bitmap;listener=cb;handler=h;}
    }
    public static void request(SurfaceView source,Bitmap bitmap,OnPixelCopyFinishedListener listener,Handler handler){
        if(bitmap.isRecycled())throw new AssertionError("copy into recycled bitmap");
        submitted++;pending.add(new Request(bitmap,listener,handler));
    }
    public static void complete(int result){
        if(pending.isEmpty())throw new AssertionError("no pending PixelCopy");
        Request request=pending.remove(0);
        if(request.destination.isRecycled())throw new AssertionError("bitmap recycled during native copy");
        request.handler.post(()->request.listener.onPixelCopyFinished(result));
    }
    public static void reset(){pending.clear();submitted=0;}
}
