package local.rc2.hud;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import static local.rc2.hud.ForearmLedJobTest.*;

/** Raw-byte policy and toggle lifecycle regressions; no cached UI state. */
public final class ForearmLedToggleTest {
    static void exhaustive() {
        check(!ForearmLedJob.layout(null),"null layout rejected");
        for(int mask=0;mask<256;mask++) {
            if(mask==33 || mask==6 || mask==39) continue;
            boolean rejected=false;
            try { new ForearmLedJob(new Port(),(task,delay)->()->{},new MutationFence(),mask); }
            catch(IllegalArgumentException expected) { rejected=true; }
            check(rejected,"unapproved constructor mask rejected");
            rejected=false;
            try { ForearmLedJob.updated(200,true,mask); }
            catch(IllegalArgumentException expected) { rejected=true; }
            check(rejected,"unapproved update mask rejected");
        }
        for(int raw=-1;raw<=256;raw++) {
            boolean valid=raw>=0 && raw<=255 && ((raw&33)==0 || (raw&33)==33);
            check(ForearmLedJob.layout(raw)==valid,"exact front layout for "+raw);
            for(int mask:new int[]{33,6,39}) {
                Port port=new Port(); port.raw=raw;
                MutationFence fence=new MutationFence();
                ForearmLedJob job=new ForearmLedJob(port,(task,delay)->()->{},fence,mask);
                int[] completions={0};
                job.toggle((ok,message)->{check(ok==valid,"layout determines success");completions[0]++;});
                check(completions[0]==1 && !fence.pending(),"one terminal result and released reservation");
                if(valid) {
                    int expected=(raw&mask)==0?raw|mask:raw&~mask;
                    check(port.raw==expected && port.writes==1 && port.reads==2,"fresh read, one toggle and matching readback");
                    check((port.raw&~mask)==(raw&~mask),"outside bits preserved");
                } else check(port.writes==0,"invalid raw never written");
                job.close();
            }
        }
    }
    static void sequential() {
        Port port=new Port(); port.raw=200; MutationFence fence=new MutationFence();
        ForearmLedJob front=new ForearmLedJob(port,(task,delay)->()->{},fence);
        ForearmLedJob rear=new ForearmLedJob(port,(task,delay)->()->{},fence,6);
        LedJob.Result result=(ok,message)->check(ok,"toggle verified");
        front.toggle(result); check(port.raw==233,"front on preserves rear off");
        rear.toggle(result); check(port.raw==239,"rear on preserves front on");
        front.toggle(result); check(port.raw==206,"front off preserves rear on");
        rear.toggle(result); check(port.raw==200,"rear off preserves front off");
        // External change after earlier toggles must replace any remembered baseline.
        port.raw=255; front.toggle(result); check(port.raw==222,"fresh external baseline and unrelated bits preserved");
        for(int partial:new int[]{2,4}) {
            port.raw=233|partial; rear.toggle(result); check(port.raw==233,"partial rear turns both off");
            rear.toggle(result); check(port.raw==239,"zero rear turns both on");
        }
        front.close(); rear.close();
    }
    static void guarded() {
        for(GroundGate gate:new GroundGate[]{GroundGate.unknown(),new GroundGate(true,true,false,true),
                new GroundGate(true,true,true,false),new GroundGate(true,false,false,false)}) {
            Fixture initial=new Fixture(); initial.port.gate=gate;
            check(!initial.job.toggle(initial.result) && initial.port.reads==0 && !initial.fence.pending(),"initial unsafe state blocked");
            Fixture beforeWrite=new Fixture(); beforeWrite.port.pauseRead=true;
            beforeWrite.job.toggle(beforeWrite.result); beforeWrite.port.gate=gate; beforeWrite.port.read.success(239);
            check(beforeWrite.port.writes==0 && !beforeWrite.fence.pending(),"fresh unsafe gate blocks write and releases");
        }
        Fixture readback=new Fixture(); readback.port.pauseWrite=true; readback.job.toggle(readback.result);
        check(readback.results.isEmpty() && readback.fence.pending(),"ack alone is not UI success");
        readback.port.pauseRead=true; readback.port.write.success(true);
        check(readback.results.isEmpty() && readback.fence.pending(),"UI waits for actual readback");
        readback.port.read.success(readback.port.raw);
        check(readback.results.size()==1 && readback.results.get(0).startsWith("true:") && !readback.fence.pending(),"matching readback succeeds");
        Fixture late=new Fixture(); late.port.pauseWrite=true; late.job.toggle(late.result); late.timeout.run();
        late.port.write.success(true);
        check(!late.fence.pending() && late.results.size()==1,"late toggle reconciliation releases without duplicate result");
        Fixture cancelled=new Fixture(); cancelled.port.pauseGround=true; cancelled.job.toggle(cancelled.result);
        cancelled.job.close(); cancelled.port.ground.success(GROUND);
        check(cancelled.port.writes==0 && !cancelled.fence.pending(),"toggle close prevents write");
        Fixture elapsed=new Fixture(); elapsed.port.pauseRead=true; elapsed.job.toggle(elapsed.result);
        elapsed.now=10000000000L; elapsed.port.read.success(239);
        check(elapsed.port.writes==0 && !elapsed.fence.pending(),"toggle deadline prevents write");
        check(!new Fixture().job.toggle(null),"null result rejected");
    }
    static void submissionBarriers() throws Exception {
        for(int mode=0;mode<3;mode++) {
            Fixture fixture=new Fixture(); fixture.port.beforeSubmit=new CountDownLatch(1);
            fixture.port.resumeSubmit=new CountDownLatch(1);
            Thread preparing=new Thread(()->fixture.job.toggle(fixture.result)); preparing.start();
            waitFor(fixture.port.beforeSubmit);
            check(fixture.fence.pending(),"toggle reserves during reflection/submission preparation");
            if(mode==0) fixture.job.close();
            if(mode==1) fixture.now=10000000000L;
            if(mode==2) fixture.port.gate=GroundGate.unknown();
            fixture.port.resumeSubmit.countDown(); preparing.join(2000);
            check(!preparing.isAlive() && fixture.port.writes==0 && !fixture.fence.pending(),"close/deadline/unknown wins before dispatch");
        }
        Fixture submitted=new Fixture(); submitted.port.insideSdk=new CountDownLatch(1);
        submitted.port.resumeSdk=new CountDownLatch(1);
        Thread writer=new Thread(()->submitted.job.toggle(submitted.result)); writer.start();waitFor(submitted.port.insideSdk);
        CountDownLatch closeReturned=new CountDownLatch(1);
        Thread closer=new Thread(()->{submitted.job.close();closeReturned.countDown();});closer.start();
        check(!closeReturned.await(20,TimeUnit.MILLISECONDS),"toggle close waits for committed SDK entry");
        submitted.port.resumeSdk.countDown(); writer.join(2000);closer.join(2000);
        check(!writer.isAlive() && !closer.isAlive() && submitted.port.writes==1 && submitted.results.isEmpty()
            && !submitted.fence.pending(),"toggle committed SDK completion reconciles without disposed UI");
        Fixture failure=new Fixture(); failure.port.pauseWrite=true; failure.job.toggle(failure.result);
        failure.port.write.failure("SDK rejected callback");
        check(failure.results.get(0).startsWith("true:") && !failure.fence.pending(),"actual readback decides despite failure callback");
        Fixture unread=new Fixture(); unread.port.pauseWrite=true; unread.job.toggle(unread.result);
        unread.port.pauseRead=true; unread.port.write.success(true); unread.port.read.failure("readback unavailable");
        check(unread.fence.pending() && unread.results.get(0).startsWith("false:"),"unreadable dispatched toggle remains fenced");
        unread.port.read.success(unread.port.raw);
        check(unread.fence.pending() && unread.results.size()==1,"duplicate readback cannot unlock uncertain result");
    }
    public static void main(String[] args) throws Exception {
        exhaustive(); sequential(); guarded(); submissionBarriers();
        System.out.println("forearm_led_toggle_passed");
    }
}
