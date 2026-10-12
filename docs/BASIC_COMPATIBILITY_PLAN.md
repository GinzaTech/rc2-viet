# Basic RC Fly compatibility and private separation — 2026-10-12

User scope: move the upgraded experimental edition to a separate local folder, never publish it to GitHub, and finish the main Vietnamese/basic-menu edition for RC Fly1.21.8 and1.21.10.

## Design and boundaries

- Snapshot the complete current source/assets/EXE and advanced APK into C:/Users/kona/Desktop/Project/rc2-viet-advanced-local before removing anything. No .git directory, remote, secrets, device backups or venv is copied. Local-only metadata documents hashes and provenance.
- Main repo keeps translation and existing LED/HUD/output/radio menu. Remove the Advanced selector, builder payload path, experimental SDK/menu classes, extraction/feature-port recipes and tests from the public tree after verifying their private copies.
- Retain Basic verification/recovery improvements and historical Basic receipts. Unknown upgraded payloads are not approved by arbitrary receipt hashes.
- Main EXE and portable package are rebuilt from the Basic-only source and checked for absence of private class markers, payload files and publish metadata.
- Find and identify actual RC1.21.10 input. RedFly is excluded from all current translation, patching, installation and compatibility proof.
- Both tested versions must build menu and translation from their own resources. Check SDK identifiers, key factories, callbacks, LED value types, ground state, radio and forearm contracts from actual DEX; fix version-specific field-name assumptions without changing API permissions.
- The user later authorized USB acquisition, ground-safe Basic installation and tests. Host proof stays separate from physical aircraft/video/RF observations.

## Tasks and acceptance

1. [x] Copy and hash the private edition. Verify the initial snapshot excluded Git, credentials, device backups and environment files; later authorized runtime backups stay local and are never published. Remove advanced content from main only after copy verification.
2. [x] Remove dual-variant desktop/CLI paths and prevent non-basic requests from being queued. Keep one-click pull/patch/sign/install and existing signer-confirmation behavior.
3. [x] Keep Basic structural replay/recovery and add publication tests that scan source/assets/frozen archive for experiment markers.
4. [x] Collect1.21.8/1.21.10 inputs with exact provenance. Compare required SDK ABI and identifiers; add failing tests for differences, then fix bridge contracts and verify LED/ground/radio adapters.
5. [x] Build/sign menu APK and complete resource overlay for each confirmed input; recover the exact original and bind reports to version/hash/certificate.
6. [x] Run the source suite/coverage/review, build Basic-only EXE/ZIP, test frozen operations for both versions, and record all unresolved runtime/source limits honestly.

Public/private isolation tests must run before any eventual Git action. The experimental copy is never staged or published.

Evidence 2026-10-13: actual stock 1.21.10 F6 acquired; final Basic EXE B771 verified on both stock inputs; 2003 tests / 90.10% coverage / 15 packaging tests; Basic 1.21.10 installed with data retention and matching hash; actual EXE RRO applied/read back; SDK utility absent. See docs/adaptive-menu-verification.json for the measured limits.
