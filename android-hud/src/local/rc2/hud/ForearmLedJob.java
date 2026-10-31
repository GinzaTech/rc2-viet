package local.rc2.hud;

/** One foreground, grounded UINT8 transaction for a pinned LED mask.
 * A SET completion is followed by a correlated GET. No retry or rollback writes.
 */
final class ForearmLedJob {
    interface Submission { void run() throws ReflectiveOperationException; }
    interface WriteReply extends LedJob.Reply<Boolean> { boolean submit(Submission action) throws ReflectiveOperationException; }
    interface Port {
        GroundGate snapshot();
        void ground(LedJob.Reply<GroundGate> reply);
        void read(LedJob.Reply<Integer> reply);
        void write(int raw,WriteReply reply);
    }
    interface Next<T> { void run(T value); }
    private static final int FRONT=0x21;
    private static final class Request {
        // Null requests a toggle determined only by the fresh parameter response.
        final Boolean on;
        final long deadlineNanos;
        LedJob.Result result;
        LedJob.Cancel deadline;
        int phase=1,expected;
        final Object token;
        boolean dispatched,settled,verified;
        Request(Boolean on,LedJob.Result result,long now,Object token) {
            this.on=on; this.result=result; this.token=token; deadlineNanos=now+10000000000L;
        }
    }
    private final Port port;
    private final LedJob.Scheduler scheduler;
    private final MutationFence fence;
    private final java.util.function.LongSupplier clock;
    private final int mask;
    private final Object submissionLock=new Object();
    private Request current;
    private volatile boolean closed,closeRequested;
    ForearmLedJob(Port port,LedJob.Scheduler scheduler,MutationFence fence) {
        this(port,scheduler,fence,System::nanoTime);
    }
    ForearmLedJob(Port port,LedJob.Scheduler scheduler,MutationFence fence,java.util.function.LongSupplier clock) {
        this(port,scheduler,fence,clock,FRONT);
    }
    ForearmLedJob(Port port,LedJob.Scheduler scheduler,MutationFence fence,int mask) {
        this(port,scheduler,fence,System::nanoTime,mask);
    }
    private ForearmLedJob(Port port,LedJob.Scheduler scheduler,MutationFence fence,java.util.function.LongSupplier clock,int mask) {
        if(mask!=FRONT && mask!=6 && mask!=39) throw new IllegalArgumentException("Only pinned LED fields allowed");
        this.port=port; this.scheduler=scheduler; this.fence=fence; this.clock=clock; this.mask=mask;
    }
    static int updated(int raw,boolean on) {
        return updated(raw,on,FRONT);
    }
    static int updated(int raw,boolean on,int mask) {
        if(raw<0 || raw>255) throw new IllegalArgumentException("UINT8 required");
        if(mask!=FRONT && mask!=6 && mask!=39) throw new IllegalArgumentException("Fixed LED mask required");
        return on?raw|mask:raw&~mask;
    }
    static boolean layout(Integer raw) {
        return raw!=null && raw>=0 && raw<=255 && ((raw&FRONT)==0 || (raw&FRONT)==FRONT);
    }
    private GroundGate state() {
        try { GroundGate value=port.snapshot(); return value==null?GroundGate.unknown():value; }
        catch(RuntimeException | LinkageError error) { return GroundGate.unknown(); }
    }
    boolean request(boolean on,LedJob.Result result) {
        return start(on,result);
    }
    boolean toggle(LedJob.Result result) {
        return start(null,result);
    }
    private boolean start(Boolean on,LedJob.Result result) {
        if(result==null) return false;
        Request request;
        synchronized(this) {
            if(closed || closeRequested) return false;
            if(current!=null) { result.finished(false,"Lệnh trước chưa kết thúc; chưa gửi thêm LED."); return false; }
            GroundGate gate=state();
            if(!gate.allowed()) { result.finished(false,gate.explanation()); return false; }
            // Reserve the complete read/modify/write/readback transaction. Separate
            // front/rear/all jobs must never derive targets from the same baseline.
            long now=clock.getAsLong();
            Object token=fence.begin();
            if(token==null) { result.finished(false,"Lệnh trước chưa kết thúc; chưa gửi thêm LED."); return false; }
            request=new Request(on,result,now,token); current=request;
        }
        try {
            LedJob.Cancel deadline=scheduler.schedule(()->finish(request,false,"Hết thời gian chờ LED; không tự gửi lại."),10000);
            if(deadline==null) throw new IllegalStateException("LED deadline required");
            synchronized(this) {
                if(current!=request) { deadline.cancel(); return false; }
                request.deadline=deadline;
            }
            port.ground(reply(request,1,gate->{
                if(!grounded(request,2,gate)) return;
                port.read(reply(request,2,raw->{
                    if(!layout(raw)) { finish(request,false,"Giá trị LED không khớp layout đã kiểm tra; không gửi lệnh."); return; }
                    boolean onTarget=request.on==null?(raw&mask)==0:request.on;
                    request.expected=updated(raw,onTarget,mask);
                    if(request.expected==raw) { finish(request,true,"LED đã ở trạng thái yêu cầu."); return; }
                    if(!live(request,3)) return;
                    port.ground(reply(request,3,fresh->{
                        if(grounded(request,4,fresh)) port.write(request.expected,writer(request));
                    }));
                }));
            }));
            return true;
        } catch(RuntimeException | LinkageError error) { finish(request,false,"Không mở được tác vụ LED."); return false; }
    }
    private boolean grounded(Request request,int phase,GroundGate gate) {
        if(!live(request,phase)) return false;
        GroundGate actual=state();
        if(gate==null || !gate.allowed() || !actual.allowed()) {
            finish(request,false,(gate==null?GroundGate.unknown():!gate.allowed()?gate:actual).explanation()); return false;
        }
        return true;
    }
    private synchronized boolean live(Request request,int phase) {
        if(closed || closeRequested || current!=request || request.result==null || request.phase!=phase) return false;
        if(clock.getAsLong()>=request.deadlineNanos) {
            finish(request,false,"Hết thời gian chờ LED; không tự gửi lại."); return false;
        }
        return true;
    }
    private <T> LedJob.Reply<T> reply(Request request,int phase,Next<T> next) {
        return new LedJob.Reply<T>() {
            public boolean active() { return live(request,phase); }
            public void success(T value) {
                synchronized(ForearmLedJob.this) {
                    if(!live(request,phase)) return;
                    request.phase=phase+1;
                }
                try { if(live(request,phase+1)) next.run(value); }
                catch(RuntimeException | LinkageError error) { finish(request,false,"Lỗi xử lý trạng thái LED."); }
            }
            public void failure(String message) { if(active()) finish(request,false,message); }
        };
    }
    private WriteReply writer(Request request) {
        return new WriteReply() {
            public boolean active() { return live(request,4); }
            public boolean submit(Submission action) throws ReflectiveOperationException {
                synchronized(submissionLock) {
                  synchronized(ForearmLedJob.this) {
                    if(!live(request,4)) return false;
                    GroundGate gate=state();
                    if(!gate.allowed()) { finish(request,false,gate.explanation()); return false; }
                    if(!live(request,4)) return false;
                    request.dispatched=true; request.phase=5;
                  }
                  // No lifecycle monitor is held across SDK entry/callbacks.
                  // close waits for this committed SDK submission to return.
                  action.run(); return true;
                }
            }
            public void success(Boolean accepted) { settle(request); }
            public void failure(String message) {
                if(request.dispatched) settle(request);
                else finish(request,false,message);
            }
        };
    }
    private void settle(Request request) {
        synchronized(this) {
            if(!request.dispatched || request.settled) return;
            request.settled=true;
        }
        // This verification survives owner cancellation/deadline: the aircraft
        // operation cannot be cancelled by closing an Android view.
        try { port.read(new LedJob.Reply<Integer>() {
            public void success(Integer actual) {
                synchronized(ForearmLedJob.this) {
                    if(request.verified) return;
                    request.verified=true;
                    if(layout(actual) && actual==request.expected) {
                        fence.reconciled(request.token);
                        finish(request,true,"Đã cập nhật LED; giá trị đọc lại khớp.");
                    } else finish(request,false,"Giá trị LED đọc lại chưa khớp; thao tác tiếp theo bị khóa.");
                }
            }
            public void failure(String message) {
                synchronized(ForearmLedJob.this) {
                    if(request.verified) return; request.verified=true;
                    finish(request,false,"Chưa đọc lại được LED; thao tác tiếp theo bị khóa.");
                }
            }
        }); } catch(RuntimeException | LinkageError error) { finish(request,false,"Không xác nhận được LED sau khi gửi lệnh."); }
    }
    private void finish(Request request,boolean ok,String message) {
        LedJob.Result result; LedJob.Cancel deadline;
        synchronized(this) {
            if(current!=request) return;
            current=null; result=request.result; request.result=null;
            deadline=request.deadline; request.deadline=null;
            if(!request.dispatched && request.token!=null) fence.reconciled(request.token);
        }
        if(deadline!=null) deadline.cancel();
        if(ok && clock.getAsLong()>=request.deadlineNanos) { ok=false; message="Hết thời gian chờ LED; giá trị mới đã được đối chiếu."; }
        if(result!=null && !closed && !closeRequested) result.finished(ok,message);
    }
    void close() {
        Request request;
        closeRequested=true;
        synchronized(submissionLock) {
            synchronized(this) { closed=true; request=current; if(request!=null) request.result=null; }
        }
        if(request!=null) finish(request,false,"Đã đóng menu LED.");
    }
}
