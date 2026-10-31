package local.rc2.hud;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;
import java.util.Timer;
import java.util.TimerTask;

/** Fresh, read-only area-code GETs pinned to stock Fly 1.21.8 classes12.dex.
 * No cached read, listener, retry, raw socket, SET, or FCC/CE inference.
 * The six-second deadline bounds callback completion, including a stalled submission.
 * SDK submission runs on the calling thread: call inspect off the UI thread if necessary.
 * Completion runs on the SDK/deadline/calling thread; the caller owns UI dispatch.
 * close suppresses delivery and further submissions; an already committed GET cannot
 * be cancelled in the SDK. Its late callback retains no Reply/Activity reference.
 */
final class AirlinkInspection {
    private static final String PREFIX = "uav.sdk.keyvalue.";
    private static final String SKY = "AreaCodeFromSky", GROUND = "AreaCodeFromGround";
    private static final long DEADLINE_MS = 6000;

    interface Reply {
        void finished(Result result);
        default boolean active() { return true; }
    }
    interface Cancel { void cancel(); }
    interface Scheduler { Cancel schedule(Runnable task, long delayMillis); }
    enum Status {
        OK, BUSY, TIMEOUT, SDK_BINDING_ERROR, KEY_MISMATCH, CALLBACK_MISMATCH,
        SDK_FAILURE, VALUE_MISSING, VALUE_TYPE, VALUE_FIELDS
    }
    static final class Reading {
        final String keyName;
        final Status status;
        final String areaCode;
        final Integer acValue, errorCode;
        private Reading(String keyName, Status status, String area, Integer ac, Integer error) {
            this.keyName = keyName; this.status = status; areaCode = area; acValue = ac; errorCode = error;
        }
        String metadata() {
            return keyName + " status=" + status.name() + " area_code=" + safeArea(areaCode)
                + " ac_value=" + number(acValue) + " error_code=" + number(errorCode);
        }
    }
    static final class Result {
        final Reading sky, ground;
        private Result(Reading sky, Reading ground) { this.sky = sky; this.ground = ground; }
        String metadata() {
            return "airlink_get " + sky.metadata() + " | " + ground.metadata() + " effective_mode=unknown";
        }
    }
    private static final class Request {
        Reply reply;
        Cancel deadline;
        Reading sky, ground;
        Object skyKey, groundKey;
        Request(Reply reply) { this.reply = reply; }
    }
    private static final class Binding {
        final Class<?> info, key, callback, area;
        final Method keyName, factory, get, areaCode, acValue;
        Binding(ClassLoader loader) throws ReflectiveOperationException {
            info = type(loader, "key.UAVKeyInfoBase"); key = type(loader, "key.UAVKey");
            callback = type(loader, "callback.IGetCallback");
            area = type(loader, "value.common.AreaCodeInfo");
            keyName = info.getMethod("e"); factory = key.getMethod("i", info);
            get = type(loader, "UAVKeyManager").getMethod("t", key, callback);
            areaCode = area.getMethod("getAreaCode"); acValue = area.getMethod("getAcValue");
            if (keyName.getReturnType() != String.class || factory.getReturnType() != key
                || !Modifier.isStatic(factory.getModifiers()) || get.getReturnType() != void.class
                || !Modifier.isStatic(get.getModifiers()) || !callback.isInterface()
                || callback.getMethod("b", key, Object.class).getReturnType() != void.class
                || callback.getMethod("a", key, int.class, String.class).getReturnType() != void.class
                || areaCode.getReturnType() != String.class || acValue.getReturnType() != Integer.class)
                throw new NoSuchMethodException("Pinned Airlink GET signatures required");
        }
    }
    private final ClassLoader loader;
    private final Scheduler scheduler;
    private Request current;
    private boolean closed;

    AirlinkInspection(ClassLoader loader) { this(loader, AirlinkInspection::scheduleDeadline); }
    AirlinkInspection(ClassLoader loader, Scheduler scheduler) {
        if (loader == null || scheduler == null) throw new IllegalArgumentException("Inspection dependencies required");
        this.loader = loader; this.scheduler = scheduler;
    }
    private static Class<?> type(ClassLoader loader, String name) throws ClassNotFoundException {
        return Class.forName(PREFIX + name, false, loader);
    }
    private static Cancel scheduleDeadline(Runnable task, long delay) {
        Timer timer = new Timer("RC2-AirlinkGetDeadline", true);
        timer.schedule(new TimerTask() { public void run() { task.run(); } }, delay);
        return timer::cancel;
    }

    /** One active inspection. true means accepted, never that an RF mode is active.
     * Both readings are delivered once, possibly synchronously, while Reply is active.
     * Inactive/closed returns false silently; BUSY returns false with two BUSY readings.
     */
    boolean inspect(Reply reply) {
        if (reply == null) throw new IllegalArgumentException("Inspection reply required");
        if (!reply.active()) return false;
        Request request;
        synchronized (this) {
            if (closed) return false;
            request = current == null ? new Request(reply) : null;
            if (request != null) current = request;
        }
        if (request == null) { reply.finished(pair(Status.BUSY)); return false; }
        if (!installDeadline(request)) return false;
        try {
            Binding binding = new Binding(loader);
            submit(request, binding, true, "w", SKY);
            submit(request, binding, false, "x", GROUND);
        } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
            terminate(request, Status.SDK_BINDING_ERROR);
        }
        return true;
    }
    private boolean installDeadline(Request request) {
        try {
            Cancel cancel = scheduler.schedule(() -> terminate(request, Status.TIMEOUT), DEADLINE_MS);
            synchronized (this) {
                if (current != request) { if (cancel != null) cancel.cancel(); return false; }
                if (cancel == null) throw new IllegalStateException("Deadline cancellation required");
                request.deadline = cancel;
            }
            return true;
        } catch (RuntimeException | LinkageError error) {
            terminate(request, Status.SDK_BINDING_ERROR); return false;
        }
    }
    private void submit(Request request, Binding binding, boolean sky, String field, String name) {
        if (!pending(request, sky)) return;
        try {
            Object info = type(loader, "key.UAVAirlinkKey").getField(field).get(null);
            if (!binding.info.isInstance(info) || !name.equals(binding.keyName.invoke(info))) {
                complete(request, sky, empty(name, Status.KEY_MISMATCH, null)); return;
            }
            Object key = binding.factory.invoke(null, info);
            if (!binding.key.isInstance(key)) throw new IllegalStateException("Missing Airlink key");
            Object callback = Proxy.newProxyInstance(binding.callback.getClassLoader(),
                new Class<?>[]{binding.callback}, (self, method, args) -> {
                    if (method.getDeclaringClass() == Object.class) return objectMethod(self, method, args);
                    receive(request, binding, sky, name, method.getName(), args); return null;
                });
            synchronized (this) {
                if (!pendingLocked(request, sky)) return;
                // Commit before calling out: no lifecycle lock is held across SDK/JNI calls.
                if (sky) request.skyKey = key; else request.groundKey = key;
            }
            binding.get.invoke(null, key, callback);
        } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
            complete(request, sky, empty(name, Status.SDK_BINDING_ERROR, null));
        }
    }
    private void receive(Request request, Binding binding, boolean sky, String name, String method, Object[] args) {
        synchronized (this) {
            if (!pendingLocked(request, sky)) return;
            Object expected = sky ? request.skyKey : request.groundKey;
            if (args == null || args.length < 1 || args[0] != expected) {
                // Decode outside the lock; all terminal transitions recheck the request.
                args = null;
            }
        }
        if (args == null) { complete(request, sky, empty(name, Status.CALLBACK_MISMATCH, null)); return; }
        if ("a".equals(method) && args.length == 3 && args[1] instanceof Integer) {
            complete(request, sky, empty(name, Status.SDK_FAILURE, (Integer)args[1]));
        } else if ("b".equals(method) && args.length == 2) {
            complete(request, sky, decode(binding, name, args[1]));
        } else complete(request, sky, empty(name, Status.CALLBACK_MISMATCH, null));
    }
    private static Reading decode(Binding binding, String name, Object value) {
        if (value == null) return empty(name, Status.VALUE_MISSING, null);
        if (!binding.area.isInstance(value)) return empty(name, Status.VALUE_TYPE, null);
        try {
            String area = (String)binding.areaCode.invoke(value);
            Integer ac = (Integer)binding.acValue.invoke(value);
            return new Reading(name, area == null || ac == null ? Status.VALUE_FIELDS : Status.OK, area, ac, null);
        } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
            return empty(name, Status.SDK_BINDING_ERROR, null);
        }
    }
    private synchronized boolean pending(Request request, boolean sky) { return pendingLocked(request, sky); }
    private boolean pendingLocked(Request request, boolean sky) {
        return !closed && current == request && (sky ? request.sky : request.ground) == null;
    }
    private void complete(Request request, boolean sky, Reading reading) {
        synchronized (this) {
            if (!pendingLocked(request, sky)) return;
            if (sky) { request.sky = reading; request.skyKey = null; }
            else { request.ground = reading; request.groundKey = null; }
        }
        deliverIfComplete(request);
    }
    private void terminate(Request request, Status status) {
        synchronized (this) {
            if (closed || current != request) return;
            if (request.sky == null) request.sky = empty(SKY, status, null);
            if (request.ground == null) request.ground = empty(GROUND, status, null);
        }
        deliverIfComplete(request);
    }
    private void deliverIfComplete(Request request) {
        Reply reply; Result result; Cancel deadline;
        synchronized (this) {
            if (closed || current != request || request.sky == null || request.ground == null) return;
            current = null; reply = request.reply; result = new Result(request.sky, request.ground);
            deadline = release(request);
        }
        if (deadline != null) deadline.cancel();
        // This is the committed delivery. close cannot retract a callback already committed.
        if (reply.active()) reply.finished(result);
    }
    void close() {
        Cancel deadline = null;
        synchronized (this) {
            closed = true;
            if (current != null) { deadline = release(current); current = null; }
        }
        if (deadline != null) deadline.cancel();
    }
    private static Cancel release(Request request) {
        Cancel deadline = request.deadline;
        request.deadline = null; request.reply = null;
        request.skyKey = null; request.groundKey = null;
        return deadline;
    }
    private static Reading empty(String name, Status status, Integer code) {
        return new Reading(name, status, null, null, code);
    }
    private static Result pair(Status status) { return new Result(empty(SKY, status, null), empty(GROUND, status, null)); }
    private static String number(Integer value) { return value == null ? "unknown" : value.toString(); }
    private static String safeArea(String value) {
        if (value == null) return "unknown";
        StringBuilder safe = new StringBuilder();
        for (int index = 0; index < Math.min(value.length(), 32); index++) {
            char c = value.charAt(index);
            safe.append(c >= 'A' && c <= 'Z' || c >= 'a' && c <= 'z' || c >= '0' && c <= '9'
                || c == '-' || c == '_' || c == '.' ? c : '_');
        }
        if (value.length() > 32) safe.append("...");
        return safe.toString();
    }
    private static Object objectMethod(Object self, Method method, Object[] args) {
        if ("hashCode".equals(method.getName())) return System.identityHashCode(self);
        if ("equals".equals(method.getName())) return args != null && args.length == 1 && self == args[0];
        return "RC2AirlinkGetCallback";
    }
}
