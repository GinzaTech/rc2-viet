import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Map;
import java.util.TreeMap;
import brut.androlib.src.SmaliBuilder;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.iface.ClassDef;
import com.android.tools.smali.dexlib2.writer.builder.DexBuilder;
import com.android.tools.smali.dexlib2.writer.io.FileDataStore;

/** Change only the utilities menu and its generated callbacks in the Basic bridge. */
public final class NestedMenuDexTool {
    static boolean includeHome;
    static boolean selected(String type) {
        if(includeHome)for(String name:new String[]{"DeviceMenu","ExternalOutput","DisplayPortRetry","HudProvider","CapabilityReader","CapabilityAudit"}) {
            String root="Llocal/rc2/hud/"+name;
            if(type.equals(root+";")||type.startsWith(root+"$"))return true;
        }
        for(String name:new String[]{"PortIntegration","AdvancedSectionMenu","AdvancedSectionPolicy","Air3sFeaturePanel"}) {
            String root="Llocal/rc2/hud/"+name;
            if(type.equals(root+";")||type.startsWith(root+"$$")||
                (name.equals("Air3sFeaturePanel")&&type.startsWith(root+"$")))return true;
        }
        return false;
    }
    public static void main(String[] args) throws Exception {
        if(args[0].equals("dump")) {
            Path folder=Paths.get(args[1]);Files.createDirectories(folder);
            for(int i=2;i<args.length;i++)for(Map.Entry<String,ClassDef> row:AdaptiveHudTool.classes(Paths.get(args[i])).entrySet()) {
                String type=row.getKey();
                if(selected(type)||type.equals("Lflysettings/S;")||type.equals("Llocal/rc2/hud/DeviceMenu;"))
                    Files.writeString(folder.resolve(type.substring(1,type.length()-1).replace('/','.')+".smali"),AdaptiveHudTool.dump(row.getValue()),StandardCharsets.UTF_8);
            }
            return;
        }
        includeHome=args[0].equals("merge-ui");
        if((!args[0].equals("merge")&&!includeHome)||args.length!=5)throw new IllegalArgumentException();
        Map<String,ClassDef> original=AdaptiveHudTool.classes(Paths.get(args[1]));
        Map<String,ClassDef> fresh=AdaptiveHudTool.classes(Paths.get(args[2]));
        Map<String,ClassDef> result=new TreeMap<>(original);
        result.keySet().removeIf(NestedMenuDexTool::selected);
        for(Map.Entry<String,ClassDef> row:fresh.entrySet())if(selected(row.getKey()))result.put(row.getKey(),row.getValue());
        Path output=Paths.get(args[3]),work=Paths.get(args[4]);Files.createDirectories(work);
        if(Files.exists(output))throw new IllegalArgumentException("Output already exists");
        ArrayList<Path> files=new ArrayList<>();int index=0;
        for(ClassDef type:result.values()) {
            Path file=work.resolve("class"+(index++)+".smali");
            Files.writeString(file,AdaptiveHudTool.dump(type),StandardCharsets.UTF_8);files.add(file);
        }
        DexBuilder dex=new DexBuilder(new Opcodes(30,-1));SmaliBuilder compiler=new SmaliBuilder(work.toFile(),30);
        for(Path file:files)compiler.buildFile(file.getFileName().toString(),dex);
        FileDataStore store=new FileDataStore(output.toFile());try{dex.writeTo(store);}finally{store.raf.close();}
        Map<String,ClassDef> checked=AdaptiveHudTool.classes(output);int preserved=0;
        if(!checked.keySet().equals(result.keySet()))throw new IllegalStateException("Class inventory changed");
        for(Map.Entry<String,ClassDef> row:original.entrySet())if(!selected(row.getKey())) {
            if(!AdaptiveHudTool.dump(row.getValue()).equals(AdaptiveHudTool.dump(checked.get(row.getKey()))))
                throw new IllegalStateException("Original menu/HUD class changed: "+row.getKey());
            preserved++;
        }
        System.out.print(preserved);
    }
}
