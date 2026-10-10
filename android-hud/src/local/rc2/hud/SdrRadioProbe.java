package local.rc2.hud;

import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Timer;
import java.util.TimerTask;

/** Explicit read-only Midware inspection pinned to stock Fly 1.21.8 classes12.dex.
 * Only Sky/CP_A7/Byte_Data at the two existing FreeFCC profile addresses.
 * No write class, singleton, port, register scan, polling or application retry.
 * Invoke inspect off the UI thread: the stock start method may block.
 * Stock transport can retry its GET internally; close suppresses delivery,
 * not an already submitted SDK request. Never infer effective RF mode here.
 */
final class SdrRadioProbe {
    private static final String MODEL="uav.midware.data.model.P3.DataOsdSetSdrAssitantRead";
    interface Reply { void finished(Result result); default boolean active(){return true;} }
    interface Cancel { void cancel(); }
    interface Scheduler { Cancel schedule(Runnable task,long millis); }
    enum Status { OK, BUSY, TIMEOUT, SDK_BINDING_ERROR, CALLBACK_MISMATCH,
        RESPONSE_MISSING, RESPONSE_LENGTH, PARSER_MISMATCH, SDK_FAILURE }
    static final class Result {
        final Status status;
        final int address, responseLength, firstByte;
        final Integer value, errorCode;
        Result(Status status,int address,int length,int firstByte,Integer value,Integer code){
            this.status=status; this.address=address; responseLength=length;
            this.firstByte=firstByte; this.value=value; errorCode=code;
        }
        String metadata(){
            return "sdr_get status="+status+" address="+Integer.toHexString(address)
                +" device=Sky cpu=CP_A7 data_type=Byte_Data response_length="+responseLength
                +" first_byte="+firstByte+" value="+(value==null?"unknown":value)
                +" error_code="+(errorCode==null?"unknown":errorCode)+" effective_mode=unknown";
        }
    }
    private static final class Request {
        final int address; final Reply reply;
        Cancel deadline; Object model; Method recData, intValue;
        Request(int address,Reply reply){this.address=address;this.reply=reply;}
    }
    private final ClassLoader loader;
    private final Scheduler scheduler;
    private Request current;
    private boolean closed;
    SdrRadioProbe(ClassLoader loader){this(loader,SdrRadioProbe::deadline);}
    SdrRadioProbe(ClassLoader loader,Scheduler scheduler){
        if(loader==null || scheduler==null)throw new IllegalArgumentException("Probe dependencies required");
        this.loader=loader;this.scheduler=scheduler;
    }
    private static Cancel deadline(Runnable runnable,long millis){
        Timer timer=new Timer("RC2-SdrReadDeadline",true);
        timer.schedule(new TimerTask(){public void run(){runnable.run();}},millis);
        return timer::cancel;
    }
    boolean inspect(int address,Reply reply){
        if(address!=0xffff0048 && address!=0xffff0063)
            throw new IllegalArgumentException("Address outside read allowlist");
        if(reply==null)throw new IllegalArgumentException("Reply required");
        Request request;
        synchronized(this){
            if(closed || !reply.active())return false;
            if(current!=null){reply.finished(empty(Status.BUSY,address,null));return false;}
            request=new Request(address,reply);current=request;
        }
        try {
            Cancel timeout=scheduler.schedule(()->finish(request,empty(Status.TIMEOUT,address,null)),6000);
            synchronized(this){
                if(!active(request)){if(timeout!=null)timeout.cancel();return false;}
                if(timeout==null)throw new IllegalStateException("Deadline required");
                request.deadline=timeout;
            }
            return submit(request);
        }catch(ReflectiveOperationException | RuntimeException | LinkageError error){
            finish(request,empty(Status.SDK_BINDING_ERROR,address,null));return false;
        }
    }
    private Class<?> type(String name)throws ClassNotFoundException{
        return Class.forName(name,false,loader);
    }
    private Object constant(Class<?> enumClass,String name,int value)throws ReflectiveOperationException{
        Object item=enumClass.getField(name).get(null);
        if(!enumClass.isEnum() || !enumClass.isInstance(item)
            || !Integer.valueOf(value).equals(enumClass.getMethod("value").invoke(item)))
            throw new NoSuchMethodException("Enum contract changed");
        return item;
    }
    private boolean submit(Request request)throws ReflectiveOperationException{
        Class<?> model=type(MODEL);
        Class<?> cpu=type(MODEL+"$SdrCpuType"),data=type(MODEL+"$SdrDataType"),device=type(MODEL+"$SdrDeviceType");
        Class<?> callback=type("uav.midware.interfaces.UAVDataCallBack"),ccode=type("uav.midware.data.config.P3.Ccode");
        Object cpuValue=constant(cpu,"CP_A7",0),dataValue=constant(data,"Byte_Data",2),deviceValue=constant(device,"Sky",0);
        Method start=model.getMethod("start",callback),rec=model.getMethod("getRecData"),integer=model.getMethod("getIntValue");
        Method code=ccode.getMethod("c");
        if(start.getReturnType()!=void.class || rec.getReturnType()!=byte[].class
            || integer.getReturnType()!=int.class || code.getReturnType()!=int.class || !callback.isInterface()
            || callback.getMethod("onSuccess",Object.class).getReturnType()!=void.class
            || callback.getMethod("onFailure",ccode).getReturnType()!=void.class)
            throw new NoSuchMethodException("Read contract changed");
        Object instance=model.getConstructor().newInstance();
        configure(model,instance,"setSdrCpuType",cpu,cpuValue);
        configure(model,instance,"setSdrDataType",data,dataValue);
        configure(model,instance,"setSdrDeviceType",device,deviceValue);
        configure(model,instance,"setAddress",int.class,request.address);
        synchronized(this){
            if(!active(request))return false;
            request.model=instance;request.recData=rec;request.intValue=integer;
        }
        Object proxy=Proxy.newProxyInstance(callback.getClassLoader(),new Class<?>[]{callback},(self,method,args)->{
            if(method.getDeclaringClass()==Object.class){
                if("hashCode".equals(method.getName()))return System.identityHashCode(self);
                if("equals".equals(method.getName()))return args!=null && args.length==1 && self==args[0];
                return "RC2SdrReadCallback";
            }
            receive(request,method.getName(),args,ccode,code);return null;
        });
        synchronized(this){if(!active(request))return false;}
        start.invoke(instance,proxy);return true;
    }
    private static void configure(Class<?> type,Object model,String name,Class<?> arg,Object value)
            throws ReflectiveOperationException{
        Method method=type.getMethod(name,arg);
        if(method.getReturnType()!=type || method.invoke(model,value)!=model)
            throw new NoSuchMethodException("Read setter identity changed");
    }
    private synchronized void receive(Request request,String name,Object[] args,Class<?> ccode,Method code){
        if(!active(request))return;
        try{
            if("onFailure".equals(name)){
                Integer error=args!=null && args.length==1 && ccode.isInstance(args[0])?(Integer)code.invoke(args[0]):null;
                finish(request,empty(Status.SDK_FAILURE,request.address,error));
            }else if("onSuccess".equals(name)){
                if(args==null || args.length!=1 || args[0]!=request.model){
                    finish(request,empty(Status.CALLBACK_MISMATCH,request.address,null));return;
                }
                byte[] raw=(byte[])request.recData.invoke(request.model);
                if(raw==null){finish(request,empty(Status.RESPONSE_MISSING,request.address,null));return;}
                byte[] bytes=raw.clone(); int first=bytes.length==0?-1:bytes[0]&255;
                // Byte_Data can return one byte. Stock BytesUtil.O clamps its requested
                // four-byte length to available bytes. Accept only UINT8 or the full
                // integer representation; retain length to distinguish firmware formats.
                if(bytes.length!=1 && bytes.length!=4){finish(request,new Result(Status.RESPONSE_LENGTH,request.address,bytes.length,first,null,null));return;}
                int value=0;
                for(int i=bytes.length-1;i>=0;i--)value=(value<<8)|(bytes[i]&255);
                Integer parsed=(Integer)request.intValue.invoke(request.model);
                finish(request,new Result(parsed.intValue()==value?Status.OK:Status.PARSER_MISMATCH,
                    request.address,bytes.length,first,parsed.intValue()==value?value:null,null));
            }
        }catch(ReflectiveOperationException | RuntimeException | LinkageError error){
            finish(request,empty(Status.SDK_BINDING_ERROR,request.address,null));
        }
    }
    private static Result empty(Status status,int address,Integer error){return new Result(status,address,-1,-1,null,error);}
    private boolean active(Request request){return !closed && current==request;}
    private synchronized void finish(Request request,Result result){
        if(!active(request))return;
        current=null;if(request.deadline!=null)request.deadline.cancel();
        if(request.reply.active())request.reply.finished(result);
    }
    synchronized void close(){
        closed=true;
        if(current!=null && current.deadline!=null)current.deadline.cancel();
        current=null;
    }
}
