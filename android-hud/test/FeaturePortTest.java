import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;
import com.android.tools.smali.dexlib2.iface.ClassDef;

public final class FeaturePortTest {
    public static void main(String[] args) throws Exception {
        Path root=Paths.get(args[0]);
        String type="Lcom/uav/fpv/leftbar/component/takeoffandland/LandAndGoHomeVM;";
        String original=".class public "+type+"\n.super Ljava/lang/Object;\n"
            +".method public j()V\n    .registers 2\n    const/4 v0, 0x1\n    return-void\n.end method\n";
        String patched=FeatureHookTool.patch(original,type);
        if(!patched.contains("Guard;->manual()V") || !patched.contains(".catch Ljava/lang/LinkageError;")
           || !patched.contains("const/4 v0, 0x1"))throw new AssertionError("Fallback/body lost");
        for(String bad:new String[]{original.replace(".registers 2",".registers 1"),
                original+original.substring(original.indexOf(".method")),patched,
                original.replace("public j","public native j")}) {
            try{FeatureHookTool.patch(bad,type);throw new AssertionError("Invalid hook accepted");}
            catch(IllegalArgumentException expected){}
        }
        if(!FeatureHookTool.patch(original,"Lother/Preserved;").equals(original))throw new AssertionError();
        Path smali=root.resolve("input");Files.createDirectories(smali);
        Files.writeString(smali.resolve("host.smali"),patched);
        Files.writeString(smali.resolve("parent.smali"),".class public Lsample/Parent;\n.super Ljava/lang/Object;\n"
                +".method public getOrNull()Ljava/lang/Object;\n    .registers 1\n    return-object p0\n.end method\n");
        Files.writeString(smali.resolve("child.smali"),".class public Lsample/Child;\n.super Lsample/Parent;\n");
        Path dex=root.resolve("assembled.dex");
        FeatureAssemblyTool.main(new String[]{"assemble",dex.toString(),smali.toString()});
        Map<String,ClassDef> classes=AdaptiveHudTool.classes(dex);
        if(classes.size()!=3 || !FeatureAuditTool.hasMethod(classes,"Lsample/Child;","getOrNull()Ljava/lang/Object;"))
            throw new AssertionError("Inherited API not resolved");
        if(FeatureAuditTool.hasMethod(classes,"Lsample/Child;","missing()V"))throw new AssertionError();
        if(!FeatureAuditTool.isFeature("Llanstream/Lan;") || FeatureAuditTool.isFeature("Lridkill/R;"))
            throw new AssertionError("Feature scope drift");
        System.out.println("feature_extraction_host_guards_and_dependency_inheritance_passed");
    }
}
