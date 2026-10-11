import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import brut.androlib.src.SmaliBuilder;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.writer.builder.DexBuilder;
import com.android.tools.smali.dexlib2.writer.io.FileDataStore;

public final class AdaptiveHudToolTest {
    static final String APP="Lcom/AppGuard/AppGuard/RenamedApplication;";
    static void assemble(Path root,Path output,String application) throws Exception {
        Files.createDirectories(root);
        Files.writeString(root.resolve("app.smali"),application);
        Files.writeString(root.resolve("other.smali"),".class public Lother/Preserved;\n.super Ljava/lang/Object;\n"
            +".field public static final VALUE:Ljava/lang/String; = \"untouched\"\n");
        DexBuilder dex=new DexBuilder(new Opcodes(30,-1));
        SmaliBuilder compiler=new SmaliBuilder(root.toFile(),30);
        compiler.buildFile("app.smali",dex); compiler.buildFile("other.smali",dex);
        FileDataStore store=new FileDataStore(output.toFile());
        try {dex.writeTo(store);} finally {store.raf.close();}
    }
    public static void main(String[] args) throws Exception {
        Path root=Paths.get(args[0]);
        String header=".class public "+APP+"\n.super Landroid/app/Application;\n";
        String swap="    invoke-static {p0}, "+APP+"->replaceApplicationContext(Landroid/app/Application;)V\n";
        String body=".method public onCreate()V\n    .registers 8\n"+swap
            +"    invoke-virtual {p0}, "+APP+"->getApplicationContext()Landroid/content/Context;\n"
            +"    move-result-object v0\n    invoke-static {v0}, "+APP+"->post(Landroid/content/Context;)V\n"
            +"    return-void\n.end method\n";
        Path source=root.resolve("source.dex"),patched=root.resolve("patched.dex");
        assemble(root.resolve("source-smali"),source,header+body);
        if(!AdaptiveHudTool.inspect(source,APP).contains("context_swap"))throw new AssertionError();
        AdaptiveHudTool.patch(source,patched,root.resolve("work"),APP);
        String result=AdaptiveHudTool.dump(AdaptiveHudTool.classes(patched).get(APP));
        if(result.indexOf("->post(")>result.indexOf("HudController;->install"))throw new AssertionError("Original tail skipped");
        if(AdaptiveHudTool.classes(patched).size()!=2)throw new AssertionError("Class lost");
        for(String bad:new String[]{body.replace(swap,swap+swap),body.replace(".registers 8",".registers 2"),
                                  body.replace("    return-void","    :branch\n    return-void")}){
            try{AdaptiveHudTool.hook(header+bad,APP);throw new AssertionError("Ambiguous hook accepted");}
            catch(IllegalArgumentException expected){}
        }
        try{AdaptiveHudTool.patch(patched,root.resolve("twice.dex"),root.resolve("work2"),APP);throw new AssertionError();}
        catch(IllegalArgumentException expected){}
        System.out.println("adaptive_bootstrap_preserved_classes_and_tail");
    }
}
