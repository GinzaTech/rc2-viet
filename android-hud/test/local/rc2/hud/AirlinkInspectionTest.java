package local.rc2.hud;

import java.lang.reflect.Proxy;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;
import uav.sdk.keyvalue.UAVKeyManager;
import uav.sdk.keyvalue.UAVKeyManager.Call;
import uav.sdk.keyvalue.key.UAVAirlinkKey;
import uav.sdk.keyvalue.key.UAVKey;
import uav.sdk.keyvalue.value.common.AreaCodeInfo;

public final class AirlinkInspectionTest {
    private static void check(boolean value, String reason) { if (!value) throw new AssertionError(reason); }
    private static final class Clock implements AirlinkInspection.Scheduler {
        Runnable task;
        int cancellations;
        boolean fail, immediate, absent;
        public AirlinkInspection.Cancel schedule(Runnable task, long delay) {
            check(delay == 6000, "one bounded six second inspection deadline");
            if (fail) throw new IllegalStateException("PRIVATE scheduler detail");
            this.task = task;
            if (immediate) task.run();
            return absent ? null : () -> cancellations++;
        }
        void fire() { task.run(); }
    }
    private static final class Reply implements AirlinkInspection.Reply {
        volatile int deliveries;
        volatile boolean live = true;
        volatile AirlinkInspection.Result result;
        public boolean active() { return live; }
        public void finished(AirlinkInspection.Result value) { result = value; deliveries++; }
    }
    private static AirlinkInspection probe(Clock clock) {
        return new AirlinkInspection(AirlinkInspectionTest.class.getClassLoader(), clock);
    }
    private static void reset() {
        UAVKeyManager.calls.clear(); UAVKeyManager.writes = 0; UAVKeyManager.cached = 0;
        UAVKeyManager.throwGet = null; UAVKeyManager.immediate = false;
        UAVKeyManager.entered = null; UAVKeyManager.release = null;
        UAVKey.throwFactory = false; UAVKey.nullFactory = false; UAVKey.factoryCalls = 0;
        UAVAirlinkKey.w.name = "AreaCodeFromSky"; UAVAirlinkKey.x.name = "AreaCodeFromGround";
        UAVAirlinkKey.w.throwName = false; UAVAirlinkKey.x.throwName = false;
    }
    private static void noWrites() {
        check(UAVKeyManager.writes == 0 && UAVKeyManager.cached == 0, "only fresh GETs, no write/cache fallback");
        for (Call call : UAVKeyManager.calls)
            check(call.key.info == UAVAirlinkKey.w || call.key.info == UAVAirlinkKey.x, "only the pinned area keys");
    }
    private static void statuses(Reply reply, String sky, String ground) {
        check(reply.deliveries == 1, "one terminal delivery");
        check(reply.result.sky.status.name().equals(sky), "sky expected " + sky);
        check(reply.result.ground.status.name().equals(ground), "ground expected " + ground);
        check(!reply.result.metadata().contains("PRIVATE"), "no SDK error text or objects in metadata");
        check(reply.result.metadata().contains("effective_mode=unknown"), "readback is not a mode claim");
        noWrites();
    }
    private static AreaCodeInfo value() { return new AreaCodeInfo("US", 7); }
    private static void success() {
        Clock clock = new Clock(); AirlinkInspection p = probe(clock); Reply reply = new Reply();
        check(p.inspect(reply), "accepted"); check(UAVKeyManager.calls.size() == 2, "exactly two fresh GETs");
        check(UAVKeyManager.calls.get(0).key.info == UAVAirlinkKey.w, "sky first");
        check(UAVKeyManager.calls.get(1).key.info == UAVAirlinkKey.x, "ground second");
        UAVKeyManager.calls.get(1).success(new AreaCodeInfo("VN", -3));
        check(reply.deliveries == 0, "wait for both independent readings");
        UAVKeyManager.calls.get(0).success(value()); statuses(reply, "OK", "OK");
        check("US".equals(reply.result.sky.areaCode) && reply.result.sky.acValue == 7, "sky raw values");
        check("VN".equals(reply.result.ground.areaCode) && reply.result.ground.acValue == -3, "ground raw values unclassified");
        check(clock.cancellations == 1, "deadline cancelled"); p.close();
    }
    private static void partial() {
        AirlinkInspection p = probe(new Clock()); Reply reply = new Reply(); p.inspect(reply);
        UAVKeyManager.calls.get(0).failure(-9); UAVKeyManager.calls.get(1).success(value());
        statuses(reply, "SDK_FAILURE", "OK"); check(reply.result.sky.errorCode == -9, "preserve numeric failure");
        check(reply.result.sky.areaCode == null && reply.result.sky.acValue == null, "no fabricated failure values"); p.close();
    }
    private static void failures() {
        AirlinkInspection p = probe(new Clock()); Reply reply = new Reply(); p.inspect(reply);
        UAVKeyManager.calls.get(0).failure(-261); UAVKeyManager.calls.get(1).failure(0);
        statuses(reply, "SDK_FAILURE", "SDK_FAILURE");
        check(reply.result.ground.errorCode == 0, "failure callback zero is still failure"); p.close();
    }
    private static void values() {
        Object[] values = {null, new Object(), new AreaCodeInfo(null, 12), new AreaCodeInfo("US", null)};
        String[] statuses = {"VALUE_MISSING", "VALUE_TYPE", "VALUE_FIELDS", "VALUE_FIELDS"};
        for (int i = 0; i < values.length; i++) {
            reset(); AirlinkInspection p = probe(new Clock()); Reply reply = new Reply(); p.inspect(reply);
            UAVKeyManager.calls.get(0).success(values[i]); UAVKeyManager.calls.get(1).success(value());
            statuses(reply, statuses[i], "OK"); p.close();
        }
        for (int i = 0; i < 2; i++) {
            reset(); AirlinkInspection p = probe(new Clock()); Reply reply = new Reply(); p.inspect(reply);
            AreaCodeInfo broken = value(); broken.throwArea = i == 0; broken.throwValue = i == 1;
            UAVKeyManager.calls.get(0).success(broken); UAVKeyManager.calls.get(1).success(value());
            statuses(reply, "SDK_BINDING_ERROR", "OK"); p.close();
        }
        reset(); AirlinkInspection p = probe(new Clock()); Reply reply = new Reply(); p.inspect(reply);
        String unsafe = "US\n\r\t='" + String.join("", java.util.Collections.nCopies(100, "x"));
        UAVKeyManager.calls.get(0).success(new AreaCodeInfo(unsafe, Integer.MIN_VALUE));
        UAVKeyManager.calls.get(1).success(new AreaCodeInfo("", Integer.MAX_VALUE)); statuses(reply, "OK", "OK");
        check(unsafe.equals(reply.result.sky.areaCode), "raw API string preserved");
        check(!reply.result.metadata().contains("\n") && reply.result.metadata().length() < 500, "bounded safe single line metadata"); p.close();
    }
    private static void wrongKey() {
        AirlinkInspection p = probe(new Clock()); Reply reply = new Reply(); p.inspect(reply);
        Call sky = UAVKeyManager.calls.get(0), ground = UAVKeyManager.calls.get(1);
        sky.callback.b(ground.key, value()); ground.callback.a(null, -9, "PRIVATE");
        statuses(reply, "CALLBACK_MISMATCH", "CALLBACK_MISMATCH"); p.close();
    }
    private static void duplicate() {
        Clock clock = new Clock(); AirlinkInspection p = probe(clock); Reply reply = new Reply(); p.inspect(reply);
        Call sky = UAVKeyManager.calls.get(0), ground = UAVKeyManager.calls.get(1);
        sky.success(value()); sky.failure(-9); ground.success(value()); statuses(reply, "OK", "OK");
        sky.success(null); ground.failure(-9); clock.fire(); check(reply.deliveries == 1, "late events ignored");
        Reply next = new Reply(); p.inspect(next); sky.success(value()); clock.fire();
        statuses(next, "TIMEOUT", "TIMEOUT"); p.close();
    }
    private static void timeout() {
        Clock clock = new Clock(); AirlinkInspection p = probe(clock); Reply reply = new Reply(); p.inspect(reply);
        UAVKeyManager.calls.get(0).success(value()); clock.fire(); statuses(reply, "OK", "TIMEOUT");
        UAVKeyManager.calls.get(1).success(value()); check(reply.deliveries == 1, "late completion discarded"); p.close();
    }
    private static void close() {
        Clock clock = new Clock(); AirlinkInspection p = probe(clock); Reply reply = new Reply(); p.inspect(reply);
        p.close(); p.close(); clock.fire();
        for (Call call : UAVKeyManager.calls) call.success(value());
        check(reply.deliveries == 0 && clock.cancellations == 1 && !p.inspect(new Reply()), "closed probe silent and no new GET"); noWrites();
    }
    private static void inactive() {
        Clock clock = new Clock(); AirlinkInspection p = probe(clock); Reply reply = new Reply(); reply.live = false;
        check(!p.inspect(reply) && UAVKeyManager.calls.isEmpty(), "inactive prevents sending"); reply.live = true; p.inspect(reply);
        reply.live = false; for (Call call : UAVKeyManager.calls) call.success(value());
        check(reply.deliveries == 0 && clock.cancellations == 1, "inactive suppresses delivery and releases resources"); p.close(); noWrites();
    }
    private static void busy() {
        Clock clock = new Clock(); AirlinkInspection p = probe(clock); Reply first = new Reply(), busy = new Reply(); p.inspect(first);
        check(!p.inspect(busy), "busy rejected"); statuses(busy, "BUSY", "BUSY");
        check(UAVKeyManager.calls.size() == 2, "busy sends nothing"); clock.fire(); statuses(first, "TIMEOUT", "TIMEOUT"); p.close();
    }
    private static void binding() {
        for (int i = 0; i < 5; i++) {
            reset(); AirlinkInspection p = probe(new Clock()); Reply reply = new Reply();
            UAVAirlinkKey.w.name = i == 0 ? "PRIVATE wrong key" : "AreaCodeFromSky";
            UAVAirlinkKey.w.throwName = i == 1; UAVKey.throwFactory = i == 2; UAVKey.nullFactory = i == 3;
            UAVKeyManager.throwGet = i == 4 ? "AreaCodeFromSky" : null;
            p.inspect(reply);
            for (Call call : UAVKeyManager.calls) call.success(value());
            String error = i == 0 ? "KEY_MISMATCH" : "SDK_BINDING_ERROR";
            statuses(reply, error, (i == 2 || i == 3) ? error : "OK"); p.close();
        }
        reset(); AirlinkInspection p = new AirlinkInspection(new ClassLoader(null) {}, new Clock()); Reply reply = new Reply();
        p.inspect(reply); statuses(reply, "SDK_BINDING_ERROR", "SDK_BINDING_ERROR"); check(UAVKeyManager.calls.isEmpty(), "missing classes no dispatch"); p.close();
    }
    private static void scheduler() {
        for (int i = 0; i < 3; i++) {
            reset(); Clock clock = new Clock(); clock.fail = i == 0; clock.absent = i != 0; clock.immediate = i == 2;
            AirlinkInspection p = probe(clock); Reply reply = new Reply(); p.inspect(reply);
            statuses(reply, i == 2 ? "TIMEOUT" : "SDK_BINDING_ERROR", i == 2 ? "TIMEOUT" : "SDK_BINDING_ERROR");
            check(UAVKeyManager.calls.isEmpty(), "deadline must be installed before sending"); p.close();
        }
    }
    private static void immediate() {
        Clock clock = new Clock(); clock.immediate = true; AirlinkInspection p = probe(clock); Reply reply = new Reply();
        check(!p.inspect(reply), "timeout before dispatch"); statuses(reply, "TIMEOUT", "TIMEOUT");
        check(UAVKeyManager.calls.isEmpty() && clock.cancellations == 1, "no expired send, returned deadline handle cancelled"); p.close();
        reset(); UAVKeyManager.immediate = true;
        p = new AirlinkInspection(AirlinkInspectionTest.class.getClassLoader()); reply = new Reply();
        check(p.inspect(reply), "synchronous GET accepted"); statuses(reply, "OK", "OK"); p.close();
    }
    private static void objects() throws Throwable {
        AirlinkInspection p = probe(new Clock()); Reply reply = new Reply(); p.inspect(reply);
        Object callback = UAVKeyManager.calls.get(0).callback;
        check(callback.hashCode() == System.identityHashCode(callback), "identity hash");
        check(callback.equals(callback) && !callback.equals(null) && !callback.equals(new Object()), "identity equality");
        check(callback.toString().equals("RC2AirlinkGetCallback"), "safe object name");
        java.lang.reflect.Method success = uav.sdk.keyvalue.callback.IGetCallback.class.getMethod("b", UAVKey.class, Object.class);
        Proxy.getInvocationHandler(callback).invoke(callback, success, null);
        UAVKeyManager.calls.get(1).success(value()); statuses(reply, "CALLBACK_MISMATCH", "OK"); p.close();
    }
    private static void races() throws Exception {
        for (int round = 0; round < 30; round++) {
            reset(); Clock clock = new Clock(); AirlinkInspection p = probe(clock); Reply reply = new Reply(); p.inspect(reply);
            Call sky = UAVKeyManager.calls.get(0), ground = UAVKeyManager.calls.get(1);
            Runnable[] tasks = {() -> sky.success(value()), () -> sky.failure(-9), () -> ground.success(value()), clock::fire};
            CountDownLatch go = new CountDownLatch(1); AtomicReference<Throwable> error = new AtomicReference<>();
            Thread[] threads = new Thread[tasks.length];
            for (int i = 0; i < tasks.length; i++) {
                final Runnable action = tasks[i]; threads[i] = new Thread(() -> {
                    try { go.await(); action.run(); } catch (Throwable problem) { error.compareAndSet(null, problem); }
                }); threads[i].start();
            }
            go.countDown(); for (Thread thread : threads) { thread.join(3000); check(!thread.isAlive(), "no callback deadlock"); }
            check(error.get() == null && reply.deliveries == 1 && clock.cancellations == 1, "racing events terminate once"); p.close(); noWrites();
        }
    }
    private static void boundaries() {
        boolean rejected = false;
        try { new AirlinkInspection(null, new Clock()); } catch (IllegalArgumentException expected) { rejected = true; }
        check(rejected, "null loader rejected"); rejected = false;
        try { new AirlinkInspection(AirlinkInspectionTest.class.getClassLoader(), null); } catch (IllegalArgumentException expected) { rejected = true; }
        check(rejected, "null scheduler rejected"); rejected = false; AirlinkInspection p = probe(new Clock());
        try { p.inspect(null); } catch (IllegalArgumentException expected) { rejected = true; }
        check(rejected, "null reply rejected"); p.close();
    }
    private static void stalledSubmission() throws Exception {
        Clock clock = new Clock(); AirlinkInspection p = probe(clock); Reply reply = new Reply();
        UAVKeyManager.entered = new CountDownLatch(1); UAVKeyManager.release = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread submit = new Thread(() -> {
            try { p.inspect(reply); } catch (Throwable error) { failure.set(error); }
        });
        submit.setDaemon(true); submit.start();
        try {
            check(UAVKeyManager.entered.await(3, java.util.concurrent.TimeUnit.SECONDS), "submission entered SDK");
            clock.fire(); statuses(reply, "TIMEOUT", "TIMEOUT");
            p.close(); check(clock.cancellations == 1, "deadline and close are not blocked by JNI submission");
        } finally {
            UAVKeyManager.release.countDown(); submit.join(3000);
        }
        check(!submit.isAlive() && failure.get() == null, "no lock deadlock on stalled SDK");
        check(UAVKeyManager.calls.size() == 1, "ground GET not submitted after timeout/close");
        UAVKeyManager.calls.get(0).success(value()); check(reply.deliveries == 1, "stalled submission late callback ignored");
    }
    public static void main(String[] args) throws Throwable {
        reset();
        switch (args[0]) {
            case "success": success(); break; case "partial": partial(); break;
            case "failures": failures(); break; case "values": values(); break;
            case "wrong-key": wrongKey(); break; case "duplicate": duplicate(); break;
            case "timeout": timeout(); break; case "close": close(); break;
            case "inactive": inactive(); break; case "busy": busy(); break;
            case "binding": binding(); break; case "scheduler": scheduler(); break;
            case "immediate": immediate(); break; case "objects": objects(); break;
            case "races": races(); break; case "boundaries": boundaries(); break;
            case "stalled": stalledSubmission(); break;
            default: throw new AssertionError("unknown scenario");
        }
        noWrites(); System.out.println("airlink_inspection_passed:" + args[0]);
    }
}
