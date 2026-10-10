package local.rc2.hud;

import java.io.IOException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Stock SDK ForceFcc plus a fresh SDR readback. No raw port/profile or invented CE value. */
final class SdkRadioSender implements NativeRadio.Sender {
    static final class Factory implements NativeRadio.Factory {
        private final ClassLoader loader;
        private final java.util.function.Supplier<String> aircraftIdentity;
        private Integer original;
        private String owner;
        Factory(ClassLoader loader) {
            this(loader,()->{
                try {
                    Object value=new FlySdk(loader).cached("c"); // stock FlightController SerialNumber
                    if(!(value instanceof String) || !((String)value).matches("[A-Za-z0-9]{6,32}")) return null;
                    byte[] digest=java.security.MessageDigest.getInstance("SHA-256")
                        .digest(((String)value).getBytes(java.nio.charset.StandardCharsets.US_ASCII));
                    StringBuilder result=new StringBuilder();
                    for(byte item:digest) result.append(String.format(java.util.Locale.ROOT,"%02x",item&255));
                    return result.toString();
                } catch(ReflectiveOperationException | java.security.NoSuchAlgorithmException | RuntimeException | LinkageError error) { return null; }
            });
        }
        Factory(ClassLoader loader,java.util.function.Supplier<String> aircraftIdentity) { this.loader=loader; this.aircraftIdentity=aircraftIdentity; }
        public NativeRadio.Sender create() { return new SdkRadioSender(loader,this); }
        String identity() { return aircraftIdentity.get(); }
        synchronized void remember(String identity,int value) {
            if(identity==null) return;
            if(!identity.equals(owner)) { owner=identity;original=null; }
            if(original==null && value!=2) original=value;
        }
        synchronized Integer original(String identity) { return identity!=null && identity.equals(owner)?original:null; }
    }
    private final ClassLoader loader;
    private final Factory factory;
    private volatile boolean closed,verified;
    private volatile String message="Chưa xác nhận được cấu hình radio.";
    private volatile Runnable reconciled=()->{};
    private volatile SdrRadioProbe initial;
    private final Object submissionLock=new Object();
    SdkRadioSender(ClassLoader loader,Factory factory) { this.loader=loader; this.factory=factory; }
    public void onReconciled(Runnable callback) { reconciled=callback; }
    public boolean verified() { return verified; }
    public String userMessage() { return message; }
    public void close() {
        closed=true;
        synchronized(submissionLock) { SdrRadioProbe probe=initial; if(probe!=null)probe.close(); }
    }
    public void send(boolean fcc,RadioTransport.Guard guard) throws IOException {
        require(guard);
        CountDownLatch read=new CountDownLatch(1);
        SdrRadioProbe.Result[] before={null};
        initial=new SdrRadioProbe(loader);
        initial.inspect(0xffff0048,result->{before[0]=result; read.countDown();});
        await(read,guard); initial.close(); initial=null;
        if(!byteValue(before[0])) {
            message="Không đọc được cấu hình radio từ SDK; chưa gửi lệnh.";
            throw new IOException("SDK radio baseline unavailable");
        }
        String identity=factory.identity();
        if(fcc) factory.remember(identity,before[0].value);
        Integer target=fcc?Integer.valueOf(2):factory.original(identity);
        if(target==null) {
            message="Chưa có giá trị radio ban đầu của phiên này; không đoán giá trị CE.";
            throw new IOException("Original radio value unavailable");
        }
        if(before[0].value.equals(target)) {
            verified=true; message=fcc?"Cấu hình Force FCC đã có giá trị 2.":"Cấu hình radio ban đầu đã được giữ."; return;
        }
        require(guard);
        CountDownLatch done=new CountDownLatch(1);
        AtomicBoolean terminal=new AtomicBoolean();
        try {
            Class<?> model=type("uav.midware.data.model.P3.DataOsdSetSdrAssitantWrite");
            Class<?> callback=type("uav.midware.interfaces.UAVDataCallBack");
            Class<?> ccode=type("uav.midware.data.config.P3.Ccode");
            Method start=model.getMethod("start",callback);
            if(start.getReturnType()!=void.class || !callback.isInterface()
                    || callback.getMethod("onSuccess",Object.class).getReturnType()!=void.class
                    || callback.getMethod("onFailure",ccode).getReturnType()!=void.class)
                throw new NoSuchMethodException("Pinned SDR SET callbacks required");
            Object request=model.getConstructor().newInstance();
            if(fcc) configure(model,request,"setForceFcc",null,null);
            else {
                String readModel="uav.midware.data.model.P3.DataOsdSetSdrAssitantRead";
                configure(model,request,"setSdrDeviceType",type(readModel+"$SdrDeviceType"),constant(readModel+"$SdrDeviceType","Sky",0));
                configure(model,request,"setSdrCpuType",type(readModel+"$SdrCpuType"),constant(readModel+"$SdrCpuType","CP_A7",0));
                configure(model,request,"setSdrDataType",type(readModel+"$SdrDataType"),constant(readModel+"$SdrDataType","Byte_Data",2));
                configure(model,request,"setAddress",int.class,0xffff0048);
                configure(model,request,"setWriteValue",int.class,target);
            }
            Object proxy=Proxy.newProxyInstance(callback.getClassLoader(),new Class<?>[]{callback},(self,method,args)->{
                if(method.getDeclaringClass()==Object.class) return objectMethod(self,method,args);
                boolean ack="onSuccess".equals(method.getName()) && args!=null && args.length==1 && args[0]==request;
                boolean failure="onFailure".equals(method.getName()) && args!=null && args.length==1 && ccode.isInstance(args[0]);
                if(!ack && !failure) { System.err.println("RC2-Radio ignored malformed SDK callback");return null; }
                if(!terminal.compareAndSet(false,true)) return null;
                System.err.println("RC2-Radio sdk_set terminal ack="+ack+" target="+target);
                // A late SDK terminal callback still reconciles the shared fence.
                // Owner/deadline cancellation only suppresses the UI/next SET.
                verify(target,fcc,done);
                return null;
            });
            synchronized(submissionLock) {
                require(guard); guard.dispatched();
                // This is the committed SDK handoff; close cannot return before
                // entry completes. Never cancel between handoff and SDK entry.
                message=fcc?"Đang ghi Force FCC qua SDK…":"Đang khôi phục giá trị radio ban đầu…";
                System.err.println("RC2-Radio sdk_set dispatch target="+target);
                start.invoke(request,proxy);
            }
            await(done,guard);
            if(!verified) throw new IOException("SDK radio readback mismatch");
        } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
            message="Không thực hiện được API radio của phiên bản này; chưa xác nhận hiệu lực.";
            throw new IOException("SDK radio binding or submission failed",error);
        }
    }
    private void verify(int target,boolean fcc,CountDownLatch done) {
        SdrRadioProbe proof=new SdrRadioProbe(loader);
        try { proof.inspect(0xffff0048,result->{
            proof.close(); System.err.println("RC2-Radio "+result.metadata());
            if(byteValue(result) && result.value==target) {
                verified=true;
                message=fcc?"Đã ghi và đọc lại Force FCC. Cần kiểm tra Truyền tín hiệu.":"Đã khôi phục và đọc lại cấu hình radio ban đầu.";
                reconciled.run();
            } else message="Giá trị radio đọc lại chưa khớp; chưa xác nhận hiệu lực.";
            done.countDown();
        }); } catch(RuntimeException | LinkageError error) {
            proof.close(); message="Không đọc lại được radio sau SET."; done.countDown();
        }
    }
    private static boolean byteValue(SdrRadioProbe.Result result) {
        return result!=null && result.status==SdrRadioProbe.Status.OK && result.value!=null
            && result.value>=0 && result.value<=255;
    }
    private void await(CountDownLatch done,RadioTransport.Guard guard) throws IOException {
        while(true) {
            require(guard);
            try { if(done.await(100,TimeUnit.MILLISECONDS)) return; }
            catch(InterruptedException error) { Thread.currentThread().interrupt(); throw new IOException("SDK radio cancelled",error); }
        }
    }
    private void require(RadioTransport.Guard guard) throws IOException {
        if(closed || Thread.currentThread().isInterrupted() || !guard.allowed()) throw new IOException("SDK radio inactive or unsafe");
    }
    private Class<?> type(String name) throws ClassNotFoundException { return Class.forName(name,false,loader); }
    private Object constant(String name,String field,int expected) throws ReflectiveOperationException {
        Class<?> kind=type(name); Object value=kind.getField(field).get(null);
        if(!kind.isEnum() || !Integer.valueOf(expected).equals(kind.getMethod("value").invoke(value)))
            throw new NoSuchMethodException("SDR enum drift");
        return value;
    }
    private static void configure(Class<?> model,Object request,String name,Class<?> arg,Object value) throws ReflectiveOperationException {
        Method method=arg==null?model.getMethod(name):model.getMethod(name,arg);
        if(method.getReturnType()!=model || (arg==null?method.invoke(request):method.invoke(request,value))!=request)
            throw new NoSuchMethodException("SDR configuration signature drift");
    }
    private static Object objectMethod(Object self,Method method,Object[] args) {
        if("hashCode".equals(method.getName())) return System.identityHashCode(self);
        if("equals".equals(method.getName())) return args!=null && args.length==1 && self==args[0];
        return "RC2SdrSetCallback";
    }
}
