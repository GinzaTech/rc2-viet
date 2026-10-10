package uav.sdk.keyvalue.value.common;

public final class AreaCodeInfo {
    private final String areaCode;
    private final Integer acValue;
    public boolean throwArea, throwValue;
    public AreaCodeInfo(String areaCode, Integer acValue) {
        this.areaCode = areaCode; this.acValue = acValue;
    }
    public String getAreaCode() {
        if (throwArea) throw new IllegalStateException("PRIVATE SDK detail");
        return areaCode;
    }
    public Integer getAcValue() {
        if (throwValue) throw new IllegalStateException("PRIVATE SDK detail");
        return acValue;
    }
    public String toString() { throw new AssertionError("SDK objects must not be stringified"); }
}
