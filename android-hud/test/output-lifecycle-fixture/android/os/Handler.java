package android.os;
import java.util.ArrayList;
import java.util.List;
/** Deterministic single-main-thread queue; delayed tasks require explicit clock advance. */
public class Handler {
    private static final List<Task> queue=new ArrayList<>();
    private static long now,order;
    private static final class Task {
        final Handler owner;final Runnable action;final long due,sequence;
        Task(Handler h,Runnable r,long d){owner=h;action=r;due=d;sequence=order++;}
    }
    public Handler(){this(Looper.getMainLooper());}
    public Handler(Looper looper){}
    public boolean post(Runnable action){return postDelayed(action,0);}
    public boolean postDelayed(Runnable action,long delay){queue.add(new Task(this,action,now+delay));return true;}
    public void removeCallbacks(Runnable action){queue.removeIf(t->t.owner==this && t.action==action);}
    public static Runnable nextReady(){
        Task best=null;
        for(Task t:queue)if(t.due<=now && (best==null || t.due<best.due || (t.due==best.due && t.sequence<best.sequence)))best=t;
        if(best==null)return null;queue.remove(best);return best.action;
    }
    public static void drain(){
        for(int n=0;n<1000;n++){Runnable action=nextReady();if(action==null)return;action.run();}
        throw new AssertionError("main queue did not quiesce");
    }
    public static void advance(long millis){now+=millis;drain();}
    public static int readyCount(){int n=0;for(Task t:queue)if(t.due<=now)n++;return n;}
    public static void reset(){queue.clear();now=0;order=0;}
}
