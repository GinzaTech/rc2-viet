package local.rc2.hud;

import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class HudInteractionTest {
    static void check(boolean ok, String why) { if (!ok) throw new AssertionError(why); }
    static boolean tap(TripleTap detector, long time, float x, float y) {
        detector.down(time, x, y, true, 1);
        return detector.up(time + 45, x, y, 1);
    }
    static TripleTap detector() { return new TripleTap(12, 36); }
    static void gestures() {
        TripleTap d = detector();
        check(!tap(d, 0, 100, 100), "one tap must not toggle");
        check(!tap(d, 160, 102, 99), "two taps must not toggle");
        check(tap(d, 320, 103, 101), "three close taps toggle");
        check(!tap(d, 430, 100, 100), "cooldown prevents repeated toggle");
        check(!tap(d, 620, 100, 100), "cooldown tap is not a new sequence");
        d = detector();
        tap(d, 0, 100, 100); tap(d, 180, 100, 100);
        check(!tap(d, 650, 100, 100), "long gap starts over");
        check(!tap(d, 800, 100, 100), "only second tap after gap");
        check(tap(d, 950, 100, 100), "fresh sequence after gap");
        d = detector(); tap(d, 0, 100, 100); tap(d, 180, 100, 100);
        check(!tap(d, 350, 200, 100), "distant third tap is new sequence");
        d = detector(); tap(d, 0, 100, 100);
        d.down(150, 100, 100, true, 1); d.move(125, 100, 1);
        check(!d.up(200, 100, 100, 1), "drag returning to origin is not tap");
        check(!tap(d, 300, 100, 100) && !tap(d, 450, 100, 100), "drag clears sequence");
        d = detector(); tap(d, 0, 100, 100); d.down(150, 100, 100, true, 2);
        check(!d.up(200, 100, 100, 1), "multitouch resets");
        check(!tap(d, 300, 100, 100) && !tap(d, 450, 100, 100), "multitouch clears sequence");
        d = detector(); tap(d, 0, 100, 100); d.down(150, 100, 100, false, 1);
        d.up(200, 100, 100, 1);
        check(!tap(d, 300, 100, 100) && !tap(d, 450, 100, 100), "UI control clears sequence");
        d = detector(); tap(d, 0, 100, 100); d.down(150, 100, 100, true, 1);
        check(!d.up(500, 100, 100, 1), "long press is not tap");
        d = detector(); tap(d, 0, 100, 100); tap(d, 150, 100, 100); d.reset();
        check(!tap(d, 300, 100, 100), "pause or cancellation resets");
        d = detector(); d.down(200, 100, 100, true, 1);
        check(!d.up(190, 100, 100, 1), "backward clock rejected");
    }
    public interface OriginalWindow {
        boolean dispatchTouchEvent(Object event);
        int other(int input);
        void onWindowFocusChanged(boolean focused);
        void throwOriginal();
    }
    static void delegation() {
        AtomicInteger dispatched = new AtomicInteger(), observed = new AtomicInteger(), faults = new AtomicInteger();
        Object event = new Object();
        IllegalStateException originalFailure = new IllegalStateException("original-window-error");
        OriginalWindow target = new OriginalWindow() {
            public boolean dispatchTouchEvent(Object e) { check(e == event, "same event"); dispatched.incrementAndGet(); return false; }
            public int other(int n) { return n + 7; }
            public void onWindowFocusChanged(boolean focused) { }
            public void throwOriginal() { throw originalFailure; }
        };
        TouchDispatch observer = new TouchDispatch(new TouchDispatch.Observer() {
            public void before(Object e) { check(dispatched.get() == observed.get(), "before original"); }
            public void after(Object e) { observed.incrementAndGet(); }
            public void focusChanged(boolean focused) { if (!focused) observed.addAndGet(10); }
            public void failed(RuntimeException e) { faults.incrementAndGet(); }
        });
        OriginalWindow wrapped = observer.wrap(OriginalWindow.class, target);
        check(!wrapped.dispatchTouchEvent(event), "retain false return value");
        check(dispatched.get() == 1 && observed.get() == 1, "delegate and observe once");
        check(wrapped.other(10) == 17 && observed.get() == 1, "delegate other methods");
        try { wrapped.throwOriginal(); throw new AssertionError("exception swallowed"); }
        catch (IllegalStateException failure) { check(failure == originalFailure, "unwrap original exception"); }
        wrapped.onWindowFocusChanged(false);
        check(observed.get() == 11, "focus loss reaches observer for sequence reset");
        observer.stop(); wrapped.dispatchTouchEvent(event);
        check(dispatched.get() == 2 && observed.get() == 11, "pause disables observer while delegate remains");
        TouchDispatch bad = new TouchDispatch(new TouchDispatch.Observer() {
            public void before(Object e) { throw new IllegalStateException("observer"); }
            public void after(Object e) { throw new IllegalStateException("observer"); }
            public void failed(RuntimeException e) { faults.incrementAndGet(); }
        });
        check(!bad.wrap(OriginalWindow.class, target).dispatchTouchEvent(event), "observer failure never consumes input");
        check(dispatched.get() == 3 && faults.get() == 2, "original dispatch survives observer failure");
    }
    static byte[] hex(String text) {
        byte[] bytes = new byte[text.length()/2];
        for (int n=0; n<bytes.length; n++) bytes[n]=(byte)Integer.parseInt(text.substring(n*2,n*2+2),16);
        return bytes;
    }
    static void frames() {
        // Golden vectors are computed independently from FreeFCC v1.5.5's LED profile and CRC tables.
        check(Arrays.equals(LedProtocol.frame(false, 0x1000), hex("55cc307512000000551204c7020300104003f9a259ceed00b793")), "LED OFF wire vector");
        check(Arrays.equals(LedProtocol.frame(true, 0x1000), hex("55cc307512000000551204c7020300104003f9a259ceedef4e8c")), "LED ON wire vector");
        check(!Arrays.equals(LedProtocol.frame(false, 0x1000), LedProtocol.frame(false, 0x1001)), "sequence advances");
        try { LedProtocol.frame(false, -1); throw new AssertionError("negative sequence"); }
        catch (IllegalArgumentException expected) { }
    }
    static LedClient.Result waitResult(LedClient client, boolean on) throws Exception {
        CountDownLatch ready = new CountDownLatch(1);
        AtomicReference<LedClient.Result> result = new AtomicReference<>();
        check(client.send(on, value -> { result.set(value); ready.countDown(); }), "request accepted");
        check(ready.await(8, TimeUnit.SECONDS), "bounded completion");
        return result.get();
    }
    static void transport() throws Exception {
        AtomicInteger received = new AtomicInteger();
        AtomicReference<Throwable> failed = new AtomicReference<>();
        try (ServerSocket server = new ServerSocket(0, 16, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(4000);
            Thread reader = new Thread(() -> {
                try {
                    for (int n=0; n<10; n++) try (Socket socket=server.accept()) {
                        byte[] value = new byte[26];
                        int read=0;
                        while (read<value.length) {
                            int count=socket.getInputStream().read(value,read,value.length-read);
                            if(count<0) throw new IOException("short frame");
                            read+=count;
                        }
                        check(Arrays.equals(value, LedProtocol.frame(false, 0x1000+n)), "exact local TCP frame");
                        received.incrementAndGet();
                        socket.getOutputStream().write(1); socket.getOutputStream().flush();
                    }
                } catch(Throwable error) { failed.set(error); }
            });
            reader.start();
            LedClient client = new LedClient(new LedClient.TcpSender(server.getLocalPort()), 0x1000);
            LedClient.Result result=waitResult(client,false);
            reader.join(5000);
            check(!reader.isAlive() && failed.get()==null, "synthetic TCP server finished");
            check(result.sent==10 && result.responses==10 && result.complete() && received.get()==10, "ten writes with responses");
            client.cancel();
        }
        AtomicInteger count=new AtomicInteger();
        LedClient.Sender partial = new LedClient.Sender() {
            public boolean write(byte[] bytes) throws IOException { if(count.incrementAndGet()==3) throw new IOException("drop"); return false; }
            public void cancel() { }
        };
        LedClient client=new LedClient(partial,0x1000);
        LedClient.Result result=waitResult(client,true);
        check(result.sent==2 && result.responses==0 && !result.complete(), "partial/no readback not success");
        client.cancel();
        int unused;
        try(ServerSocket temporary=new ServerSocket(0)) { unused=temporary.getLocalPort(); }
        client=new LedClient(new LedClient.TcpSender(unused),0x1000);
        result=waitResult(client,false);
        check(result.sent==0 && !result.complete(), "disconnected proxy fails");
        client.cancel();
        client=new LedClient(new LedClient.Sender() {
            public boolean write(byte[] bytes) { throw new SecurityException("synthetic permission denial"); }
            public void cancel() { }
        },0x1000);
        result=waitResult(client,false);
        check(result.sent==0 && !result.complete() && result.error.equals("SecurityException"), "permission denial is reported without worker crash");
        client.cancel();
    }
    static void cancellation() throws Exception {
        CountDownLatch entered=new CountDownLatch(1), released=new CountDownLatch(1), finished=new CountDownLatch(1);
        AtomicInteger writes=new AtomicInteger();
        AtomicReference<LedClient.Result> result=new AtomicReference<>();
        LedClient client=new LedClient(new LedClient.Sender() {
            public boolean write(byte[] bytes) throws IOException {
                writes.incrementAndGet(); entered.countDown();
                try { released.await(); } catch(InterruptedException e) { throw new IOException("cancelled"); }
                return false;
            }
            public void cancel() { released.countDown(); }
        },0x1000);
        check(client.send(false,value->{result.set(value);finished.countDown();}),"first send");
        check(entered.await(2,TimeUnit.SECONDS),"worker started");
        check(!client.send(true,value->{}),"busy prevents duplicate sends");
        client.cancel();
        check(finished.await(2,TimeUnit.SECONDS),"cancel finishes promptly");
        check(result.get().cancelled && writes.get()==1,"no sends after cancellation");
        check(!client.send(true,value->{}),"disposed client never restarts");
    }
    public static void main(String[] args) throws Exception {
        gestures(); delegation(); frames(); transport(); cancellation();
        System.out.println("hud_interactions_passed");
    }
}
