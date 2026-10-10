package local.rc2.hud;

/** Process-wide exclusion: a UI cancellation never cancels an aircraft-side mutation. */
final class MutationFence {
    interface Cancel { void cancel(); }
    private static final MutationFence HARDWARE=new MutationFence();
    static MutationFence hardware() { return HARDWARE; }
    private Object pending;
    private final java.util.List<Observer> observers=new java.util.ArrayList<>();
    private final class Observer implements Cancel {
        final Runnable listener;
        volatile boolean active=true;
        Observer(Runnable listener) { this.listener=listener; }
        public void cancel() {
            synchronized(MutationFence.this) {
                active=false; observers.remove(this);
            }
        }
        void fire() {
            if(!active) return;
            try { listener.run(); }
            catch(RuntimeException | LinkageError error) {
                System.err.println("Mutation reconciliation observer failed.");
            }
        }
    }
    synchronized Cancel observe(Runnable listener) {
        if(listener==null) throw new IllegalArgumentException("Mutation observer required");
        Observer observer=new Observer(listener); observers.add(observer); return observer;
    }
    synchronized Object begin() {
        if(pending!=null) return null;
        pending=new Object(); return pending;
    }
    synchronized boolean pending() { return pending!=null; }
    void reconciled(Object request) {
        java.util.List<Observer> listeners;
        synchronized(this) {
            if(request==null || pending!=request) return;
            pending=null; listeners=new java.util.ArrayList<>(observers);
        }
        for(Observer observer:listeners) observer.fire();
    }
}
