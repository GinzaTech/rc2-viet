package local.rc2.hud;
public final class MenuPlacementTest {
    static void check(boolean ok,String why) { if(!ok) throw new AssertionError(why); }
    public static void main(String[] args) {
        int[] position=MenuPlacement.place(1222,921,100,0,0,1920,1080,120,20,20);
        check(position[0]==1082 && position[1]==911,"same vertical center as full 100px Go Fly button");
        position=MenuPlacement.place(1300,1021,100,78,100,1920,1080,120,20,20);
        check(position[0]==1082 && position[1]==911,"screen origin removed exactly once");
        position=MenuPlacement.place(50,10,100,0,0,300,200,120,20,20);
        check(position[0]==20 && position[1]==20,"left/top clipping guard");
        position=MenuPlacement.place(400,190,100,0,0,300,200,120,20,20);
        check(position[0]==160 && position[1]==60,"root bounds respected");
        System.out.println("menu_placement_passed");
    }
}
