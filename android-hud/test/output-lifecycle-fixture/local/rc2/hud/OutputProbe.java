package local.rc2.hud;
import android.app.Activity;
import android.os.Bundle;
import android.view.SurfaceView;
/** Inert collaborator: virtual-display probing is not under test in this suite. */
final class OutputProbe {
    void start(Activity activity,SurfaceView preview){}
    void stop(){}
    Bundle status(){return new Bundle();}
}
