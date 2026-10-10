package android.view;
import android.graphics.Rect;
public interface SurfaceHolder {
    interface Callback {
        void surfaceCreated(SurfaceHolder holder);
        void surfaceChanged(SurfaceHolder holder,int format,int width,int height);
        void surfaceDestroyed(SurfaceHolder holder);
    }
    Surface getSurface();Rect getSurfaceFrame();
    void addCallback(Callback callback);void removeCallback(Callback callback);
}
