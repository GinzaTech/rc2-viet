package local.rc2.hud;

import java.util.ArrayList;
import java.util.List;

/** Deterministic SDK transaction tests. No aircraft, network or Android runtime. */
public final class LedJobTest {
    static final GroundGate GROUND=new GroundGate(true,true,false,false);
    static void check(boolean value,String message) { if(!value) throw new AssertionError(message); }
    static final class Clock implements LedJob.Scheduler {
        Runnable deadline;
        boolean canceled;
        public LedJob.Cancel schedule(Runnable task,long delay) {
            check(delay==6000,"bounded deadline"); deadline=task; canceled=false;
            return ()->canceled=true;
        }
        void expire() { deadline.run(); }
    }
    static final class Port implements LedJob.Port {
        GroundGate cached=GROUND;
        LedJob.Reply<GroundGate> gate;
        LedJob.Reply<LedJob.Lights> read;
        LedJob.Reply<Boolean> write;
        LedJob.Lights written;
        int writes,reads,grounds;
        public GroundGate snapshot() { return cached; }
        public void ground(LedJob.Reply<GroundGate> reply) { gate=reply; grounds++; }
        public void read(LedJob.Reply<LedJob.Lights> reply) { read=reply; reads++; }
        public void write(LedJob.Lights lights,LedJob.Reply<Boolean> reply) { written=lights; write=reply; writes++; }
    }
    static final class Fixture {
        final Port port=new Port(); final Clock clock=new Clock();
        final LedJob job=new LedJob(port,clock); final List<Boolean> results=new ArrayList<>();
        boolean start(boolean on) { return job.request(on,(ok,message)->{ check(!message.isEmpty(),"feedback"); results.add(ok); }); }
        void toWrite() {
            check(start(false),"accepted"); port.gate.success(GROUND);
            port.read.success(new LedJob.Lights(true,true,false,true));
            port.gate.success(GROUND);
        }
    }
    public static void main(String[] args) {
        Fixture f=new Fixture(); f.toWrite();
        check(f.port.writes==1,"one SDK write only");
        check(!f.port.written.front && f.port.written.status && !f.port.written.rear && f.port.written.navigation,
              "preserve all non-front flags");
        f.port.write.success(true); check(f.results.isEmpty(),"write ACK is not readback");
        f.port.read.success(f.port.written); check(f.results.equals(java.util.Arrays.asList(true)),"confirmed result");
        check(f.clock.canceled,"deadline released");
        f.port.write.success(true); f.port.read.success(f.port.written); f.clock.expire();
        check(f.results.size()==1 && f.port.writes==1,"duplicate and expired callbacks ignored");

        f=new Fixture(); f.toWrite(); f.port.write.success(true);
        f.port.read.success(new LedJob.Lights(false,false,false,true));
        check(f.results.equals(java.util.Arrays.asList(false)),"any changed non-front flag fails verification");

        for(GroundGate blocked:new GroundGate[]{GroundGate.unknown(),new GroundGate(true,false,false,false),
                new GroundGate(true,true,true,false),new GroundGate(true,true,false,true)}) {
            f=new Fixture(); f.port.cached=blocked; check(!f.start(false),"cached unsafe state blocked");
            check(f.port.grounds==0 && f.port.writes==0,"blocked before SDK IO");
            f=new Fixture(); f.start(false); f.port.gate.success(blocked);
            check(f.port.reads==0 && f.port.writes==0,"fresh unsafe state blocked");
            f=new Fixture(); f.start(false); f.port.gate.success(GROUND);
            f.port.read.success(new LedJob.Lights(true,false,true,false)); f.port.gate.success(blocked);
            check(f.port.writes==0,"state changed during LED read blocks write");
        }

        f=new Fixture(); f.start(false); LedJob.Reply<GroundGate> late=f.port.gate;
        check(!f.start(true),"busy request rejected"); f.clock.expire(); late.success(GROUND);
        check(f.port.writes==0 && f.port.reads==0 && f.results.size()==2,"timeout prevents late writes");
        check(f.start(false),"new request allowed after timeout"); late.success(GROUND);
        check(f.port.reads==0,"old callback cannot affect new request");

        f=new Fixture(); f.toWrite(); f.clock.expire();
        check(!f.start(true),"unresolved dispatched write remains excluded after UI timeout");
        f.port.write.success(true); f.port.read.success(f.port.written);
        check(f.results.equals(java.util.Arrays.asList(false,false)),"late reconciliation has no second UI success");
        check(f.start(true),"terminal reconciled write permits next operation");

        f=new Fixture(); f.start(false); f.port.gate.success(GROUND);
        LedJob.Reply<LedJob.Lights> lateRead=f.port.read; f.job.close();
        lateRead.success(new LedJob.Lights(true,true,true,true)); f.clock.expire();
        check(f.port.writes==0 && f.results.isEmpty() && f.clock.canceled,"pause cancels work and feedback");
        check(!f.start(true),"closed instance cannot submit another write");

        f=new Fixture(); f.toWrite(); f.job.close(); f.port.write.success(true);
        check(f.port.reads==1 && f.results.isEmpty(),"pause after committed write suppresses further IO");

        f=new Fixture(); f.start(false); f.port.gate.failure("SDK unavailable");
        check(f.results.equals(java.util.Arrays.asList(false)) && f.port.writes==0,"SDK failure stops transaction");

        f=new Fixture(); f.start(false); f.port.gate.success(GROUND);
        f.port.read.success(new LedJob.Lights(false,true,false,true));
        check(f.port.writes==0 && f.results.equals(java.util.Arrays.asList(true)),"already matching value avoids write");
        System.out.println("led_job_passed");
    }
}
