package local.rc2.hud;

import uav.midware.data.config.P3.Ccode;
import uav.midware.data.manager.P3.UAVFlycParamInfoManager;
import uav.midware.data.model.P3.DataFlycGetParamInfo.TypeId;
import uav.midware.data.model.P3.DataFlycGetParams;
import uav.midware.data.params.P3.ParamInfo;

public final class ForearmParamProbeTest {
    private static void check(boolean ok,String reason) { if(!ok) throw new AssertionError(reason); }
    private static byte[] frame(int header,int value) {
        return new byte[]{(byte)header,(byte)0xa2,0x59,(byte)0xce,(byte)0xed,(byte)value};
    }
    private static final class Clock implements ForearmParamProbe.Scheduler {
        Runnable task;
        int cancellations;
        boolean fail, immediate;
        public ForearmParamProbe.Cancel schedule(Runnable task,long delay) {
            check(delay==6000,"bounded 6 second deadline");
            if(fail) throw new IllegalStateException("PRIVATE SDK DETAIL");
            this.task=task;
            if(immediate) task.run();
            return ()->cancellations++;
        }
        void fire() { task.run(); }
    }
    private static final class Reply implements ForearmParamProbe.Reply {
        ForearmParamProbe.Result result;
        int calls;
        boolean live=true;
        public boolean active() { return live; }
        public void finished(ForearmParamProbe.Result result) { this.result=result; calls++; }
    }
    private static void reset() {
        UAVFlycParamInfoManager.info=new ParamInfo(); UAVFlycParamInfoManager.newProtocol=true;
        DataFlycGetParams.last=null; DataFlycGetParams.starts=0; DataFlycGetParams.singletonCalls=0;
        DataFlycGetParams.throwStart=false; DataFlycGetParams.throwConstruct=false;
        DataFlycGetParams.throwSet=false; DataFlycGetParams.immediate=null;
        DataFlycGetParams.foreignConfigured=false; Ccode.throwCode=false;
    }
    private static ForearmParamProbe probe(Clock clock) {
        return new ForearmParamProbe(ForearmParamProbeTest.class.getClassLoader(),clock);
    }
    private static void status(Reply reply,String expected) {
        check(reply.calls==1 && reply.result.status.name().equals(expected),"expected "+expected);
        check(!reply.result.metadata().contains("PRIVATE"),"metadata contains only safe fields");
    }
    private static void validAndMalformedResponses() {
        for(int value:new int[]{0,1,127,128,239,255}) {
            reset(); Clock clock=new Clock(); ForearmParamProbe p=probe(clock); Reply reply=new Reply();
            check(p.inspect(reply),"GET accepted");
            check(DataFlycGetParams.starts==1 && DataFlycGetParams.singletonCalls==0,"isolated model GET only");
            check(DataFlycGetParams.last.names.length==1 && DataFlycGetParams.last.names[0].equals(ForearmParamProbe.NAME),"exact named GET");
            DataFlycGetParams.last.succeed(frame(7,value)); status(reply,"OK");
            check(reply.result.rawValue==value && reply.result.responseByte0==7,"unsigned raw byte, header is unassigned");
            check(reply.result.responseHash==ForearmParamProbe.HASH && reply.result.responseLength==6,"wire hash and length");
            check(reply.result.metadata().contains("raw_value="+value),"safe raw value log");
            check(clock.cancellations==1,"deadline cancelled");
            DataFlycGetParams.last.pending.onFailure(Ccode.GET_PARAM_FAILED);
            clock.fire(); check(reply.calls==1,"duplicate/late/timeout cannot overwrite success"); p.close();
        }
        for(int length:new int[]{0,1,2,3,4,5,7,8}) {
            reset(); ForearmParamProbe p=probe(new Clock()); Reply reply=new Reply(); p.inspect(reply);
            DataFlycGetParams.last.succeed(new byte[length]); status(reply,"RESPONSE_LENGTH");
            check(reply.result.rawValue==-1 && reply.result.responseLength==length,"no fabricated raw value"); p.close();
        }
        reset(); ForearmParamProbe p=probe(new Clock()); Reply reply=new Reply(); p.inspect(reply);
        byte[] wrong=frame(0,42); wrong[1]=0; DataFlycGetParams.last.succeed(wrong);
        status(reply,"RESPONSE_HASH"); check(reply.result.rawValue==-1,"wrong hash not treated as forearm"); p.close();
        reset(); p=probe(new Clock()); reply=new Reply(); p.inspect(reply);
        DataFlycGetParams.last.succeed(null); status(reply,"RESPONSE_MISSING"); p.close();
    }
    private static void metadataBeforeSend() {
        for(int mode=0;mode<8;mode++) {
            reset(); ParamInfo info=UAVFlycParamInfoManager.info;
            if(mode==0) UAVFlycParamInfoManager.info=null;
            if(mode==1) info.hash=0;
            if(mode==2) info.size=2;
            if(mode==3) info.index=0;
            if(mode==4) info.name="PRIVATE SDK DETAIL";
            if(mode==5) info.type=Byte.class;
            if(mode==6) info.typeId=TypeId.INT08S;
            if(mode==7) UAVFlycParamInfoManager.newProtocol=false;
            ForearmParamProbe p=probe(new Clock()); Reply reply=new Reply(); p.inspect(reply);
            status(reply,mode==0?"METADATA_MISSING":"METADATA_MISMATCH");
            check(DataFlycGetParams.starts==0,"invalid/unloaded metadata must not send a zero/guessed hash"); p.close();
        }
    }
    private static void errorsAndLifecycle() {
        reset(); Clock clock=new Clock(); ForearmParamProbe p=probe(clock); Reply first=new Reply(), busy=new Reply();
        p.inspect(first); check(!p.inspect(busy),"one outstanding GET"); status(busy,"BUSY");
        DataFlycGetParams old=DataFlycGetParams.last;
        old.pending.onFailure(Ccode.GET_PARAM_FAILED); status(first,"SDK_FAILURE");
        check(first.result.errorCode==231 && first.result.rawValue==-1,"exact Midware numeric error");
        Reply next=new Reply(); check(p.inspect(next),"another GET after completion");
        old.succeed(frame(0,1)); check(next.calls==0,"previous callback cannot complete new GET");
        clock.fire(); status(next,"TIMEOUT");
        DataFlycGetParams.last.succeed(frame(0,9)); check(next.calls==1,"late success suppressed");
        Reply cancelled=new Reply(); p.inspect(cancelled); p.close();
        DataFlycGetParams.last.succeed(frame(0,1)); clock.fire();
        check(cancelled.calls==0 && !p.inspect(new Reply()),"closed lifecycle prevents all delivery and new sends");
        reset(); p=probe(new Clock()); Reply inactive=new Reply(); inactive.live=false;
        check(!p.inspect(inactive) && DataFlycGetParams.starts==0,"inactive owner prevents send"); p.close();
        reset(); p=probe(new Clock()); inactive=new Reply(); p.inspect(inactive); inactive.live=false;
        DataFlycGetParams.last.succeed(frame(0,1)); check(inactive.calls==0,"inactive owner suppresses response"); p.close();
        reset(); p=probe(new Clock()); Reply reply=new Reply(); p.inspect(reply);
        DataFlycGetParams.last.pending.onSuccess(new Object()); status(reply,"CALLBACK_MISMATCH"); p.close();
        reset(); p=probe(new Clock()); reply=new Reply(); p.inspect(reply);
        DataFlycGetParams.last.pending.onFailure(null); status(reply,"SDK_FAILURE");
        check(reply.result.errorCode==null,"unknown code remains unknown"); p.close();
        for(int mode=0;mode<4;mode++) {
            reset(); p=probe(new Clock()); reply=new Reply();
            DataFlycGetParams.throwConstruct=mode==0; DataFlycGetParams.throwSet=mode==1;
            DataFlycGetParams.throwStart=mode==2;
            p.inspect(reply);
            if(mode==3) { DataFlycGetParams.last.throwRead=true; DataFlycGetParams.last.succeed(frame(0,1)); }
            status(reply,"SDK_BINDING_ERROR"); p.close();
        }
        reset(); clock=new Clock(); clock.fail=true; p=probe(clock); reply=new Reply(); p.inspect(reply);
        status(reply,"SDK_BINDING_ERROR"); check(DataFlycGetParams.starts==0,"scheduler failure prevents send"); p.close();
        reset(); clock=new Clock(); clock.immediate=true; p=probe(clock); reply=new Reply();
        check(!p.inspect(reply),"expired before send"); status(reply,"TIMEOUT");
        check(DataFlycGetParams.starts==0 && clock.cancellations==1,"immediate deadline cancelled and no send"); p.close();
        reset(); DataFlycGetParams.immediate=frame(0,255); p=probe(new Clock()); reply=new Reply(); p.inspect(reply);
        status(reply,"OK"); p.close();
        reset(); ClassLoader missing=new ClassLoader(null) { };
        p=new ForearmParamProbe(missing,new Clock()); reply=new Reply(); p.inspect(reply);
        status(reply,"SDK_BINDING_ERROR"); p.close();
    }
    private static void boundariesAndCallbackObjects() {
        reset(); ForearmParamProbe p=probe(new Clock()); Reply reply=new Reply(); p.inspect(reply);
        Object callback=DataFlycGetParams.last.pending;
        check(callback.hashCode()==System.identityHashCode(callback),"callback hash identity");
        check(callback.equals(callback) && !callback.equals(new Object()) && !callback.equals(null),"callback equality identity");
        check(callback.toString().equals("RC2ForearmGetCallback"),"callback safe name");
        DataFlycGetParams.last.pending.onSuccess(null); status(reply,"CALLBACK_MISMATCH"); p.close();
        reset(); p=probe(new Clock()); reply=new Reply(); p.inspect(reply); Ccode.throwCode=true;
        DataFlycGetParams.last.pending.onFailure(Ccode.GET_PARAM_FAILED); status(reply,"SDK_FAILURE");
        check(reply.result.errorCode==null,"code reflection failure remains unknown"); p.close();
        reset(); DataFlycGetParams.foreignConfigured=true; p=probe(new Clock()); reply=new Reply(); p.inspect(reply);
        status(reply,"SDK_BINDING_ERROR"); check(DataFlycGetParams.starts==0,"foreign configured model prevents send"); p.close();
        reset(); p=new ForearmParamProbe(ForearmParamProbeTest.class.getClassLoader(),(task,delay)->null);
        reply=new Reply(); p.inspect(reply); status(reply,"SDK_BINDING_ERROR");
        check(DataFlycGetParams.starts==0,"absent cancellation handle prevents send"); p.close();
        reset(); p=new ForearmParamProbe(ForearmParamProbeTest.class.getClassLoader(),(task,delay)->{task.run();return null;});
        reply=new Reply(); check(!p.inspect(reply),"early timeout with absent handle prevents send"); status(reply,"TIMEOUT"); p.close();
        reset(); DataFlycGetParams.immediate=frame(0,128);
        p=new ForearmParamProbe(ForearmParamProbeTest.class.getClassLoader());
        final int[] delivered={0};
        p.inspect(new ForearmParamProbe.Reply() {
            public void finished(ForearmParamProbe.Result result) {
                check(result.status==ForearmParamProbe.Status.OK && result.rawValue==128,"real deadline scheduler, default active owner");
                delivered[0]++;
            }
        });
        check(delivered[0]==1,"default timer scheduler delivers once"); p.close();
        boolean rejected=false;
        try { new ForearmParamProbe(null,new Clock()); } catch(IllegalArgumentException expected) { rejected=true; }
        check(rejected,"null loader rejected"); rejected=false;
        try { new ForearmParamProbe(ForearmParamProbeTest.class.getClassLoader(),null); }
        catch(IllegalArgumentException expected) { rejected=true; }
        check(rejected,"null scheduler rejected"); rejected=false; p=probe(new Clock());
        try { p.inspect(null); } catch(IllegalArgumentException expected) { rejected=true; }
        check(rejected,"null reply rejected"); p.close();
    }
    private static void racingCompletion() throws Exception {
        for(int n=0;n<20;n++) {
            reset(); Clock clock=new Clock(); ForearmParamProbe p=probe(clock); Reply reply=new Reply(); p.inspect(reply);
            DataFlycGetParams model=DataFlycGetParams.last;
            java.util.concurrent.CountDownLatch go=new java.util.concurrent.CountDownLatch(1);
            java.util.concurrent.atomic.AtomicReference<Throwable> failure=new java.util.concurrent.atomic.AtomicReference<>();
            Runnable[] actions={()->model.succeed(frame(0,255)),()->model.pending.onFailure(Ccode.GET_PARAM_FAILED),clock::fire};
            Thread[] threads=new Thread[actions.length];
            for(int i=0;i<actions.length;i++) {
                final Runnable action=actions[i];
                threads[i]=new Thread(()->{
                    try { go.await(); action.run(); } catch(Throwable error) { failure.compareAndSet(null,error); }
                });
                threads[i].start();
            }
            go.countDown();
            for(Thread thread:threads) { thread.join(5000); check(!thread.isAlive(),"completion cannot deadlock"); }
            check(failure.get()==null && reply.calls==1 && clock.cancellations==1,"success/failure/deadline race has one terminal result");
            p.close();
        }
    }
    public static void main(String[] args) throws Exception {
        validAndMalformedResponses(); metadataBeforeSend(); errorsAndLifecycle();
        boundariesAndCallbackObjects(); racingCompletion();
        System.out.println("forearm_param_probe_passed");
    }
}
