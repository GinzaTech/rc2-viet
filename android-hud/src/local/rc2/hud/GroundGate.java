package local.rc2.hud;

/** Flight-state gate: no altitude heuristics and no permissive fallback. */
final class GroundGate {
    final boolean valid, fresh, motorsOn;
    final Boolean flying;
    GroundGate(boolean valid, boolean fresh, boolean motorsOn, Boolean flying) {
        this.valid=valid; this.fresh=fresh; this.motorsOn=motorsOn; this.flying=flying;
    }
    boolean allowed() { return valid && fresh && !motorsOn && Boolean.FALSE.equals(flying); }
    static GroundGate unknown() { return new GroundGate(false,false,true,null); }
    String explanation() {
        if(!valid || !fresh || flying==null) return "Không đọc được trạng thái máy bay mới nhất. Thao tác bị khóa.";
        if(motorsOn || flying) return "Chỉ thao tác khi máy bay đã hạ cánh và động cơ đã dừng.";
        return "Máy bay ở mặt đất, động cơ đã dừng.";
    }
}
