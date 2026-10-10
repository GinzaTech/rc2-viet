// SPDX-License-Identifier: AGPL-3.0-only
package local.rc2.hud;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/** Deterministic transaction tests, including cancellation before/after dispatch. */
public final class RadioNativeTest {
    static final GroundGate GROUND=new GroundGate(true,true,false,false);
    static void check(boolean value,String label) { RadioProtocolTest.check(value,label); }
    static final class Aircraft implements NativeRadio.Aircraft {
        GroundGate cached=GROUND;
        LedJob.Reply<GroundGate> reply;
        int reads;
        public GroundGate snapshot() { return cached; }
        public void ground(LedJob.Reply<GroundGate> value) { reply=value; reads++; }
    }
    static final class Runtime implements NativeRadio.Runtime {
        Runnable worker,deadline;
        int starts,cancels;
        boolean deadlineCancelFails;
        public NativeRadio.Cancel start(Runnable task) { worker=task; starts++; return ()->cancels++; }
        public NativeRadio.Cancel after(Runnable task,long delay) {
            check(delay==NativeRadio.DEADLINE_MILLIS,"bounded global deadline");
            deadline=task; return ()->{cancels++; if(deadlineCancelFails) throw new IllegalStateException("SECRET-cancel");};
        }
    }
    static final class Sender implements NativeRadio.Sender {
        int sends,closes;
        boolean selected,dispatch,fail,closeFails;
        Runnable afterDispatch;
        RadioTransport.Guard capturedGuard;
        public void send(boolean fcc,RadioTransport.Guard guard) throws IOException {
            check(guard.allowed(),"gate at sender"); capturedGuard=guard; selected=fcc; sends++;
            if(dispatch) guard.dispatched();
            if(afterDispatch!=null) afterDispatch.run();
            if(fail) throw new IOException("fake failure");
        }
        public void close() { closes++; if(closeFails) throw new IllegalStateException("SECRET-close"); }
    }
    static final class Fixture {
        final Aircraft aircraft=new Aircraft(); final Runtime runtime=new Runtime();
        final Sender sender=new Sender(); final MutationFence fence=new MutationFence();
        final NativeRadio radio=new NativeRadio(aircraft,()->sender,runtime,fence);
        final List<Boolean> results=new ArrayList<>(); final List<String> messages=new ArrayList<>();
        boolean start(boolean fcc) { return radio.request(fcc,(ok,message)->{ results.add(ok); messages.add(message); }); }
        void ready() { check(start(true),"request accepted"); aircraft.reply.success(GROUND); }
    }
    public static void main(String[] args) {
        Fixture f=new Fixture(); f.ready();
        check(f.sender.sends==0 && f.runtime.starts==1,"asynchronous no write on caller thread");
        check(!f.aircraft.reply.active(),"ground reply consumed once");
        f.aircraft.reply.success(GROUND); f.aircraft.reply.failure("late error");
        check(f.runtime.starts==1,"duplicate and late failure ignored");
        f.sender.dispatch=true; f.runtime.worker.run();
        check(f.results.equals(java.util.Arrays.asList(true)),"profile delivery completion");
        check(f.messages.get(0).contains("chưa xác nhận"),"ACK never claims effective FCC");
        check(f.fence.pending(),"delivery and ACK_BEFORE_EXEC cannot reconcile uncertain hardware mutation");
        check(f.sender.closes==1,"session closed after completion");
        f.runtime.deadline.run(); check(f.results.size()==1,"late deadline cannot report twice");
        check(!f.start(false),"unverified FCC cannot be followed by another mutation");
        f=new Fixture(); f.sender.dispatch=true;
        check(f.start(false),"explicit restore accepted before any mutation"); f.aircraft.reply.success(GROUND); f.runtime.worker.run();
        check(!f.sender.selected && f.messages.get(0).contains("nhà máy"),"factory restore wording");
        check(!f.messages.get(0).contains("Đã bật CE"),"no direct CE claim");
        check(f.fence.pending(),"no-ACK dispatched restore remains uncertain");
        check(!f.start(true),"no automatic retry of uncertain mutation");

        for(GroundGate blocked:new GroundGate[]{GroundGate.unknown(),new GroundGate(true,false,false,false),
                new GroundGate(true,true,true,false),new GroundGate(true,true,false,true)}) {
            f=new Fixture(); f.aircraft.cached=blocked; check(!f.start(true),"unsafe cached state blocked");
            check(f.aircraft.reads==0 && f.runtime.starts==0,"no IO when cached gate unsafe");
            f=new Fixture(); f.start(true); f.aircraft.reply.success(blocked);
            check(f.runtime.starts==0,"unsafe fresh gate blocks send");
            f=new Fixture(); f.ready(); f.aircraft.cached=blocked; f.runtime.worker.run();
            check(f.sender.sends==0,"state changed before worker blocks send");
        }
        f=new Fixture(); f.start(true); LedJob.Reply<GroundGate> late=f.aircraft.reply;
        check(!f.start(false),"single flight"); f.runtime.deadline.run();
        check(!late.active(),"timeout stops ground SDK chain"); late.success(GROUND);
        check(f.runtime.starts==0,"late success cannot dispatch");
        check(f.start(true),"no-dispatch timeout releases fence"); late.success(GROUND);
        check(f.runtime.starts==0,"old generation cannot affect new request");

        f=new Fixture(); f.start(true); late=f.aircraft.reply; f.radio.close();
        check(!late.active(),"close stops ground SDK chain"); late.success(GROUND); f.runtime.deadline.run();
        check(f.results.isEmpty() && f.runtime.starts==0,"close suppresses feedback and work");
        check(!f.start(true),"closed instance rejects");
        f=new Fixture(); f.ready(); Runnable queued=f.runtime.worker; f.radio.close(); queued.run();
        check(f.sender.sends==0 && !f.fence.pending(),"close before dispatch releases fence");

        f=new Fixture(); f.ready(); f.sender.dispatch=true; f.sender.fail=true; f.runtime.worker.run();
        check(f.results.equals(java.util.Arrays.asList(false)) && f.fence.pending(),"partial write fails and latches fence");
        f=new Fixture(); f.ready(); f.sender.dispatch=true; f.sender.afterDispatch=f.runtime.deadline;
        f.runtime.worker.run();
        check(f.results.equals(java.util.Arrays.asList(false)) && f.fence.pending(),"post-dispatch timeout keeps uncertainty and reports once");
        check(f.sender.closes==1 && !f.radio.status().busy,"deadline closes sender and ends UI transaction");
        final Fixture transientLoss=new Fixture(); transientLoss.ready(); transientLoss.sender.dispatch=true;
        transientLoss.sender.afterDispatch=()->{
            transientLoss.aircraft.cached=GroundGate.unknown();
            check(!transientLoss.sender.capturedGuard.allowed(),"native observes unsafe state");
            transientLoss.aircraft.cached=GROUND;
        };
        transientLoss.runtime.worker.run();
        check(transientLoss.results.equals(java.util.Arrays.asList(false)) && transientLoss.fence.pending(),"native unsafe state remains latched after recovery");
        NativeRadio replacement=new NativeRadio(f.aircraft,()->new Sender(),f.runtime,f.fence);
        check(!replacement.request(false,(ok,message)->{}),"new menu instance cannot bypass uncertainty");
        f=new Fixture(); f.ready(); f.sender.fail=true; f.runtime.worker.run();
        check(!f.fence.pending() && f.start(false),"pre-dispatch connect failure allows explicit retry");
        f=new Fixture(); f.start(true); f.aircraft.reply.failure("SDK unavailable");
        check(f.results.equals(java.util.Arrays.asList(false)) && !f.fence.pending(),"SDK failure no mutation");
        f=new Fixture(); check(f.radio.state()==GROUND,"menu ground state");
        for(boolean restore:new boolean[]{false,true}) {
            f=new Fixture();
            final List<NativeRadio.Status> menuA=new ArrayList<>(),menuB=new ArrayList<>();
            NativeRadio.Cancel subscription=f.radio.observe(menuA::add);
            f.start(!restore); f.aircraft.reply.success(GROUND); subscription.cancel();
            int detached=menuA.size(); f.sender.dispatch=true; f.runtime.worker.run();
            f.radio.observe(menuB::add).cancel();
            check(menuA.size()==detached,"disposed menu no longer observes result");
            NativeRadio.Status status=menuB.get(0);
            check(!status.busy && !status.message.isEmpty() && status.locked,"new menu retains dispatch uncertainty for either profile");
        }
        f=new Fixture(); f.start(true); f.runtime.deadline.run();
        check(!f.radio.status().busy && !f.radio.status().locked && !f.radio.status().message.isEmpty(),"retained pre-dispatch timeout result");
        f=new Fixture(); f.ready(); f.sender.dispatch=true; f.sender.fail=true; f.runtime.worker.run();
        check(!f.radio.status().busy && f.radio.status().locked && !f.radio.status().message.isEmpty(),"retained partial-write lock result");
        check(!f.radio.request(true,null),"null result rejected");
        NativeRadio absent=new NativeRadio(new ClassLoader(null){});
        check(!absent.state().allowed(),"missing native SDK fails closed");
        check(!absent.request(true,(ok,message)->check(!ok,"missing SDK callback")),"unsupported runtime no IO");
        absent.close();
        for(boolean closeFails:new boolean[]{true,false}) {
            f=new Fixture(); f.ready(); f.sender.dispatch=true;
            f.sender.closeFails=closeFails; f.runtime.deadlineCancelFails=!closeFails;
            f.runtime.worker.run();
            check(f.runtime.cancels==2 && f.sender.closes==1,"all cleanup attempted despite exception");
            check(f.results.size()==1 && f.results.get(0) && !f.radio.status().busy && f.fence.pending(),"cleanup failure cannot lose result or release uncertainty");
            check(!f.messages.get(0).contains("SECRET"),"cleanup exception text never exposed");
        }
        f=new Fixture();
        f.radio.observe(status->{if(status.busy) throw new NoClassDefFoundError("SECRET-UI-observer");});
        check(f.start(true) && f.runtime.deadline!=null,"bad observer cannot strand startup without deadline");
        f.aircraft.reply.success(GROUND); f.sender.dispatch=true; f.runtime.worker.run();
        check(f.results.size()==1 && !f.radio.status().busy && f.fence.pending(),"bad observer cannot suppress completion");
        final long[] clock={0}; final int[] cancelled={0};
        Aircraft startupAircraft=new Aircraft(); MutationFence startupFence=new MutationFence();
        List<Boolean> startupResults=new ArrayList<>();
        NativeRadio.Runtime stalledStartup=new NativeRadio.Runtime() {
            public NativeRadio.Cancel start(Runnable task) { throw new AssertionError("expired startup cannot start worker"); }
            public NativeRadio.Cancel after(Runnable task,long delay) {
                clock[0]=NativeRadio.DEADLINE_MILLIS*1000000L+1;
                return ()->cancelled[0]++;
            }
        };
        NativeRadio startup=new NativeRadio(startupAircraft,()->{throw new AssertionError("expired startup cannot create sender");},
            stalledStartup,startupFence,()->clock[0]);
        check(!startup.request(true,(ok,message)->startupResults.add(ok)),"startup expired during scheduling");
        check(!startup.status().busy && !startupFence.pending() && startupAircraft.reads==0,"expired undispatched startup ends and releases fence");
        check(startupResults.equals(java.util.Arrays.asList(false)) && cancelled[0]==1,"expired startup cancels timer and reports exactly once");
        System.out.println("RadioNativeTest_passed");
    }
}
