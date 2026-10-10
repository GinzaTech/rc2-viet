package local.rc2.hud;

import java.util.concurrent.CountDownLatch;
import static local.rc2.hud.ForearmLedJobTest.*;

/** Deterministic barriers cover shared ownership before SDK entry, without a device. */
public final class ForearmLedTransactionFenceTest {
    static void exclusion(boolean frontFirst) throws Exception {
        MutationFence fence=new MutationFence();
        Port first=new Port(),second=new Port(); first.pauseRead=true;
        ForearmLedJob owner=new ForearmLedJob(first,(task,delay)->()->{},fence,frontFirst?33:6);
        ForearmLedJob contender=new ForearmLedJob(second,(task,delay)->()->{},fence,frontFirst?6:33);
        check(owner.toggle((ok,message)->check(ok,"owner verified")),"owner starts");
        check(fence.pending() && first.reads==1,"ownership reserved before baseline read");
        CountDownLatch rejected=new CountDownLatch(1);
        Thread thread=new Thread(()->{
            check(!contender.toggle((ok,message)->{
                check(!ok,"contender reports busy"); rejected.countDown();
            }),"concurrent contender rejected");
        });
        thread.start(); waitFor(rejected); thread.join(2000);
        check(second.reads==0 && second.writes==0,"contender cannot read an old baseline");
        first.pauseRead=false; first.read.success(first.raw);
        check(first.writes==1 && !fence.pending(),"owner holds through matching readback");
        second.raw=first.raw;
        check(contender.toggle((ok,message)->check(ok,"next group verified")),"next group starts after release");
        check(second.raw==200,"sequential group change preserves owner change");
        owner.close(); contender.close();
    }
    public static void main(String[] args) throws Exception {
        exclusion(true); exclusion(false);
        Fixture readFailure=new Fixture(); readFailure.port.pauseRead=true;
        readFailure.job.request(false,readFailure.result);
        check(readFailure.fence.pending(),"fresh read owns fence");
        readFailure.port.read.failure("read failed");
        check(!readFailure.fence.pending() && readFailure.port.writes==0,"read failure releases reservation");
        Fixture groundFailure=new Fixture(); groundFailure.port.pauseGround=true;
        groundFailure.job.request(false,groundFailure.result); groundFailure.port.ground.failure("ground failed");
        check(!groundFailure.fence.pending(),"ground failure releases reservation");
        Fixture cancelled=new Fixture(); cancelled.port.pauseRead=true;
        cancelled.job.request(false,cancelled.result); cancelled.job.close(); cancelled.port.read.success(239);
        check(!cancelled.fence.pending() && cancelled.port.writes==0 && cancelled.results.isEmpty(),"close releases read reservation");
        Fixture timeout=new Fixture(); timeout.port.pauseRead=true;
        timeout.job.request(false,timeout.result); timeout.timeout.run(); timeout.port.read.success(239);
        check(!timeout.fence.pending() && timeout.port.writes==0 && timeout.results.size()==1,"timer releases before dispatch");
        Fixture expired=new Fixture(); expired.port.pauseRead=true;
        expired.job.request(false,expired.result); expired.now=10000000000L; expired.port.read.success(239);
        check(!expired.fence.pending() && expired.port.writes==0 && expired.results.size()==1,"clock expiry releases without timer delivery");
        Fixture noop=new Fixture(); noop.job.request(true,noop.result);
        check(!noop.fence.pending() && noop.results.size()==1,"explicit no-op releases reservation");
        check(!noop.results.get(0).contains("SET"),"no-op product text has no transport jargon");
        MutationFence scheduleFence=new MutationFence();
        ForearmLedJob broken=new ForearmLedJob(new Port(),(task,delay)->{throw new IllegalStateException();},scheduleFence);
        check(!broken.request(false,(ok,message)->check(!ok,"schedule failed")) && !scheduleFence.pending(),"scheduler failure releases");
        MutationFence nullFence=new MutationFence();
        ForearmLedJob noDeadline=new ForearmLedJob(new Port(),(task,delay)->null,nullFence);
        check(!noDeadline.toggle((ok,message)->check(!ok,"deadline required")) && !nullFence.pending(),"missing scheduler deadline releases");
        MutationFence immediateFence=new MutationFence(); Port immediatePort=new Port();
        ForearmLedJob immediate=new ForearmLedJob(immediatePort,(task,delay)->{task.run();return ()->{};},immediateFence);
        check(!immediate.toggle((ok,message)->check(!ok,"immediate timeout")) && !immediateFence.pending()
            && immediatePort.reads==0,"synchronous timeout releases before any read");
        System.out.println("forearm_led_transaction_fence_passed");
    }
}
