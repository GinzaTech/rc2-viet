import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import com.android.tools.smali.dexlib2.iface.ClassDef;
import com.android.tools.smali.dexlib2.iface.Field;
import com.android.tools.smali.dexlib2.iface.Method;
import com.android.tools.smali.dexlib2.iface.instruction.Instruction;
import com.android.tools.smali.dexlib2.iface.instruction.ReferenceInstruction;
import com.android.tools.smali.dexlib2.iface.reference.FieldReference;
import com.android.tools.smali.dexlib2.iface.reference.MethodReference;
import com.android.tools.smali.dexlib2.iface.reference.Reference;
import com.android.tools.smali.dexlib2.iface.reference.TypeReference;

/** Reads DEX metadata and instructions; never loads feature or native code. */
public final class FeatureAuditTool {
    static boolean isFeature(String type) {
        if(type.startsWith("Lapp/openfcc/battery/"))return true;
        if(!type.startsWith("L") || !type.contains("/"))return false;
        return FeatureAssemblyTool.PREFIXES.contains(type.substring(1,type.indexOf('/')));
    }
    static String signature(MethodReference m) {
        StringBuilder s=new StringBuilder(m.getName()).append('(');
        for(Object p:m.getParameterTypes())s.append(p);
        return s.append(')').append(m.getReturnType()).toString();
    }
    static boolean hasMethod(Map<String,ClassDef> classes,String type,String signature) {
        return hasMethod(classes,type,signature,new HashSet<>());
    }
    private static boolean hasMethod(Map<String,ClassDef> classes,String type,String signature,Set<String> seen) {
        if(!seen.add(type))return false;
        ClassDef c=classes.get(type);if(c==null)return false;
        for(Method m:methods(c))if(signature(m).equals(signature))return true;
        if(c.getSuperclass()!=null && hasMethod(classes,c.getSuperclass(),signature,seen))return true;
        for(Object i:c.getInterfaces())if(hasMethod(classes,(String)i,signature,seen))return true;
        return false;
    }
    private static boolean hasField(Map<String,ClassDef> classes,String type,FieldReference field,Set<String> seen) {
        if(!seen.add(type))return false;
        ClassDef c=classes.get(type);if(c==null)return false;
        for(Field f:fields(c))if(f.getName().equals(field.getName()) && f.getType().equals(field.getType()))return true;
        if(c.getSuperclass()!=null && hasField(classes,c.getSuperclass(),field,seen))return true;
        for(Object i:c.getInterfaces())if(hasField(classes,(String)i,field,seen))return true;
        return false;
    }
    private static String owner(Reference r) {
        if(r instanceof MethodReference)return ((MethodReference)r).getDefiningClass();
        if(r instanceof FieldReference)return ((FieldReference)r).getDefiningClass();
        if(r instanceof TypeReference)return ((TypeReference)r).getType();
        return "";
    }
    private static List<Method> methods(ClassDef c) {
        List<Method> out=new ArrayList<>();
        for(Object m:c.getDirectMethods())out.add((Method)m);
        for(Object m:c.getVirtualMethods())out.add((Method)m);
        return out;
    }
    private static List<Field> fields(ClassDef c) {
        List<Field> out=new ArrayList<>();
        for(Object f:c.getStaticFields())out.add((Field)f);
        for(Object f:c.getInstanceFields())out.add((Field)f);
        return out;
    }
    private static boolean platform(String type) {
        while(type.startsWith("["))type=type.substring(1);
        if(type.length()==1)return true;
        return type.startsWith("Ljava/") || type.startsWith("Ljavax/") || type.startsWith("Landroid/")
            || type.startsWith("Ldalvik/") || type.startsWith("Lorg/xml/") || type.startsWith("Lorg/w3c/")
            || type.startsWith("Lorg/json/") || type.startsWith("Lsun/");
    }
    private static boolean inheritedPlatform(Map<String,ClassDef> classes,String type,Set<String> seen) {
        if(type.equals("Ljava/lang/Object;"))return false;
        if(platform(type))return true;
        if(!seen.add(type))return false;
        ClassDef c=classes.get(type);return c!=null && c.getSuperclass()!=null
            && inheritedPlatform(classes,c.getSuperclass(),seen);
    }
    static void hosts(Path output,Path[] inputs) throws Exception {
        if(Files.exists(output))throw new IllegalArgumentException("Audit destination exists");
        Files.createDirectories(output);List<String> rows=new ArrayList<>();int n=0;
        for(Path input:inputs)for(ClassDef c:AdaptiveHudTool.classes(input).values()) {
            if(isFeature(c.getType()))continue;
            List<String> selected=new ArrayList<>();
            for(Method m:methods(c))if(m.getImplementation()!=null) {
                Set<String> refs=new TreeSet<>();
                for(Object ins:m.getImplementation().getInstructions())if(ins instanceof ReferenceInstruction) {
                    Reference ref=((ReferenceInstruction)ins).getReference();
                    if(isFeature(owner(ref)))refs.add(ref.toString());
                }
                for(String ref:refs)selected.add(input.getFileName()+"\t"+c.getType()+"\t"+signature(m)+"\t"+ref);
            }
            if(selected.isEmpty())continue;
            String file="host-"+(n++)+".smali";
            Files.writeString(output.resolve(file),AdaptiveHudTool.dump(c),StandardCharsets.UTF_8);
            for(String row:selected)rows.add(file+"\t"+row);
        }
        Files.write(output.resolve("hosts.tsv"),rows,StandardCharsets.UTF_8);
        System.out.println("host_classes="+n+",call_rows="+rows.size());
    }
    private static Method resolvedMethod(Map<String,ClassDef> classes,String type,String sig,Set<String> seen) {
        if(!seen.add(type))return null;
        ClassDef c=classes.get(type);if(c==null)return null;
        for(Method m:methods(c))if(signature(m).equals(sig))return m;
        Method found=c.getSuperclass()==null?null:resolvedMethod(classes,c.getSuperclass(),sig,seen);
        if(found!=null)return found;
        for(Object i:c.getInterfaces()){found=resolvedMethod(classes,(String)i,sig,seen);if(found!=null)return found;}
        return null;
    }
    private static String packageName(String type) { return type.substring(0,type.lastIndexOf('/')+1); }
    static void check(Path output,Path stock,Path[] features) throws Exception {
        Map<String,ClassDef> classes=new TreeMap<>();
        try(java.util.stream.Stream<Path> files=Files.list(stock)) {
            for(Path p:files.filter(p->p.getFileName().toString().endsWith(".dex")).sorted().toList())
                for(Map.Entry<String,ClassDef> c:AdaptiveHudTool.classes(p).entrySet())
                    if(classes.put(c.getKey(),c.getValue())!=null)throw new IllegalArgumentException("Duplicate stock class");
        }
        Map<String,ClassDef> added=new TreeMap<>();
        for(Path input:features)for(Map.Entry<String,ClassDef> c:AdaptiveHudTool.classes(input).entrySet())
            if(added.put(c.getKey(),c.getValue())!=null)throw new IllegalArgumentException("Duplicate added class");
        for(Map.Entry<String,ClassDef> c:added.entrySet())
            if(classes.put(c.getKey(),c.getValue())!=null)throw new IllegalArgumentException("Feature shadows source class");
        Set<String> missing=new TreeSet<>(),inherited=new TreeSet<>();
        for(ClassDef c:added.values()) {
            for(Method m:methods(c))if(m.getImplementation()!=null)
                for(Object ins:m.getImplementation().getInstructions())if(ins instanceof ReferenceInstruction) {
                    Reference ref=((ReferenceInstruction)ins).getReference();String type=owner(ref);
                    if(type.isEmpty() || platform(type))continue;
                    boolean found=true;
                    if(ref instanceof MethodReference) {
                        MethodReference method=(MethodReference)ref;
                        if(type.startsWith("[") && signature(method).equals("clone()Ljava/lang/Object;"))continue;
                        found=hasMethod(classes,type,signature(method));
                        if(!found && inheritedPlatform(classes,type,new HashSet<>()))inherited.add(ref.toString());
                        else if(!found)missing.add("method\t"+c.getType()+"\t"+ref);
                        if(found && !added.containsKey(type)) {
                            Method definition=resolvedMethod(classes,type,signature(method),new HashSet<>());
                            int flags=definition.getAccessFlags();
                            if((flags&1)==0 && !packageName(c.getType()).equals(packageName(definition.getDefiningClass())))
                                missing.add("method_access\t"+c.getType()+"\t"+ref);
                        }
                    } else if(ref instanceof FieldReference) {
                        found=hasField(classes,type,(FieldReference)ref,new HashSet<>());
                        if(!found)missing.add("field\t"+c.getType()+"\t"+ref);
                    } else {
                        while(type.startsWith("["))type=type.substring(1);
                        if(!platform(type) && !classes.containsKey(type))missing.add("type\t"+c.getType()+"\t"+type);
                    }
                }
        }
        Files.write(output,missing,StandardCharsets.UTF_8);
        Files.write(output.resolveSibling("platform-inherited.tsv"),inherited,StandardCharsets.UTF_8);
        System.out.println("classes="+added.size()+",missing="+missing.size()+",platform_inherited="+inherited.size());
    }
    static void dumpSelected(Path output,Path typesFile,Path[] inputs) throws Exception {
        if(Files.exists(output))throw new IllegalArgumentException("Dump destination exists");
        Set<String> needed=new HashSet<>(Files.readAllLines(typesFile,StandardCharsets.UTF_8));
        Files.createDirectories(output);List<String> rows=new ArrayList<>();
        for(Path input:inputs)for(ClassDef c:AdaptiveHudTool.classes(input).values())if(needed.remove(c.getType())) {
            String name="class-"+rows.size()+".smali";
            Files.writeString(output.resolve(name),AdaptiveHudTool.dump(c),StandardCharsets.UTF_8);
            rows.add(c.getType()+"\t"+name+"\t"+input.getFileName());
        }
        Files.write(output.resolve("classes.tsv"),rows,StandardCharsets.UTF_8);
        Files.write(output.resolve("missing-types.txt"),needed,StandardCharsets.UTF_8);
        System.out.println("dumped="+rows.size()+",missing="+needed.size());
    }
    public static void main(String[] args) throws Exception {
        if(args.length<3)throw new IllegalArgumentException();
        if(args[0].equals("hosts")) {
            Path[] inputs=new Path[args.length-2];for(int i=2;i<args.length;i++)inputs[i-2]=Paths.get(args[i]);
            hosts(Paths.get(args[1]),inputs);
        } else if(args[0].equals("dump") && args.length>=4) {
            Path[] inputs=new Path[args.length-3];for(int i=3;i<args.length;i++)inputs[i-3]=Paths.get(args[i]);
            dumpSelected(Paths.get(args[1]),Paths.get(args[2]),inputs);
        } else if(args[0].equals("check") && args.length>=4) {
            Path[] inputs=new Path[args.length-3];for(int i=3;i<args.length;i++)inputs[i-3]=Paths.get(args[i]);
            check(Paths.get(args[1]),Paths.get(args[2]),inputs);
        }
        else throw new IllegalArgumentException();
    }
}
