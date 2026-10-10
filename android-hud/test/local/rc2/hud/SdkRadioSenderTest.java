package local.rc2.hud;
import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import uav.midware.data.model.P3.DataOsdSetSdrAssitantRead;
import uav.midware.data.model.P3.DataOsdSetSdrAssitantWrite;
public final class SdkRadioSenderTest {
    static final class Guard implements RadioTransport.Guard {
        volatile boolean allowed=true;
        volatile int dispatched;
        public boolean allowed(){return allowed;}
        public void dispatched(){dispatched++;}
    }
    static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception {
        String[] aircraft={"fixture-air-a"};
        SdkRadioSender.Factory factory=new SdkRadioSender.Factory(SdkRadioSenderTest.class.getClassLoader(),()->aircraft[0]);
        SdkRadioSender fcc=(SdkRadioSender)factory.create(); Guard guard=new Guard();int[] reconciled={0};
        fcc.onReconciled(()->reconciled[0]++);fcc.send(true,guard);
        check(fcc.verified() && guard.dispatched==1 && DataOsdSetSdrAssitantWrite.writes==1,"SDK SET and matching GET");
        check(DataOsdSetSdrAssitantWrite.target==2 && reconciled[0]==1 && DataOsdSetSdrAssitantRead.reads==2,"one write/readback despite duplicate ACK");
        DataOsdSetSdrAssitantRead.value=1; // DJI changed the register after our apply.
        SdkRadioSender restore=(SdkRadioSender)factory.create();restore.send(false,new Guard());
        check(restore.verified() && DataOsdSetSdrAssitantRead.value==0 && DataOsdSetSdrAssitantWrite.target==0,"restore observed baseline without CE guess");
        DataOsdSetSdrAssitantRead.fail=true;int writes=DataOsdSetSdrAssitantWrite.writes;
        try{factory.create().send(true,new Guard());throw new AssertionError();}catch(IOException expected){}
        check(DataOsdSetSdrAssitantWrite.writes==writes,"failed baseline no SET");DataOsdSetSdrAssitantRead.fail=false;
        DataOsdSetSdrAssitantWrite.mismatch=true;
        SdkRadioSender mismatch=(SdkRadioSender)factory.create();
        try{mismatch.send(true,new Guard());throw new AssertionError();}catch(IOException expected){}
        check(!mismatch.verified(),"ACK alone never verifies FCC");DataOsdSetSdrAssitantWrite.mismatch=false;
        DataOsdSetSdrAssitantWrite.wrongThenTrue=true;
        SdkRadioSender malformed=(SdkRadioSender)factory.create();malformed.send(true,new Guard());
        check(malformed.verified(),"foreign callback must not consume genuine reconciliation");
        DataOsdSetSdrAssitantWrite.wrongThenTrue=false;
        DataOsdSetSdrAssitantRead.value=2;
        SdkRadioSender.Factory unknown=new SdkRadioSender.Factory(SdkRadioSenderTest.class.getClassLoader(),()->"fixture-air-a");
        writes=DataOsdSetSdrAssitantWrite.writes;
        try{unknown.create().send(false,new Guard());throw new AssertionError();}catch(IOException expected){}
        check(DataOsdSetSdrAssitantWrite.writes==writes,"unknown baseline not replaced with invented CE");
        aircraft[0]="fixture-air-b";
        try{factory.create().send(false,new Guard());throw new AssertionError();}catch(IOException expected){}
        check(DataOsdSetSdrAssitantWrite.writes==writes,"baseline of another aircraft cannot be restored");
        aircraft[0]="fixture-air-a";
        DataOsdSetSdrAssitantRead.value=0;DataOsdSetSdrAssitantWrite.hold=true;
        SdkRadioSender late=(SdkRadioSender)factory.create();int[] lateReconcile={0};late.onReconciled(()->lateReconcile[0]++);
        Guard pending=new Guard();Thread worker=new Thread(()->{try{late.send(true,pending);}catch(IOException expected){}});
        worker.start();long end=System.nanoTime()+2000000000L;
        while(pending.dispatched==0 && System.nanoTime()<end)Thread.sleep(1);
        check(pending.dispatched==1,"late write dispatched");late.close();worker.join(2000);
        DataOsdSetSdrAssitantWrite.pending.onSuccess(DataOsdSetSdrAssitantWrite.instance);
        check(!worker.isAlive() && late.verified() && lateReconcile[0]==1,"late terminal callback reconciles after close");
        DataOsdSetSdrAssitantWrite.hold=false;DataOsdSetSdrAssitantRead.value=0;
        DataOsdSetSdrAssitantWrite.configured=new CountDownLatch(1);DataOsdSetSdrAssitantWrite.resumeConfigure=new CountDownLatch(1);
        SdkRadioSender preparing=(SdkRadioSender)factory.create();Guard prepareGuard=new Guard();writes=DataOsdSetSdrAssitantWrite.writes;
        Thread prepareWorker=new Thread(()->{try{preparing.send(true,prepareGuard);}catch(IOException expected){}});prepareWorker.start();
        check(DataOsdSetSdrAssitantWrite.configured.await(2,TimeUnit.SECONDS),"configuration reached");preparing.close();
        DataOsdSetSdrAssitantWrite.resumeConfigure.countDown();prepareWorker.join(2000);
        check(!prepareWorker.isAlive() && prepareGuard.dispatched==0 && DataOsdSetSdrAssitantWrite.writes==writes,"close before submission has no SET or false dispatched latch");
        DataOsdSetSdrAssitantWrite.configured=null;DataOsdSetSdrAssitantWrite.insideSdk=new CountDownLatch(1);DataOsdSetSdrAssitantWrite.resumeSdk=new CountDownLatch(1);
        SdkRadioSender submitting=(SdkRadioSender)factory.create();Guard submitGuard=new Guard();
        Thread submitWorker=new Thread(()->{try{submitting.send(true,submitGuard);}catch(IOException expected){}});submitWorker.start();
        check(DataOsdSetSdrAssitantWrite.insideSdk.await(2,TimeUnit.SECONDS),"SDK entry committed");
        CountDownLatch closeReturned=new CountDownLatch(1);Thread closer=new Thread(()->{submitting.close();closeReturned.countDown();});closer.start();
        check(!closeReturned.await(20,TimeUnit.MILLISECONDS),"close cannot return before SDK entry completes");
        DataOsdSetSdrAssitantWrite.resumeSdk.countDown();submitWorker.join(2000);closer.join(2000);
        check(!submitWorker.isAlive() && !closer.isAlive() && submitting.verified(),"committed submission readback survives close");
        System.out.println("sdk_radio_sender_passed");
    }
}
