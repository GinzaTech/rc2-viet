package uav.midware.data.model.P3;
import uav.midware.interfaces.UAVDataCallBack;
import uav.midware.data.config.P3.Ccode;
public class DataOsdSetSdrAssitantRead {
    public enum SdrCpuType { CP_A7; public int value(){return 0;} }
    public enum SdrDataType { Byte_Data; public int value(){return 2;} }
    public enum SdrDeviceType { Sky; public int value(){return 0;} }
    public static int value=0,reads;
    public static boolean fail;
    public int address;
    public DataOsdSetSdrAssitantRead setAddress(int address){this.address=address;return this;}
    public DataOsdSetSdrAssitantRead setSdrDeviceType(SdrDeviceType value){return this;}
    public DataOsdSetSdrAssitantRead setSdrCpuType(SdrCpuType value){return this;}
    public DataOsdSetSdrAssitantRead setSdrDataType(SdrDataType value){return this;}
    public byte[] getRecData(){return new byte[]{(byte)value};}
    public int getIntValue(){return value;}
    public void start(UAVDataCallBack reply){reads++; if(fail)reply.onFailure(Ccode.GET_PARAM_FAILED);else reply.onSuccess(this);}
}
