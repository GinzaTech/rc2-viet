package uav.midware.data.manager.P3;
public abstract class DataBase {
    public byte[] response;
    public boolean throwRead;
    public byte[] getRecData() {
        if(throwRead) throw new IllegalStateException("PRIVATE SDK DETAIL");
        return response;
    }
}
