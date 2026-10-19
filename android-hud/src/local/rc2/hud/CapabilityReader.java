package local.rc2.hud;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicBoolean;

/** Exact legacy SDK GET contract. This adapter has no write or action entry point. */
final class CapabilityReader {
    private final ClassLoader loader;
    CapabilityReader(ClassLoader loader){this.loader=loader;}
    private Class<?> type(String name)throws ClassNotFoundException{return Class.forName(name,false,loader);}
    private static Method exact(Class<?> c,String name,Class<?> result,boolean isStatic,Class<?>... args)throws NoSuchMethodException{
        Method m=c.getMethod(name,args);
        if(m.getReturnType()!=result||Modifier.isStatic(m.getModifiers())!=isStatic||!Modifier.isPublic(m.getModifiers()))throw new NoSuchMethodException("ABI mismatch");
        return m;
    }
    void get(String family,String id,LedJob.Reply<Object> reply){
        AtomicBoolean done=new AtomicBoolean();
        try{
            if(!reply.active())return;
            if(!family.matches("FlightController|FlightAssistant|RemoteController|Camera|Gimbal")||!id.matches("[A-Za-z][A-Za-z0-9_]*"))throw new IllegalArgumentException("Unreviewed key");
            Class<?> base=type("uav.sdk.keyvalue.key.UAVKeyInfoBase"),keyType=type("uav.sdk.keyvalue.key.UAVKey");
            Method identifier=exact(base,"e",String.class,false),canGet=exact(base,"i",boolean.class,false);
            Method action=exact(base,"k",boolean.class,false),event=exact(base,"m",boolean.class,false);
            Object selected=null;
            for(Field f:type("uav.sdk.keyvalue.key.UAV"+family+"Key").getFields()){
                if(!Modifier.isStatic(f.getModifiers())||!base.isAssignableFrom(f.getType()))continue;
                Object d=f.get(null);if(d==null||!id.equals(identifier.invoke(d)))continue;
                if(selected!=null)throw new IllegalStateException("Ambiguous descriptor");selected=d;
            }
            if(selected==null)throw new NoSuchFieldException("Missing descriptor");
            if(!Boolean.TRUE.equals(canGet.invoke(selected))||Boolean.TRUE.equals(action.invoke(selected))||Boolean.TRUE.equals(event.invoke(selected)))throw new IllegalStateException("GET unavailable");
            Object key=exact(keyType,"l",keyType,true,base,int.class,int.class,int.class).invoke(null,selected,0,0,0);
            if(key==null||!keyType.isInstance(key))throw new IllegalStateException("Invalid key");
            Class<?> cb=type("uav.sdk.keyvalue.callback.IGetCallback");
            Method success=exact(cb,"b",void.class,false,keyType,Object.class),failure=exact(cb,"a",void.class,false,keyType,int.class,String.class);
            if(!cb.isInterface()||cb.getMethods().length!=2)throw new NoSuchMethodException("Callback mismatch");
            Method get=exact(type("uav.sdk.keyvalue.UAVKeyManager"),"t",void.class,true,keyType,cb);
            Object callback=Proxy.newProxyInstance(cb.getClassLoader(),new Class<?>[]{cb},(self,m,args)->{
                if(m.getDeclaringClass()==Object.class){
                    if(m.getName().equals("hashCode"))return System.identityHashCode(self);
                    if(m.getName().equals("equals"))return args!=null&&args.length==1&&self==args[0];
                    return "RC2CapabilityGET";
                }
                if(!reply.active()||done.get())return null;
                if((!m.equals(success)&&!m.equals(failure))||args==null||args.length!=m.getParameterCount()||!key.equals(args[0])){
                    if(done.compareAndSet(false,true))reply.failure("INVALID_CALLBACK");return null;
                }
                if(done.compareAndSet(false,true)){
                    if(m.equals(failure))reply.failure("SDK_ERROR:"+args[1]);
                    else if(args[1]==null)reply.failure("NO_VALUE");
                    else reply.success(args[1]);
                }
                return null;
            });
            if(reply.active())get.invoke(null,key,callback);
        }catch(ReflectiveOperationException|RuntimeException|LinkageError error){
            if(reply.active()&&done.compareAndSet(false,true))reply.failure("UNAVAILABLE:"+error.getClass().getSimpleName());
        }
    }
}
