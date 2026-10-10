package uav.sdk.keyvalue.key;

public final class UAVKey {
    public final UAVKeyInfoBase info;
    public static boolean throwFactory, nullFactory;
    public static int factoryCalls;
    public UAVKey(UAVKeyInfoBase info) { this.info = info; }
    public static UAVKey i(UAVKeyInfoBase info) {
        factoryCalls++;
        if (throwFactory) throw new IllegalStateException("PRIVATE SDK detail");
        return nullFactory ? null : new UAVKey(info);
    }
}
