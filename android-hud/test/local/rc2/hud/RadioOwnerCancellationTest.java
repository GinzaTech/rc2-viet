package local.rc2.hud;

import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Exercises the real owner's guard/cancellation lock ordering, not just Sender.close. */
public final class RadioOwnerCancellationTest {
    static final GroundGate GROUND=new GroundGate(true,true,false,false);
    static final class Runtime implements NativeRadio.Runtime {
        Runnable timeout;Thread worker;
        public NativeRadio.Cancel start(Runnable action) {
            worker=new Thread(action,"radio-owner-test");worker.setDaemon(true);worker.start();return worker::interrupt;
        }
        public NativeRadio.Cancel after(Runnable action,long delay) { timeout=action;return ()->{}; }
    }
    static final class Sender implements NativeRadio.Sender {
        final Object submissionLock=new Object();
        final CountDownLatch entered=new CountDownLatch(1),resume=new CountDownLatch(1),closing=new CountDownLatch(1);
        int writes;
        public void send(boolean fcc,RadioTransport.Guard guard)throws IOException {
            synchronized(submissionLock) {
                entered.countDown();waitFor(resume);
                if(guard.allowed()) { guard.dispatched();writes++; }
            }
        }
        public void close() { closing.countDown();synchronized(submissionLock){} }
    }
    static void waitFor(CountDownLatch value) {
        try { if(!value.await(2,TimeUnit.SECONDS))throw new AssertionError("barrier timeout"); }
        catch(InterruptedException error) { Thread.currentThread().interrupt();throw new AssertionError(error); }
    }
    static void check(boolean value,String message) { if(!value)throw new AssertionError(message); }
    public static void main(String[] args)throws Exception {
        for(boolean timeout:new boolean[]{false,true}) {
            Runtime runtime=new Runtime();Sender sender=new Sender();MutationFence fence=new MutationFence();
            NativeRadio owner=new NativeRadio(new NativeRadio.Aircraft() {
                public GroundGate snapshot(){return GROUND;}
                public void ground(LedJob.Reply<GroundGate> reply){reply.success(GROUND);}
            },()->sender,runtime,fence);
            check(owner.request(true,(ok,message)->{}),"request accepted");waitFor(sender.entered);
            Thread cancel=new Thread(()->{if(timeout)runtime.timeout.run();else owner.close();});cancel.setDaemon(true);cancel.start();
            waitFor(sender.closing);sender.resume.countDown();
            cancel.join(2000);runtime.worker.join(2000);
            check(!cancel.isAlive() && !runtime.worker.isAlive(),"owner cleanup cannot hold guard monitor while waiting sender");
            check(sender.writes==0 && !fence.pending(),"cancellation wins before handoff and releases reservation");
            owner.close();
        }
        System.out.println("RadioOwnerCancellationTest_passed");
    }
}
