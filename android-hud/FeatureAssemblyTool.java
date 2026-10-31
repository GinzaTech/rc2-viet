import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import brut.androlib.src.SmaliBuilder;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.iface.ClassDef;
import com.android.tools.smali.dexlib2.writer.builder.DexBuilder;
import com.android.tools.smali.dexlib2.writer.io.FileDataStore;

/** Offline-only assembly of explicitly selected feature namespaces. */
public final class FeatureAssemblyTool {
    static final Set<String> PREFIXES=new HashSet<>(Arrays.asList(
        "flyctl","flysettings","gimcal","gpskill","homequick","landing","lanstream","lte4g",
        "mapsrc","modi18n","modinfo","paramedit","probe42","redfly","redprefs","rthguard",
        "rxspeed","screenrecguard","cleanview","fpvextras","frtool"));
    public static void main(String[] args) throws Exception {
        if(args.length<3)throw new IllegalArgumentException();
        String mode=args[0];Path output=Paths.get(args[1]).toAbsolutePath();
        if(mode.equals("extract")) {
            Files.createDirectories(output);Set<String> seen=new HashSet<>();int count=0;
            for(int i=2;i<args.length;i++)for(Map.Entry<String,ClassDef> row:AdaptiveHudTool.classes(Paths.get(args[i])).entrySet()) {
                String type=row.getKey();String pkg=type.substring(1).split("/")[0];
                if(!PREFIXES.contains(pkg)&&!type.startsWith("Lapp/openfcc/battery/"))continue;
                if(!seen.add(type))throw new IllegalArgumentException("Duplicate feature definition");
                String text=AdaptiveHudTool.dump(row.getValue());
                Files.writeString(output.resolve("feature-"+(count++)+".smali"),text,StandardCharsets.UTF_8);
            }
            System.out.print(count);return;
        }
        if(!mode.equals("assemble")||args.length!=3||Files.exists(output))throw new IllegalArgumentException();
        Path source=Paths.get(args[2]).toAbsolutePath();ArrayList<Path> files=new ArrayList<>();
        try(java.util.stream.Stream<Path> stream=Files.list(source)) {
            stream.filter(p->p.getFileName().toString().endsWith(".smali")).sorted().forEach(files::add);
        }
        if(files.isEmpty()||files.size()>2000)throw new IllegalArgumentException();
        DexBuilder dex=new DexBuilder(new Opcodes(30,-1));SmaliBuilder compiler=new SmaliBuilder(source.toFile(),30);
        for(Path p:files)compiler.buildFile(p.getFileName().toString(),dex);
        FileDataStore store=new FileDataStore(output.toFile());
        try {dex.writeTo(store);}finally {store.raf.close();}
        if(AdaptiveHudTool.classes(output).size()!=files.size())throw new IllegalStateException("Feature class lost");
        System.out.print(files.size());
    }
}
