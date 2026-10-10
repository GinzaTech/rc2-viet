package uav.sdk.keyvalue;

import java.util.ArrayList;
import java.util.List;
import uav.sdk.keyvalue.callback.IGetCallback;
import uav.sdk.keyvalue.key.UAVKey;

public final class UAVKeyManager {
    public static final class Call {
        public final UAVKey key;
        public final IGetCallback callback;
        Call(UAVKey key, IGetCallback callback) { this.key = key; this.callback = callback; }
        public void success(Object value) { callback.b(key, value); }
        public void failure(int code) { callback.a(key, code, "PRIVATE SDK detail"); }
    }
    public static final List<Call> calls = new ArrayList<>();
    public static int writes, cached;
    public static String throwGet;
    public static boolean immediate;
    public static java.util.concurrent.CountDownLatch entered, release;
    public static void t(UAVKey key, IGetCallback callback) {
        if (entered != null) {
            entered.countDown();
            try { release.await(); } catch (InterruptedException error) { Thread.currentThread().interrupt(); }
        }
        if (key.info.name.equals(throwGet)) throw new IllegalStateException("PRIVATE SDK detail");
        Call call = new Call(key, callback); calls.add(call);
        if (immediate) call.success(new uav.sdk.keyvalue.value.common.AreaCodeInfo("US", 7));
    }
    public static Object r(UAVKey key) { cached++; throw new AssertionError("no cached GET"); }
    public static void x(UAVKey key, Object value, Object callback) {
        writes++; throw new AssertionError("inspection cannot write");
    }
}
