package local.rc2.hud;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.function.BooleanSupplier;

/** One HPD request, real sink readback, and failure cleanup. No simulated EDID or USB role changes. */
final class DisplayPortRetry {
    static final String HPD="/sys/kernel/debug/drm_dp/hpd";
    static final String CONNECTOR="/sys/class/drm/card0-DP-1/";
    enum Result { READY, ALREADY, NO_SCREEN, DENIED, UNSUPPORTED, FAILED, CANCELLED, CLEANUP_FAILED }
    interface Port {
        boolean supported();
        boolean writable();
        boolean sinkReady() throws IOException;
        void hpd(boolean high) throws IOException;
        long now();
        void waitStep() throws InterruptedException;
    }
    static final class KernelPort implements Port {
        public boolean supported(){return new File(HPD).isFile()&&new File(CONNECTOR+"status").isFile();}
        public boolean writable(){return new File(HPD).canWrite();}
        private static byte[] read(String path,int limit)throws IOException {
            try(FileInputStream input=new FileInputStream(path)) {
                byte[] buffer=new byte[limit];int used=0,n;
                while(used<buffer.length&&(n=input.read(buffer,used,buffer.length-used))>0)used+=n;
                return java.util.Arrays.copyOf(buffer,used);
            }
        }
        private static String text(String name)throws IOException {
            return new String(read(CONNECTOR+name,4096),StandardCharsets.US_ASCII).trim();
        }
        public boolean sinkReady()throws IOException {
            return "connected".equals(text("status"))&&"enabled".equals(text("enabled"))
                &&!text("modes").isEmpty()&&validEdid(read(CONNECTOR+"edid",128));
        }
        public void hpd(boolean high)throws IOException {
            try(FileOutputStream output=new FileOutputStream(HPD)){output.write((high?"1\n":"0\n").getBytes(StandardCharsets.US_ASCII));}
        }
        public long now(){return System.nanoTime()/1000000L;}
        public void waitStep()throws InterruptedException {Thread.sleep(250);}
    }
    static boolean validEdid(byte[] data) {
        if(data.length<128||data[0]!=0||data[7]!=0)return false;
        for(int i=1;i<7;i++)if((data[i]&255)!=255)return false;
        int sum=0;for(int i=0;i<128;i++)sum+=data[i]&255;return (sum&255)==0;
    }
    static Result run(Port port,BooleanSupplier displayReady,BooleanSupplier cancelled) {
        boolean attempted=false,keep=false;Result result=Result.FAILED;
        try {
            if(cancelled.getAsBoolean())return Result.CANCELLED;
            if(displayReady.getAsBoolean())return Result.ALREADY;
            if(!port.supported())return Result.UNSUPPORTED;
            if(!port.writable())return Result.DENIED;
            attempted=true;port.hpd(true);
            long deadline=port.now()+10000;
            while(port.now()<deadline&&!cancelled.getAsBoolean()) {
                if(port.sinkReady()&&displayReady.getAsBoolean()) {keep=true;result=Result.READY;break;}
                port.waitStep();
            }
            if(!keep)result=cancelled.getAsBoolean()?Result.CANCELLED:Result.NO_SCREEN;
        } catch(InterruptedException error) {
            Thread.currentThread().interrupt();result=Result.CANCELLED;
        } catch(IOException|RuntimeException error) {result=Result.FAILED;}
        finally {
            if(attempted&&!keep)try {port.hpd(false);}catch(IOException|RuntimeException error){result=Result.CLEANUP_FAILED;}
        }
        return result;
    }
}
