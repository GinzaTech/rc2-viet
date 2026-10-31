package uav.midware.data.manager.P3;
import uav.midware.data.params.P3.ParamInfo;
public final class UAVFlycParamInfoManager {
    public static boolean newProtocol=true;
    public static ParamInfo info=new ParamInfo();
    public static String requestedName;
    public static boolean isNew() { return newProtocol; }
    public static ParamInfo read(String name) { requestedName=name; return info; }
}
