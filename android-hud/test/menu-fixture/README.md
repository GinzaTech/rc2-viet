# Executable DeviceMenu interaction fixture

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_hud_menu.py -q
```

The pytest module compiles the **current production** `DeviceMenu.java`,
`MenuPlacement.java`, `GroundGate.java`, and `LedJob.java` with `javac`.
Each scenario runs in a separate JVM with temporary class output. No Android
SDK, ADB, device, network, APK, EXE or hardware mutation is involved.

Android stubs expose only the UI API needed by this menu (including API 30
state descriptions). The test traverses the real dialog tree and invokes the
actual listeners. Front/rear controls are located by their accessibility
content description or text prefix, independent of row nesting. It asserts
labels, selected/enabled state, backend commands, dialog behavior, callback
fencing, and subscription/layout cleanup. It never asserts production source
strings or reimplements the menu logic.

`NativeLed` records `toggleFront`, `toggleRear` and the retained explicit
`request`, `requestRear`, `requestAll` boundaries. `inspect` stores typed
`LedJob.Reply<LedJob.Lights>` callbacks. Tests supply actual `Lights` and command
results separately, including failures and rejection with/without an inline
callback. `observe(Runnable)` stores LED reconciliation listeners and returns
an observable cancellation handle. Command completion and the shared mutation
fence are separate: tests can time out a command while keeping `mutationPending`
true, deliver actual GET data, then explicitly release the fence and publish an
event. `NativeRadio.status()` includes this fixture fence, matching the shared
hardware exclusion seen by menu controls. `close()` records remaining listeners
to verify the menu cancels its LED subscription **before** closing the backend.
The fixture does not implement matching late-read release logic; that belongs to
the real backend worker's tests. It verifies how the real menu reacts to the
resulting event. Other backends are inert; observer cancellation is observable.
`Activity` executes main-thread callbacks directly or queues them when asked;
background callbacks are always queued. Tests explicitly drain that queue.
`View.performClick` invokes a listener even while disabled, matching the
programmatic Android API; `userClick` honors enabled/visible state. Rapid-click
and ground-race tests deliberately use programmatic delivery to exercise the
handler's own guards.

Common `SharedPreferences`, `ViewTreeObserver`, `Window`, `Rect`, `Log`, and
`DisplayMetrics` types were copied from `output-lifecycle-fixture` **into this
owned folder**, then adapted here. That fixture is unchanged and is never
included in this suite's compilation.

The suite retains the original 38 cases and adds 11 event scenarios: timeout
with a pending fence followed by late reconciliation, closed/disposed owners,
reopen after release, release during a reopened GET, command-busy and read-busy
events, queued event bursts, queued dismiss/dispose, and failed reconciliation
GET recovery. GET call counts and actual state assertions distinguish new
reads from optimistic unlocks; widget snapshots catch stale UI mutations.

The narrow-root scenario verifies interaction remains reachable through a
nested row layout. Geometry setters are inert; it does not verify pixel
placement, screen-edge clamping or Android window rendering.

Passing this suite proves JVM interaction and callback behavior, not Android
rendering/accessibility service behavior, device timing or aircraft LED IO.
