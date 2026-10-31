import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import com.android.tools.smali.dexlib2.iface.ClassDef;

/** Audit executable recipe payloads, independently of descriptive manifest fields. */
public final class MenuPolicyPayloadAudit {
    private static void require(boolean condition,String message) {
        if(!condition)throw new AssertionError(message);
    }
    private static String method(String text,String signature) {
        require(text!=null,"Required menu class is missing");
        Matcher match=Pattern.compile("(?ms)^\\.method [^\\n]* "+Pattern.quote(signature)+"\\n.*?^\\.end method").matcher(text);
        require(match.find(),"Missing executable method: "+signature);
        String result=match.group();
        require(!match.find(),"Ambiguous method: "+signature);
        return result;
    }
    public static void main(String[] args) throws Exception {
        Map<String,String> classes=new TreeMap<>();
        for(String filename:args)for(Map.Entry<String,ClassDef> item:AdaptiveHudTool.classes(Paths.get(filename)).entrySet())
            require(classes.put(item.getKey(),AdaptiveHudTool.dump(item.getValue()))==null,"Duplicate class: "+item.getKey());

        String entry=method(classes.get("Lflysettings/S;"),"showSettings(Landroid/content/Context;)V");
        List<String> code=new ArrayList<>();
        for(String line:entry.split("\\n")) {
            line=line.trim();
            if(line.isEmpty()||line.startsWith(".method ")||line.startsWith(".registers ")||line.startsWith(".line ")||line.equals(".end method"))continue;
            code.add(line);
        }
        require(code.equals(Arrays.asList(
            "invoke-static {p0}, Llocal/rc2/hud/AdvancedSectionMenu;->showSelector(Landroid/content/Context;)V","return-void")),
            "Settings entry must delegate only to the two-page selector: "+code);

        String policy=classes.get("Llocal/rc2/hud/AdvancedSectionPolicy;");
        require(policy!=null,"Missing compiled section policy");
        Set<String> factories=new HashSet<>();
        Matcher strings=Pattern.compile("const-string(?:/jumbo)? [vp]\\d+, \"([^\"]+)\"").matcher(policy);
        while(strings.find()) {
            String value=strings.group(1);
            if(value.startsWith("tab")||value.equals("gimbalPage"))factories.add(value);
        }
        require(factories.equals(new HashSet<>(Arrays.asList("tabAdvanced","gimbalPage"))),
            "Compiled section policy exposes unexpected factories: "+factories);

        Pattern hidden=Pattern.compile("(?m)^    invoke-[^\\n]* Lflysettings/S;->(tabBasic|tabControl|tabSafety)\\(");
        for(Map.Entry<String,String> item:classes.entrySet()) {
            Matcher call=hidden.matcher(item.getValue());
            require(!call.find(),"Hidden page factory remains directly reachable from "+item.getKey());
        }
        String menu=classes.get("Llocal/rc2/hud/AdvancedSectionMenu;");
        method(menu,"showSelector(Landroid/content/Context;)V");method(menu,"show(Landroid/content/Context;I)V");
        System.out.println("two_page_recipe_payload_verified classes="+classes.size());
    }
}
