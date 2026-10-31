package local.rc2.hud;

import java.util.Timer;
import java.util.TimerTask;

/** Pinned parameter LED adapter; no typed LED writes, retries or recurring poll. */
final class NativeLed {
    interface Result extends LedJob.Result { }
    interface Cancel { void cancel(); }
    private static final MutationFence mutations=MutationFence.hardware();
    private final NativeAircraft aircraft;
    private final NativeForearmLed forearm;
    private volatile boolean closed;
    private final java.util.List<Timer> probes=new java.util.ArrayList<>();
    private final java.util.List<Observer> observers=new java.util.ArrayList<>();
    private final class Observer implements Cancel {
        final Runnable listener;
        volatile boolean active=true;
        MutationFence.Cancel subscription;
        Observer(Runnable listener) { this.listener=listener; }
        void fire() { if(active && !closed) listener.run(); }
        public void cancel() {
            MutationFence.Cancel detached;
            synchronized(NativeLed.this) {
                if(!active) return;
                active=false; observers.remove(this); detached=subscription;
            }
            if(detached!=null) detached.cancel();
        }
    }
    NativeLed(ClassLoader loader) {
        aircraft=new NativeAircraft(loader);
        forearm=new NativeForearmLed(loader,aircraft,mutations);
    }
    GroundGate state() { return aircraft.snapshot(); }
    Cancel observe(Runnable listener) {
        if(listener==null) throw new IllegalArgumentException("LED observer required");
        synchronized(this) {
            if(closed) return ()->{};
            Observer observer=new Observer(listener);
            observer.subscription=mutations.observe(observer::fire);
            observers.add(observer); return observer;
        }
    }
    boolean toggleFront(Result result) {
        return !closed && result!=null && forearm.toggleFront(result);
    }
    boolean toggleRear(Result result) {
        return !closed && result!=null && forearm.toggleRear(result);
    }
    boolean request(boolean on,Result result) {
        return !closed && result!=null && forearm.request(on,result);
    }
    boolean requestRear(boolean on,Result result) {
        return !closed && result!=null && forearm.requestRear(on,result);
    }
    boolean requestAll(boolean on,Result result) {
        return !closed && result!=null && forearm.requestAll(on,result);
    }
    void inspect(LedJob.Reply<LedJob.Lights> result) {
        if(result==null) return;
        Timer timer;
        synchronized(this) {
            if(closed) return;
            timer=new Timer("RC2-LedReadDeadline",true); probes.add(timer);
        }
        java.util.concurrent.atomic.AtomicBoolean live=new java.util.concurrent.atomic.AtomicBoolean(true);
        LedJob.Reply<LedJob.Lights> reply=new LedJob.Reply<LedJob.Lights>() {
            public boolean active() { return live.get() && !closed && result.active(); }
            private boolean complete() {
                synchronized(NativeLed.this) {
                    if(!live.compareAndSet(true,false)) return false;
                    probes.remove(timer);
                }
                timer.cancel(); return !closed && result.active();
            }
            public void success(LedJob.Lights lights) { if(complete()) result.success(lights); }
            public void failure(String message) { if(complete()) result.failure(message); }
        };
        try {
            timer.schedule(new TimerTask() {
                public void run() { reply.failure("LED: hết thời gian chờ đọc trạng thái."); }
            },9000);
            if(reply.active()) forearm.inspect(reply);
        } catch(RuntimeException | LinkageError error) {
            reply.failure("Không mở được tác vụ đọc LED.");
        }
    }
    void close() {
        java.util.List<Timer> detachedTimers;
        java.util.List<Observer> detachedObservers;
        synchronized(this) {
            if(closed) return;
            closed=true;
            detachedTimers=new java.util.ArrayList<>(probes); probes.clear();
            detachedObservers=new java.util.ArrayList<>(observers); observers.clear();
        }
        // No owner monitor is held while cancelling subscriptions or waiting for
        // a child's committed SDK submission/foreign reconciliation callback.
        for(Timer timer:detachedTimers) timer.cancel();
        for(Observer observer:detachedObservers) observer.cancel();
        forearm.close();
    }
}
