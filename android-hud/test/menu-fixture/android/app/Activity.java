package android.app;
import java.util.ArrayDeque;
public class Activity extends android.content.Context {
 private final Thread main=Thread.currentThread(); private final ArrayDeque<Runnable> queue=new ArrayDeque<>(); public boolean defer;
 public void runOnUiThread(Runnable task){if(Thread.currentThread()==main&&!defer)task.run();else synchronized(queue){queue.add(task);}}
 public void drain(){while(true){Runnable task;synchronized(queue){task=queue.poll();}if(task==null)return;task.run();}}
}
