package uav.midware.interfaces;
import uav.midware.data.config.P3.Ccode;
// Exact classes12.dex interface; PC fake only, never bundled in the HUD.
public interface UAVDataCallBack {
    void onSuccess(Object model);
    void onFailure(Ccode error);
}
