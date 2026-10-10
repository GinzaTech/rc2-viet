// SPDX-License-Identifier: AGPL-3.0-only
// Fixed profile attribution: doesthings/FreeFCC v1.5.5, upstream AGPL-3.0.
// The adapter and lifecycle implementation are local; see RadioProtocol.java for provenance.
package local.rc2.hud;

import java.io.IOException;
import java.util.Timer;
import java.util.TimerTask;

/**
 * Self-contained grounded radio adapter. Runtime uses the stock SDK ForceFcc
 * setter and a fresh readback of its SDR override. This proves the observed
 * override value, not measured RF power/mode. Restore uses the immutable value
 * observed before apply, bound to the aircraft identity; it never guesses CE.
 * Legacy fixed-profile senders remain host-testable through the same interface.
 *
 * The owner may retain this instance from menu to camera until a request ends;
 * closing a popup need not close it. close() is terminal on owner teardown.
 * No automatic radio writes on construction, navigation, reconnect, idle or
 * in the background. Persistence under DJI Fly is tested separately; a stored
 * requested mode is never reported as an effective or maintained RF mode.
 * No repeating radio writer is enabled in this candidate.
 */
final class NativeRadio {
    interface Result { void finished(boolean ok,String message); }
    interface Aircraft { GroundGate snapshot(); void ground(LedJob.Reply<GroundGate> reply); }
    interface Sender {
        void send(boolean fcc,RadioTransport.Guard guard) throws IOException;
        void close();
        default RadioDiagnostics.Report diagnostics() { return RadioDiagnostics.Report.empty(); }
        default boolean verified() { return false; }
        default String userMessage() { return ""; }
        default void onReconciled(Runnable callback) { }
    }
    interface Factory { Sender create(); }
    interface Cancel { void cancel(); }
    interface Observer { void changed(Status status); }
    static final class Status {
        final boolean busy,locked;
        final String message;
        Status(boolean busy,boolean locked,String message) { this.busy=busy; this.locked=locked; this.message=message; }
    }
    interface Runtime { Cancel start(Runnable task); Cancel after(Runnable task,long delay); }
    static final long DEADLINE_MILLIS=10000;
    private static final MutationFence MUTATIONS=MutationFence.hardware();
    private static final class Request {
        final boolean fcc;
        final Result result;
        final Object token;
        final long deadlineNanos;
        Cancel deadline,worker;
        Sender sender;
        boolean groundAnswered,dispatched,unsafe;
        Request(boolean fcc,Result result,Object token,long startedNanos) {
            this.fcc=fcc; this.result=result; this.token=token;
            deadlineNanos=startedNanos+DEADLINE_MILLIS*1000000L;
        }
    }
    private final Aircraft aircraft;
    private final Factory factory;
    private final Runtime runtime;
    private final MutationFence mutations;
    private final java.util.function.LongSupplier clock;
    private Request current;
    private boolean closed;
    private String lastMessage="";
    private final java.util.List<Observer> observers=new java.util.ArrayList<>();
    NativeRadio(ClassLoader loader) {
        this(aircraft(loader),new SdkRadioSender.Factory(loader),new Runtime() {
            public Cancel start(Runnable task) {
                Thread worker=new Thread(task,"RC2-RadioRequest"); worker.setDaemon(true); worker.start();
                return worker::interrupt;
            }
            public Cancel after(Runnable task,long delay) {
                Timer timer=new Timer("RC2-RadioDeadline",true);
                timer.schedule(new TimerTask() { public void run() { task.run(); } },delay);
                return timer::cancel;
            }
        },MUTATIONS);
    }
    NativeRadio(Aircraft aircraft,Factory factory,Runtime runtime,MutationFence mutations) {
        this(aircraft,factory,runtime,mutations,System::nanoTime);
    }
    NativeRadio(Aircraft aircraft,Factory factory,Runtime runtime,MutationFence mutations,java.util.function.LongSupplier clock) {
        this.aircraft=aircraft; this.factory=factory; this.runtime=runtime; this.mutations=mutations;
        this.clock=clock;
    }
    private static Aircraft aircraft(ClassLoader loader) {
        NativeAircraft nativeAircraft=new NativeAircraft(loader);
        return new Aircraft() {
            public GroundGate snapshot() { return nativeAircraft.snapshot(); }
            public void ground(LedJob.Reply<GroundGate> reply) { nativeAircraft.readGround(reply); }
        };
    }
    GroundGate state() {
        try { GroundGate gate=aircraft.snapshot(); return gate==null?GroundGate.unknown():gate; }
        catch(RuntimeException | LinkageError error) { return GroundGate.unknown(); }
    }
    synchronized Status status() {
        boolean locked=mutations.pending();
        String message=lastMessage;
        if(message.isEmpty() && locked) message="Lệnh điều khiển trước chưa kết thúc; thao tác bị khóa.";
        return new Status(current!=null,locked,message);
    }
    Cancel observe(Observer observer) {
        Status initial;
        synchronized(this) { if(!closed) observers.add(observer); initial=status(); }
        try { observer.changed(initial); }
        catch(RuntimeException | LinkageError error) { synchronized(this) { observers.remove(observer); } }
        return ()->{synchronized(NativeRadio.this) { observers.remove(observer); }};
    }
    private void publish() {
        Status value; java.util.List<Observer> targets;
        synchronized(this) { value=status(); targets=new java.util.ArrayList<>(observers); }
        for(Observer observer:targets) {
            try { observer.changed(value); }
            catch(RuntimeException | LinkageError error) { synchronized(this) { observers.remove(observer); } }
        }
    }
    boolean request(boolean fcc,Result result) {
      if(result==null) return false;
      Request created=null; String rejection=null;
      GroundGate gate=state();
      synchronized(this) {
        if(closed) return false;
        if(current!=null) rejection="Đang xử lý yêu cầu radio. Chờ kết quả trước khi thao tác lại.";
        else if(!gate.allowed()) rejection=gate.explanation();
        else {
            Object token=mutations.begin();
            if(token==null) rejection="Lệnh điều khiển trước chưa kết thúc; thao tác bị khóa trong tiến trình này.";
            else {
                created=new Request(fcc,result,token,clock.getAsLong()); current=created;
                lastMessage=fcc?"Đang xử lý yêu cầu FCC…":"Đang khôi phục vùng gốc…";
            }
        }
      }
      if(rejection!=null) { notifyResult(result,false,rejection);return false; }
      Request request=created;
        try {
            publish();
            Cancel deadline=runtime.after(()->timeout(request),DEADLINE_MILLIS);
            boolean retained;
            synchronized(this) { retained=current==request; if(retained) request.deadline=deadline; }
            if(!retained) cancelHandle(deadline);
            if(!active(request)) {
                timeout(request);
                return false;
            }
            aircraft.ground(groundReply(request));
            return true;
        } catch(RuntimeException | LinkageError error) {
            finish(request,false,"Không đọc được trạng thái SDK hoặc mở tác vụ radio."); return false;
        }
    }
    private LedJob.Reply<GroundGate> groundReply(Request request) {
        return new LedJob.Reply<GroundGate>() {
            public boolean active() {
                synchronized(NativeRadio.this) { return NativeRadio.this.active(request) && !request.groundAnswered; }
            }
            public void success(GroundGate value) {
                synchronized(NativeRadio.this) {
                    if(!active()) return;
                    request.groundAnswered=true;
                }
                    if(value==null || !value.allowed()) {
                        finish(request,false,value==null?GroundGate.unknown().explanation():value.explanation()); return;
                    }
                    GroundGate latest=state();
                    if(!latest.allowed()) { finish(request,false,latest.explanation()); return; }
                    try {
                        Sender sender=factory.create();
                        sender.onReconciled(()->mutations.reconciled(request.token));
                        boolean retained;
                        synchronized(NativeRadio.this) { retained=NativeRadio.this.active(request); if(retained) request.sender=sender; }
                        if(!retained) { cancelHandle(sender::close); return; }
                        Cancel worker=runtime.start(()->send(request));
                        synchronized(NativeRadio.this) { retained=NativeRadio.this.active(request); if(retained) request.worker=worker; }
                        if(!retained) cancelHandle(worker);
                    } catch(RuntimeException | LinkageError error) { finish(request,false,"Không mở được tác vụ radio."); }
            }
            public void failure(String message) {
                synchronized(NativeRadio.this) {
                    if(!active()) return;
                    request.groundAnswered=true;
                }
                finish(request,false,"Không đọc được trạng thái máy bay mới nhất; không gửi lệnh radio.");
            }
        };
    }
    private synchronized boolean active(Request request) {
        return !closed && current==request && clock.getAsLong()<request.deadlineNanos;
    }
    private RadioTransport.Guard guard(Request request) {
        return new RadioTransport.Guard() {
            public boolean allowed() {
                synchronized(NativeRadio.this) {
                    if(!active(request) || request.unsafe) return false;
                    if(!state().allowed()) { request.unsafe=true; return false; }
                    return true;
                }
            }
            public void dispatched() throws IOException {
                synchronized(NativeRadio.this) {
                    if(!allowed()) throw new IOException("Radio request inactive before dispatch");
                    request.dispatched=true;
                }
            }
        };
    }
    private void send(Request request) {
        boolean ok=false;
        String message="Yêu cầu radio thất bại; chế độ hiệu lực chưa xác nhận.";
        try {
            RadioTransport.Guard guard=guard(request);
            if(!guard.allowed()) throw new IOException("Radio request inactive");
            request.sender.send(request.fcc,guard);
            if(!guard.allowed()) throw new IOException("Radio request cancelled before completion");
            ok=true;
            message=request.fcc
                ? "Đã gửi đủ profile FCC; chế độ radio hiệu lực chưa xác nhận. DJI Fly có thể đặt lại vùng; không chạy keepalive."
                : "Đã gửi yêu cầu khôi phục vùng nhà máy (không có ACK); vùng và chế độ hiệu lực chưa xác nhận. Thao tác tiếp theo bị khóa.";
        } catch(IOException | RuntimeException | LinkageError error) {
            // A possibly dispatched write is fenced; no retry, rollback or exit-service write.
        }
            if(request.sender!=null && !request.sender.userMessage().isEmpty()) message=request.sender.userMessage();
            // ACK_BEFORE_EXEC and successful writes do not prove execution/readback.
            // Keep the same hardware fence used by LED until independent reconciliation.
            finish(request,ok,message);
    }
    private void timeout(Request request) {
        finish(request,false,"Hết thời gian chờ radio; chế độ hiệu lực chưa xác nhận.");
    }
    private void finish(Request request,boolean ok,String message) {
      synchronized(this) {
        if(current!=request) return;
        current=null;
        if(!request.dispatched || request.sender!=null && request.sender.verified()) mutations.reconciled(request.token);
        String diagnostic=request.sender==null?"":diagnostic(request.sender);
        lastMessage=message+(mutations.pending()?" Lệnh có thể đã gửi; thao tác bị khóa.":"")+diagnostic;
      }
        // Sender cleanup may wait for SDK entry; never hold the owner/guard monitor.
        cancel(request); publish();
        if(!closed) notifyResult(request.result,ok,lastMessage);
    }
    private static String diagnostic(Sender sender) {
        try {
            RadioDiagnostics.Report report=sender.diagnostics();
            return report==null || report.total==0?"":" [Radio "+report.summary()+"]";
        } catch(RuntimeException | LinkageError error) { return ""; }
    }
    private static void cancel(Request request) {
        if(request.sender!=null) cancelHandle(request.sender::close);
        cancelHandle(request.deadline);
        cancelHandle(request.worker);
    }
    private static void cancelHandle(Cancel handle) {
        if(handle==null) return;
        try { handle.cancel(); }
        catch(RuntimeException | LinkageError error) { /* Attempt other cleanup and preserve the result/fence. */ }
    }
    private static void notifyResult(Result result,boolean ok,String message) {
        try { result.finished(ok,message); }
        catch(RuntimeException | LinkageError error) { /* Consumer failure cannot restart radio IO or leak its resources. */ }
    }
    void close() {
      Request request;
      synchronized(this) {
        closed=true;
        if(current==null) { observers.clear(); return; }
        request=current; current=null;
        if(!request.dispatched) mutations.reconciled(request.token);
        lastMessage=(mutations.pending()?"Tác vụ radio đã dừng; lệnh trước chưa xác nhận, thao tác bị khóa.":"Tác vụ radio đã dừng trước khi gửi lệnh.")
            +(request.sender==null?"":diagnostic(request.sender));
      }
        cancel(request); publish();
        synchronized(this) { observers.clear(); }
    }
}
