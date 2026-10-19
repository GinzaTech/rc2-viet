package local.rc2.hud;

/** The two utility pages exposed below the Advanced utilities parent entry. */
final class AdvancedSectionPolicy {
    private static final String[] TITLES={"Nâng cao","Hiệu chỉnh gimbal"};
    private static final String[] FACTORIES={"tabAdvanced","gimbalPage"};
    private static final String[] DESCRIPTIONS={"Tùy chỉnh HUD, hiển thị và tham số",
        "Hiệu chỉnh, chế độ và chuyển động gimbal"};
    private AdvancedSectionPolicy() { }
    static int count() {return TITLES.length;}
    private static void check(int section) {
        if(section<0||section>=count())throw new IllegalArgumentException("Section is not selected");
    }
    static String title(int section) {
        check(section);return TITLES[section];
    }
    static String factory(int section) {
        check(section);return FACTORIES[section];
    }
    static String description(int section) {check(section);return DESCRIPTIONS[section];}
}
