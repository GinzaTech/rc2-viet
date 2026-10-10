package uav.sdk.keyvalue.callback;
import uav.sdk.keyvalue.key.UAVKey;
public interface IGetCallback {
    void a(UAVKey key,int code,String detail);
    void b(UAVKey key,Object value);
}
