package local.rc2.hud;

import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Timer;
import java.util.TimerTask;

/** One in-process Midware GET, pinned to stock Fly 1.21.8 classes12.dex.
 * The parameter is a raw UINT8; no physical LED bit semantics are inferred.
 * Integrator calls inspect explicitly and close when its owner is destroyed.
 * No singleton, cached value, SET, raw transport, polling or application retry.
 */
final class ForearmParamProbe {
    static final String NAME="g_config.misc_cfg.forearm_lamp_ctrl_0";
    static final long HASH=0xedce59a2L;
    private static final String PREFIX="uav.midware.";
    private static final long DEADLINE_MS=6000;

    interface Reply {
        void finished(Result result);
        default boolean active() { return true; }
    }
    interface Cancel { void cancel(); }
    interface Scheduler { Cancel schedule(Runnable task,long delayMillis); }
    enum Status {
        OK, BUSY, TIMEOUT, METADATA_MISSING, METADATA_MISMATCH, SDK_BINDING_ERROR,
        CALLBACK_MISMATCH, RESPONSE_MISSING, RESPONSE_LENGTH, RESPONSE_HASH, SDK_FAILURE
    }
    static final class Result {
        final Status status;
        final String stage;
        final int responseLength,responseByte0,rawValue;
        final long responseHash;
        final Integer errorCode;
        Result(Status status,String stage,int length,int byte0,long hash,int value,Integer errorCode) {
            this.status=status; this.stage=stage; responseLength=length; responseByte0=byte0;
            responseHash=hash; rawValue=value; this.errorCode=errorCode;
        }
        // Only constants and numeric observations. Never stringify SDK objects/exceptions.
        String metadata() {
            return "forearm_get status="+status.name()+" stage="+stage+" expected_hash="+HASH
                +" expected_index=1327 expected_size=1 expected_type_id=0 response_length="+responseLength
                +" response_byte0="+responseByte0+" response_hash="+responseHash
                +" raw_value="+rawValue+" error_code="+(errorCode==null?"unknown":errorCode);
        }
    }
    private static final class Request {
        Reply reply;
        Cancel deadline;
        Object model;
        Method recData;
        String stage="deadline";
        Request(Reply reply) { this.reply=reply; }
    }
    private final ClassLoader loader;
    private final Scheduler scheduler;
    private Request current;
    private boolean closed;

    ForearmParamProbe(ClassLoader loader) { this(loader,ForearmParamProbe::scheduleDeadline); }
    ForearmParamProbe(ClassLoader loader,Scheduler scheduler) {
        if(loader==null || scheduler==null) throw new IllegalArgumentException("Probe dependencies required");
        this.loader=loader; this.scheduler=scheduler;
    }
    private static Cancel scheduleDeadline(Runnable task,long delay) {
        Timer timer=new Timer("RC2-ForearmGetDeadline",true);
        timer.schedule(new TimerTask() { public void run() { task.run(); } },delay);
        return timer::cancel;
    }
    private Class<?> type(String name) throws ClassNotFoundException {
        return Class.forName(PREFIX+name,false,loader);
    }

    /** Returns true when SDK start returns normally; a terminal reply may arrive synchronously.
     * Outcome is delivered exactly once while active.
     * Reply runs on the completing thread; dispatch to the UI thread in the caller if needed.
     */
    synchronized boolean inspect(Reply reply) {
        if(reply==null) throw new IllegalArgumentException("Probe reply required");
        if(closed || !reply.active()) return false;
        if(current!=null) { reply.finished(empty(Status.BUSY,"deadline",null)); return false; }
        Request request=new Request(reply); current=request;
        try {
            Cancel deadline=scheduler.schedule(()->timeout(request),DEADLINE_MS);
            if(current!=request) { if(deadline!=null) deadline.cancel(); return false; }
            if(deadline==null) throw new IllegalStateException("Deadline required");
            request.deadline=deadline;
            request.stage="metadata";
            Status metadata=validateMetadata();
            if(metadata!=Status.OK) { finish(request,empty(metadata,request.stage,null)); return false; }
            bindAndStart(request);
            return true;
        } catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
            finish(request,empty(Status.SDK_BINDING_ERROR,request.stage,null)); return false;
        }
    }
    private Status validateMetadata() throws ReflectiveOperationException {
        Class<?> manager=type("data.manager.P3.UAVFlycParamInfoManager");
        if(!Boolean.TRUE.equals(manager.getMethod("isNew").invoke(null))) return Status.METADATA_MISMATCH;
        Class<?> param=type("data.params.P3.ParamInfo");
        Method read=manager.getMethod("read",String.class);
        if(read.getReturnType()!=param) throw new NoSuchMethodException("Metadata signature");
        Object info=read.invoke(null,NAME);
        if(info==null) return Status.METADATA_MISSING;
        Class<?> typeId=type("data.model.P3.DataFlycGetParamInfo$TypeId");
        Object id=param.getField("typeId").get(info);
        boolean matches=NAME.equals(param.getField("name").get(info))
            && param.getField("hash").getLong(info)==HASH
            && param.getField("index").getInt(info)==1327
            && param.getField("size").getInt(info)==1
            && param.getField("type").get(info)==Integer.class
            && typeId.isInstance(id) && Integer.valueOf(0).equals(typeId.getMethod("value").invoke(id));
        return matches?Status.OK:Status.METADATA_MISMATCH;
    }
    private void bindAndStart(Request request) throws ReflectiveOperationException {
        request.stage="bind";
        Class<?> model=type("data.model.P3.DataFlycGetParams");
        Class<?> callback=type("interfaces.UAVDataCallBack");
        Class<?> ccode=type("data.config.P3.Ccode");
        Method setInfos=model.getMethod("setInfos",String[].class);
        Method start=model.getMethod("start",callback);
        request.recData=model.getMethod("getRecData");
        Method failureCode=ccode.getMethod("c");
        if(setInfos.getReturnType()!=model || start.getReturnType()!=void.class
            || request.recData.getReturnType()!=byte[].class || failureCode.getReturnType()!=int.class
            || !callback.isInterface() || callback.getMethod("onSuccess",Object.class).getReturnType()!=void.class
            || callback.getMethod("onFailure",ccode).getReturnType()!=void.class)
            throw new NoSuchMethodException("GET callback signature");
        request.stage="construct";
        request.model=model.getConstructor().newInstance();
        request.stage="configure";
        if(setInfos.invoke(request.model,(Object)new String[]{NAME})!=request.model)
            throw new IllegalStateException("GET model identity");
        Object proxy=Proxy.newProxyInstance(callback.getClassLoader(),new Class<?>[]{callback},(self,method,args)->{
            if(method.getDeclaringClass()==Object.class) return objectMethod(self,method,args);
            receive(request,method.getName(),args,ccode,failureCode);
            return null;
        });
        request.stage="start";
        start.invoke(request.model,proxy);
    }
    private synchronized void receive(Request request,String name,Object[] args,Class<?> ccode,Method code) {
        if(!active(request)) return;
        request.stage="callback";
        if("onFailure".equals(name)) {
            Integer number=null;
            try { if(args!=null && args.length==1 && ccode.isInstance(args[0])) number=(Integer)code.invoke(args[0]); }
            catch(ReflectiveOperationException | RuntimeException | LinkageError error) { /* Unknown numeric code. */ }
            finish(request,empty(Status.SDK_FAILURE,request.stage,number));
        } else if("onSuccess".equals(name)) {
            if(args==null || args.length!=1 || args[0]!=request.model) {
                finish(request,empty(Status.CALLBACK_MISMATCH,request.stage,null)); return;
            }
            try { finish(request,decode((byte[])request.recData.invoke(request.model))); }
            catch(ReflectiveOperationException | RuntimeException | LinkageError error) {
                finish(request,empty(Status.SDK_BINDING_ERROR,request.stage,null));
            }
        }
    }
    private static Result decode(byte[] bytes) {
        if(bytes==null) return empty(Status.RESPONSE_MISSING,"callback",null);
        // One requested UINT8 has exactly header + hash[4] + value[1]. No trailing records accepted.
        if(bytes.length!=6) return new Result(Status.RESPONSE_LENGTH,"callback",bytes.length,-1,-1,-1,null);
        byte[] snapshot=bytes.clone();
        long hash=0;
        for(int index=0;index<4;index++) hash|=(long)(snapshot[index+1]&0xff)<<(8*index);
        boolean matches=hash==HASH;
        // Offset 0 is skipped by the stock parser; retain it without inventing result semantics.
        return new Result(matches?Status.OK:Status.RESPONSE_HASH,"callback",6,snapshot[0]&0xff,
            hash,matches?snapshot[5]&0xff:-1,null);
    }
    private static Result empty(Status status,String stage,Integer code) {
        return new Result(status,stage,-1,-1,-1,-1,code);
    }
    private boolean active(Request request) { return !closed && current==request; }
    private synchronized void timeout(Request request) { finish(request,empty(Status.TIMEOUT,request.stage,null)); }
    private void finish(Request request,Result result) {
        if(!active(request)) return;
        current=null;
        Reply reply=request.reply;
        release(request);
        if(reply.active()) reply.finished(result);
    }
    private static void release(Request request) {
        if(request.deadline!=null) request.deadline.cancel();
        request.deadline=null; request.reply=null; request.model=null; request.recData=null;
    }
    synchronized void close() {
        closed=true;
        if(current!=null) { release(current); current=null; }
    }
    private static Object objectMethod(Object self,Method method,Object[] args) {
        if("hashCode".equals(method.getName())) return System.identityHashCode(self);
        if("equals".equals(method.getName())) return args!=null && args.length==1 && self==args[0];
        return "RC2ForearmGetCallback";
    }
}
