package local.rc2.hud;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class ForearmLedJobTest {
    static final GroundGate GROUND=new GroundGate(true,true,false,false);
    static final class Port implements ForearmLedJob.Port {
        GroundGate gate=GROUND;
        int raw=239,writes,reads;
        boolean pauseGround,pauseWrite,pauseRead,wrongRead;
        LedJob.Reply<GroundGate> ground;
        LedJob.Reply<Integer> read;
        ForearmLedJob.WriteReply write;
        CountDownLatch beforeSubmit,resumeSubmit,insideSdk,resumeSdk;
        public GroundGate snapshot() { return gate; }
        public void ground(LedJob.Reply<GroundGate> reply) { ground=reply; if(!pauseGround) reply.success(gate); }
        public void read(LedJob.Reply<Integer> reply) {
            reads++; read=reply;
            if(!pauseRead) reply.success(wrongRead && writes>0?239:raw);
        }
        public void write(int value,ForearmLedJob.WriteReply reply) {
            write=reply;
            if(beforeSubmit!=null) { beforeSubmit.countDown();waitFor(resumeSubmit); }
            try { reply.submit(()->{
                if(insideSdk!=null) { insideSdk.countDown();waitFor(resumeSdk); }
                writes++; raw=value;
                if(!pauseWrite) reply.success(true);
            }); } catch(ReflectiveOperationException error) { reply.failure("fixture submission"); }
        }
    }
    static final class Fixture {
        final Port port=new Port();
        final MutationFence fence=new MutationFence();
        final List<String> results=new ArrayList<>();
        Runnable timeout;
        long now;
        ForearmLedJob job=new ForearmLedJob(port,(task,delay)->{timeout=task;return ()->{};},fence,()->now);
        LedJob.Result result=(ok,message)->results.add(ok+":"+message);
    }
    static void check(boolean value,String name) { if(!value) throw new AssertionError(name); }
    static void waitFor(CountDownLatch latch) { try { if(!latch.await(2,TimeUnit.SECONDS))throw new AssertionError("fixture barrier timeout"); }
        catch(InterruptedException error) { Thread.currentThread().interrupt();throw new AssertionError(error); } }
    public static void main(String[] args) throws Exception {
        check(ForearmLedJob.updated(239,false)==206,"only front mask off");
        check(ForearmLedJob.updated(206,true)==239,"only front mask on");
        check(ForearmLedJob.updated(206,false,6)==200,"rear/status off preserves front off");
        check(ForearmLedJob.updated(239,false,39)==200,"single OFF disables front/rear/status together");
        check(ForearmLedJob.updated(200,true,39)==239,"single ON restores front/rear/status together");
        for(int raw=0;raw<256;raw++) for(boolean on:new boolean[]{false,true}) {
            int next=ForearmLedJob.updated(raw,on);
            check((next&0xde)==(raw&0xde),"preserve all non-front bits");
        }
        for(int raw=0;raw<256;raw++) for(boolean on:new boolean[]{false,true})
            check((ForearmLedJob.updated(raw,on,6)&0xf9)==(raw&0xf9),"rear/status preserves front/navigation/unknown bits");
        for(int raw=0;raw<256;raw++) for(boolean on:new boolean[]{false,true})
            check((ForearmLedJob.updated(raw,on,39)&0xd8)==(raw&0xd8),"all LED action preserves every unrelated bit");
        Port rearPort=new Port();rearPort.raw=206;
        ForearmLedJob rearJob=new ForearmLedJob(rearPort,(task,delay)->()->{},new MutationFence(),6);
        rearJob.request(false,(ok,message)->check(ok,"rear/status readback"));
        check(rearPort.raw==200 && rearPort.writes==1,"one rear/status mutation");rearJob.close();
        Fixture off=new Fixture(); off.job.request(false,off.result);
        check(off.port.writes==1 && off.port.raw==206 && off.port.reads==2,"fresh read write readback");
        check(off.results.get(0).startsWith("true:") && !off.fence.pending(),"verified release");
        Fixture noop=new Fixture(); noop.job.request(true,noop.result); check(noop.port.writes==0,"no-op has no SET");
        Fixture airborne=new Fixture(); airborne.port.gate=new GroundGate(true,true,true,false);
        check(!airborne.job.request(false,airborne.result) && airborne.port.reads==0,"armed blocked");
        Fixture inconsistent=new Fixture(); inconsistent.port.raw=1; inconsistent.job.request(false,inconsistent.result);
        check(inconsistent.port.writes==0 && inconsistent.results.get(0).startsWith("false:"),"unverified layout blocked");
        Fixture cancelled=new Fixture(); cancelled.port.pauseGround=true; cancelled.job.request(false,cancelled.result);
        cancelled.job.close(); cancelled.port.ground.success(GROUND); check(cancelled.port.reads==0,"late ground cancelled");
        Fixture changed=new Fixture(); changed.port.pauseGround=true; changed.job.request(false,changed.result);
        changed.port.gate=new GroundGate(true,true,false,true); changed.port.ground.success(GROUND);
        check(changed.port.writes==0,"snapshot changed before read");
        Fixture elapsed=new Fixture(); elapsed.port.pauseGround=true; elapsed.job.request(false,elapsed.result);
        elapsed.now=10000000001L; elapsed.port.ground.success(GROUND);
        check(elapsed.port.reads==0 && elapsed.port.writes==0,"elapsed deadline enforced without timer delivery");
        Fixture timed=new Fixture(); timed.port.pauseWrite=true; timed.job.request(false,timed.result);
        timed.timeout.run(); check(timed.fence.pending() && timed.results.size()==1,"dispatched timeout fenced");
        timed.port.write.success(true); check(!timed.fence.pending() && timed.results.size()==1,"late verified release no second result");
        Fixture closed=new Fixture(); closed.port.pauseWrite=true; closed.job.request(false,closed.result);
        closed.job.close(); closed.port.write.success(true);
        check(!closed.fence.pending() && closed.results.isEmpty(),"close preserves reconciliation suppresses UI");
        Fixture mismatch=new Fixture(); mismatch.port.wrongRead=true; mismatch.job.request(false,mismatch.result);
        check(mismatch.fence.pending() && mismatch.results.get(0).startsWith("false:"),"wrong readback stays fenced");
        Fixture duplicate=new Fixture(); duplicate.port.pauseWrite=true; duplicate.job.request(false,duplicate.result);
        duplicate.port.write.success(true); duplicate.port.write.success(true); duplicate.port.write.failure("late");
        check(duplicate.port.reads==2 && duplicate.results.size()==1,"duplicate SET callback no more GET");
        Fixture busy=new Fixture(); busy.fence.begin(); busy.job.request(false,busy.result);
        check(busy.port.writes==0 && busy.results.get(0).startsWith("false:"),"shared fence prevents SET");
        Fixture beforeSubmit=new Fixture(); beforeSubmit.port.beforeSubmit=new CountDownLatch(1);beforeSubmit.port.resumeSubmit=new CountDownLatch(1);
        Thread preparing=new Thread(()->beforeSubmit.job.request(false,beforeSubmit.result));preparing.start();
        waitFor(beforeSubmit.port.beforeSubmit);beforeSubmit.job.close();beforeSubmit.port.resumeSubmit.countDown();preparing.join(2000);
        check(!preparing.isAlive() && beforeSubmit.port.writes==0 && !beforeSubmit.fence.pending(),"close wins before SDK submission");
        Fixture submitted=new Fixture();submitted.port.insideSdk=new CountDownLatch(1);submitted.port.resumeSdk=new CountDownLatch(1);
        Thread submitting=new Thread(()->submitted.job.request(false,submitted.result));submitting.start();waitFor(submitted.port.insideSdk);
        CountDownLatch closeReturned=new CountDownLatch(1);Thread closer=new Thread(()->{submitted.job.close();closeReturned.countDown();});closer.start();
        check(!closeReturned.await(20,TimeUnit.MILLISECONDS),"close waits committed SDK entry, no lifecycle lock deadlock");
        submitted.port.resumeSdk.countDown();submitting.join(2000);closer.join(2000);
        check(!submitting.isAlive() && !closer.isAlive() && submitted.port.writes==1 && submitted.results.isEmpty()
            && !submitted.fence.pending(),"SDK handoff completes before close returns and reconciles");
        System.out.println("forearm_led_job_passed");
    }
}
