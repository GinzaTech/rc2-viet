import java.io.File;
import java.nio.file.Files;
import java.nio.file.Paths;
import brut.androlib.src.SmaliBuilder;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.writer.builder.DexBuilder;
import com.android.tools.smali.dexlib2.writer.io.FileDataStore;

public final class AssembleLoader {
    public static void main(String[] args) throws Exception {
        DexBuilder dex = new DexBuilder(new Opcodes(30, -1));
        SmaliBuilder compiler = new SmaliBuilder(new File(args[0]), 30);
        try (java.util.stream.Stream<java.nio.file.Path> files = Files.list(Paths.get(args[0]))) {
            for (java.nio.file.Path file : (Iterable<java.nio.file.Path>) files.sorted()::iterator) {
                if (file.toString().endsWith(".smali")) compiler.buildFile(file.getFileName().toString(), dex);
            }
        }
        dex.writeTo(new FileDataStore(new File(args[1])));
    }
}
