package local.rc2.hud;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicBoolean;

/** Basic stock SDK contract: semantic keys, exact ABI, no permissive fallback.
 * Stock 1.21.8 supplies the ABI evidence; renamed fixtures are not 1.21.10 proof.
 */
final class FlySdk {
    private static final String LED="LEDsSettings";
    private final ClassLoader loader;
    FlySdk(ClassLoader loader) { this.loader=loader; }
    private Class<?> type(String name) throws ClassNotFoundException { return Class.forName(name,false,loader); }
    private Class<?> keyType() throws ClassNotFoundException { return type("uav.sdk.keyvalue.key.UAVKey"); }
    private static Method exact(Class<?> owner,String name,Class<?> result,boolean isStatic,Class<?>... args)
        throws ReflectiveOperationException {
        Method method=owner.getMethod(name,args);
        if(method.getReturnType()!=result || Modifier.isStatic(method.getModifiers())!=isStatic
            || !Modifier.isPublic(method.getModifiers())) throw new NoSuchMethodException("Basic SDK signature mismatch");
        return method;
    }
    private static String identifier(String name) throws NoSuchFieldException {
        if(name==null) throw new NoSuchFieldException("Basic key required");
        switch(name) {
            case "he": case "Connection": return "Connection";
            case "J": case "AreMotorsOn": return "AreMotorsOn";
            case "K": case "IsFlying": return "IsFlying";
            case "U2": case "LEDsSettings": return LED;
            case "c": case "SerialNumber": return "SerialNumber";
            default: throw new NoSuchFieldException("Unknown Basic key");
        }
    }
    private Object descriptor(String identifier,Class<?> infoType) throws ReflectiveOperationException {
        Method name=exact(infoType,"e",String.class,false);
        Method get=exact(infoType,"i",boolean.class,false),set=exact(infoType,"l",boolean.class,false);
        Method listen=exact(infoType,"j",boolean.class,false),action=exact(infoType,"k",boolean.class,false);
        Method event=exact(infoType,"m",boolean.class,false);
        Object selected=null;
        for(Field field:type("uav.sdk.keyvalue.key.UAVFlightControllerKey").getFields()) {
            if(!Modifier.isPublic(field.getModifiers()) || !Modifier.isStatic(field.getModifiers())
                || !infoType.isAssignableFrom(field.getType())) continue;
            Object info=field.get(null);
            if(info==null || !identifier.equals(name.invoke(info))) continue;
            if(selected!=null) throw new NoSuchFieldException("Ambiguous Basic key");
            selected=info;
        }
        if(selected==null) throw new NoSuchFieldException("Missing Basic key");
        // No action/event fallback. LEDs must be readable AND settable before any access.
        if(!Boolean.TRUE.equals(get.invoke(selected)) || Boolean.TRUE.equals(action.invoke(selected))
            || Boolean.TRUE.equals(event.invoke(selected))
            || (LED.equals(identifier) && !Boolean.TRUE.equals(set.invoke(selected))))
            throw new NoSuchFieldException("Basic key permissions mismatch");
        // Validate the remaining metadata accessors, without requiring a listener or writing a flag.
        set.invoke(selected); listen.invoke(selected);
        return selected;
    }
    private Object key(String name) throws ReflectiveOperationException {
        String identifier=identifier(name);
        Class<?> infoType=type("uav.sdk.keyvalue.key.UAVKeyInfoBase"),keyType=keyType();
        Object info=descriptor(identifier,infoType),key;
        // Preserve FlyModel's LED tuple, and the existing ground wildcard subIndex 65534.
        if(LED.equals(identifier)) key=exact(keyType,"l",keyType,true,infoType,int.class,int.class,int.class)
            .invoke(null,info,0,0,0);
        else key=exact(keyType,"i",keyType,true,infoType).invoke(null,info);
        if(!keyType.isInstance(key)) throw new ReflectiveOperationException("Missing Basic SDK key");
        return key;
    }
    Object cached(String name) throws ReflectiveOperationException {
        Method cached=exact(type("uav.sdk.keyvalue.UAVKeyManager"),"r",Object.class,true,keyType());
        return cached.invoke(null,key(name));
    }
    void get(String name,LedJob.Reply<Object> reply) {
        Once<Object> answer=new Once<>(reply);
        if(!answer.active()) return;
        try {
            Class<?> callbackType=callbackType(false);
            Method get=exact(type("uav.sdk.keyvalue.UAVKeyManager"),"t",void.class,true,keyType(),callbackType);
            Object key=key(name),callback=callback(callbackType,key,false,answer);
            if(answer.active()) get.invoke(null,key,callback);
        } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
            answer.failure("Không đọc được trạng thái từ SDK của DJI Fly.");
        }
    }
    void setLights(LedJob.Lights lights,LedJob.Reply<Boolean> reply) {
        Once<Boolean> answer=new Once<>(reply);
        if(!answer.active()) return;
        try {
            if(lights==null) throw new IllegalArgumentException("Four LED flags required");
            Class<?> callbackType=callbackType(true),settings=lightType();
            Method set=exact(type("uav.sdk.keyvalue.UAVKeyManager"),"x",void.class,true,keyType(),Object.class,callbackType);
            Object key=key(LED);
            Object value=settings.getConstructor(Boolean.class,Boolean.class,Boolean.class,Boolean.class)
                .newInstance(lights.front,lights.status,lights.rear,lights.navigation);
            LedJob.Reply<Object> adapter=new LedJob.Reply<Object>() {
                public boolean active() { return answer.active(); }
                public void success(Object ignored) { answer.success(true); }
                public void failure(String message) { answer.failure(message); }
            };
            Object callback=callback(callbackType,key,true,new Once<>(adapter));
            if(answer.active()) set.invoke(null,key,value,callback);
        } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
            answer.failure("SDK LED chưa hỗ trợ trên phiên bản/máy bay này.");
        }
    }
    private Class<?> lightType() throws ReflectiveOperationException {
        Class<?> settings=type("uav.sdk.keyvalue.value.flightcontroller.LEDsSettings");
        settings.getConstructor(Boolean.class,Boolean.class,Boolean.class,Boolean.class);
        for(String getter:new String[]{"getFrontLEDsOn","getStatusIndicatorOn","getRearLEDsOn","getNavigationEnabled"})
            exact(settings,getter,Boolean.class,false);
        return settings;
    }
    void getLights(LedJob.Reply<LedJob.Lights> reply) {
        Once<LedJob.Lights> answer=new Once<>(reply);
        if(!answer.active()) return;
        try {
            Class<?> settings=lightType();
            get(LED,new LedJob.Reply<Object>() {
                public boolean active() { return answer.active(); }
                public void failure(String message) { answer.failure("Không đọc được LED phía trước. "+message); }
                public void success(Object value) {
                    try {
                        if(!settings.isInstance(value)) throw new IllegalStateException("Unexpected LED type");
                        answer.success(new LedJob.Lights(flag(settings,value,"getFrontLEDsOn"),
                            flag(settings,value,"getStatusIndicatorOn"),flag(settings,value,"getRearLEDsOn"),
                            flag(settings,value,"getNavigationEnabled")));
                    } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
                        answer.failure("Không xác định đủ bốn trạng thái LED; không gửi lệnh.");
                    }
                }
            });
        } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
            answer.failure("Không xác định đủ bốn trạng thái LED; không gửi lệnh.");
        }
    }
    private boolean flag(Class<?> type,Object value,String name) throws ReflectiveOperationException {
        Object result=exact(type,name,Boolean.class,false).invoke(value);
        if(!(result instanceof Boolean)) throw new IllegalStateException("Unknown LED field");
        return (Boolean)result;
    }
    private Class<?> callbackType(boolean set) throws ReflectiveOperationException {
        Class<?> callback=type("uav.sdk.keyvalue.callback."+(set?"ISetCallback":"IGetCallback"));
        if(!callback.isInterface() || !Modifier.isPublic(callback.getModifiers()))
            throw new NoSuchMethodException("Basic SDK callback interface required");
        Method failure=exact(callback,"a",void.class,false,keyType(),int.class,String.class);
        Method success=set?exact(callback,"b",void.class,false,keyType())
            :exact(callback,"b",void.class,false,keyType(),Object.class);
        if(callback.getMethods().length!=2 || !Modifier.isAbstract(failure.getModifiers())
            || !Modifier.isAbstract(success.getModifiers())) throw new NoSuchMethodException("Basic SDK callback mismatch");
        return callback;
    }
    private Object callback(Class<?> callbackType,Object key,boolean set,Once<Object> reply)
        throws ReflectiveOperationException {
        Class<?> keyType=keyType();
        Method failure=callbackType.getMethod("a",keyType,int.class,String.class);
        Method success=set?callbackType.getMethod("b",keyType):callbackType.getMethod("b",keyType,Object.class);
        return Proxy.newProxyInstance(callbackType.getClassLoader(),new Class<?>[]{callbackType},(proxy,method,args)->{
            if(method.getDeclaringClass()==Object.class) return objectMethod(proxy,method,args);
            if(!reply.active()) return null;
            try {
                int count=method.equals(failure)?3:set?1:2;
                if(args==null || args.length!=count || !keyType.isInstance(args[0]) || !key.equals(args[0]))
                    reply.failure("Phản hồi SDK không hợp lệ.");
                else if(method.equals(failure)) reply.failure("SDK từ chối yêu cầu (mã "+args[1]+").");
                else if(method.equals(success)) reply.success(set?null:args[1]);
                else reply.failure("Phản hồi SDK không hợp lệ.");
            } catch(RuntimeException | LinkageError error) { reply.failure("Phản hồi SDK không hợp lệ."); }
            return null;
        });
    }
    private static final class Once<T> implements LedJob.Reply<T> {
        private final LedJob.Reply<T> reply;
        private final AtomicBoolean answered=new AtomicBoolean();
        Once(LedJob.Reply<T> reply) { this.reply=reply; }
        public boolean active() { return !answered.get() && reply.active(); }
        public void success(T value) { if(active() && answered.compareAndSet(false,true)) reply.success(value); }
        public void failure(String message) { if(active() && answered.compareAndSet(false,true)) reply.failure(message); }
    }
    private static Object objectMethod(Object proxy,Method method,Object[] args) {
        if(method.getName().equals("hashCode")) return System.identityHashCode(proxy);
        if(method.getName().equals("equals")) return args!=null && args.length==1 && proxy==args[0];
        return "RC2SdkCallback";
    }
}
