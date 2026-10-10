# DJI Fly HUD toggle — feasibility and runtime probe — 2026-10-08

Target: current DJI RC2 rc331, Android11/API30, dji.go.v5 1.21.8/code3115809. Installed APK and local analyzed APK both SHA256 cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e. Android phone1.21.12 is a different profile and was not runtime-tested for HUD in this investigation.

Current result: the permanent HUD APK has been built, normally installed on RC2 with the user's explicit remove/reinstall approval, and verified after an application restart and controller reboot. The earlier temporary prototype and its limits remain below as historical evidence. The final APK uses locally signed v3 for Android11 and retains the original v2 record as a native-loader input; this does not mean it preserves the original Android package signer or that its old v2 signature is valid for modified content.

## Findings

Live foreground is com.uav.component.fpv.FpvComponentActivity. A read-only UIAutomator dump shows video separately from top_bar_shell_layout, osd_shell_top_layout, left_bar_shell_layout, right_bar_shell_layout, map_shell_layout, radar_shell_layout and other layers. Video uses preview_shell_layout/view_surface_container/view_surface. No iv_full_screen or btn_fullscreen appears in the current camera UI dump.

Resource fpv_root_container_high_profile.xml defines HighProfileFpvContainer, with independent preview/touch/mission/metering layers and toolbar/map/OSD layers. HighProfileFpvContainer.requiresFullscreen() returns true while live HUD is still present. FpvComponentActivity.shouldEnableFullscreen() returns fullscreenSubject.hide() (Rx observable encapsulation, not a call hiding HUD views). These names do not establish a clean-HUD feature.

There are fullscreen icons/buttons in fpv_portrait_shell_preview.xml (iv_full_screen) and fpv_mvi_bottom_tools_slot.xml (btn_fullscreen, default GONE). Traced PortraitPreviewShellGate.onShellFinishInflate$lambda$4(boolean) calls IFpvFlyTabPageContainer.changePreviewToWifiHorizontal(boolean), a portrait/Wi-Fi layout switch. This is not evidence of a universal RC2 landscape HUD toggle. The model and shell are in classes21.dex; landscape activity/container are in classes20.dex.

## Feasibility and limits

A new in-process Eye/Hide-HUD button could technically set selected HUD group visibility while retaining the video surface and a separate always-available restore control. Exact grouping needs runtime testing: some layers contain focus/touch/mission warnings, not just decorative data; hiding all descendants indiscriminately can remove interactions or important state. A visibility-only mode can keep original layout dimensions and restore original per-view visibility rather than recreate the FPV activity.

The existing Vietnamese RRO has no executable code. It cannot by itself register a new click listener and implement a HUD toggle. A layout-only new icon without an existing wired handler is not a completed implementation. External launcher/accessibility overlay also cannot call setVisibility on another app's internal Views; drawing over the HUD would cover video instead of produce clean preview.

The inspected APK declares AppGuard application/protection and includes libAppGuard.so. The prior re-signed Vietnamese full APK installed but crashed native SIGSEGV; the local FINAL_INSTALLATION_REPORT records that and says the exact protection cause was not fully isolated. Prior runtime Java-bridge/JNI probes also failed/crashed/timed out. This established a practical deployment blocker; it did not prove a particular signature-check algorithm. No such probe or reinstall was repeated during the initial read-only pass.

Initial conclusion: UI structure permits the feature in principle. An installable/reliable mod on this protected DJI Fly build is NOT VERIFIED. A prototype would first require a stable way to add/execute the handler without breaking AppGuard, then ground tests for video continuity, hide/show/restore, touch behavior, dialogs and restart. No flight/drone/radio commands or HUD visibility changes were made during the initial pass.

## References

- DJI official camera-page guide: https://repair.dji.com/help/content?customId=01700006562&lang=en&paperDocType=ARTICLE&re=US&spaceId=17 . It describes flight status/battery/signals/telemetry; the cited page does not document a general Hide-HUD switch.
- Local resource layout and selective DEX disassembly; private research artifacts stay under ignored phone-work/hud/.
- Local prior deployment evidence: DJI_RC2_VIETNAMESE_20261005/FINAL_INSTALLATION_REPORT.md, lines50–52. It records crash history rather than successful HUD modification.

No modified DJI Fly APK was produced or installed during the initial feasibility/prototype passes. The subsequent permanent-APK work is described below.

## Authorized retry: direct JNI runtime prototype

The user confirmed the aircraft was off and the controller was in its launcher before the probe. The connection baseline still showed Fly in FPV, so RC Launcher was explicitly brought forward before injection. Subsequent FPV captures showed a live camera feed and ground telemetry (0.0 m, 0.0 m/s); physical aircraft power-off was not independently verified. Actions were restricted to software inspection, adding/removing the probe, switching controller activities and pressing the observed Eye button. No flight, takeoff, RTH, radio or FreeFCC controls were exercised.

AppGuard is involved in bootstrapping, not simply a Settings switch: manifest Application is com.AppGuard.AppGuard.QLVRK, its attachBaseContext calls LTQMG.load(), and its bootstrap attaches the configured com.dji.component.application.DJIApplication. Its provider TOSQY also patches application context. All 22 on-disk DEX files were inspected; that exact DJIApplication definition was absent from them, while direct JNI in the running process resolved it successfully. The live library exposes DexFileLoader/prepare_vmdex symbols. These observations support keeping the loader intact while testing a UI handler; they do not establish that deleting the library is a viable bypass.

The earlier full Vietnamese draft and original have byte-identical DEX and native-library entries. Their manifest/resources and signing/container differ. The earlier SIGSEGV cause is therefore still not narrowed to a specific signature-check function. No signature-check patch, library removal or AppGuard-disable candidate was installed in this retry.

Native Frida inspection succeeded against the original 32-bit ARM Fly process. A small direct JNI probe obtained the VM, attached its thread, resolved ActivityThread.currentApplication(), read package dji.go.v5 and application class DJIApplication, and detached. This avoided the previously failing high-level Java-bridge path. The Fly PID remained 3205 throughout the short investigation.

A standalone Java helper (Android framework Views only) was compiled with javac and D8, then loaded through DexClassLoader via direct JNI. The tested final DEX is 10,316 bytes, SHA256 9c00aaedf2260f5228ed6f1ed886e191894a4c17dd24e0b733b0dcb833d21c20. It registers Application.ActivityLifecycleCallbacks and places a 48 dp Eye icon on the independent activity content FrameLayout when FpvComponentActivity resumes. Clicking it hides selected HUD groups with INVISIBLE while keeping originally GONE/INVISIBLE states unchanged. Clicking again restores each original visibility. Pause restores automatically; destruction removes the button and state. No recurring poll/timer is used by the UI helper.

Final target groups are top_bar_shell_layout, osd_shell_top_layout, osd_shell_layout, left_bar_shell_layout, right_bar_shell_layout, map_shell_layout, radar_shell_layout, histogram_shell_layout, zoom_focus_layer_layout, right_bottom_shell_layout, attitude_bar_shell_layout, osd_shell_top_child_layout, portrait_right_bar_shell_layout, metering_shell_layout and gimbal_shell_layout. The preview surface, its ancestors, mission/touch-warning/error/menu layers are not hidden by this prototype. A guard rejects a candidate group if it contains view_surface. The restore button is outside all selected groups.

## Observed results and limits

- Button presence and clickability were verified in UIAutomator XML; taps used the current observed button bounds.
- Final log records `hud_hidden groups=15`; a captured screen shows the video and independent red Eye icon with the selected HUD absent.
- The preview SurfaceView's last presented timestamp advanced from 2771315054202 to 2773281774305 ns across the final hide probe. This establishes continued video presentation during the sampled interval, not a general FPS or latency guarantee.
- Show-HUD restored every resource ID present in the immediately preceding baseline XML; the missing-ID set was empty.
- Hiding then switching to RC Launcher and back restored normal HUD and the `Ẩn HUD thử nghiệm` button state.
- The helper uninstall path was exercised. An initial live-list iteration raced callback removal; it was corrected to iterate a `toArray()` snapshot, and the corrected uninstall reported exactly one removed helper without a Java exception. Removal restored views and removed the button; the final helper was subsequently re-registered.
- Original Fly APK SHA256 still matched the stock value, libAppGuard.so remained mapped, Fly PID remained 3205, and no frida-inject process remained after bounded probes.
- Last verified controller foreground after the final hide/show/pause/resume checks was RC Launcher, with HUD restored. The corrected uninstall was then tested and the helper was re-registered successfully. The subsequent foreground/UI recheck timed out; Windows and the app's WinUSB discovery then found zero connected RC2 devices. Final controller foreground and button availability after that USB loss are NOT VERIFIED. If the same Fly process is still running, the registration is temporary; if the controller/Fly restarted, it is lost.

This helper is lost when the Fly process exits or the controller reboots. Normal camera activity navigation within the same process was exercised; reboot survival, automatic reinjection, long-duration stability, CPU/RAM impact, flight use, aircraft/model variants, phone Fly 1.21.12 and desktop EXE integration are NOT VERIFIED. It is not a permanent AppGuard bypass, a modified signed Fly APK, or a released desktop feature. Restarting the Fly process/controller returns to the original code path without the helper. Probe files in Fly code_cache are local test artifacts and do not provide autostart by themselves.

Private source, DEX, scripts, runtime ELF segment, logs, XML and camera captures are under ignored phone-work/appguard/. The camera images and runtime dumps were not committed or published. `final-proof.json` stores the bounded observations and the subsequent disconnect limitation. The owned ADB connection was closed after Windows ceased detecting the device; the planned removal of temporary device diagnostics could not be executed and is pending reconnection. The desktop EXE and its published release were not changed in this task.

Runtime mechanism references: [Frida JavaScript/native API](https://frida.re/docs/javascript-api/) and [Android DexClassLoader](https://developer.android.com/reference/dalvik/system/DexClassLoader). Local observations, rather than these API references, establish the RC2 results above.

## Permanent APK installed — 2026-10-08

The final APK is dji.go.v5 1.21.8/code3115809, 468,112,209 bytes, SHA256 abeff2051350dde3dfc524cd1f3ebd63864349e7366cd9f84406cee9778ba750. Its only changed ZIP entry contents are AndroidManifest.xml and classes.dex; classes23.dex is added. DEX2-22, resources and native libraries retain both extracted bytes and compressed payload bytes. Compression method/size, CRC, file size and timestamps are validated for unchanged entries. ZIP offsets/alignment padding/signing block layout can change; entire container/header identity is not claimed.

The helper is Android framework Java in android-hud/src/local/rc2/hud/. A private provider with exported=false and initOrder=-10 registers it; an idempotent startup call is also added to QLVRK.onCreate after real-Application initialization. The existing AppGuard bootstrap/provider/native libraries remain. The final UI changes only visible matched groups, logs changed/tracked counts separately, restores original per-view visibility and automatically restores on pause. Preview ancestors and warning/error/mission layers remain available.

An unchanged-code re-sign control crashed native at 0xb4c. Retaining DJI's legacy JAR entries alone did not fix it. Replacing only the new v2 signing-block entry with the original v2 record while retaining a valid local v3 signature allowed the control and embedded-HUD candidate to boot. This isolates dependence on that v2 record/layout; it does not establish which certificate/signature/digest field the native protector derives its key from. The SDK apksigner verified the selected Android11/API30 v3 path after replacement. Older verifier paths are not supported by this result; the stale retained v2 record must not be described as a valid signature of the modified APK.

A root bind-path trial demonstrated startup without Frida and one Eye control. Android's normal `pm install -r` then rejected the different signer with INSTALL_FAILED_UPDATE_INCOMPATIBLE, leaving stock unchanged. The user separately approved removing/reinstalling with backup and the Keystore/login limitation. A verified 458,784,768-byte Fly-only archive was kept on PC and verified again after transfer to a private device directory. `pm uninstall` and `pm install` both returned Success. The new package UID is 10029; restored app-file ownership was remapped from 10022 to 10029, including cache GID 20022 to 20029, without following symlinks. Stale code_cache and native-library symlinks were excluded. Android Keystore keys were not restored or claimed restored.

Normal-install observations:

- Installed file hash matches the final APK, and the Vietnamese overlay is enabled.
- Eye toggles between `Ẩn HUD` and `Hiện HUD`; the final log recorded changed=15/tracked=15 in the observed camera state.
- The restore check found no missing resource IDs from the baseline.
- Force-stop/new-process test: old PID1642, new PID18041; Eye appeared without an injector or temporary mount. An early read of a transition/home window was not counted as a pass; the final camera tree was explicitly observed.
- Controller reboot changed boot ID from 137db226-88e4-478c-a444-8f65dc830e53 to 418fb592-6094-46b2-a1bf-ad09219bcc0e. sys.boot_completed=1; boot foreground was RC Launcher. After opening Fly/camera, Eye appeared and the final APK hash still matched.
- Vietnamese and three-button navigation overlays stayed enabled after reboot. No frida-inject process or APK trial mount was present.

The earlier mounted trial had a live camera preview with warnings retained. During final normal-install checks the aircraft was disconnected: SurfaceFlinger video timestamps were zero and the preview was blank. Final post-install live-aircraft video/link/flight operation, account-session recovery, flight use and long-duration thermal/RAM stability are NOT VERIFIED. Do not turn those missing checks into a successful-flight claim.

Evidence is private under phone-work/appguard/persistent/: final-validation.json, installation.json, normal-install-proof.json, coldstart-proof.json and reboot-proof.json. Camera images/logs/backups are not published. The installable local file is C:/Users/kona/Downloads/DJI-Fly-RC2-1.21.8-HUD.apk. RC2 PC source now explicitly allows this exact hash alongside stock; local Windows compatibility build is 0.2.1, with no new desktop HUD installer UI or embedded 468MB Fly APK.

## Local0.3.0 EXE pipeline — 2026-10-09

The Windows app now provides offline HUD creation and a guarded installer. Its bundled minimal Java runtime runs a Java helper that reproduces the bootstrap startup patch, appends the pinned HUD DEX, updates the private provider, aligns/signs the container and verifies the selected API30 v3 signer. The native/resource and compressed unchanged-entry checks are retained. Private signer storage is per Windows user with DPAPI and owner/SYSTEM-only DACLs; original Fly input and private keys are outside the EXE.

The newly generated APK, using the prior local signer, has SHA256 `6a7818e0f6c2cabd31f770b0d0aa99285e2f158deca327b6f0f15143e2c289f7`. Its `classes.dex` differs from the manually installed APK above; all other extracted entries match that prior artifact. A frozen EXE build using its own Java runtime, with host PATH restricted to System32 and JAVA_HOME/CLASSPATH removed, produced the new APK and exited0. Host tests cover source/recipe/signature validation, GUI commands, confirmation state, backup/cancellation/cleanup, and the current portable/checksum packaging.

No RC was available during this pipeline verification. The exact new artifact's device boot/reboot and the new installer on real hardware are **NOT VERIFIED**. The manual APK's earlier device evidence does not close that gap. See [HUD_APK.md](HUD_APK.md) for the supported profile and usage. GitHub publication was not performed in this request.
