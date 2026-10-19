package local.rc2.hud;

import java.util.ArrayList;
import java.util.List;

/** Inert boundary recorder. Tests deliver command results, reads and fence events separately. */
final class NativeLed {
    interface Result extends LedJob.Result { }
    interface Cancel { void cancel(); }
    static NativeLed instance;
    final List<LedJob.Reply<LedJob.Lights>> reads=new ArrayList<>();
    final List<String> calls=new ArrayList<>();
    final List<Runnable> observers=new ArrayList<>();
    Result pending;
    int closeCount,cancelled,observersAtClose;
    boolean accept=true,mutationPending;
    Boolean inlineResult;

    NativeLed(ClassLoader loader) { instance=this; }
    Cancel observe(Runnable callback) {
        observers.add(callback);
        return ()->{if(observers.remove(callback))cancelled++;};
    }
    void publish() {
        for(Runnable callback:new ArrayList<>(observers))callback.run();
    }
    void reconcile() { mutationPending=false;publish(); }
    void inspect(LedJob.Reply<LedJob.Lights> callback) { reads.add(callback); }
    boolean toggleFront(Result result) { return record("toggleFront",result); }
    boolean toggleRear(Result result) { return record("toggleRear",result); }
    boolean request(boolean on,Result result) { return record("request:"+on,result); }
    boolean requestRear(boolean on,Result result) { return record("requestRear:"+on,result); }
    boolean requestAll(boolean on,Result result) { return record("requestAll:"+on,result); }
    private boolean record(String call,Result result) {
        calls.add(call);pending=accept?result:null;
        if(inlineResult!=null) { pending=null;result.finished(inlineResult,"inline result"); }
        return accept;
    }
    void complete(boolean success) {
        Result callback=pending;
        if(callback==null)throw new AssertionError("no pending LED command");
        pending=null;callback.finished(success,success?"done":"failed");
    }
    void actual(boolean front,boolean status,boolean rear) {
        reads.get(reads.size()-1).success(new LedJob.Lights(front,status,rear,true));
    }
    void close() { observersAtClose=observers.size();closeCount++; }
}
