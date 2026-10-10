package local.rc2.hud;

import static local.rc2.hud.ForearmLedJobTest.*;

public final class MutationFenceObserverTest {
    public static void main(String[] args) {
        MutationFence fence=new MutationFence(); int[] calls={0};
        MutationFence.Cancel observer=fence.observe(()->{
            check(!Thread.holdsLock(fence),"observer outside fence monitor");
            check(!fence.pending(),"reconciled state visible"); calls[0]++;
        });
        check(calls[0]==0,"subscribe does not notify");
        fence.reconciled(null); Object token=fence.begin();
        check(calls[0]==0,"begin does not notify");
        fence.reconciled(new Object()); check(calls[0]==0 && fence.pending(),"wrong token ignored");
        fence.reconciled(token); fence.reconciled(token);
        check(calls[0]==1,"matching reconciliation notifies exactly once");
        observer.cancel(); observer.cancel(); token=fence.begin(); fence.reconciled(token);
        check(calls[0]==1,"cancel is idempotent");
        MutationFence.Cancel throwing=fence.observe(()->{throw new IllegalStateException("private observer details");});
        MutationFence.Cancel healthy=fence.observe(()->calls[0]++);
        token=fence.begin(); fence.reconciled(token);
        check(calls[0]==2,"observer failure cannot interrupt others"); throwing.cancel();healthy.cancel();
        Fixture late=new Fixture(); late.port.pauseWrite=true; int[] unlocks={0};
        late.fence.observe(()->unlocks[0]++); late.job.toggle(late.result); late.timeout.run();
        check(unlocks[0]==0 && late.fence.pending(),"dispatched timeout does not notify");
        late.port.write.success(true); late.port.write.success(true);
        check(unlocks[0]==1 && !late.fence.pending() && late.results.size()==1,"late verified readback unlocks once without second UI result");
        Fixture mismatch=new Fixture(); mismatch.port.wrongRead=true; mismatch.fence.observe(()->unlocks[0]++);
        mismatch.job.toggle(mismatch.result);
        check(mismatch.fence.pending() && unlocks[0]==1,"mismatch never notifies");
        System.out.println("mutation_fence_observer_passed");
    }
}
