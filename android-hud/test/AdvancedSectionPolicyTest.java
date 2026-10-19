package local.rc2.hud;

public final class AdvancedSectionPolicyTest {
    public static void main(String[] args) {
        String[] titles={"Nâng cao","Hiệu chỉnh gimbal"};
        String[] factories={"tabAdvanced","gimbalPage"};
        if(AdvancedSectionPolicy.count()!=2)throw new AssertionError("Wrong settings page count");
        for(int i=0;i<2;i++) {
            if(!titles[i].equals(AdvancedSectionPolicy.title(i))||!factories[i].equals(AdvancedSectionPolicy.factory(i)))
                throw new AssertionError("Incorrect page mapping: "+i);
        }
        for (int index : new int[]{-1,2,3,Integer.MAX_VALUE}) {
            try { AdvancedSectionPolicy.factory(index); throw new AssertionError("Unselected page accepted"); }
            catch (IllegalArgumentException expected) { }
            try { AdvancedSectionPolicy.title(index); throw new AssertionError("Unselected title accepted"); }
            catch (IllegalArgumentException expected) { }
        }
        System.out.println("advanced_and_gimbal_pages_are_allowed");
    }
}
