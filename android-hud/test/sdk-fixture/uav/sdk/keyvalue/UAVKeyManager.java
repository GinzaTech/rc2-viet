package uav.sdk.keyvalue;
import uav.sdk.keyvalue.key.UAVKey;
import uav.sdk.keyvalue.callback.IGetCallback;
import uav.sdk.keyvalue.callback.ISetCallback;
public final class UAVKeyManager {
    public static Object value,written;
    public static String field;
    public static int subIndex;
    public static int error,writes;
    public static boolean hold;
    public static IGetCallback pending;
    public static UAVKey pendingKey;
    public static boolean holdSet;
    public static ISetCallback pendingSet;
    public static UAVKey pendingSetKey;
    public static final java.util.List<String> reads=new java.util.ArrayList<>();
    public static final java.util.Map<String,Object> cache=new java.util.HashMap<>();
    public static Object r(UAVKey key) { field=key.info.name; subIndex=key.subIndex; return cache.containsKey(field)?cache.get(field):value; }
    public static void t(UAVKey key,IGetCallback callback) {
        field=key.info.name;
        subIndex=key.subIndex;
        reads.add(field);
        if(hold) { pending=callback; pendingKey=key; return; }
        if(error!=0) callback.a(key,error,"PRIVATE SDK DETAIL"); else callback.b(key,cache.containsKey(field)?cache.get(field):value);
    }
    public static void x(UAVKey key,Object value,ISetCallback callback) {
        field=key.info.name; written=value; writes++;
        subIndex=key.subIndex;
        if(holdSet) { pendingSet=callback; pendingSetKey=key; return; }
        cache.put(field,value);
        if(error!=0) callback.a(key,error,"PRIVATE SDK DETAIL"); else callback.b(key);
    }
}
