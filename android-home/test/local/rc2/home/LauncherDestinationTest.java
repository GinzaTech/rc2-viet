package local.rc2.home;
import java.util.ArrayList;
import java.util.List;

public final class LauncherDestinationTest {
    public static void main(String[] args) {
        List<String> calls=new ArrayList<>();
        boolean opened=LauncherDestination.open((p,c)-> {calls.add(p);return p.equals("dev.rclauncher.rc2.debug");});
        if(!opened||calls.size()!=1||!calls.get(0).equals("dev.rclauncher.rc2.debug"))throw new AssertionError("RC must be the first and only successful destination");
        calls.clear();opened=LauncherDestination.open((p,c)->{calls.add(p);return p.equals("app.lawnchair");});
        if(!opened||calls.size()!=3||!calls.get(2).equals("app.lawnchair"))throw new AssertionError("Old launcher is fallback only");
        if(LauncherDestination.open((p,c)->false))throw new AssertionError("Missing apps must not return success");
        System.out.println("3 launcher destination scenarios passed");
    }
}
