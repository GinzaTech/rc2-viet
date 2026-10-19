package uav.midware.data.model.P3;
import uav.midware.interfaces.UAVDataCallBack;
import uav.midware.data.config.P3.Ccode;
public final class DataFlycSetParams {
    public static String name;
    public static Number value;
    public static int starts;
    public static String mode="success";
    public DataFlycSetParams setInfo(String input,Number raw) { name=input; value=raw; return this; }
    public void start(UAVDataCallBack reply) {
        starts++;
        if("failure".equals(mode)) reply.onFailure(Ccode.GET_PARAM_FAILED);
        else if("wrong".equals(mode)) reply.onSuccess(new Object());
        else if("wrongThenTrue".equals(mode)) { reply.onSuccess(new Object());reply.onSuccess(this); }
        else if("throw".equals(mode)) throw new IllegalStateException("PRIVATE SDK DETAIL");
        else { reply.onSuccess(this); reply.onSuccess(this); }
    }
}
