package uav.sdk.keyvalue.key;
public final class UAVKey {
    public final UAVKeyInfoBase info;
    public final int subIndex;
    private UAVKey(UAVKeyInfoBase info,int subIndex) { this.info=info; this.subIndex=subIndex; }
    public static UAVKey i(UAVKeyInfoBase info) { return new UAVKey(info,65534); }
    public static UAVKey l(UAVKeyInfoBase info,int product,int component,int subIndex) {
        if(product!=0 || component!=0) throw new IllegalArgumentException("fixture key scope");
        return new UAVKey(info,subIndex);
    }
}
