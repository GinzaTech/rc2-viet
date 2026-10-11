package local.rc2.hud;

/** Activity roles come from the view tree; obfuscated Activity names are optional hints. */
final class ScreenRoles {
    interface Lookup { boolean has(String name); }
    static final String[] HOME = {"main_page_ui_state_startfly_btn", "main_page_ui_device_disconnect_state_button",
        "direct_enter_fpv_view", "layout_direct_enter_fpv", "connection_guide_enter_fpv_button"};
    static final String[] HUD = {"top_bar_shell_layout", "osd_shell_top_layout", "osd_shell_layout",
        "left_bar_shell_layout", "right_bar_shell_layout", "map_shell_layout", "radar_shell_layout",
        "histogram_shell_layout", "zoom_focus_layer_layout", "right_bottom_shell_layout", "attitude_bar_shell_layout",
        "osd_shell_top_child_layout", "portrait_right_bar_shell_layout", "metering_shell_layout", "gimbal_shell_layout"};
    static boolean home(Lookup lookup) {
        for (String name : HOME) if (lookup.has(name)) return true;
        return false;
    }
    static boolean flight(Lookup lookup) {
        if (!lookup.has("view_surface")) return false;
        int count=0;
        for (String name : HUD) if (lookup.has(name) && ++count>=2) return true;
        return false;
    }
    static int select(String activity, Lookup lookup) {
        if(activity.endsWith(".FpvComponentActivity")) return 2;
        if(activity.equals("com.dji.mainpageui.device.DJIDeviceActivity")) return 1;
        if(flight(lookup)) return 2;
        return home(lookup)?1:0;
    }
}
