package uav.sdk.keyvalue.key;

public class UAVKeyInfoBase {
    public String name;
    public boolean throwName;
    public UAVKeyInfoBase(String name) { this.name = name; }
    public String e() {
        if (throwName) throw new IllegalStateException("PRIVATE SDK detail");
        return name;
    }
}
