package local.rc2.hud;

/** Independently encoded fixed LED protocol fields from FreeFCC v1.5.5's public LED profiles.
 * Source: https://github.com/doesthings/FreeFCC/tree/v1.5.5/app/src/main/assets/profiles
 * This class exposes no arbitrary command/parameter, FCC/4G or endpoint controls.
 */
final class LedProtocol {
    private LedProtocol() { }
    static byte[] frame(boolean on, int sequence) {
        if (sequence < 0 || sequence > 65535) throw new IllegalArgumentException("Sequence out of range");
        byte[] inner = { 0x55, 18, 4, 0, 2, 3, (byte)sequence, (byte)(sequence >> 8),
            0x40, 3, (byte)0xf9, (byte)0xa2, 0x59, (byte)0xce, (byte)0xed, (byte)(on ? 0xef : 0), 0, 0 };
        inner[3] = (byte)crc(inner, 3, 0x77, 0x8c);
        int checksum = crc(inner, inner.length - 2, 0x3692, 0x8408);
        inner[16] = (byte)checksum; inner[17] = (byte)(checksum >> 8);
        byte[] packet = new byte[inner.length + 8];
        packet[0] = 0x55; packet[1] = (byte)0xcc; packet[2] = 0x30; packet[3] = 0x75;
        packet[4] = (byte)inner.length;
        System.arraycopy(inner, 0, packet, 8, inner.length);
        return packet;
    }
    private static int crc(byte[] data, int length, int value, int polynomial) {
        for (int index = 0; index < length; index++) {
            value ^= data[index] & 255;
            for (int bit = 0; bit < 8; bit++) value = (value >>> 1) ^ ((value & 1) == 0 ? 0 : polynomial);
        }
        return value;
    }
}
