// SPDX-License-Identifier: AGPL-3.0-only
package local.rc2.hud;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.net.SocketAddress;
import java.net.SocketTimeoutException;
import java.util.ArrayList;
import java.util.List;

/** In-memory proxy faults; no controller endpoint, SDK, ADB or RF writes. */
public final class RadioDiagnosticsTest {
    static void check(boolean value,String label) { RadioProtocolTest.check(value,label); }
    static final class Guard implements RadioTransport.Guard {
        boolean allowed=true;
        int dispatches;
        public boolean allowed() { return allowed; }
        public void dispatched() { dispatches++; }
    }
    static final class Proxy implements RadioTransport.SocketFactory {
        int created,closed;
        int failConnect=-1,failWrite=-1;
        String reply="zero";
        final List<byte[]> packets=new ArrayList<>();
        public Socket create() {
            final int index=created++;
            return new Socket() {
                final ByteArrayOutputStream output=new ByteArrayOutputStream();
                public void connect(SocketAddress address,int timeout) throws IOException {
                    if(index==failConnect) throw new IOException("SECRET-connect");
                }
                public void setTcpNoDelay(boolean on) { }
                public void setSoTimeout(int value) { check(value>0 && value<=50,"bounded FCC read"); }
                public OutputStream getOutputStream() {
                    return new OutputStream() {
                        public void write(int value) throws IOException {
                            if(index==failWrite) throw new IOException("SECRET-write");
                            output.write(value);
                        }
                        public void flush() { packets.add(output.toByteArray()); }
                    };
                }
                public InputStream getInputStream() throws IOException {
                    byte[] request=output.toByteArray();
                    byte[] body="nack".equals(reply)?new byte[]{7}:
                        "body".equals(reply)?new byte[]{83,69,67,82,69,84}:new byte[]{0};
                    byte[] response=RadioProtocolTest.ack(request,body);
                    if("type".equals(reply)) { response[8]=(byte)0xa0; RadioProtocolTest.repair(response); }
                    if("encrypted".equals(reply)) { response[8]=(byte)0x81; RadioProtocolTest.repair(response); }
                    if("empty".equals(reply)) response=RadioProtocolTest.ack(request,new byte[0]);
                    if("limit".equals(reply)) {
                        byte[] unrelated=request.clone(); unrelated[6]^=1;
                        byte[] noise=RadioProtocolTest.ack(unrelated,new byte[]{0});
                        ByteArrayOutputStream stream=new ByteArrayOutputStream();
                        for(int n=0;n<64;n++) stream.write(noise);
                        return new ByteArrayInputStream(stream.toByteArray());
                    }
                    if("emptyRead".equals(reply)) return new InputStream() {
                        public int read() { return 0; }
                        public int read(byte[] data,int offset,int length) { return 0; }
                    };
                    if("route".equals(reply)) { response[4]^=1; RadioProtocolTest.repair(response); }
                    if("sequence".equals(reply)) { response[6]^=1; RadioProtocolTest.repair(response); }
                    if("command".equals(reply)) { response[10]^=1; RadioProtocolTest.repair(response); }
                    if("request".equals(reply)) { response[8]=0; RadioProtocolTest.repair(response); }
                    if("crc".equals(reply)) response[response.length-1]^=1;
                    if("header".equals(reply)) response[3]^=1;
                    if("eof".equals(reply)) return new ByteArrayInputStream(new byte[0]);
                    if("truncated".equals(reply)) return new ByteArrayInputStream(java.util.Arrays.copyOf(response,6));
                    if("timeout".equals(reply) || "io".equals(reply)) return new InputStream() {
                        public int read() throws IOException {
                            if("timeout".equals(reply)) throw new SocketTimeoutException("SECRET-timeout");
                            throw new IOException("SECRET-io");
                        }
                    };
                    return new ByteArrayInputStream(response);
                }
                public synchronized void close() { closed++; }
            };
        }
    }
    static RadioTransport transport(Proxy proxy,List<RadioDiagnostics.Frame> events) {
        return new RadioTransport(proxy,millis->{},events::add);
    }
    static void acknowledgments() throws Exception {
        String[] replies={"zero","type","nack","body","route","sequence","command","request",
            "crc","header","eof","truncated","timeout","io","encrypted","empty","limit","emptyRead"};
        RadioDiagnostics.Ack[] expected={RadioDiagnostics.Ack.ZERO_STATUS,RadioDiagnostics.Ack.ZERO_STATUS,
            RadioDiagnostics.Ack.NONZERO_STATUS,RadioDiagnostics.Ack.BODY_UNINTERPRETED,
            RadioDiagnostics.Ack.EOF,RadioDiagnostics.Ack.EOF,RadioDiagnostics.Ack.EOF,RadioDiagnostics.Ack.EOF,
            RadioDiagnostics.Ack.INVALID_CRC,RadioDiagnostics.Ack.INVALID_HEADER,RadioDiagnostics.Ack.EOF,
            RadioDiagnostics.Ack.TRUNCATED,RadioDiagnostics.Ack.TIMEOUT,RadioDiagnostics.Ack.IO_ERROR,
            RadioDiagnostics.Ack.BODY_UNINTERPRETED,RadioDiagnostics.Ack.EMPTY_BODY,
            RadioDiagnostics.Ack.FRAME_LIMIT,RadioDiagnostics.Ack.EMPTY_READ};
        for(int i=0;i<replies.length;i++) {
            Proxy proxy=new Proxy(); proxy.reply=replies[i]; Guard guard=new Guard();
            List<RadioDiagnostics.Frame> events=new ArrayList<>(); RadioTransport sender=transport(proxy,events);
            sender.send(true,guard); RadioDiagnostics.Report report=sender.diagnostics();
            check(proxy.created==42 && proxy.closed==42 && guard.dispatches==42,"one complete pinned profile: "+replies[i]);
            check(report.complete && report.written==42 && report.writeFailures==0,"delivery only: "+replies[i]);
            check(events.size()==42 && report.last.ack==expected[i],"exact ACK reason: "+replies[i]);
            check(report.matchedReplies==(i<4 || i==14 || i==15?42:0),"matched replies independent of unproven body semantics");
            RadioDiagnostics.Frame first=events.get(0);
            check(first.index==0 && first.round==1 && first.position==1 && first.total==42,"indexed send metadata");
            check(first.request.sender==130 && first.request.destination==18 && first.request.bodyLength==3,"routing/body length");
            check(!report.summary().contains("SECRET") && !first.summary().contains("SECRET"),"no body or exception text");
            check(first.status==(i==2?7:i<2?0:-1),"status only for matched single-byte status bodies");
            if(i>=4 && i<=7) check(first.lastMismatch!=RadioDiagnostics.Ack.NOT_READ,"mismatch survives drain EOF");
            if(i>=2 && i!=15) check(report.firstIssue.index==0,"first problematic frame retained");
            sender.close();
        }
    }
    static void writeFaults() throws Exception {
        for(boolean connect:new boolean[]{true,false}) {
            Proxy proxy=new Proxy(); if(connect) proxy.failConnect=2; else proxy.failWrite=2;
            Guard guard=new Guard(); List<RadioDiagnostics.Frame> events=new ArrayList<>();
            RadioTransport sender=transport(proxy,events);
            try { sender.send(true,guard); throw new AssertionError("partial write series is failure"); }
            catch(IOException expected) { check(!expected.getMessage().contains("SECRET"),"sanitized transport failure"); }
            RadioDiagnostics.Report report=sender.diagnostics();
            check(report.complete && report.attempted==42 && report.written==41 && report.writeFailures==1,"all frames attempted; failed series");
            check(report.firstIssue.index==2 && report.firstIssue.stage==(connect?RadioDiagnostics.Stage.CONNECT_FAILED:RadioDiagnostics.Stage.WRITE_FAILED),"failure send index");
            check(guard.dispatches==(connect?41:42),"connect failure does not dispatch; failed write remains uncertain");
            check(proxy.closed==42 && proxy.packets.size()==41,"failed frame never retried");
        }
    }
    static void cancellationAndObservers() throws Exception {
        Proxy proxy=new Proxy(); Guard guard=new Guard(); List<RadioDiagnostics.Frame> events=new ArrayList<>();
        RadioTransport sender=new RadioTransport(proxy,millis->{},frame->{events.add(frame); guard.allowed=false;});
        try { sender.send(true,guard); throw new AssertionError("guard loss"); } catch(IOException expected) { }
        check(proxy.created==1 && sender.diagnostics().written==1 && !sender.diagnostics().complete,"guard loss stops remaining writes");
        proxy=new Proxy(); final Proxy safe=proxy;
        sender=new RadioTransport(safe,millis->{},frame->{throw new IllegalStateException("SECRET-observer");});
        sender.send(true,new Guard()); check(safe.packets.size()==42,"observer failure cannot interrupt profile");
        RadioDiagnostics.Report immutable=sender.diagnostics(); sender.close();
        check(immutable.complete && immutable.written==42,"immutable completed snapshot");
        RadioTransport closed=new RadioTransport(()->{throw new AssertionError("closed must not create socket");}); closed.close();
        try { closed.send(true,new Guard()); throw new AssertionError("closed"); } catch(IOException expected) { }
        proxy=new Proxy(); final Proxy paused=proxy;
        sender=new RadioTransport(paused,millis->{throw new InterruptedException();},events::add);
        try { sender.send(true,new Guard()); throw new AssertionError("interruption"); }
        catch(IOException expected) { check(Thread.currentThread().isInterrupted(),"interrupt preserved"); }
        finally { Thread.interrupted(); }
        check(paused.created==1 && !sender.diagnostics().complete,"interrupted settle stops subsequent frames");
        final Guard duringWrite=new Guard();
        RadioTransport.SocketFactory socketFactory=()->new Socket() {
            public void connect(SocketAddress address,int timeout) { }
            public void setTcpNoDelay(boolean on) { }
            public OutputStream getOutputStream() { return new OutputStream() {
                public void write(int value) throws IOException { duringWrite.allowed=false; throw new IOException("SECRET-prefix"); }
            }; }
        };
        sender=new RadioTransport(socketFactory,millis->{},events::add);
        try { sender.send(true,duringWrite); throw new AssertionError("unsafe after prefix"); } catch(IOException expected) { }
        check(duringWrite.dispatches==1 && sender.diagnostics().last.stage==RadioDiagnostics.Stage.WRITE_FAILED,"uncertain prefix and no retry");
        sender=new RadioTransport(()->{throw new IOException("SECRET-factory");},millis->{},events::add);
        try { sender.send(true,new Guard()); throw new AssertionError("socket factory failures"); } catch(IOException expected) { }
        check(sender.diagnostics().attempted==42 && sender.diagnostics().writeFailures==42,"factory failures aggregated without dispatch");
    }
    static void nativeIntegration() throws Exception {
        Proxy proxy=new Proxy(); proxy.reply="body";
        List<RadioDiagnostics.Frame> events=new ArrayList<>(); RadioTransport sender=transport(proxy,events);
        RadioNativeTest.Aircraft aircraft=new RadioNativeTest.Aircraft();
        RadioNativeTest.Runtime runtime=new RadioNativeTest.Runtime(); MutationFence fence=new MutationFence();
        NativeRadio radio=new NativeRadio(aircraft,()->sender,runtime,fence);
        List<Boolean> results=new ArrayList<>(); List<String> messages=new ArrayList<>();
        check(radio.request(true,(ok,message)->{results.add(ok); messages.add(message);}),"native integration request");
        aircraft.reply.success(RadioNativeTest.GROUND); runtime.worker.run();
        check(results.equals(java.util.Arrays.asList(true)) && proxy.packets.size()==42,"real adapter delivery completion");
        String message=messages.get(0);
        check(message.contains("written=42") && message.contains("matchedReplies=42") && message.contains("BODY_UNINTERPRETED"),"safe diagnostics reach native result");
        check(!message.contains("SECRET") && !message.contains("Đã nhận ACK") && message.contains("chưa xác nhận"),"no body or mode claims");
        check(fence.pending() && radio.status().locked,"unverified dispatch fenced after delivery");
        radio.close();
        NativeRadio reopened=new NativeRadio(aircraft,()->sender,runtime,fence);
        check(!reopened.request(false,(ok,reply)->{}),"new native owner cannot bypass shared mutation fence");
    }
    static void safetyHandoffs() throws Exception {
        final boolean[] denyOnce={false}; final int[] denials={0},writes={0};
        RadioTransport.Guard transientGuard=new RadioTransport.Guard() {
            public boolean allowed() {
                if(denyOnce[0]) { denyOnce[0]=false; denials[0]++; return false; }
                return true;
            }
            public void dispatched() { }
        };
        RadioTransport sender=new RadioTransport(()->new Socket() {
            public void connect(SocketAddress address,int timeout) { }
            public void setTcpNoDelay(boolean on) { }
            public void setSoTimeout(int millis) { }
            public OutputStream getOutputStream() { return new OutputStream() {
                public void write(int value) { writes[0]++; }
            }; }
            public InputStream getInputStream() {
                denyOnce[0]=true; return new ByteArrayInputStream(new byte[0]);
            }
        },millis->{},frame->{});
        try { sender.send(true,transientGuard); throw new AssertionError("transient guard denial must terminate request"); }
        catch(IOException expected) { }
        check(denials[0]==1 && writes[0]==16 && !sender.diagnostics().complete,"observed unsafe state cannot recover within same request");
        final Guard acquisition=new Guard(); final int[] acquiredWrites={0};
        sender=new RadioTransport(()->new Socket() {
            public void connect(SocketAddress address,int timeout) { }
            public void setTcpNoDelay(boolean on) { }
            public OutputStream getOutputStream() {
                acquisition.allowed=false; return new OutputStream() {
                    public void write(int value) { acquiredWrites[0]++; }
                };
            }
        },millis->{},frame->{});
        try { sender.send(true,acquisition); throw new AssertionError("unsafe stream acquisition"); } catch(IOException expected) { }
        check(acquiredWrites[0]==0 && acquisition.dispatches==0,"stream acquired before final authorization and dispatch latch");
        Proxy proxy=new Proxy(); final Proxy observed=proxy;
        sender=new RadioTransport(observed,millis->{},frame->{throw new NoClassDefFoundError("SECRET-observer");});
        sender.send(true,new Guard()); check(observed.packets.size()==42,"LinkageError diagnostic observer cannot truncate profile");
    }
    public static void main(String[] args) throws Exception {
        acknowledgments(); writeFaults(); cancellationAndObservers(); nativeIntegration(); safetyHandoffs();
        System.out.println("RadioDiagnosticsTest_passed");
    }
}
