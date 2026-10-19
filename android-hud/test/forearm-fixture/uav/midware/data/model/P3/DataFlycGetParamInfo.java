package uav.midware.data.model.P3;
public final class DataFlycGetParamInfo {
    public enum TypeId {
        INT08U(0), INT08S(4);
        private final int value;
        TypeId(int value) { this.value=value; }
        public int value() { return value; }
    }
}
