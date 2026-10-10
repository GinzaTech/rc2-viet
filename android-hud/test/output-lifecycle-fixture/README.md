# External output lifecycle host fixture

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_hud_external_lifecycle.py -q
```

The suite compiles the real `CleanPresentation`, `ExternalOutput`, and
`OutputGeometry` classes with isolated Java Android stubs. Each scenario runs in
a fresh JVM. The deterministic Handler queue has explicit time advancement;
PixelCopy completion is delivered explicitly, with checks for recycled native
copy destinations. SurfaceControl records geometry and resource releases and
can throw after a successful initial mirror. Presentation models queued
OnDismiss delivery and metrics-change cancellation in both listener orders.

ViewTreeObserver dispatch exercises preview inflation after resume, an initially
invalid surface becoming ready, source identity replacement/removal, unchanged
layout events, and listener/holder-callback cleanup on pause, close, and owner
replacement. Diagnostic booleans are checked for each binding state. This
single-main-thread fixture does not emulate actual Binder scheduling. A one-shot
Bundle callback deterministically pauses the owner between `has_preview` and
`surface_valid` assembly, verifying that both use the captured preview and that
the next response sees the cleared binding. An executable negative control
restoring the mutable-field access must fail this snapshot assertion.

The explicit `preferMirror=false` scenario counts every mirror-method invocation,
including failures, and verifies direct PixelCopy selection, resize, bounded
buffers, and deferred recycling on close. The existing default-constructor tests
continue exercising the mirror-first production path. No host copy callback
constitutes pixel-content or physical output verification.

Five executable negative controls compile temporary faulted production copies
and require the relevant scenario to fail. They never modify runtime sources.

Limits: these stubs do not render pixels, model SurfaceFlinger's mirrored child
hierarchy/transforms, enforce Android permissions, emulate RenderThread/GPU
fences, or prove physical DisplayPort/HDMI output. Geometry assertions concern
the transaction submitted by the application. OutputProbe is an inert test
collaborator; virtual-display buffers are outside this suite. Presentation
window sizing, focus, and physical display behavior still require Android tests.
