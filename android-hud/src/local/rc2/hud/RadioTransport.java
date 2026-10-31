// SPDX-License-Identifier: AGPL-3.0-only
// Profile/transport provenance: doesthings/FreeFCC v1.5.5 (AGPL-3.0),
// commit 597157bd52120dfeb9677f79a8ad46b6027ce8dc; see RadioProtocol.java.
package local.rc2.hud;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * One fixed universal profile, one frame per connection to RC2's 127.0.0.1:40009.
 * Upstream sendFrames attempts every frame and ignores ACK drain errors. ACKs
 * here are bounded observations, not a prerequisite for subsequent model-specific
 * frames. All writes must succeed for delivery completion. No mode assertion,
 * port scanning, retries, rollback, keepalive or guard bypass.
 */
final class RadioTransport implements NativeRadio.Sender {
    interface Guard { boolean allowed(); void dispatched() throws IOException; }
    interface SocketFactory { Socket create() throws IOException; }
    interface Pause { void sleep(int millis) throws InterruptedException; }
    interface Observer { void frame(RadioDiagnostics.Frame value); }
    private static final AtomicInteger SEQUENCE=new AtomicInteger(0x1000+(int)(System.nanoTime()&0xfff));
    private static final int CONNECT_MILLIS=500;
    private final SocketFactory sockets;
    private final Pause delay;
    private final Observer observer;
    private volatile Socket active;
    private volatile boolean closed;
    private volatile boolean stopped;
    private static final class Cancelled extends IOException {
        Cancelled() { super("Radio request cancelled or unsafe"); }
    }
    private volatile RadioDiagnostics.Report report=RadioDiagnostics.Report.empty();
    RadioTransport() { this(Socket::new); }
    /** PC sockets redirect the fixed endpoint to an ephemeral loopback port. */
    RadioTransport(SocketFactory sockets) {
        this(sockets,Thread::sleep,value->System.err.println("RC2-Radio "+value.summary()));
    }
    RadioTransport(SocketFactory sockets,Pause delay,Observer observer) {
        this.sockets=sockets; this.delay=delay; this.observer=observer;
    }
    public RadioDiagnostics.Report diagnostics() { return report; }
    public void send(boolean fcc,Guard guard) throws IOException {
        requireActive(guard);
        RadioProtocol.Profile profile=RadioProtocol.profile(fcc,SEQUENCE.getAndAdd(fcc?21:1)&65535);
        report=RadioDiagnostics.Report.start(profile.count());
        for(int index=0;index<profile.count();index++) {
            requireActive(guard);
            byte[] packet=profile.packet(index);
            RadioDiagnostics.Frame frame=RadioDiagnostics.Frame.begin(index,profile,packet);
            progress(frame);
            frame=exchange(packet,profile,guard,frame); progress(frame); emit(frame);
            pause(profile.frameDelayMillis,guard);
            if((index+1)%profile.roundSize()==0 && index+1<profile.count()) pause(profile.roundDelayMillis,guard);
        }
        requireActive(guard); report=report.completed();
        if(report.writeFailures>0) throw new IOException("Radio profile has failed writes");
    }
    private RadioDiagnostics.Frame exchange(byte[] packet,RadioProtocol.Profile profile,Guard guard,
            RadioDiagnostics.Frame frame) throws IOException {
        requireActive(guard);
        Socket socket=null;
        try {
            try {
                socket=sockets.create(); active=socket; requireActive(guard);
                socket.connect(new InetSocketAddress("127.0.0.1",40009),CONNECT_MILLIS);
                socket.setTcpNoDelay(true);
            } catch(IOException error) {
                requireActive(guard); return frame.stage(RadioDiagnostics.Stage.CONNECT_FAILED);
            }
            OutputStream output;
            try { output=socket.getOutputStream(); }
            catch(IOException error) {
                requireActive(guard); return frame.stage(RadioDiagnostics.Stage.WRITE_FAILED);
            }
            requireActive(guard);
            // Latch uncertainty before any byte might enter the proxy.
            // Stream acquisition precedes authorization. NativeRadio.dispatched()
            // commits the handoff under its request lock; close still unblocks IO.
            guard.dispatched(); frame=frame.stage(RadioDiagnostics.Stage.DISPATCHING); progress(frame);
            requireActive(guard);
            try { output.write(packet); output.flush(); }
            catch(IOException error) {
                frame=frame.stage(RadioDiagnostics.Stage.WRITE_FAILED); progress(frame);
                requireActive(guard); return frame;
            }
            frame=frame.stage(RadioDiagnostics.Stage.WRITTEN); progress(frame);
            if((packet[8]&0x60)==0) return frame.ack(RadioDiagnostics.Ack.NOT_EXPECTED,
                RadioDiagnostics.Ack.NOT_READ,null,-1,0,0);
            return readAck(socket,packet,profile.readMillis,guard,frame);
        } finally {
            if(socket!=null) {
                try { socket.close(); } catch(IOException error) { /* Upstream ignores close/drain errors. */ }
                finally { if(active==socket) active=null; }
            }
        }
    }
    private RadioDiagnostics.Frame readAck(Socket socket,byte[] request,int readMillis,Guard guard,
            RadioDiagnostics.Frame frame) throws IOException {
        long deadline=System.nanoTime()+readMillis*1000000L;
        Read state=new Read(deadline);
        RadioDiagnostics.Ack mismatch=RadioDiagnostics.Ack.NOT_READ;
        RadioDiagnostics.Metadata metadata=null;
        int observed=0;
        try {
            InputStream input=socket.getInputStream();
            for(;observed<64;observed++) {
                state.frameBytes=0;
                byte[] header=new byte[4]; read(input,socket,header,0,4,state,guard);
                int length=RadioProtocol.length(header);
                if(length<0) return frame.ack(RadioDiagnostics.Ack.INVALID_HEADER,mismatch,metadata,-1,state.received,observed);
                byte[] response=new byte[length]; System.arraycopy(header,0,response,0,4);
                read(input,socket,response,4,length-4,state,guard);
                RadioDiagnostics.Ack reason=RadioProtocol.classify(request,response);
                metadata=RadioDiagnostics.Metadata.of(response);
                if(reason==RadioDiagnostics.Ack.INVALID_CRC) return frame.ack(reason,mismatch,null,-1,state.received,observed+1);
                if(!RadioProtocol.matches(request,response)) { mismatch=reason; continue; }
                int status=reason==RadioDiagnostics.Ack.ZERO_STATUS || reason==RadioDiagnostics.Ack.NONZERO_STATUS
                    ?response[11]&255:-1;
                requireActive(guard);
                return frame.ack(reason,mismatch,metadata,status,state.received,observed+1);
            }
            return frame.ack(RadioDiagnostics.Ack.FRAME_LIMIT,mismatch,metadata,-1,state.received,observed);
        } catch(Cancelled error) {
            cancelledAck(frame,mismatch,metadata,state.received,observed); throw error;
        } catch(IOException error) {
            try { requireActive(guard); }
            catch(Cancelled cancelled) {
                cancelledAck(frame,mismatch,metadata,state.received,observed); throw cancelled;
            }
            return frame.ack(state.failure,mismatch,metadata,-1,state.received,observed);
        }
    }
    private void cancelledAck(RadioDiagnostics.Frame frame,RadioDiagnostics.Ack mismatch,
            RadioDiagnostics.Metadata metadata,int received,int observed) {
        RadioDiagnostics.Frame cancelled=frame.ack(RadioDiagnostics.Ack.CANCELLED,mismatch,metadata,-1,received,observed);
        progress(cancelled); emit(cancelled);
    }
    private static final class Read {
        final long deadline;
        int received,frameBytes;
        RadioDiagnostics.Ack failure=RadioDiagnostics.Ack.IO_ERROR;
        Read(long deadline) { this.deadline=deadline; }
    }
    private void read(InputStream input,Socket socket,byte[] out,int offset,int count,Read state,Guard guard) throws IOException {
        int end=offset+count;
        while(offset<end) {
            requireActive(guard);
            long remaining=state.deadline-System.nanoTime();
            if(remaining<=0) { state.failure=RadioDiagnostics.Ack.TIMEOUT; throw new SocketTimeoutException("Radio ACK deadline"); }
            socket.setSoTimeout((int)Math.max(1,(remaining+999999)/1000000));
            int received;
            try { received=input.read(out,offset,end-offset); }
            catch(SocketTimeoutException error) { state.failure=RadioDiagnostics.Ack.TIMEOUT; throw error; }
            if(received<0) {
                state.failure=state.frameBytes==0?RadioDiagnostics.Ack.EOF:RadioDiagnostics.Ack.TRUNCATED;
                throw new IOException("Radio ACK EOF");
            }
            if(received==0) { state.failure=RadioDiagnostics.Ack.EMPTY_READ; throw new IOException("Radio ACK empty read"); }
            offset+=received; state.received+=received; state.frameBytes+=received;
        }
        if(System.nanoTime()>state.deadline) { state.failure=RadioDiagnostics.Ack.TIMEOUT; throw new SocketTimeoutException("Radio ACK deadline"); }
    }
    private void progress(RadioDiagnostics.Frame frame) { report=report.with(frame); }
    private void emit(RadioDiagnostics.Frame frame) {
        try { observer.frame(frame); } catch(RuntimeException | LinkageError error) { /* Diagnostics cannot alter delivery. */ }
    }
    private void requireActive(Guard guard) throws IOException {
        if(closed || stopped || Thread.currentThread().isInterrupted() || !guard.allowed()) {
            stopped=true; throw new Cancelled();
        }
    }
    private void pause(int millis,Guard guard) throws IOException {
        requireActive(guard);
        if(millis>0) {
            try { delay.sleep(millis); }
            catch(InterruptedException error) { Thread.currentThread().interrupt(); throw new IOException("Radio request interrupted"); }
        }
        requireActive(guard);
    }
    public void close() {
        closed=true;
        Socket socket=active;
        if(socket!=null) {
            try { socket.close(); }
            catch(IOException error) { /* Cancellation remains latched. */ }
        }
    }
}
