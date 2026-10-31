package uav.midware.data.config.P3;
public enum Ccode {
    GET_PARAM_FAILED(231), TIMEOUT(256);
    private final int value;
    public static boolean throwCode;
    Ccode(int value) { this.value=value; }
    public int c() {
        if(throwCode) throw new IllegalStateException("PRIVATE SDK DETAIL");
        return value;
    }
    public String toString() { throw new AssertionError("PRIVATE SDK DETAIL must not be logged"); }
}
