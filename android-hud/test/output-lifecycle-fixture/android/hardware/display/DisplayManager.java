package android.hardware.display;
import android.os.Handler;
import android.view.Display;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
public class DisplayManager {
    public static final String DISPLAY_CATEGORY_PRESENTATION="presentation";
    public interface DisplayListener {
        void onDisplayAdded(int id);void onDisplayRemoved(int id);void onDisplayChanged(int id);
    }
    private static final class Entry {
        final DisplayListener listener;final Handler handler;
        Entry(DisplayListener l,Handler h){listener=l;handler=h;}
    }
    private final List<Entry> listeners=new ArrayList<>();
    public Display external=new Display(3);
    public Display[] getDisplays(String category){return external!=null && external.valid?new Display[]{external}:new Display[0];}
    public void registerDisplayListener(DisplayListener listener,Handler handler){listeners.add(new Entry(listener,handler));}
    public void unregisterDisplayListener(DisplayListener listener){listeners.removeIf(e->e.listener==listener);}
    public void changeMetrics(boolean reverseOrder){
        external.version++;external.width+=160;
        List<Entry> copy=new ArrayList<>(listeners);if(reverseOrder)Collections.reverse(copy);
        int id=external.getDisplayId();for(Entry entry:copy)entry.handler.post(()->entry.listener.onDisplayChanged(id));
    }
    public int listenerCount(){return listeners.size();}
}
