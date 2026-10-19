package uav.midware.data.model.P3;
import uav.midware.interfaces.UAVDataCallBack;
import uav.midware.data.config.P3.Ccode;
public class DataOsdSetSdrAssitantWrite {
    public static int writes,target;
    public static boolean mismatch,hold,wrongThenTrue;
    public static UAVDataCallBack pending;
    public static DataOsdSetSdrAssitantWrite instance;
    public static java.util.concurrent.CountDownLatch configured,resumeConfigure,insideSdk,resumeSdk;
    public int address,value;
    public DataOsdSetSdrAssitantWrite setForceFcc(){
        address=0xffff0048;value=2;
        if(configured!=null){configured.countDown();waitFor(resumeConfigure);}return this;
    }
    private static void waitFor(java.util.concurrent.CountDownLatch latch){
        try{if(!latch.await(2,java.util.concurrent.TimeUnit.SECONDS))throw new AssertionError("fixture barrier timeout");}
        catch(InterruptedException error){Thread.currentThread().interrupt();throw new AssertionError(error);}
    }
    public DataOsdSetSdrAssitantWrite setAddress(int address){this.address=address;return this;}
    public DataOsdSetSdrAssitantWrite setWriteValue(int value){this.value=value;return this;}
    public DataOsdSetSdrAssitantWrite setSdrDeviceType(DataOsdSetSdrAssitantRead.SdrDeviceType value){return this;}
    public DataOsdSetSdrAssitantWrite setSdrCpuType(DataOsdSetSdrAssitantRead.SdrCpuType value){return this;}
    public DataOsdSetSdrAssitantWrite setSdrDataType(DataOsdSetSdrAssitantRead.SdrDataType value){return this;}
    public void start(UAVDataCallBack reply){
        if(address!=0xffff0048)throw new AssertionError("arbitrary address");
        writes++;target=value;instance=this;pending=reply;
        if(insideSdk!=null){insideSdk.countDown();waitFor(resumeSdk);}
        if(wrongThenTrue)reply.onSuccess(new Object());
        if(!mismatch)DataOsdSetSdrAssitantRead.value=value;
        if(!hold){reply.onSuccess(this);reply.onSuccess(this);}
    }
}
