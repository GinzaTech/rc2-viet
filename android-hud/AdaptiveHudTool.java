import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import brut.androlib.src.SmaliBuilder;
import com.android.tools.smali.baksmali.Adaptors.ClassDefinition;
import com.android.tools.smali.baksmali.BaksmaliOptions;
import com.android.tools.smali.baksmali.formatter.BaksmaliWriter;
import com.android.tools.smali.dexlib2.DexFileFactory;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.dexbacked.DexBackedDexFile;
import com.android.tools.smali.dexlib2.iface.ClassDef;
import com.android.tools.smali.dexlib2.iface.MultiDexContainer;
import com.android.tools.smali.dexlib2.writer.builder.DexBuilder;
import com.android.tools.smali.dexlib2.writer.io.FileDataStore;

/** Structural bootstrap patch; class names, DEX index and version are input data. */
public final class AdaptiveHudTool {
    private static final int SDK = 30;
    private static final Pattern TYPE = Pattern.compile("L[^.;\\[\\x00\\r\\n]+;");
    private static final Pattern CREATE = Pattern.compile("(?ms)^\\.method public onCreate\\(\\)V\\n.*?^\\.end method");
    private static final Pattern SWAP = Pattern.compile(
        "(?m)^    invoke-static \\{p0\\}, (L[A-Za-z0-9_$/]+;)->replaceApplicationContext\\(Landroid/app/Application;\\)V\\n");
    private static final Pattern REGISTERS = Pattern.compile("(?m)^    \\.(registers|locals) (\\d+)\\s*$");

    private AdaptiveHudTool() { }

    static Map<String, ClassDef> classes(Path input) throws Exception {
        if (Files.size(input) > 256L*1024*1024) throw new IllegalArgumentException();
        byte[] magic = new byte[4];
        try (java.io.InputStream stream = Files.newInputStream(input)) {
            if (stream.read(magic) != 4 || !java.util.Arrays.equals(magic, new byte[]{'d','e','x','\n'}))
                throw new IllegalArgumentException();
        }
        MultiDexContainer container = DexFileFactory.loadDexContainer(input.toFile(), new Opcodes(SDK, -1));
        if (container.getDexEntryNames().size() != 1) throw new IllegalArgumentException();
        DexBackedDexFile dex = container.getEntry((String)container.getDexEntryNames().get(0)).getDexFile();
        if (dex.classSection.size() > 100000) throw new IllegalArgumentException();
        Map<String,ClassDef> result = new TreeMap<>();
        for (Object row : dex.classSection) {
            ClassDef definition = (ClassDef)row;
            if (!TYPE.matcher(definition.getType()).matches() || result.put(definition.getType(),definition) != null)
                throw new IllegalArgumentException();
        }
        return result;
    }

    static String dump(ClassDef definition) throws Exception {
        StringWriter text = new StringWriter();
        try (BaksmaliWriter writer = new BaksmaliWriter(text)) {
            new ClassDefinition(new BaksmaliOptions(), definition).writeTo(writer);
        }
        return text.toString().replace("\r\n", "\n");
    }

    static String hook(String text, String application) {
        if (text.contains("Llocal/rc2/hud/") || text.contains(":rc2menu_")) throw new IllegalArgumentException();
        Matcher create = CREATE.matcher(text);
        if (!create.find()) throw new IllegalArgumentException();
        int start = create.start(), end = create.end();
        String method = create.group();
        if (create.find()) throw new IllegalArgumentException();
        Matcher swap = SWAP.matcher(method);
        if (!swap.find()) throw new IllegalArgumentException();
        int afterSwap = swap.end();
        if (swap.find())
            throw new IllegalArgumentException();
        Matcher terminal = Pattern.compile("(?m)^    return-void\\s*\\n\\.end method$").matcher(method);
        if (!terminal.find() || terminal.start() < afterSwap) throw new IllegalArgumentException();
        int insertion = terminal.start();
        if (terminal.find()) throw new IllegalArgumentException();
        String tail = method.substring(afterSwap,insertion);
        if (Pattern.compile("(?m)^\\s*(?::|if-|goto|.*switch|throw|return-|\\.catch)").matcher(tail).find())
            throw new IllegalArgumentException();
        Matcher registers = REGISTERS.matcher(method);
        if (!registers.find()) throw new IllegalArgumentException();
        int count = Integer.parseInt(registers.group(2));
        int locals = registers.group(1).equals("locals") ? count : count-1;
        if (locals < 3 || count > 65535 || registers.find()) throw new IllegalArgumentException();
        String hook = "\n    :rc2menu_start\n"
            + "    invoke-virtual {p0}, " + application + "->getApplicationContext()Landroid/content/Context;\n"
            + "    move-result-object v0\n    check-cast v0, Landroid/app/Application;\n"
            + "    invoke-static {v0}, Llocal/rc2/hud/HudController;->install(Landroid/app/Application;)Ljava/lang/String;\n"
            + "    :rc2menu_end\n"
            + "    .catch Ljava/lang/RuntimeException; {:rc2menu_start .. :rc2menu_end} :rc2menu_error\n"
            + "    .catch Ljava/lang/LinkageError; {:rc2menu_start .. :rc2menu_end} :rc2menu_error\n"
            + "    goto :rc2menu_done\n    :rc2menu_error\n    move-exception v0\n"
            + "    const-string v1, \"RC2Hud\"\n    const-string v2, \"bootstrap_hook_failed\"\n"
            + "    invoke-static {v1, v2, v0}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I\n"
            + "    :rc2menu_done\n";
        return text.substring(0,start)+method.substring(0,insertion)+hook+method.substring(insertion)+text.substring(end);
    }

    public static String inspect(Path input, String application) throws Exception {
        if (!TYPE.matcher(application).matches()) throw new IllegalArgumentException();
        Map<String,ClassDef> classes = classes(input);
        ClassDef target = classes.get(application);
        if (target == null) return "{\"found\":false,\"class_count\":"+classes.size()+"}";
        String text = dump(target), mode = "provider";
        if (application.startsWith("Lcom/AppGuard/") || text.contains("->replaceApplicationContext(Landroid/app/Application;)V")) {
            hook(text,application); mode="context_swap";
        }
        if (text.contains("Llocal/rc2/hud/")) throw new IllegalArgumentException();
        String superclass = target.getSuperclass();
        if (superclass==null || !superclass.matches("L[A-Za-z0-9_$/]+;")) throw new IllegalArgumentException();
        return "{\"found\":true,\"class_count\":"+classes.size()+",\"mode\":\""+mode
            +"\",\"superclass\":\""+superclass+"\"}";
    }

    public static void patch(Path input, Path output, Path work, String application) throws Exception {
        if (!TYPE.matcher(application).matches() || input.equals(output) || Files.exists(output))
            throw new IllegalArgumentException();
        Map<String,ClassDef> original = classes(input);
        if (!original.containsKey(application)) throw new IllegalArgumentException();
        String changed = hook(dump(original.get(application)),application);
        Files.createDirectories(work);
        Path smali = Files.createTempDirectory(work,"adaptive-smali-");
        ArrayList<Path> files = new ArrayList<>();
        try {
            int index = 0;
            for (Map.Entry<String,ClassDef> row : original.entrySet()) {
                Path file = smali.resolve("class"+(index++)+".smali"); files.add(file);
                Files.write(file,(row.getKey().equals(application)?changed:dump(row.getValue())).getBytes(StandardCharsets.UTF_8));
            }
            DexBuilder dex = new DexBuilder(new Opcodes(SDK,-1));
            SmaliBuilder compiler = new SmaliBuilder(smali.toFile(),SDK);
            for (Path file : files) compiler.buildFile(file.getFileName().toString(),dex);
            FileDataStore data = new FileDataStore(output.toFile());
            try { dex.writeTo(data); } finally { data.raf.close(); }
            Map<String,ClassDef> result = classes(output);
            if (!result.keySet().equals(original.keySet())) throw new IllegalStateException();
            for (String type : original.keySet()) {
                if (!type.equals(application) && !dump(original.get(type)).equals(dump(result.get(type))))
                    throw new IllegalStateException();
            }
            if (!dump(result.get(application)).contains("Llocal/rc2/hud/HudController;->install"))
                throw new IllegalStateException();
        } catch (Exception | LinkageError failure) {
            Files.deleteIfExists(output); throw failure;
        } finally {
            for (Path file : files) Files.deleteIfExists(file);
            Files.deleteIfExists(smali);
        }
    }

    public static String dumpPrefix(Path input, Path output, String prefix) throws Exception {
        if (!prefix.matches("L[A-Za-z0-9_$/]+/")) throw new IllegalArgumentException();
        Files.createDirectories(output);
        int matches = 0;
        for (Map.Entry<String,ClassDef> row : classes(input).entrySet()) {
            String text = dump(row.getValue());
            if (!row.getKey().startsWith(prefix) && !text.contains(prefix)) continue;
            String name = "class-"+matches+".smali";
            Files.write(output.resolve(name),text.getBytes(StandardCharsets.UTF_8)); matches++;
        }
        return "{\"dumped\":"+matches+"}";
    }
}
