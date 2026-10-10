package android.view;

import java.util.ArrayList;
import java.util.List;

/** Main-thread observer dispatch with explicit late-layout delivery. */
public final class ViewTreeObserver {
    public interface OnGlobalLayoutListener {void onGlobalLayout();}
    private final List<OnGlobalLayoutListener> listeners=new ArrayList<>();
    private boolean alive=true;
    public boolean isAlive(){return alive;}
    public void addOnGlobalLayoutListener(OnGlobalLayoutListener listener){
        if(!alive)throw new IllegalStateException("dead observer");listeners.add(listener);
    }
    public void removeOnGlobalLayoutListener(OnGlobalLayoutListener listener){
        if(!alive)throw new IllegalStateException("dead observer");listeners.remove(listener);
    }
    public void dispatchOnGlobalLayout(){
        if(!alive)return;
        for(OnGlobalLayoutListener listener:new ArrayList<>(listeners))listener.onGlobalLayout();
    }
    public int listenerCount(){return listeners.size();}
    public void kill(){alive=false;listeners.clear();}
}
