// SPDX-License-Identifier: AGPL-3.0-only
package local.rc2.hud;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Every actual TCP connection is redirected to a PC ephemeral loopback server. */
public final class RadioTransportTest {
    static void check(boolean value,String label) { RadioProtocolTest.check(value,label); }
    static final class Guard implements RadioTransport.Guard {
        volatile boolean allowed=true;
        int dispatched;
        public boolean allowed() { return allowed; }
        public void dispatched() { dispatched++; }
    }
    interface Response { void write(Socket socket,byte[] request) throws Exception; }
    static byte[] read(InputStream input) throws IOException {
        ByteArrayOutputStream data=new ByteArrayOutputStream();
        for(int i=0;i<3;i++) { int b=input.read(); if(b<0) throw new IOException("EOF"); data.write(b); }
        byte[] header=data.toByteArray(); int size=(header[1]&255)|((header[2]&3)<<8);
        for(int i=3;i<size;i++) { int b=input.read(); if(b<0) throw new IOException("EOF"); data.write(b); }
        return data.toByteArray();
    }
    static final class Server implements AutoCloseable {
        final ServerSocket server;
        final Thread thread;
        final List<byte[]> packets=new ArrayList<>();
        final AtomicReference<Throwable> failure=new AtomicReference<>();
        Server(int count,Response response) throws IOException {
            server=new ServerSocket(0,50,InetAddress.getByName("127.0.0.1")); server.setSoTimeout(5000);
            thread=new Thread(()->{
                try {
                    for(int i=0;i<count;i++) try(Socket socket=server.accept()) {
                        socket.setTcpNoDelay(true);
                        socket.setSoTimeout(1000); byte[] request=read(socket.getInputStream());
                        packets.add(request); response.write(socket,request);
                    }
                } catch(Throwable error) { if(!server.isClosed()) failure.set(error); }
            }); thread.setDaemon(true); thread.start();
        }
        static void verifyUnrelatedStreams() throws Exception {
        Guard guard;
        for(int fragmented=0;fragmented<2;fragmented++) {
            final boolean split=fragmented==1;
            try(Server server=new Server(42,(socket,request)->{
                byte[] unrelated=request.clone(); unrelated[6]^=1;
                byte[] noise=RadioProtocolTest.ack(unrelated,new byte[]{0});
                byte[] ack=RadioProtocolTest.ack(request,new byte[]{0});
                ByteArrayOutputStream combined=new ByteArrayOutputStream(); combined.write(noise); combined.write(ack);
                if(split) for(byte item:combined.toByteArray()) socket.getOutputStream().write(item);
                else socket.getOutputStream().write(combined.toByteArray());
                socket.getOutputStream().flush();
            })) {
                guard=new Guard(); RadioTransport transport=server.transport(); transport.send(true,guard); server.joined();
                check(guard.dispatched==42,"valid unrelated frame does not abort matching ACK profile"); transport.close();
            }
        }
        for(int negative=0;negative<2;negative++) {
            final boolean nack=negative==1;
            try(Server server=new Server(42,(socket,request)->{
                byte[] unrelated=request.clone(); unrelated[6]^=1;
                socket.getOutputStream().write(RadioProtocolTest.ack(unrelated,new byte[]{0}));
                if(nack) socket.getOutputStream().write(RadioProtocolTest.ack(request,new byte[]{1}));
                socket.getOutputStream().flush();
            })) {
                guard=new Guard(); RadioTransport transport=server.transport(); transport.send(true,guard); server.joined();
                check(guard.dispatched==42,"unrelated responses and model-specific NACK do not suppress later profile frames"); transport.close();
            }
        }
        }
        RadioTransport transport() {
            return new RadioTransport(()->new Socket() {
                public void connect(SocketAddress address,int timeout) throws IOException {
                    InetSocketAddress fixed=(InetSocketAddress)address;
                    check(fixed.getAddress().getHostAddress().equals("127.0.0.1") && fixed.getPort()==40009,"pinned endpoint no scanning");
                    super.connect(new InetSocketAddress("127.0.0.1",server.getLocalPort()),timeout);
                }
            });
        }
        void joined() throws InterruptedException {
            thread.join(5000); check(!thread.isAlive(),"server completed");
            check(failure.get()==null,"loopback server error "+failure.get());
        }
        public void close() throws IOException { server.close(); }
    }
    static void expectFailure(RadioTransport transport,boolean fcc,Guard guard) {
        try { transport.send(fcc,guard); throw new AssertionError("expected failure"); }
        catch(IOException expected) { }
    }
    public static void main(String[] args) throws Exception {
        Server.verifyUnrelatedStreams();
        Guard guard=new Guard();
        try(Server server=new Server(42,(socket,request)->{
            byte[] ack=RadioProtocolTest.ack(request,new byte[]{0});
            socket.getOutputStream().write(ack,0,3); socket.getOutputStream().flush();
            socket.getOutputStream().write(ack,3,ack.length-3); socket.getOutputStream().flush();
        })) {
            RadioTransport transport=server.transport(); transport.send(true,guard); server.joined();
            check(guard.dispatched==42 && server.packets.size()==42,"42 exact writes");
            check(java.util.Arrays.equals(server.packets.get(0),server.packets.get(21)),"pinned same sequences both rounds");
            transport.close(); expectFailure(transport,true,guard);
        }
        for(int mode=0;mode<5;mode++) {
            final int selected=mode;
            try(Server server=new Server(42,(socket,request)->{
                byte[] ack=RadioProtocolTest.ack(request,new byte[]{selected==1?(byte)1:(byte)0});
                if(selected==0) ack[6]^=1;
                if(selected==2) { socket.getOutputStream().write(ack,0,6); return; }
                if(selected==3) return;
                if(selected==4) ack[2]=8;
                if(selected!=2) socket.getOutputStream().write(ack);
            })) {
                guard=new Guard(); RadioTransport transport=server.transport(); transport.send(true,guard);
                server.joined(); check(guard.dispatched==42,"all fixed frames attempted despite unavailable ACK; no extra retries"); transport.close();
            }
        }
        try(Server server=new Server(1,(socket,request)->{})) {
            guard=new Guard(); RadioTransport transport=server.transport(); transport.send(false,guard); server.joined();
            byte[] packet=server.packets.get(0);
            check(packet[5]==32 && packet[8]==6,"factory restore no ACK required");
            check(guard.dispatched==1,"one-shot restore"); transport.close();
        }
        Guard stopped=new Guard(); stopped.allowed=false;
        RadioTransport never=new RadioTransport(()->{throw new AssertionError("no socket when gate denied");});
        expectFailure(never,true,stopped); never.close();
        CountDownLatch readStarted=new CountDownLatch(1),release=new CountDownLatch(1);
        RadioTransport blocked=new RadioTransport(()->new Socket() {
            public void connect(SocketAddress address,int timeout) { }
            public void setTcpNoDelay(boolean on) { }
            public void setSoTimeout(int value) { }
            public java.io.OutputStream getOutputStream() { return new ByteArrayOutputStream(); }
            public InputStream getInputStream() { return new InputStream() {
                public int read() throws IOException {
                    readStarted.countDown();
                    try { release.await(2,TimeUnit.SECONDS); } catch(InterruptedException error) { Thread.currentThread().interrupt(); }
                    throw new IOException("cancelled");
                }
            }; }
            public synchronized void close() { release.countDown(); }
        });
        AtomicReference<Throwable> workerFailure=new AtomicReference<>();
        Thread worker=new Thread(()->{try { expectFailure(blocked,true,new Guard()); } catch(Throwable error) { workerFailure.set(error); }}); worker.start();
        check(readStarted.await(2,TimeUnit.SECONDS),"read entered"); blocked.close(); worker.join(1000);
        check(!worker.isAlive(),"close actively unblocks read");
        check(workerFailure.get()==null,"worker assertions propagate to main test");
        System.out.println("RadioTransportTest_passed");
    }
}
