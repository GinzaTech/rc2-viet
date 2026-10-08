package local.rc2.home;

/** Prefer the RC dashboard; retain the previously working launcher as recovery. */
public final class LauncherDestination {
    public interface Starter { boolean open(String packageName,String className); }
    public static boolean open(Starter starter) {
        if(starter.open("dev.rclauncher.rc2.debug","dev.rclauncher.rc2.RCLauncher"))return true;
        if(starter.open("dev.rclauncher.rc2","dev.rclauncher.rc2.RCLauncher"))return true;
        return starter.open("app.lawnchair","app.lawnchair.LawnchairLauncher");
    }
}
