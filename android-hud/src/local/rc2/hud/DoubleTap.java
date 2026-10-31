package local.rc2.hud;

/** Bounded single-pointer tap recognition. No timers, touch consumption or Android dependencies. */
final class DoubleTap {
    static boolean enabled(boolean option,boolean hidden) { return option || hidden; }
    private static final long MAX_PRESS_MS = 250, MAX_GAP_MS = 350, MAX_SPAN_MS = 500, COOLDOWN_MS = 400;
    private final float slopSquared, radiusSquared;
    private boolean pressed;
    private int count;
    private long downTime, firstUp, lastUp, cooldownUntil;
    private float downX, downY, firstX, firstY;

    DoubleTap(float slop, float radius) {
        if (slop <= 0 || radius <= 0) throw new IllegalArgumentException("Tap bounds must be positive");
        slopSquared = slop * slop;
        radiusSquared = radius * radius;
    }
    void reset() { clearSequence(); cooldownUntil = 0; }
    private void clearSequence() { pressed = false; count = 0; }
    void down(long time, float x, float y, boolean eligible, int pointers) {
        if (!eligible || pointers != 1 || time < cooldownUntil) { clearSequence(); return; }
        if (count > 0 && (time < lastUp || time - lastUp > MAX_GAP_MS
                || distance(x, y, firstX, firstY) > radiusSquared)) clearSequence();
        pressed = true; downTime = time; downX = x; downY = y;
    }
    void move(float x, float y, int pointers) {
        if (pointers != 1 || (pressed && distance(x, y, downX, downY) > slopSquared)) clearSequence();
    }
    boolean up(long time, float x, float y, int pointers) {
        if (!pressed) return false;
        pressed = false;
        if (pointers != 1 || time < downTime || time - downTime > MAX_PRESS_MS
                || distance(x, y, downX, downY) > slopSquared) { clearSequence(); return false; }
        if (count == 0 || time < lastUp || time - firstUp > MAX_SPAN_MS) {
            count = 0; firstUp = time; firstX = x; firstY = y;
        }
        lastUp = time;
        if (++count < 2) return false;
        clearSequence(); cooldownUntil = time + COOLDOWN_MS;
        return true;
    }
    private static float distance(float x, float y, float otherX, float otherY) {
        float dx = x - otherX, dy = y - otherY;
        return dx * dx + dy * dy;
    }
}
