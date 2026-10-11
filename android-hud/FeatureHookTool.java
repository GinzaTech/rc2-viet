import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import brut.androlib.src.SmaliBuilder;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.iface.ClassDef;
import com.android.tools.smali.dexlib2.writer.builder.DexBuilder;
import com.android.tools.smali.dexlib2.writer.io.FileDataStore;

/** Candidate-only guarded entry hooks; unrelated method bodies are preserved. */
public final class FeatureHookTool {
    static String patch(String text,String type) {
        String[][] hooks;
        if(type.equals("Lcom/uav/fpv/leftbar/component/takeoffandland/LandAndGoHomeVM;"))
            hooks=new String[][]{{"j()V","manual"}};
        else if(type.equals("Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandView;"))
            hooks=new String[][]{{"d0(Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandViewModel$CountDownEvent;)V","suppress"}};
        else if(type.equals("Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandViewModel;"))
            hooks=new String[][]{{"N1()V","video"},{"h1()V","video"}};
        else return text;
        for(String[] hook:hooks) {
            Pattern p=Pattern.compile("(?ms)^\\.method ([^\\n]* "+Pattern.quote(hook[0])+")\\n(.*?)^\\.end method");
            Matcher m=p.matcher(text);
            if(!m.find()||m.group(1).contains("native"))throw new IllegalArgumentException("Required host method missing/native");
            int start=m.start(),end=m.end();String method=m.group();
            if(m.find()||method.contains("rc2port_"))throw new IllegalArgumentException("Ambiguous or existing hook");
            Matcher registers=Pattern.compile("(?m)^    \\.(registers|locals) (\\d+)\\s*$").matcher(method);
            if(!registers.find())throw new IllegalArgumentException("Registers missing");
            int number=Integer.parseInt(registers.group(2));
            int params=hook[1].equals("suppress")?2:1;
            if((registers.group(1).equals("registers")?number-params:number)<1)
                throw new IllegalArgumentException("No scratch local available");
            int offset=registers.end();String mode=hook[1];String label="rc2port_"+mode;
            String call=mode.equals("manual")?"    invoke-static {}, Lrthguard/Guard;->manual()V\n":
                mode.equals("suppress")?"    invoke-static {p1}, Lrthguard/Guard;->suppressLegacy(Ljava/lang/Object;)Z\n":
                "    invoke-static {}, Lrthguard/Guard;->blockVideo()Z\n";
            String code="\n    :"+label+"_start\n"+call;
            if(!mode.equals("manual"))code+="    move-result v0\n    if-eqz v0, :"+label+"_done\n    return-void\n";
            code+="    :"+label+"_end\n    .catch Ljava/lang/RuntimeException; {:"+label+"_start .. :"+label+"_end} :"+label+"_error\n"
                +"    .catch Ljava/lang/LinkageError; {:"+label+"_start .. :"+label+"_end} :"+label+"_error\n"
                +"    goto :"+label+"_done\n    :"+label+"_error\n    move-exception v0\n    :"+label+"_done\n";
            text=text.substring(0,start)+method.substring(0,offset)+code+method.substring(offset)+text.substring(end);
        }
        return text;
    }
    public static void main(String[] args) throws Exception {
        if(args.length!=3 && args.length!=4)throw new IllegalArgumentException();
        Path input=Paths.get(args[0]),output=Paths.get(args[1]),work=Paths.get(args[2]);
        if(Files.exists(output))throw new IllegalArgumentException();
        Map<String,ClassDef> classes=AdaptiveHudTool.classes(input);Files.createDirectories(work);
        Map<String,String> replacements=new java.util.TreeMap<>();
        if(args.length==4)try(java.util.stream.Stream<Path> paths=Files.list(Paths.get(args[3]))) {
            for(Path p:paths.filter(p->p.getFileName().toString().endsWith(".smali")).sorted().toList()) {
                String text=Files.readString(p,StandardCharsets.UTF_8);
                Matcher type=Pattern.compile("(?m)^\\.class [^\\n]* (L[^\\n]+)$").matcher(text);
                if(!type.find())throw new IllegalArgumentException("Patch class missing");
                if(classes.containsKey(type.group(1)) && replacements.put(type.group(1),text)!=null)
                    throw new IllegalArgumentException("Duplicate replacement");
            }
        }
        ArrayList<Path> files=new ArrayList<>();int count=0,changed=0;
        for(Map.Entry<String,ClassDef> row:classes.entrySet()) {
            String before=AdaptiveHudTool.dump(row.getValue()),after=replacements.getOrDefault(row.getKey(),before);
            after=patch(after,row.getKey());
            if(!before.equals(after))changed++;
            Path file=work.resolve("class"+(count++)+".smali");Files.writeString(file,after,StandardCharsets.UTF_8);files.add(file);
        }
        if(changed==0)throw new IllegalArgumentException("No host hook targets in DEX");
        DexBuilder dex=new DexBuilder(new Opcodes(30,-1));SmaliBuilder compiler=new SmaliBuilder(work.toFile(),30);
        for(Path file:files)compiler.buildFile(file.getFileName().toString(),dex);
        FileDataStore store=new FileDataStore(output.toFile());try{dex.writeTo(store);}finally{store.raf.close();}
        Map<String,ClassDef> result=AdaptiveHudTool.classes(output);
        if(!result.keySet().equals(classes.keySet()))throw new IllegalStateException("Host class lost");
        for(String type:classes.keySet()) {
            String before=AdaptiveHudTool.dump(classes.get(type));
            if(!replacements.containsKey(type) && patch(before,type).equals(before)&&!before.equals(AdaptiveHudTool.dump(result.get(type))))
                throw new IllegalStateException("Unrelated class changed");
        }
        System.out.print(changed);
    }
}
