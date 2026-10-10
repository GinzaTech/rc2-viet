package android.app;
import android.content.Context;
import android.content.DialogInterface;
import android.hardware.display.DisplayManager;
import android.os.Bundle;
import android.os.Handler;
import android.view.Display;
import android.view.View;
import android.view.Window;
import java.util.ArrayList;
import java.util.List;
/** Models the Android 11 show/dismiss and metrics-change cancellation contract. */
public class Presentation implements DialogInterface {
    public static final List<Presentation> created=new ArrayList<>();
    private final Context context;private final Display display;private final Window window=new Window();
    private final Handler main=new Handler();private final int version;
    private View content;private boolean initialized,showing;
    private DialogInterface.OnDismissListener dismissListener;
    private final DisplayManager.DisplayListener events=new DisplayManager.DisplayListener(){
        public void onDisplayAdded(int id){}
        public void onDisplayRemoved(int id){if(showing && display.getDisplayId()==id)cancel();}
        public void onDisplayChanged(int id){if(showing && display.getDisplayId()==id && version!=display.version)cancel();}
    };
    public Presentation(Context context,Display display){this.context=context;this.display=display;version=display.version;created.add(this);}
    public Context getContext(){return context;}public Display getDisplay(){return display;}
    public Window getWindow(){return window;}
    protected void onCreate(Bundle state){}
    public void setContentView(View value){content=value;}
    public View content(){return content;}
    public boolean isShowing(){return showing;}
    public void setOnDismissListener(DialogInterface.OnDismissListener listener){dismissListener=listener;}
    public void show(){
        if(!initialized){onCreate(null);initialized=true;}
        showing=true;Context.manager.registerDisplayListener(events,main);
        if(content!=null)content.attach(display.width,display.height);
    }
    public void dismiss(){
        boolean wasShowing=showing;showing=false;Context.manager.unregisterDisplayListener(events);
        if(wasShowing && content!=null)content.detach();
        if(wasShowing && dismissListener!=null){DialogInterface.OnDismissListener listener=dismissListener;main.post(()->listener.onDismiss(this));}
    }
    public void cancel(){dismiss();}
    public static int liveWindows(){int n=0;for(Presentation p:created)if(p.showing)n++;return n;}
}
