package local.rc2.hud;

import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

/** Exact SDK bridge for stock Fly 1.21.8. Unknown signatures/values are rejected. */
final class FlySdk {
    private final ClassLoader loader;
    FlySdk(ClassLoader loader) { this.loader=loader; }
    private Class<?> type(String name) throws ClassNotFoundException { return Class.forName(name,false,loader); }
    private Class<?> keyType() throws ClassNotFoundException { return type("uav.sdk.keyvalue.key.UAVKey"); }
    private Object key(String field) throws ReflectiveOperationException {
        Object info=type("uav.sdk.keyvalue.key.UAVFlightControllerKey").getField(field).get(null);
        // LED's FlyModel infra key uses (product=0, componentIndex=0, subComponentIndex=0).
        // Keep the existing wildcard factory for the flight-state keys already verified live.
        if("U2".equals(field)) return keyType().getMethod("l",type("uav.sdk.keyvalue.key.UAVKeyInfoBase"),
            int.class,int.class,int.class).invoke(null,info,0,0,0);
        return keyType().getMethod("i",type("uav.sdk.keyvalue.key.UAVKeyInfoBase")).invoke(null,info);
    }
    Object cached(String field) throws ReflectiveOperationException {
        return type("uav.sdk.keyvalue.UAVKeyManager").getMethod("r",keyType()).invoke(null,key(field));
    }
    void get(String field,LedJob.Reply<Object> reply) {
        try {
            Class<?> callbackType=type("uav.sdk.keyvalue.callback.IGetCallback");
            type("uav.sdk.keyvalue.UAVKeyManager").getMethod("t",keyType(),callbackType)
                .invoke(null,key(field),callback(callbackType,reply));
        } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
            reply.failure("Không đọc được trạng thái từ SDK của DJI Fly.");
        }
    }
    void setLights(LedJob.Lights lights,LedJob.Reply<Boolean> reply) {
        try {
            Object value=type("uav.sdk.keyvalue.value.flightcontroller.LEDsSettings")
                .getConstructor(Boolean.class,Boolean.class,Boolean.class,Boolean.class)
                .newInstance(lights.front,lights.status,lights.rear,lights.navigation);
            Class<?> callbackType=type("uav.sdk.keyvalue.callback.ISetCallback");
            LedJob.Reply<Object> adapter=new LedJob.Reply<Object>() {
                public void success(Object ignored) { reply.success(true); }
                public void failure(String message) { reply.failure(message); }
            };
            type("uav.sdk.keyvalue.UAVKeyManager").getMethod("x",keyType(),Object.class,callbackType)
                .invoke(null,key("U2"),value,callback(callbackType,adapter));
        } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
            reply.failure("SDK LED chưa hỗ trợ trên phiên bản/máy bay này.");
        }
    }
    void getLights(LedJob.Reply<LedJob.Lights> reply) {
        get("U2",new LedJob.Reply<Object>() {
            public void failure(String message) { reply.failure("Không đọc được LED phía trước. "+message); }
            public void success(Object value) {
                try {
                    Class<?> settings=type("uav.sdk.keyvalue.value.flightcontroller.LEDsSettings");
                    if(!settings.isInstance(value)) throw new IllegalStateException("Unexpected LED type");
                    reply.success(new LedJob.Lights(flag(settings,value,"getFrontLEDsOn"),
                        flag(settings,value,"getStatusIndicatorOn"),flag(settings,value,"getRearLEDsOn"),
                        flag(settings,value,"getNavigationEnabled")));
                } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
                    reply.failure("Không xác định đủ bốn trạng thái LED; không gửi lệnh.");
                }
            }
        });
    }
    private boolean flag(Class<?> type,Object value,String method) throws ReflectiveOperationException {
        Object result=type.getMethod(method).invoke(value);
        if(!(result instanceof Boolean)) throw new IllegalStateException("Unknown LED field");
        return (Boolean)result;
    }
    private Object callback(Class<?> callbackType,LedJob.Reply<Object> reply) {
        return Proxy.newProxyInstance(callbackType.getClassLoader(),new Class<?>[]{callbackType},(proxy,method,args)->{
            if(method.getDeclaringClass()==Object.class) return objectMethod(proxy,method,args);
            if(method.getName().equals("a")) {
                String code=args!=null && args.length>1 && args[1] instanceof Number ? String.valueOf(args[1]):"?";
                reply.failure("SDK từ chối yêu cầu (mã "+code+").");
            } else if(method.getName().equals("b")) {
                if(args==null || args.length<1) reply.failure("Phản hồi SDK không hợp lệ.");
                else reply.success(args.length>1?args[1]:null);
            }
            return null;
        });
    }
    private static Object objectMethod(Object proxy,Method method,Object[] args) {
        if(method.getName().equals("hashCode")) return System.identityHashCode(proxy);
        if(method.getName().equals("equals")) return args!=null && args.length==1 && proxy==args[0];
        return "RC2SdkCallback";
    }
}
