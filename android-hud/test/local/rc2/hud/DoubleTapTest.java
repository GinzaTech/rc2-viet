package local.rc2.hud;

public final class DoubleTapTest {
    static void check(boolean yes, String why) { if (!yes) throw new AssertionError(why); }
    static boolean tap(DoubleTap detector, long time, float x) {
        detector.down(time, x, 100, true, 1);
        return detector.up(time + 40, x, 100, 1);
    }
    public static void main(String[] args) {
        DoubleTap detector = new DoubleTap(12, 36);
        check(!tap(detector, 0, 100), "one tap must not toggle");
        check(tap(detector, 160, 102), "second tap toggles");
        check(!tap(detector, 250, 100), "cooldown prevents repeated toggle");
        detector.reset();
        check(!tap(detector, 0, 100) && !tap(detector, 600, 100), "long gap starts a new sequence");
        check(tap(detector, 760, 100), "fresh second tap toggles");
        detector.reset(); tap(detector, 0, 100);
        check(!tap(detector, 160, 200), "distant tap starts over");
        detector.reset(); detector.down(0,100,100,true,1); detector.move(140,100,1);
        check(!detector.up(40,100,100,1) && !tap(detector,160,100), "drag clears the sequence");
        detector.reset(); tap(detector,0,100); detector.down(160,100,100,true,2);
        check(!detector.up(200,100,100,1) && !tap(detector,300,100), "multi touch clears sequence");
        detector.reset(); tap(detector,0,100); detector.down(160,100,100,false,1); detector.up(200,100,100,1);
        check(!tap(detector,300,100), "controls never complete a double tap");
        detector.reset(); detector.down(0,100,100,true,1);
        check(!detector.up(350,100,100,1), "long press is not a tap");
        detector.reset(); tap(detector,0,100); detector.reset();
        check(!tap(detector,160,100), "focus loss or pause clears sequence");
        check(!DoubleTap.enabled(false,false), "disabled gesture cannot hide HUD");
        check(DoubleTap.enabled(false,true), "hidden HUD always has a restoration path");
        check(DoubleTap.enabled(true,false), "enabled gesture can hide HUD");
        System.out.println("double_tap_passed");
    }
}
