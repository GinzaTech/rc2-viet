import java.io.OutputStream;
import java.io.PrintStream;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.security.Key;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import brut.androlib.src.SmaliBuilder;
import com.android.apksig.ApkSigner;
import com.android.apksig.ApkVerifier;
import com.android.apksig.KeyConfig;
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

/** Offline helper for the pinned RC2 API30 loader; requires Java 17 and the public tool jars.
 * Usage: patch inputDEX outputDEX workdir | sign input out keystore alias |
 * verify input | keycert keystore alias. Only HUD_SIGN_PASS supplies a password.
 * Successful patch/sign are silent; verify/keycert print exactly 64 lowercase hex characters.
 */
public final class HudTool {
    private static final int SDK = 30;
    private static final String PREFIX = "Lcom/AppGuard/AppGuard/";
    private static final List<String> CLASSES = Collections.unmodifiableList(Arrays.asList(
        PREFIX + "LTQMG;", PREFIX + "MKFGD;", PREFIX + "QLVRK;",
        PREFIX + "TOSQY;", PREFIX + "a;"));
    private static final String APPLICATION = PREFIX + "QLVRK;";
    private static final String ANCHOR = "    invoke-static {p0}, " + APPLICATION
        + "->replaceApplicationContext(Landroid/app/Application;)V\n";
    private static final Pattern ON_CREATE = Pattern.compile(
        "(?ms)^\\.method public onCreate\\(\\)V\\n.*?^\\.end method");
    // This mirrors the normally installed startup-hook evidence. Catch only recoverable
    // helper initialization failures; the preceding AppGuard initialization is untouched.
    private static final String HOOK = "\n"
        + "    :hud_start\n"
        + "    invoke-virtual {p0}, " + APPLICATION
        + "->getApplicationContext()Landroid/content/Context;\n"
        + "    move-result-object v0\n"
        + "    check-cast v0, Landroid/app/Application;\n"
        + "    invoke-static {v0}, Llocal/rc2/hud/HudController;"
        + "->install(Landroid/app/Application;)Ljava/lang/String;\n"
        + "    :hud_end\n"
        + "    .catch Ljava/lang/RuntimeException; {:hud_start .. :hud_end} :hud_error\n"
        + "    .catch Ljava/lang/LinkageError; {:hud_start .. :hud_end} :hud_error\n"
        + "    goto :hud_done\n"
        + "    :hud_error\n"
        + "    move-exception v0\n"
        + "    const-string v1, \"RC2Hud\"\n"
        + "    const-string v2, \"bootstrap_hook_failed\"\n"
        + "    invoke-static {v1, v2, v0}, Landroid/util/Log;"
        + "->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I\n"
        + "    :hud_done\n";

    private HudTool() { }

    public static void main(String[] args) {
        PrintStream stdout = System.out;
        PrintStream stderr = System.err;
        String mode = args.length == 0 ? "" : args[0];
        String digest = null;
        boolean failed = false;
        // Shaded smali may print parser diagnostics itself. Never let library logging,
        // exception messages or paths enter the runner's digest or credential channels.
        try (PrintStream quiet = new PrintStream(OutputStream.nullOutputStream())) {
            System.setOut(quiet);
            System.setErr(quiet);
            try {
                digest = execute(mode, args);
            } catch (Exception | LinkageError failure) {
                failed = true;
            } finally {
                System.setOut(stdout);
                System.setErr(stderr);
            }
        }
        if (failed) {
            stderr.println(errorMessage(mode));
            System.exit(1);
        } else if (digest != null) {
            stdout.print(digest);
        }
    }

    private static String execute(String mode, String[] args) throws Exception {
        switch (mode) {
            case "patch":
                requireArguments(args, 4);
                patch(path(args[1]), path(args[2]), path(args[3]));
                return null;
            case "sign":
                requireArguments(args, 5);
                sign(path(args[1]), path(args[2]), path(args[3]), args[4]);
                return null;
            case "verify":
                requireArguments(args, 2);
                return verify(path(args[1]));
            case "keycert":
                requireArguments(args, 3);
                return keyCertificate(path(args[1]), args[2]);
            default:
                throw new IllegalArgumentException();
        }
    }

    private static void requireArguments(String[] args, int count) {
        if (args.length != count) throw new IllegalArgumentException();
        for (String argument : args) {
            if (argument == null || argument.isEmpty()) throw new IllegalArgumentException();
        }
    }

    private static String errorMessage(String mode) {
        switch (mode) {
            case "patch": return "HUD patch failed.";
            case "sign": return "HUD sign failed.";
            case "verify": return "HUD verify failed.";
            case "keycert": return "HUD keycert failed.";
            default: return "HUD command failed.";
        }
    }

    private static Path path(String value) {
        return Paths.get(value).toAbsolutePath().normalize();
    }

    private static void distinctOutput(Path output, Path input) throws Exception {
        if (output.equals(input) || (Files.exists(output) && Files.isSameFile(output, input))) {
            throw new IllegalArgumentException();
        }
        if (Files.exists(output, LinkOption.NOFOLLOW_LINKS)
                && !Files.isRegularFile(output, LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalArgumentException();
        }
        if (!Files.isDirectory(output.getParent())) throw new IllegalArgumentException();
    }

    private static Map<String, ClassDef> loaderClasses(Path input) throws Exception {
        // Do not accept a ZIP/ODEX container or rebuild a DEX whose other classes would
        // be lost. The caller pins the full original APK hash before extracting this DEX.
        byte[] magic = new byte[4];
        try (java.io.InputStream stream = Files.newInputStream(input)) {
            if (stream.read(magic) != magic.length
                    || !Arrays.equals(magic, new byte[] {'d', 'e', 'x', '\n'})) {
                throw new IllegalArgumentException();
            }
        }
        MultiDexContainer container = DexFileFactory.loadDexContainer(input.toFile(), new Opcodes(SDK, -1));
        if (container.getDexEntryNames().size() != 1) throw new IllegalArgumentException();
        DexBackedDexFile dex = container.getEntry((String) container.getDexEntryNames().get(0)).getDexFile();
        if (dex.classSection.size() != CLASSES.size()) throw new IllegalArgumentException();
        Map<String, ClassDef> classes = new TreeMap<>();
        // apktool 2.12.1's shaded API exposes an erased IndexedSection, not getClasses().
        for (Object entry : dex.classSection) {
            ClassDef definition = (ClassDef) entry;
            if (!CLASSES.contains(definition.getType())
                    || classes.put(definition.getType(), definition) != null) {
                throw new IllegalArgumentException();
            }
        }
        if (classes.size() != CLASSES.size()) throw new IllegalArgumentException();
        return classes;
    }

    private static String dump(ClassDef definition) throws Exception {
        StringWriter text = new StringWriter();
        try (BaksmaliWriter writer = new BaksmaliWriter(text)) {
            new ClassDefinition(new BaksmaliOptions(), definition).writeTo(writer);
        }
        return text.toString().replace("\r\n", "\n");
    }

    private static String startupHook(String text) {
        if (text.contains("Llocal/rc2/hud/") || text.contains(":hud_")) {
            throw new IllegalArgumentException();
        }
        Matcher match = ON_CREATE.matcher(text);
        if (!match.find()) throw new IllegalArgumentException();
        int start = match.start();
        int end = match.end();
        String method = match.group();
        if (match.find() || !method.contains("\n    .registers 7\n")) {
            throw new IllegalArgumentException();
        }
        int anchor = method.indexOf(ANCHOR);
        if (anchor < 0 || method.indexOf(ANCHOR, anchor + ANCHOR.length()) >= 0) {
            throw new IllegalArgumentException();
        }
        int insertion = anchor + ANCHOR.length();
        if (!method.substring(insertion).matches("\\s*return-void\\s*\\.end method")) {
            throw new IllegalArgumentException();
        }
        String patched = method.substring(0, insertion) + HOOK + method.substring(insertion);
        return text.substring(0, start) + patched + text.substring(end);
    }

    private static void patch(Path input, Path output, Path work) throws Exception {
        distinctOutput(output, input);
        Map<String, ClassDef> classes = loaderClasses(input);
        String application = startupHook(dump(classes.get(APPLICATION)));
        Files.createDirectories(work);
        // Isolated child avoids stale .smali files and allows receipt verification to
        // repeat in the same workdir. Only the five freshly dumped files are assembled.
        Path smali = Files.createTempDirectory(work, "hud-smali-");
        Path staged = null;
        List<Path> dumped = new ArrayList<>();
        try {
            for (Map.Entry<String, ClassDef> entry : classes.entrySet()) {
                String type = entry.getKey();
                String name = type.substring(1, type.length() - 1).replace('/', '_') + ".smali";
                Path file = smali.resolve(name);
                dumped.add(file);
                Files.write(file, (APPLICATION.equals(type) ? application : dump(entry.getValue()))
                    .getBytes(StandardCharsets.UTF_8));
            }
            SmaliBuilder compiler = new SmaliBuilder(smali.toFile(), SDK);
            DexBuilder dex = new DexBuilder(new Opcodes(SDK, -1));
            for (Path file : dumped) compiler.buildFile(file.getFileName().toString(), dex);
            staged = Files.createTempFile(output.getParent(), "hud-output-", ".dex");
            FileDataStore data = new FileDataStore(staged.toFile());
            try {
                dex.writeTo(data);
            } finally {
                data.raf.close();
            }
            loaderClasses(staged);
            publish(staged, output);
        } finally {
            if (staged != null) Files.deleteIfExists(staged);
            for (Path file : dumped) Files.deleteIfExists(file);
            Files.deleteIfExists(smali);
        }
    }

    private static char[] password() {
        String value = System.getenv("HUD_SIGN_PASS");
        if (value == null || value.isEmpty()) throw new IllegalArgumentException();
        return value.toCharArray();
    }

    private static X509Certificate certificate(Certificate value) {
        if (!(value instanceof X509Certificate)) throw new IllegalArgumentException();
        return (X509Certificate) value;
    }

    private static X509Certificate signerCertificate(KeyStore store, String alias) throws Exception {
        if (!store.isKeyEntry(alias)) throw new IllegalArgumentException();
        return certificate(store.getCertificate(alias));
    }

    private static String keyCertificate(Path keystore, String alias) throws Exception {
        char[] secret = password();
        try {
            KeyStore store = KeyStore.getInstance(keystore.toFile(), secret);
            // Public certificate inspection never retrieves the alias's private key.
            return digest(signerCertificate(store, alias));
        } finally {
            Arrays.fill(secret, '\0');
        }
    }

    private static void sign(Path input, Path output, Path keystore, String alias) throws Exception {
        char[] secret = password();
        Path staged = null;
        try {
            distinctOutput(output, input);
            distinctOutput(output, keystore);
            KeyStore store = KeyStore.getInstance(keystore.toFile(), secret);
            Key key = store.getKey(alias, secret);
            if (!(key instanceof PrivateKey)) throw new IllegalArgumentException();
            Certificate[] certificates = store.getCertificateChain(alias);
            if (certificates == null || certificates.length == 0) throw new IllegalArgumentException();
            List<X509Certificate> chain = new ArrayList<>();
            for (Certificate value : certificates) chain.add(certificate(value));
            ApkSigner.SignerConfig signer = new ApkSigner.SignerConfig.Builder(
                "HUD", new KeyConfig.Jca((PrivateKey) key), chain).build();
            staged = Files.createTempFile(output.getParent(), "hud-output-", ".apk");
            new ApkSigner.Builder(Collections.singletonList(signer))
                .setInputApk(input.toFile()).setOutputApk(staged.toFile())
                .setMinSdkVersion(24).setV1SigningEnabled(false).setV2SigningEnabled(true)
                .setV3SigningEnabled(true).setV4SigningEnabled(false)
                .setOtherSignersSignaturesPreserved(true).setAlignmentPreserved(true)
                .build().sign();
            if (!digest(chain.get(0)).equals(verify(staged))) throw new IllegalStateException();
            publish(staged, output);
        } finally {
            Arrays.fill(secret, '\0');
            if (staged != null) Files.deleteIfExists(staged);
        }
    }

    private static String verify(Path input) throws Exception {
        ApkVerifier.Result result = new ApkVerifier.Builder(input.toFile())
            .setMinCheckedPlatformVersion(SDK).setMaxCheckedPlatformVersion(SDK).build().verify();
        if (!result.isVerified() || !result.isVerifiedUsingV3Scheme()
                || result.getSignerCertificates().size() != 1) {
            throw new IllegalArgumentException();
        }
        // This is the signer selected by SDK30 verification, not a legacy JAR/v2
        // certificate or a historical certificate from a rotation lineage.
        return digest(result.getSignerCertificates().get(0));
    }

    private static String digest(X509Certificate certificate) throws Exception {
        byte[] bytes = MessageDigest.getInstance("SHA-256").digest(certificate.getEncoded());
        char[] hex = "0123456789abcdef".toCharArray();
        char[] result = new char[bytes.length * 2];
        for (int index = 0; index < bytes.length; index++) {
            int value = bytes[index] & 0xff;
            result[index * 2] = hex[value >>> 4];
            result[index * 2 + 1] = hex[value & 0xf];
        }
        return new String(result);
    }

    private static void publish(Path staged, Path output) throws Exception {
        try {
            Files.move(staged, output, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException unsupported) {
            Files.move(staged, output, StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
