package local.rc2.hud;

import uav.sdk.keyvalue.UAVKeyManager;
import uav.midware.data.model.P3.DataFlycGetParams;
import uav.midware.data.model.P3.DataFlycSetParams;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class NativeLedFenceTest {
    static void check(boolean yes,String why) { if(!yes)throw new AssertionError(why); }
    static byte[] frame(int raw) { return new byte[]{0,(byte)0xa2,0x59,(byte)0xce,(byte)0xed,(byte)raw}; }
    static void waitFor(CountDownLatch latch) {
        try { check(latch.await(2,TimeUnit.SECONDS),"barrier timeout"); }
        catch(InterruptedException error) { Thread.currentThread().interrupt();throw new AssertionError(error); }
    }
    static void closeOutsideOwnerMonitor(ClassLoader loader) throws Exception {
        NativeLed owner=new NativeLed(loader); owner.request(false,(ok,message)->{});
        DataFlycGetParams.last.succeed(frame(239)); DataFlycGetParams readback=DataFlycGetParams.last;
        CountDownLatch callbackEntered=new CountDownLatch(1),resume=new CountDownLatch(1),acquired=new CountDownLatch(1);
        MutationFence.Cancel foreign=MutationFence.hardware().observe(()->{
            callbackEntered.countDown();waitFor(resume);
            synchronized(owner) { acquired.countDown(); }
        });
        Thread callback=new Thread(()->readback.succeed(frame(206)));callback.setDaemon(true);callback.start();waitFor(callbackEntered);
        Thread closer=new Thread(owner::close);closer.setDaemon(true);closer.start();
        java.lang.reflect.Field closed=NativeLed.class.getDeclaredField("closed");closed.setAccessible(true);
        long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
        while(!closed.getBoolean(owner) && System.nanoTime()<until) Thread.yield();
        check(closed.getBoolean(owner),"close detached owner state before waiting for child");
        resume.countDown();waitFor(acquired);callback.join(2000);closer.join(2000);
        check(!callback.isAlive() && !closer.isAlive(),"foreign callback and close cannot invert owner/child locks");foreign.cancel();
    }
    public static void main(String[] args) throws Exception {
        ClassLoader loader=NativeLedFenceTest.class.getClassLoader();
        UAVKeyManager.cache.put("Connection",true);UAVKeyManager.cache.put("IsFlying",false);UAVKeyManager.cache.put("AreMotorsOn",false);
        NativeLed old=new NativeLed(loader); int[] results={0},disposedNotifications={0};
        old.observe(()->disposedNotifications[0]++);
        Object other=MutationFence.hardware().begin();
        check(!old.request(false,(ok,message)->{}),"other control excludes LED");
        check(DataFlycSetParams.starts==0 && DataFlycGetParams.starts==0,"busy request performs no GET/write");
        MutationFence.hardware().reconciled(other);check(disposedNotifications[0]==1,"shared reconciliation observable");
        old.request(false,(ok,message)->results[0]++);DataFlycGetParams.last.succeed(frame(239));
        DataFlycGetParams late=DataFlycGetParams.last;check(DataFlycSetParams.starts==1,"one committed pinned write");old.close();
        NativeLed next=new NativeLed(loader);int[] notifications={0},freshReads={0};
        NativeLed.Cancel observer=next.observe(()->{
            notifications[0]++;
            next.inspect(new LedJob.Reply<LedJob.Lights>() {
                public void success(LedJob.Lights value) { check(!value.front && value.status && value.rear,"fresh observable owner state");freshReads[0]++; }
                public void failure(String message) { throw new AssertionError(message); }
            });
        });
        check(!next.request(true,(ok,message)->results[0]++),"recreated owner blocked by unresolved old write");
        late.succeed(frame(206));late.succeed(frame(206));
        check(notifications[0]==1 && disposedNotifications[0]==1 && results[0]==1,"late reconciliation unlocks live owner exactly once");
        DataFlycGetParams.last.succeed(frame(206));check(freshReads[0]==1,"observer owner GETs fresh state");observer.cancel();observer.cancel();
        next.request(true,(ok,message)->{check(ok,"restored value");results[0]++;});
        DataFlycGetParams.last.succeed(frame(206));DataFlycGetParams.last.succeed(frame(239));
        check(results[0]==2 && notifications[0]==1 && DataFlycSetParams.starts==2,"cancelled observer silent and next request verified");
        next.close();next.observe(()->notifications[0]++).cancel();
        NativeLed probe=new NativeLed(loader);int[] reads={0};int sets=DataFlycSetParams.starts;
        probe.inspect(new LedJob.Reply<LedJob.Lights>() {
            public void success(LedJob.Lights value) { reads[0]++; }
            public void failure(String message) { reads[0]++; }
        });
        DataFlycGetParams pending=DataFlycGetParams.last;probe.close();pending.succeed(frame(239));
        check(reads[0]==0 && DataFlycSetParams.starts==sets,"disposed inspect ignores late parameter read");
        closeOutsideOwnerMonitor(loader);
        check(UAVKeyManager.writes==0 && !UAVKeyManager.reads.contains("LEDsSettings"),"no typed LED GET or write");
        System.out.println("native_led_fence_passed");
    }
}
