package local.rc2.hud;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;

/** User-initiated, cancellable one-shot LED writes to the RC's loopback proxy.
 * Transport responses are not decoded as aircraft parameter readback.
 */
final class LedClient {
    interface Callback { void finished(Result result); }
    interface Sender { boolean write(byte[] packet) throws IOException; void cancel(); }
    static final class Result {
        final int sent, responses;
        final boolean cancelled;
        final String error;
        Result(int sent, int responses, boolean cancelled, String error) {
            this.sent = sent; this.responses = responses; this.cancelled = cancelled; this.error = error;
        }
        boolean complete() { return !cancelled && sent == 10; }
    }
    private final Sender sender;
    private volatile boolean cancelled;
    private Thread job;
    private int sequence;
    LedClient() { this(new TcpSender(40007), 0x1000 | (int)(System.nanoTime() & 0xfff)); }
    LedClient(Sender sender, int sequence) { this.sender = sender; this.sequence = sequence; }
    synchronized boolean send(boolean on, Callback callback) {
        if (cancelled || job != null) return false;
        job = new Thread(() -> run(on, callback), "RC2-LedOnce");
        job.setDaemon(true); job.start();
        return true;
    }
    private void run(boolean on, Callback callback) {
        int sent = 0, responses = 0;
        String error = "";
        try {
            for (int index = 0; index < 10; index++) {
                if (cancelled || Thread.currentThread().isInterrupted()) break;
                if (sender.write(LedProtocol.frame(on, sequence++ & 0xffff))) responses++;
                sent++;
                if (index != 9) Thread.sleep(100);
            }
        } catch (IOException disconnected) {
            // A partial write sequence is reported explicitly; never mark the LED state as confirmed.
            error = disconnected.getClass().getSimpleName();
        } catch (RuntimeException denied) {
            error = denied.getClass().getSimpleName();
        } catch (InterruptedException stopped) { Thread.currentThread().interrupt(); }
        finally {
            synchronized (this) { job = null; }
            callback.finished(new Result(sent, responses, cancelled, error));
        }
    }
    synchronized void cancel() {
        cancelled = true;
        if (job != null) job.interrupt();
        sender.cancel();
    }
    static final class TcpSender implements Sender {
        private final int port;
        private boolean stopped;
        private Socket active;
        TcpSender(int port) { this.port = port; }
        @Override public boolean write(byte[] packet) throws IOException {
            Socket socket = new Socket();
            synchronized (this) {
                if (stopped) { socket.close(); throw new IOException("LED sender stopped"); }
                active = socket;
            }
            try {
                socket.connect(new InetSocketAddress("127.0.0.1", port), 1500);
                socket.setTcpNoDelay(true); socket.setSoTimeout(100);
                socket.getOutputStream().write(packet); socket.getOutputStream().flush();
                try { return socket.getInputStream().read(new byte[128]) > 0; }
                catch (SocketTimeoutException noResponse) { return false; }
                catch (IOException readFailed) { return false; }
            } finally {
                synchronized (this) { if (active == socket) active = null; }
                socket.close();
            }
        }
        @Override public synchronized void cancel() {
            stopped = true;
            if (active != null) try { active.close(); } catch (IOException ignored) { /* closed in writer finally */ }
        }
    }
}
