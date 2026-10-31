package uav.midware.data.model.P3;
import uav.midware.data.manager.P3.DataBase;
import uav.midware.interfaces.UAVDataCallBack;
public final class DataFlycGetParams extends DataBase {
    public static DataFlycGetParams last;
    public static int starts, singletonCalls;
    public static boolean throwStart, throwConstruct, throwSet, foreignConfigured;
    public static byte[] immediate;
    public String[] names;
    public UAVDataCallBack pending;
    public DataFlycGetParams() {
        if(throwConstruct) throw new IllegalStateException("PRIVATE SDK DETAIL");
        last=this;
    }
    public static DataFlycGetParams getInstance() {
        singletonCalls++;
        throw new AssertionError("stock singleton must not be changed");
    }
    public DataFlycGetParams setInfos(String[] names) {
        if(throwSet) throw new IllegalStateException("PRIVATE SDK DETAIL");
        this.names=names.clone(); return foreignConfigured?new DataFlycGetParams():this;
    }
    public void start(UAVDataCallBack callback) {
        starts++; pending=callback;
        if(throwStart) throw new IllegalStateException("PRIVATE SDK DETAIL");
        if(immediate!=null) succeed(immediate);
    }
    public void succeed(byte[] bytes) { response=bytes; pending.onSuccess(this); }
}
