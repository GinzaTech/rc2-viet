package local.rc2.hud;

import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Timer;
import java.util.TimerTask;

/** SDK/Midware adapter for the pinned forearm parameter, never a raw socket.
 * The front mask is the stock native LEDsSettings encoder's 0x21; all other
 * UINT8 bits are retained. Only the consistent front layout is enabled.
 */
final class NativeForearmLed {
    private final ClassLoader loader;
    private final ForearmLedJob job;
    private final ForearmLedJob rearJob;
    private final ForearmLedJob allJob;
    NativeForearmLed(ClassLoader loader,NativeAircraft aircraft,MutationFence fence) {
        this.loader=loader;
        ForearmLedJob.Port port=new ForearmLedJob.Port() {
            public GroundGate snapshot() { return aircraft.snapshot(); }
            public void ground(LedJob.Reply<GroundGate> reply) { aircraft.readGround(reply); }
            public void read(LedJob.Reply<Integer> reply) { readRaw(loader,reply); }
            public void write(int raw,ForearmLedJob.WriteReply reply) { writeRaw(loader,raw,reply); }
        };
        LedJob.Scheduler timerFactory=(task,delay)->{
            Timer timer=new Timer("RC2-ForearmLedDeadline",true);
            timer.schedule(new TimerTask() { public void run() { task.run(); } },delay);
            return timer::cancel;
        };
        job=new ForearmLedJob(port,timerFactory,fence);
        rearJob=new ForearmLedJob(port,timerFactory,fence,6);
        allJob=new ForearmLedJob(port,timerFactory,fence,39);
    }
    boolean request(boolean on,LedJob.Result result) { return job.request(on,result); }
    boolean toggleFront(LedJob.Result result) { return job.toggle(result); }
    boolean toggleRear(LedJob.Result result) { return rearJob.toggle(result); }
    boolean requestRear(boolean on,LedJob.Result result) { return rearJob.request(on,result); }
    boolean requestAll(boolean on,LedJob.Result result) { return allJob.request(on,result); }
    void close() { job.close(); rearJob.close(); allJob.close(); }
    void inspect(LedJob.Reply<LedJob.Lights> reply) {
        readRaw(loader,new LedJob.Reply<Integer>() {
            public boolean active() { return reply.active(); }
            public void success(Integer value) {
                if(!ForearmLedJob.layout(value)) { reply.failure("Layout LED chưa được kiểm chứng; không gửi lệnh."); return; }
                reply.success(new LedJob.Lights((value&1)!=0,(value&4)!=0,(value&2)!=0,(value&16)!=0));
            }
            public void failure(String message) { reply.failure(message); }
        });
    }
    private static void readRaw(ClassLoader loader,LedJob.Reply<Integer> reply) {
        ForearmParamProbe probe=new ForearmParamProbe(loader);
        probe.inspect(new ForearmParamProbe.Reply() {
            public boolean active() { return reply.active(); }
            public void finished(ForearmParamProbe.Result result) {
                probe.close();
                android.util.Log.i("RC2Hud",result.metadata());
                if(result.status==ForearmParamProbe.Status.OK && result.responseByte0==0
                        && result.rawValue>=0 && result.rawValue<=255) reply.success(result.rawValue);
                else reply.failure("Không đọc được tham số LED ("+result.status.name()+").");
            }
        });
    }
    static void writeRaw(ClassLoader loader,int value,ForearmLedJob.WriteReply reply) {
        if(!reply.active()) return;
        if(value<0 || value>255) { reply.failure("Giá trị LED ngoài UINT8."); return; }
        try {
            Class<?> model=Class.forName("uav.midware.data.model.P3.DataFlycSetParams",false,loader);
            Class<?> callback=Class.forName("uav.midware.interfaces.UAVDataCallBack",false,loader);
            Class<?> ccode=Class.forName("uav.midware.data.config.P3.Ccode",false,loader);
            Method set=model.getMethod("setInfo",String.class,Number.class);
            Method start=model.getMethod("start",callback);
            Method code=ccode.getMethod("c");
            if(set.getReturnType()!=model || start.getReturnType()!=void.class || code.getReturnType()!=int.class
                    || !callback.isInterface() || callback.getMethod("onSuccess",Object.class).getReturnType()!=void.class
                    || callback.getMethod("onFailure",ccode).getReturnType()!=void.class)
                throw new NoSuchMethodException("Pinned forearm SET signatures required");
            Object request=model.getConstructor().newInstance();
            if(set.invoke(request,ForearmParamProbe.NAME,Integer.valueOf(value))!=request)
                throw new IllegalStateException("SET model identity");
            java.util.concurrent.atomic.AtomicBoolean answered=new java.util.concurrent.atomic.AtomicBoolean();
            Object target=Proxy.newProxyInstance(callback.getClassLoader(),new Class<?>[]{callback},(self,method,args)->{
                if(method.getDeclaringClass()==Object.class) return objectMethod(self,method,args);
                boolean success="onSuccess".equals(method.getName()) && args!=null && args.length==1 && args[0]==request;
                boolean failure="onFailure".equals(method.getName()) && args!=null && args.length==1 && ccode.isInstance(args[0]);
                if(!success && !failure) { android.util.Log.i("RC2Hud","forearm_set ignored malformed callback"); return null; }
                if(!answered.compareAndSet(false,true)) return null;
                if(success) {
                    android.util.Log.i("RC2Hud","forearm_set acknowledged target="+value);
                    reply.success(true);
                } else {
                    String error="unknown";
                    if("onFailure".equals(method.getName()) && args!=null && args.length==1 && ccode.isInstance(args[0]))
                        error=String.valueOf(code.invoke(args[0]));
                    android.util.Log.i("RC2Hud","forearm_set failed target="+value+" code="+error);
                    reply.failure("Máy bay từ chối thay đổi LED (mã "+error+").");
                }
                return null;
            });
            if(!reply.active()) return;
            reply.submit(()->{
                android.util.Log.i("RC2Hud","forearm_set dispatch target="+value);
                start.invoke(request,target);
            });
        } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
            reply.failure("Phiên bản này chưa hỗ trợ thay đổi LED.");
        }
    }
    private static Object objectMethod(Object self,Method method,Object[] args) {
        if("hashCode".equals(method.getName())) return System.identityHashCode(self);
        if("equals".equals(method.getName())) return args!=null && args.length==1 && self==args[0];
        return "RC2ForearmSetCallback";
    }
}
