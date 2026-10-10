package uav.midware.data.model.P3;
public final class DataOsdGetPushCommon {
    private static final DataOsdGetPushCommon instance=new DataOsdGetPushCommon();
    public static DataOsdGetPushCommon getInstance() { return instance; }
    public byte[] getRecData() { return new byte[36]; }
    public boolean isGetted() { return true; }
    public boolean isPushLosed() { return false; }
    public boolean isMotorUp() { return false; }
}
