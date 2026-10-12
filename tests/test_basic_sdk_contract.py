"""Basic SDK contracts on synthetic JVM layouts, never device/support proof."""
from pathlib import Path
import json
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "android-hud/test/sdk-fixture"
KEY = "uav/sdk/keyvalue/key/"
MANAGER = "uav/sdk/keyvalue/UAVKeyManager.java"
CALLBACK = "uav/sdk/keyvalue/callback/"
SOURCE_NAMES = (
    "GroundGate", "LedJob", "FlySdk", "NativeAircraft", "MutationFence",
    "NativeLed", "ForearmLedJob", "NativeForearmLed", "ForearmParamProbe",
)
TEST_NAMES = ("FlySdkTest", "NativeAircraftTest", "NativeLedFenceTest")


def compile_contract(destination, edits=None):
    edits = edits or {}
    sources = []
    for original in sorted(FIXTURE.rglob("*.java")):
        relative = original.relative_to(FIXTURE).as_posix()
        content = original.read_text(encoding="utf-8")
        for before, after in edits.get(relative, ()):
            assert before in content, (relative, before)
            content = content.replace(before, after)
        target = destination / "fixture" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        sources.append(target)
    for directory in ("forearm-fixture", "forearm-write-fixture"):
        sources += sorted((ROOT / "android-hud/test" / directory).rglob("*.java"))
    source = ROOT / "android-hud/src/local/rc2/hud"
    tests = ROOT / "android-hud/test/local/rc2/hud"
    sources += [source / (name + ".java") for name in SOURCE_NAMES]
    sources += [tests / (name + ".java") for name in TEST_NAMES]
    classes = destination / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-encoding", "UTF-8",
         "-d", str(classes), *map(str, sources)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return classes


def run_contract(classes, name="FlySdkTest", scenario=None):
    result = subprocess.run(
        ["java", "-cp", str(classes), "local.rc2.hud." + name,
         *([scenario] if scenario else [])],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout


@pytest.fixture(scope="module", params=["stock-aliases", "renamed", "reordered"])
def layout_classes(request, tmp_path_factory):
    edits = {}
    if request.param != "stock-aliases":
        table = (FIXTURE / KEY / "UAVFlightControllerKey.java").read_text(encoding="utf-8")
        fields = (
            [("zLights", "LEDsSettings"), ("bFlying", "IsFlying"),
             ("mMotors", "AreMotorsOn"), ("aConnected", "Connection")]
            if request.param == "renamed" else
            [("K", "Connection"), ("he", "LEDsSettings"),
             ("U2", "AreMotorsOn"), ("J", "IsFlying")]
        )
        content = "package uav.sdk.keyvalue.key;\npublic final class UAVFlightControllerKey {\n"
        content += '    public static final String unrelated = "LEDsSettings";\n'
        content += '    private static final UAVKeyInfoBase hidden = new UAVKeyInfoBase("Connection");\n'
        content += '    public final UAVKeyInfoBase instance = new UAVKeyInfoBase("IsFlying");\n'
        content += "".join(
            f'    public static final UAVKeyInfoBase {field} = new UAVKeyInfoBase("{identifier}");\n'
            for field, identifier in fields
        )
        content += "}\n"
        edits[KEY + "UAVFlightControllerKey.java"] = [(table, content)]
    return compile_contract(tmp_path_factory.mktemp("basic-" + request.param), edits)


@pytest.mark.parametrize("scenario", [None, "canonical", "led-matrix", "callbacks", "exceptions", "null-factory"])
def test_basic_identifiers_led_types_and_callback_lifecycle(layout_classes, scenario):
    run_contract(layout_classes, scenario=scenario)


@pytest.mark.parametrize("scenario", [None, "guards"])
def test_ground_guards_and_callback_chain_survive_field_layout_changes(layout_classes, scenario):
    run_contract(layout_classes, "NativeAircraftTest", scenario)


def test_led_mutation_fence_survives_field_layout_changes(layout_classes):
    run_contract(layout_classes, "NativeLedFenceTest")


@pytest.mark.parametrize("declaration", [
    'new UAVKeyInfoBase("LEDsSettings",true,false,true,false,false)',
    'new UAVKeyInfoBase("LEDsSettings",false,true,true,false,false)',
    'new UAVKeyInfoBase("LEDsSettings",true,true,true,false,true)',
    'new UAVKeyInfoBase("LEDsSettings",true,true,true,true,false)',
    'new UAVKeyInfoBase("AircraftName")',
    'null',
])
def test_led_without_exact_read_write_metadata_never_dispatches(tmp_path, declaration):
    classes = compile_contract(tmp_path, {
        KEY + "UAVFlightControllerKey.java": [('new UAVKeyInfoBase("LEDsSettings")', declaration)],
    })
    run_contract(classes, scenario="reject-led")


@pytest.mark.parametrize("identifier,scenario", [
    ("Connection", "reject-get"), ("LEDsSettings", "reject-led"),
])
@pytest.mark.parametrize("duplicate", ["valid", "event", "same-object"])
def test_duplicate_identifiers_fail_closed_even_for_identical_or_invalid_descriptors(
    tmp_path, identifier, scenario, duplicate,
):
    value = (
        {"Connection": "he", "LEDsSettings": "U2"}[identifier]
        if duplicate == "same-object" else
        f'new UAVKeyInfoBase("{identifier}",true,true,true,false,true)'
        if duplicate == "event" else f'new UAVKeyInfoBase("{identifier}")'
    )
    classes = compile_contract(tmp_path, {
        KEY + "UAVFlightControllerKey.java": [
            ("\n}", f"\n    public static final UAVKeyInfoBase duplicate = {value};\n}}"),
        ],
    })
    run_contract(classes, scenario=scenario)


@pytest.mark.parametrize("replacement", [
    'new UAVKeyInfoBase("Connection",false,false,true,false,false)',
    'new UAVKeyInfoBase("Connection",true,false,true,false,true)',
    'new UAVKeyInfoBase("Connection",true,false,true,true,false)',
    'new UAVKeyInfoBase("AircraftName")', 'new UAVKeyInfoBase((String)null)', 'null',
])
def test_connection_requires_readable_non_event_non_action_identifier(tmp_path, replacement):
    classes = compile_contract(tmp_path, {
        KEY + "UAVFlightControllerKey.java": [('new UAVKeyInfoBase("Connection")', replacement)],
    })
    run_contract(classes, scenario="reject-cache")
    run_contract(classes, scenario="reject-get")


@pytest.mark.parametrize("field", ["he", "U2"])
@pytest.mark.parametrize("modifier", ["private static final", "public final"])
def test_only_public_static_descriptor_fields_are_candidates(tmp_path, field, modifier):
    classes = compile_contract(tmp_path, {
        KEY + "UAVFlightControllerKey.java": [
            (f"public static final UAVKeyInfoBase {field}=", f"{modifier} UAVKeyInfoBase {field}="),
        ],
    })
    run_contract(classes, scenario="reject-get" if field == "he" else "reject-led")


@pytest.mark.parametrize("field,flag,scenario", [
    ("he", "throwName", "reject-get"), ("U2", "throwMetadata", "reject-led"),
])
def test_lookup_and_metadata_exceptions_are_normalized(tmp_path, field, flag, scenario):
    classes = compile_contract(tmp_path, {
        KEY + "UAVFlightControllerKey.java": [("\n}", f"\n    static {{ {field}.{flag}=true; }}\n}}")],
    })
    run_contract(classes, scenario=scenario)


@pytest.mark.parametrize("relative,before,after,scenario", [
    (KEY + "UAVKeyInfoBase.java", "public String e()", "public Object e()", "reject-get"),
    (KEY + "UAVKeyInfoBase.java", "public String e()", "private String e()", "reject-get"),
    (KEY + "UAVKeyInfoBase.java", "public boolean i()", "public Boolean i()", "reject-get"),
    (KEY + "UAVKeyInfoBase.java", "public boolean i()", "public boolean n()", "reject-get"),
    (KEY + "UAVKeyInfoBase.java", "public boolean l()", "public Boolean l()", "reject-led"),
    (KEY + "UAVKeyInfoBase.java", "public boolean m()", "public Boolean m()", "reject-led"),
    (KEY + "UAVKeyInfoBase.java", "public boolean k()", "public Boolean k()", "reject-get"),
    (KEY + "UAVKeyInfoBase.java", "public boolean j()", "public Boolean j()", "reject-get"),
    (KEY + "UAVKey.java", "public static UAVKey i(", "public static Object i(", "reject-get"),
    (KEY + "UAVKey.java", "public static UAVKey i(", "public UAVKey i(", "reject-get"),
    (KEY + "UAVKey.java", "public static UAVKey l(", "public static Object l(", "reject-led"),
    (KEY + "UAVKey.java", "public static UAVKey l(", "public UAVKey l(", "reject-led"),
    (MANAGER, "public static void t(", "public void t(", "reject-get"),
    (MANAGER, "public static void x(", "public void x(", "reject-set"),
    (MANAGER, "public static Object r(", "public Object r(", "reject-cache"),
    (CALLBACK + "IGetCallback.java", "void b(UAVKey key,Object value);",
     "Object b(UAVKey key,Object value);", "reject-get"),
    (CALLBACK + "IGetCallback.java", "int code", "Integer code", "reject-get"),
    (CALLBACK + "ISetCallback.java", "void b(UAVKey key);", "Object b(UAVKey key);", "reject-set"),
    (CALLBACK + "ISetCallback.java", "int code", "long code", "reject-set"),
    (CALLBACK + "IGetCallback.java", "\n}", "\n    default void unexpected() {}\n}", "reject-get"),
    ("uav/sdk/keyvalue/value/flightcontroller/LEDsSettings.java", "public Boolean getFrontLEDsOn()",
     "public Object getFrontLEDsOn()", "reject-led-read"),
    ("uav/sdk/keyvalue/value/flightcontroller/LEDsSettings.java", "public Boolean getRearLEDsOn()",
     "public Object getRearLEDsOn()", "reject-led-read"),
])
def test_exact_metadata_factory_manager_callback_and_value_signatures_fail_closed(
    tmp_path, relative, before, after, scenario,
):
    classes = compile_contract(tmp_path, {relative: [(before, after)]})
    run_contract(classes, scenario=scenario)


@pytest.mark.parametrize("method,scenario,signature", [
    ("r", "reject-cache", 'public static String r(UAVKey key) { cachedReads++; return "unsafe"; }'),
    ("t", "reject-get", 'public static Object t(UAVKey key,IGetCallback callback) { reads.add("unsafe"); return null; }'),
    ("x", "reject-set", 'public static Object x(UAVKey key,Object value,ISetCallback callback) { writes++; return null; }'),
])
def test_manager_return_types_are_checked_before_dispatch(tmp_path, method, scenario, signature):
    result = "Object" if method == "r" else "void"
    classes = compile_contract(tmp_path, {MANAGER: [
        (f"public static {result} {method}(", f"public static {result} old_{method}("),
        ("\n}", "\n    " + signature + "\n}"),
    ]})
    run_contract(classes, scenario=scenario)


def test_led_requires_the_four_boxed_boolean_constructor_before_get_or_set(tmp_path):
    relative = "uav/sdk/keyvalue/value/flightcontroller/LEDsSettings.java"
    classes = compile_contract(tmp_path, {relative: [
        ("Boolean front,Boolean status,Boolean rear,Boolean navigation",
         "Object front,Object status,Object rear,Object navigation"),
        ("this.front=front; this.status=status; this.rear=rear; this.navigation=navigation;",
         "this.front=(Boolean)front; this.status=(Boolean)status; this.rear=(Boolean)rear; this.navigation=(Boolean)navigation;"),
    ]})
    run_contract(classes, scenario="reject-led")


def test_get_callback_must_be_a_public_interface(tmp_path):
    classes = compile_contract(tmp_path, {CALLBACK + "IGetCallback.java": [
        ("public interface IGetCallback", "public abstract class IGetCallback"),
        ("void a(", "public abstract void a("),
        ("void b(", "public abstract void b("),
    ]})
    run_contract(classes, scenario="reject-get")


@pytest.mark.parametrize("duplicate", [False, True])
def test_descriptor_fields_may_use_the_stock_info_subclass_type(tmp_path, duplicate):
    table = (FIXTURE / KEY / "UAVFlightControllerKey.java").read_text(encoding="utf-8")
    subclass_table = table.replace("UAVKeyInfoBase", "FixtureInfo").replace(
        "\n}", "\n    public static final class FixtureInfo extends UAVKeyInfoBase {\n"
        "        FixtureInfo(String name) { super(name); }\n    }\n}",
    )
    if duplicate:
        subclass_table = subclass_table.replace("\n}", '\n    public static final FixtureInfo duplicate = new FixtureInfo("LEDsSettings");\n}')
    classes = compile_contract(tmp_path, {KEY + "UAVFlightControllerKey.java": [(table, subclass_table)]})
    run_contract(classes, scenario="reject-led" if duplicate else "canonical")
    run_contract(classes, "NativeAircraftTest", "guards")


def test_signature_pin_uses_stock_semantic_ids_and_retained_key_indices():
    pin = json.loads((FIXTURE / "stock-signatures.json").read_text(encoding="utf-8"))
    assert pin["stock_version"] == "1.21.8"
    assert pin["stock_sha256"] == "cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e"
    assert pin["aliases"] == {"he": "Connection", "J": "AreMotorsOn", "K": "IsFlying", "U2": "LEDsSettings"}
    assert pin["ground_factory"] == "i(UAVKeyInfoBase) -> UAVKey; indices=0,0,65534"
    assert pin["led_factory"] == "l(UAVKeyInfoBase,int,int,int) -> UAVKey; indices=0,0,0"
    for identifier in ("Connection", "AreMotorsOn", "IsFlying"):
        assert pin["descriptor_flags"][identifier] == [True, False, True, False, False]
    assert pin["descriptor_flags"]["LEDsSettings"] == [True, True, True, False, False]
    assert pin["genuine_1_21_10_contract_verified"] is False
    assert pin["device_runtime_verified"] is False
