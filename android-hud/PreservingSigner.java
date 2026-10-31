import java.io.File;
import java.io.FileInputStream;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collections;
import com.android.apksig.ApkSigner;

/** Local signing only: keeps DJI's legacy JAR certificate bytes for loader investigation. */
public final class PreservingSigner {
    public static void main(String[] args) throws Exception {
        char[] password = System.getenv("RC2VI_SIGN_PASS").toCharArray();
        KeyStore store = KeyStore.getInstance("JKS");
        try (FileInputStream input = new FileInputStream(args[2])) { store.load(input, password); }
        PrivateKey key = (PrivateKey) store.getKey(args[3], password);
        ArrayList<X509Certificate> chain = new ArrayList<>();
        for (java.security.cert.Certificate certificate : store.getCertificateChain(args[3])) {
            chain.add((X509Certificate) certificate);
        }
        ApkSigner.SignerConfig signer = new ApkSigner.SignerConfig.Builder("HUD", key, chain).build();
        new ApkSigner.Builder(Collections.singletonList(signer))
            .setInputApk(new File(args[0])).setOutputApk(new File(args[1]))
            .setMinSdkVersion(24).setV1SigningEnabled(false).setV2SigningEnabled(true)
            .setV3SigningEnabled(true).setV4SigningEnabled(false)
            .setOtherSignersSignaturesPreserved(true).setAlignmentPreserved(true).build().sign();
        java.util.Arrays.fill(password, '\0');
    }
}
