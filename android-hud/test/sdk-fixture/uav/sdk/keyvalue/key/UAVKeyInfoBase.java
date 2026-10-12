package uav.sdk.keyvalue.key;
public class UAVKeyInfoBase {
    public final String name;
    private final boolean get,set,listen,action,event;
    public boolean throwName,throwMetadata;
    public UAVKeyInfoBase(String name) { this(name,true,"LEDsSettings".equals(name),true,false,false); }
    public UAVKeyInfoBase(String name,boolean get,boolean set,boolean listen,boolean action,boolean event) {
        this.name=name; this.get=get; this.set=set; this.listen=listen; this.action=action; this.event=event;
    }
    public String e() {
        if(throwName) throw new IllegalStateException("PRIVATE identifier detail");
        return name;
    }
    public boolean i() {
        if(throwMetadata) throw new IllegalStateException("PRIVATE metadata detail");
        return get;
    }
    public boolean j() { return listen; }
    public boolean k() { return action; }
    public boolean l() { return set; }
    public boolean m() { return event; }
}
