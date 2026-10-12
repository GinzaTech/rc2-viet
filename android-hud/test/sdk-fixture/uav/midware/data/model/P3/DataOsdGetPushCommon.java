package uav.midware.data.model.P3;
public final class DataOsdGetPushCommon {
    private static final DataOsdGetPushCommon instance=new DataOsdGetPushCommon();
    public static int length=36;
    public static boolean got=true,lost=false,motors=false;
    public static DataOsdGetPushCommon getInstance() { return instance; }
    public byte[] getRecData() { return length<0?null:new byte[length]; }
    public boolean isGetted() { return got; }
    public boolean isPushLosed() { return lost; }
    public boolean isMotorUp() { return motors; }
}
