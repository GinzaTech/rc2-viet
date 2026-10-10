# DJI Fly persistent HUD APK implementation plan

> For agentic workers: execute the plan locally; use the existing read-only side task for application-bootstrap evidence and a final reviewer for the complete change.

**Goal:** Embed the previously verified Eye/HUD handler in the RC2 DJI Fly APK so it registers on every application launch without PC reinjection.

**Architecture:** Keep the stock AppGuard bootstrap and DJI code, add one independently compiled helper DEX, and call its entry point after the real Application is initialized. Preserve resources and native bytes. Investigate signing separately from HUD behavior using a stock re-sign control and a reversible, root-only code-path trial before any installer action that removes app data.

**Tech stack:** Java 8 Android framework Views, D8/API30, shaded smali tooling, APK Signature Scheme v2/v3, Python/pytest ZIP validation, isolated WinUSB/ADB.

**Spec:** ../../DJI_FLY_HUD_FEASIBILITY.md, plus the user's explicit request to install the handler permanently in the APK.

**Ruling:** Add a private provider with initOrder -10 while keeping the stock AppGuard provider at 2147483647. Also prepare an idempotent QLVRK startup-hook variant for a code-path trial, because the running PackageManager cannot discover a new provider from an APK bind mount alone. Provider-only and hook candidates are distinct, and neither trial is a normal installer pass.

**Signing finding:** The SDK signer cannot append a v3 signer while preserving an existing v3 block. Repack the original compressed ZIP payloads without the old signing block, preserve the legacy DJI.RSA/DJI.SF/MANIFEST.MF entry bytes, then create new v2/v3 signatures with the local key. This preserves loader inputs as an experiment; it does not preserve the Android package signer identity.

**Backup evidence:** A fresh 458,784,768-byte archive with 2,152 members passed length, tar end-marker and SHA256 checks. The archive contains only Fly private/device-protected/external app directories. It does not snapshot hardware keystore keys, so it is not authorization to remove retained app data.

## Constraints and acceptance

- Target exactly dji.go.v5 1.21.8/code3115809, stock SHA256 cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e; no phone-APK substitution.
- Preserve the stock bootstrap, native libraries, resources and existing DEX bytes except the scoped Application startup hook. Keep video, a restore icon, original GONE states and restore-on-pause behavior.
- Back up current Fly data with the app stopped; verify archive length, SHA256 and tar end marker. Retain stock APK and app ownership metadata privately.
- Device trials must have an explicit restoration path. Do not uninstall/wipe to evade a signature failure. A different APK signer cannot be called a same-signer update.
- A built/signed APK is not a runtime pass. Require cold application restart, Eye presence, hide/show/video presentation, return from launcher and controller reboot before claiming persistence.
- Keep signing keys, account data, camera captures and native runtime dumps private. No release/commit/push is part of this request.

## Tasks

### 1. Prepare signing and ZIP checks

- [x] Add failing Python tests for candidate ZIP duplicate entries, allowed changed DEX entry, helper DEX addition, unchanged resources/native bytes and legacy signature preservation.
- [x] Implement candidate validation and signing using the SDK APK signer. Verify both the original stock control and startup-hook candidate; log only certificate digests, never key passwords.
- [x] Distinguish a native-loader/signing failure from a handler failure using the unchanged-code signing control.

### 2. Embed the handler

- [x] Move the verified helper to android-hud/src, remove experiment labels and retain bounded framework-only behavior.
- [x] Assemble modified classes.dex from the five stock loader classes; append the helper as classes23.dex.
- [x] Patch only the end of QLVRK.onCreate after replaceApplicationContext: resolve getApplicationContext, cast Application and invoke the helper entry point. Catch handler initialization errors so the DJI bootstrap remains usable.
- [x] Rebuild ZIP preserving original entry bytes/metadata and verify the complete diff against the allowed changes.

### 3. Device trial and deployment

- [x] Re-read physical model, SDK, APK hash, foreground and storage. Create a fresh verified private backup before changing code paths.
- [x] Trial candidate code through a reversible mount of the APK path if supported. Save original path/hash; force-stop only Fly; undo the mount and relaunch stock on failure or connection uncertainty. This trial is not proof of normal APK installer compatibility.
- [x] If a candidate boots, exercise the real Eye button and then remove temporary code-path redirection. If installing a different signer requires data removal, retain the concrete APK and request that separately; do not silently wipe.
- [x] Install only a proven applicable candidate, then verify application and controller restart persistence. Preserve an honest unresolved status when protection or hardware blocks this step.

## Review focus

Certificate mismatch/data retention, AppGuard hidden-class loading, cached ART code masking the startup hook, video ancestor visibility, and recovery when USB disconnects during a trial are required review areas.

## Completion evidence

- Final APK SHA256 abeff2051350dde3dfc524cd1f3ebd63864349e7366cd9f84406cee9778ba750; normal package install succeeded after explicit user approval of remove/reinstall and Keystore limitation.
- Private file ownership remapped to UID10029/cacheGID20029 using a bounded physical-directory walk because device toybox find lacks uid/gid predicates. The walk does not follow symlinks.
- Normal install Eye/hide/show, cold application restart and RC2 reboot have live XML/hash/boot-ID evidence under ignored phone-work/appguard/persistent. Early transition/home XML was not treated as camera proof.
- Final camera during normal install was disconnected; video timestamps were zero, so final live-video/flight operation is not marked verified. Earlier mounted candidate had a live preview and preserved critical warnings.
- Provider exported bit now explicitly forced false, compressed payload preservation validated, changed/track visibility counts separated. Local Windows build0.2.1 accepts only the exact tested HUD hash plus stock, 169 build tests and95.64% PC coverage. Separate APK packaging tests24passed,89%coverage. No GitHub publication.
