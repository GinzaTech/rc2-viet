package uav.sdk.keyvalue;
import uav.sdk.keyvalue.key.UAVKey;
import uav.sdk.keyvalue.callback.IGetCallback;
import uav.sdk.keyvalue.callback.ISetCallback;
public final class UAVKeyManager {
    public static Object value,written;
    public static String field;
    public static int subIndex;
    public static int error,writes;
    public static int cachedReads;
    public static boolean throwCache,throwGet,throwSet,throwAfterCallback;
    public static boolean hold;
    public static IGetCallback pending;
    public static UAVKey pendingKey;
    public static boolean holdSet;
    public static ISetCallback pendingSet;
    public static UAVKey pendingSetKey;
    public static final java.util.List<String> reads=new java.util.ArrayList<>();
    public static final java.util.Map<String,Object> cache=new java.util.HashMap<>();
    public static Object r(UAVKey key) {
        cachedReads++; field=key.info.name; subIndex=key.subIndex;
        if(throwCache) throw new IllegalStateException("PRIVATE cache detail");
        return cache.containsKey(field)?cache.get(field):value;
    }
    public static void t(UAVKey key,IGetCallback callback) {
        field=key.info.name;
        subIndex=key.subIndex;
        reads.add(field);
        if(throwGet) throw new IllegalStateException("PRIVATE get detail");
        if(hold) { pending=callback; pendingKey=key; return; }
        if(error!=0) callback.a(key,error,"PRIVATE SDK DETAIL"); else callback.b(key,cache.containsKey(field)?cache.get(field):value);
        if(throwAfterCallback) throw new IllegalStateException("PRIVATE late get detail");
    }
    public static void x(UAVKey key,Object value,ISetCallback callback) {
        field=key.info.name; written=value; writes++;
        subIndex=key.subIndex;
        if(throwSet) throw new IllegalStateException("PRIVATE set detail");
        if(holdSet) { pendingSet=callback; pendingSetKey=key; return; }
        cache.put(field,value);
        if(error!=0) callback.a(key,error,"PRIVATE SDK DETAIL"); else callback.b(key);
        if(throwAfterCallback) throw new IllegalStateException("PRIVATE late set detail");
    }
    public static void reset() {
        value=null; written=null; field=null; error=0; writes=0; cachedReads=0;
        hold=false; holdSet=false; pending=null; pendingKey=null; pendingSet=null; pendingSetKey=null;
        throwCache=false; throwGet=false; throwSet=false; throwAfterCallback=false;
        reads.clear(); cache.clear();
    }
}
