# EXE HUD pipeline implementation plan

**Goal:** A standalone Windows EXE accepts the pinned original RC2 Fly APK and automatically extracts the bootstrap DEX, patches startup/manifest, appends the HUD DEX, aligns/signs the APK, retains the legacy v2 loader input and verifies the selected SDK30 v3 signature before offering installation.

**Architecture:** Bundle a minimal JRE and SDK/apktool tools in a hashed archive, extracted to a verified work cache. Keep signing credentials outside the EXE in per-user DPAPI-protected storage; generate a key on first use or import a user-selected existing key. Keep building offline and device installation separate. The UI retains small controls on the RC page and reports pipeline progress on the existing event queue.

**Scope:** RC2/rc331/API30/Fly1.21.8/code3115809 only, original SHA256 cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e. No phone HUD profile, arbitrary-version patch or root/ADB-key changes. No GitHub publishing.

## Contracts

- `HudBuilder(assets, work, emit, cancel=None).build(source: Path) -> dict`: status hud_built, apk path, digest, source_digest, certificate_sha256, receipt path. Also `latest() -> dict|None` and `verify(receipt) -> dict` with artifact revalidation.
- Tool archive `assets/hud/toolchain.zip`, pinned manifest `assets/hud/toolchain.json`, includes java/bin/java.exe and keytool.exe, lib/apktool.jar, lib/apksigner.jar, bin/zipalign.exe, lib/hud-tool.jar and licenses. Embedded payload `assets/hud/classes23.dex` with pinned SHA.
- Java command helper handles bootstrap extraction/patch/assembly, APK signing/verifying and public certificate inspection. Passwords only in process environment; never in command arguments, logs or bundle.
- GUI actions: Tạo APK HUD, Cài APK HUD, Mở thư mục. File selection occurs on the GUI thread; builds stay on the worker thread and can run without a USB device.
- Installation first tries data-retaining same-signer update. A signature replacement requires a verified backup/recovery plan and an explicit UI confirmation bound to current serial/installed hash/candidate hash. No implicit uninstall or force option.

## Tasks

1. [x] Implement and test builder, tool extraction/integrity, bootstrap patching, per-user key generation/protection and receipts. Reject stock mismatch, malformed/duplicate ZIP, tool tampering, unexpected changed entries and canceled builds. Real APK/frozen-EXE verification supplements host tests.
2. [x] Bundle minimal Java runtime and required jars/tools with licenses and hashes. Build/verify from paths containing spaces with no external Java/Python/SDK dependency. No private signing keys/stock468MB APK in EXE.
3. [x] Implement device install/backup/confirmation contract; handle missing connection, wrong device/version, foreground camera, corrupted archive, changed consent state and disconnect recovery. Use a physical no-symlink-follow ownership walker for UID/cacheGID remap. Contract behavior is host/fake-ADB verified; real-device execution is tracked separately below.
4. [x] Add compact RC-only controls, progress/error and recovery status, offline CLI build path and worker cancellation. Preserve Android-page actions and existing RC commands.
5. [x] Verify source tests, meaningful frozen build of the real stock APK, selected signature and archive diff; exercise GUI. Run a fresh security/correctness review, build EXE, copy local delivery and document use/limits.
6. [ ] Follow-up device verification: exercise the new installer on the actual RC and boot/reboot the exact frozen-generated APK. No RC was found during the final scan, so this evidence is NOT VERIFIED. Earlier manually installed HUD APK evidence is separate.

## Final host evidence — 2026-10-09

- 545 source tests passed; measured coverage93.87%. Fifteen release-package tests passed after packaging the final EXE.
- Final EXE0.3.0 SHA256 `52c41963badcaeab3167b29323ef4d25f11691265ea6d656af06a07ac589a0eb`, bytes82116011. Portable ZIP contains the same EXE/report and the HUD usage document; checksums verified after copying to Downloads.
- Frozen GUI smoke and real HUD build both exited0 with PATH restricted to System32 and JAVA_HOME/CLASSPATH removed. APK SHA256 `6a7818e0f6c2cabd31f770b0d0aa99285e2f158deca327b6f0f15143e2c289f7` matches the source pipeline result using this PC's retained signer.
- Current Java helper class and native RestoreOwner default ARMv7/API30 compile match bundled bytes. The final EXE contains five HUD assets and no private key/backup artifacts.
- Final review found no remaining actual High/Critical source issues. Device scan returned zero RCs. Public evidence is in `docs/hud-pipeline-verification.json`; private receipts/work remain outside Git.

Existing APK build implementation and live evidence: ../..//DJI_FLY_HUD_FEASIBILITY.md. The archive/header differences and old v2 record are not claimed to be vendor signatures of the modified APK. Hardware Keystore recovery is not promised. Last-turn user approval covered that actual install, not every future automatic erase; the app must confirm each required replacement.
