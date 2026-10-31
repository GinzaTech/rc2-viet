package local.rc2.hud;

/** One bounded LED transaction. Cancellation prevents subsequent SDK operations. */
final class LedJob {
    interface Reply<T> { void success(T value); void failure(String message); default boolean active() { return true; } }
    interface Result { void finished(boolean success,String message); }
    interface Cancel { void cancel(); }
    interface Scheduler { Cancel schedule(Runnable task,long delayMillis); }
    interface Port {
        GroundGate snapshot();
        void ground(Reply<GroundGate> reply);
        void read(Reply<Lights> reply);
        void write(Lights lights,Reply<Boolean> reply);
    }
    interface Next<T> { void run(T value); }
    static final class Lights {
        final boolean front,status,rear,navigation;
        Lights(boolean front,boolean status,boolean rear,boolean navigation) {
            this.front=front; this.status=status; this.rear=rear; this.navigation=navigation;
        }
        Lights front(boolean on) { return new Lights(on,status,rear,navigation); }
        boolean matches(Lights other) {
            return other!=null && front==other.front && status==other.status && rear==other.rear
                && navigation==other.navigation;
        }
    }
    private static final class Request {
        final boolean on;
        final Result result;
        int phase=1;
        Cancel deadline;
        boolean reported;
        Request(boolean on,Result result) { this.on=on; this.result=result; }
    }
    private final Port port;
    private final Scheduler scheduler;
    private Request current;
    private boolean closed;
    LedJob(Port port,Scheduler scheduler) { this.port=port; this.scheduler=scheduler; }
    GroundGate state() { return port.snapshot(); }
    synchronized boolean request(boolean on,Result result) {
        if(closed) return false;
        if(current!=null) { result.finished(false,"Đang xử lý LED. Chờ kết quả trước khi thao tác lại."); return false; }
        GroundGate gate=state();
        if(!gate.allowed()) { result.finished(false,gate.explanation()); return false; }
        Request request=new Request(on,result); current=request;
        try {
            request.deadline=scheduler.schedule(()->timeout(request),6000);
            if(current!=request) { request.deadline.cancel(); return false; }
            port.ground(reply(request,1,value->{
                if(!allow(request,value)) return;
                port.read(reply(request,2,lights->read(request,lights)));
            }));
            return true;
        } catch(RuntimeException | LinkageError error) { finish(request,false,"SDK LED chưa hỗ trợ trên phiên bản/máy bay này."); return false; }
    }
    private void read(Request request,Lights lights) {
        if(lights==null) { finish(request,false,"Không xác định đủ trạng thái LED; không gửi lệnh."); return; }
        if(lights.front==request.on) { finish(request,true,request.on?"LED phía trước đang bật.":"LED phía trước đang tắt."); return; }
        Lights updated=lights.front(request.on);
        port.ground(reply(request,3,gate->{
            if(!allow(request,gate) || !allow(request,state())) return;
            port.write(updated,reply(request,4,accepted->{
                if(!Boolean.TRUE.equals(accepted)) { finish(request,false,"Máy bay từ chối thay đổi LED."); return; }
                port.read(reply(request,5,actual->{
                    boolean confirmed=updated.matches(actual);
                    finish(request,confirmed,confirmed ? (request.on?"Đã bật LED phía trước.":"Đã tắt LED phía trước.")
                        : "Trạng thái LED đọc lại chưa khớp; chưa xác nhận thay đổi.");
                }));
            }));
        }));
    }
    private boolean allow(Request request,GroundGate gate) {
        if(gate!=null && gate.allowed()) return true;
        finish(request,false,gate==null?GroundGate.unknown().explanation():gate.explanation()); return false;
    }
    private <T> Reply<T> reply(Request request,int phase,Next<T> next) {
        return new Reply<T>() {
            public boolean active() {
                synchronized(LedJob.this) { return !closed && current==request && !request.reported && request.phase==phase; }
            }
            public void success(T value) {
                synchronized(LedJob.this) {
                    if(closed || current!=request || request.phase!=phase) return;
                    request.phase++;
                    try { next.run(value); }
                    catch(RuntimeException | LinkageError error) { finish(request,false,"Không xác nhận được phản hồi LED từ SDK."); }
                }
            }
            public void failure(String message) {
                synchronized(LedJob.this) {
                    if(closed || current!=request || request.phase!=phase) return;
                    request.phase++; finish(request,false,message);
                }
            }
        };
    }
    private synchronized void timeout(Request request) {
        if(current!=request || request.reported) return;
        if(request.phase<4) { finish(request,false,"Hết thời gian chờ phản hồi LED; chưa gửi lệnh thay đổi."); return; }
        request.reported=true;
        if(request.deadline!=null) request.deadline.cancel();
        request.result.finished(false,"Lệnh LED đã gửi nhưng chưa xác nhận. Khóa thao tác tiếp theo đến khi đọc lại được kết quả.");
    }
    private void finish(Request request,boolean success,String message) {
        if(current!=request) return;
        current=null;
        if(request.deadline!=null) request.deadline.cancel();
        if(!closed && !request.reported) { request.reported=true; request.result.finished(success,message); }
    }
    synchronized void close() {
        closed=true;
        if(current!=null && current.deadline!=null) current.deadline.cancel();
        current=null;
    }
}
