package local.rc2.home;

public final class HomeForwarderTest {
    private static final class Host implements HomeForwarder.Host {
        boolean unlocked=true, available=true;
        int opens, completions, retries, cancellations, fallbacks;
        String reason="";
        public boolean isUserUnlocked() { return unlocked; }
        public boolean openLauncher() { opens++; return available; }
        public void scheduleRetry() { retries++; }
        public void cancelRetry() { cancellations++; }
        public void complete() { completions++; }
        public void showFallback(boolean locked) { fallbacks++; reason=locked ? "locked" : "missing"; }
    }

    private static void require(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }

    public static void main(String[] args) {
        Host ready=new Host(); HomeForwarder first=new HomeForwarder(ready);
        first.start(); first.retry();
        require(ready.opens==1 && ready.completions==1 && ready.fallbacks==0,
                "Ready Home must forward once, finish and never show waiting UI");

        Host locked=new Host(); locked.unlocked=false;
        HomeForwarder pending=new HomeForwarder(locked); pending.start();
        require(locked.opens==0 && locked.fallbacks==0 && locked.retries==1,
                "Direct Boot must wait without launching credential-storage activity");
        locked.unlocked=true; pending.retry();
        require(locked.opens==1 && locked.completions==1 && locked.fallbacks==0,
                "Unlock must forward without unnecessary waiting screen");

        Host slow=new Host(); slow.unlocked=false; HomeForwarder delayed=new HomeForwarder(slow);
        delayed.start(); delayed.retry(); delayed.retry(); delayed.retry();
        require(slow.fallbacks==1 && slow.reason.equals("locked"),
                "A genuine prolonged lock must show one fallback");

        Host missing=new Host(); missing.available=false; HomeForwarder failed=new HomeForwarder(missing);
        failed.start(); failed.retry(); failed.retry(); failed.retry();
        require(missing.completions==0 && missing.fallbacks==1 && missing.reason.equals("missing"),
                "Missing launcher must keep usable fallback rather than finish into blank Home");
        missing.available=true; failed.start();
        require(missing.completions==1,"Retry or new Home intent must try launcher again");

        Host paused=new Host(); paused.unlocked=false; HomeForwarder pausedFlow=new HomeForwarder(paused);
        pausedFlow.start(); pausedFlow.pause(); paused.unlocked=true; pausedFlow.retry();
        require(paused.opens==0 && paused.completions==0,"Pause must cancel stale callbacks");
        pausedFlow.start(); require(paused.completions==1,"Resume must restart forwarding");

        Host timeout=new Host(); timeout.unlocked=false; HomeForwarder timed=new HomeForwarder(timeout);
        timed.start(); for (int i=0;i<130;i++) timed.retry();
        require(timeout.retries==120 && timeout.fallbacks==1 && timeout.completions==0,
                "Locked startup retries must be bounded and preserve fallback");
        System.out.println("6 home-forwarding scenarios passed");
    }
}
