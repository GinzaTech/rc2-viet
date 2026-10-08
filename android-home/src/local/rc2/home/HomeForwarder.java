package local.rc2.home;

/** Foreground-only forwarding policy, independent of Android for regression tests. */
public final class HomeForwarder {
    public interface Host {
        boolean isUserUnlocked();
        boolean openLauncher();
        void scheduleRetry();
        void cancelRetry();
        void showFallback(boolean locked);
        void complete();
    }

    private final Host host;
    private int attempts;
    private boolean completed, paused, exhausted, fallbackShown;

    public HomeForwarder(Host host) { this.host = host; }

    public void start() {
        host.cancelRetry();
        attempts = 0;
        completed = paused = exhausted = fallbackShown = false;
        retry();
    }

    public void retry() {
        if (completed || paused || exhausted) return;
        boolean locked = !host.isUserUnlocked();
        if (!locked && host.openLauncher()) {
            completed = true;
            host.cancelRetry();
            host.complete();
            return;
        }
        attempts++;
        if (attempts >= 4 && !fallbackShown) {
            fallbackShown = true;
            host.showFallback(locked);
        }
        if (attempts <= (locked ? 120 : 40)) host.scheduleRetry();
        else { exhausted = true; host.cancelRetry(); }
    }

    public void pause() { paused = true; host.cancelRetry(); }
}
