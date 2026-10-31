"""Build an independently pinned RC2 Fly 1.21.16 menu recipe offline.

Every host DEX comes from the exact 1.21.16 stock. Only the reviewed r14.5
add-on code is shared, after resource-name rebinding and a full dependency audit.
No device command, firmware operation, source APK execution or signing occurs.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rc2vi.advanced_stock_signature import verify_stock_apk
from rc2vi.hud_capsule import PROFILE_ENTRY
from rc2vi.hud_plan import analyze
from rc2vi.hud_tools import HudTools, sha256_file
from scripts.build_feature_candidate import run, parse_resource_dump
from scripts.feature_host_patch import patch_host, method as patch_method
from scripts.hud_manifest import add_adaptive_provider, inspect_application

VERSION, CODE = "1.21.16", 3132286
SOURCE_SHA256 = "9bec52ed4c43aad6c615b0a7a0650f0d35e842c4bf8a5e59d5da005a50d56b6a"
REFERENCE_SHA256 = "f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98"
CERTIFICATE_SHA256 = "01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4"
KIND = "rc2-advanced-12116"
DEX = re.compile(r"classes(?:[2-9]|[1-9][0-9]+)?\.dex\Z")
RESOURCE = re.compile(r"(?<![A-Za-z0-9_])0x7f[0-9a-fA-F]{6}\b")
POLICY = "menu-only-no-special-flight-controls-or-cell-readout-v1"
LEGACY_TARGETS = {
    "Lcom/uav/fpv/leftbar/component/takeoffandland/LandAndGoHomeVM;",
    "Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandView;",
    "Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandViewModel;",
}
VM = "Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandViewModel;"
VIEW = "Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandView;"
LAND = "Lcom/uav/fpv/leftbar/component/takeoffandland/LandAndGoHomeVM;"
RTH_VM = "Luav/containers/fullscreen/submodel/returntohome/ReturnToHomeCountDownNotificationVM;"
AREA = "Luav/services/areacode/impl/AreaCodeServiceImpl;"
STREAM = "Lcom/uav/component/fpv/widget/setting/ui/liveview/livestreaming/SettingLiveStreamingAdvanceViewModel;"
ALTITUDE = "Lcom/uav/component/fpv/widget/setting/ui/safety/SettingAltitudeLimitViewModel;"
REGION = "Lcom/uavapp/mapkit/osm/offlinemap/view/RegionSelectPageView;"
MAIN_ACTIVITY = "Lcom/dji/mainpageui/device/DJIDeviceActivity;"
BUTTON_ROUTER = "Lcom/uav/service/actioncompletable/ActionCompletableRouterKt;"
OBSERVABLE = "Lcom/uav/flymodel/api/observable/FlyObservable;"
OBSERVABLE_DEFAULT = "Lcom/uav/flymodel/api/observable/FlyObservable$DefaultImpls;"
OBSERVABLE_OLD_GETTER = OBSERVABLE + "->c()Ljava/lang/Object;"
OBSERVABLE_NEW_GETTER = OBSERVABLE + "->d()Ljava/lang/Object;"
RTH_PROTO = "(" + RTH_VM + "Luav/infra/flymodel/generated/api/flight/StartRTHCountdownInfo;)Lkotlin/Pair;"
LIMIT_PROTO = "(Lcom/uav/flymodel/generated/api/common/IntMinMax;Ljava/lang/Boolean;)Lcom/uav/flymodel/generated/api/common/IntMinMax;"
REGION_PROTO = "(" + REGION + "Lcom/uav/mapkit/core/maps/UAVAppMap;Lcom/uav/rx/csdk/Recall;)Lkotlin/Unit;"
EVENT = "Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandViewModel$CountDownEvent;"
EVENT_TYPE = "Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandViewModel$CountDownEvent$Type;"
EVENT_PRIORITY = "Lcom/uav/fpv/leftbar/component/takeoffandland/TakeOffAndLandViewModel$CountDownEvent$Priority;"
SIGNATURE_RENAMES = {
    RTH_VM: {"z" + RTH_PROTO: "C" + RTH_PROTO},
    AREA: {"I0()Ljava/lang/String;": "G0()Ljava/lang/String;"},
    STREAM: {"R()Ljava/util/ArrayList;": "V()Ljava/util/ArrayList;"},
    ALTITUDE: {"N" + LIMIT_PROTO: "R" + LIMIT_PROTO},
    REGION: {"subscribeCameraPosition$lambda$16" + REGION_PROTO: "subscribeCameraPosition$lambda$3" + REGION_PROTO},
}
LEGACY_METHODS = {
    LAND: [("j()V", "j()V", "manual")],
    VIEW: [("d0(" + EVENT + ")V", "g0(" + EVENT + ")V", "suppress")],
    VM: [("N1()V", "i2()V", "video"), ("h1()V", "B1()V", "video")],
}

# This tiny host utility reads DEX definitions without loading Android code.
# Dumping all helper classes also lets Python prove that only approved numeric
# resource references change during reassembly, including the retained policies.
DEX_TOOL = r'''
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Map;
import com.android.tools.smali.dexlib2.iface.ClassDef;
public final class Menu12116DexTool {
  public static void main(String[] args) throws Exception {
    if(args.length==3 && args[0].equals("methods")) {
      var container=com.android.tools.smali.dexlib2.DexFileFactory.loadDexContainer(Path.of(args[1]).toFile(),new com.android.tools.smali.dexlib2.Opcodes(30,-1));
      if(container.getDexEntryNames().size()!=1)throw new IllegalArgumentException();
      var dex=container.getEntry((String)container.getDexEntryNames().get(0)).getDexFile();
      ArrayList<String> rows=new ArrayList<>();
      for(Object method:dex.methodSection)rows.add(method.toString());
      Files.write(Path.of(args[2]),rows,StandardCharsets.UTF_8);System.out.print(rows.size());return;
    }
    if(args.length==5 && args[0].equals("verify")) {
      var original=AdaptiveHudTool.classes(Path.of(args[1]));var actual=AdaptiveHudTool.classes(Path.of(args[2]));
      if(!original.keySet().equals(actual.keySet()))throw new IllegalStateException("Reused class inventory differs");
      java.util.TreeMap<String,String> replacements=new java.util.TreeMap<>();
      try(var files=Files.list(Path.of(args[3]))) {
        for(Path p:files.filter(x->x.getFileName().toString().endsWith(".smali")).toList()) {
          String text=Files.readString(p,StandardCharsets.UTF_8);
          var type=java.util.regex.Pattern.compile("(?m)^\\.class [^\\n]* (L[^\\n]+)$").matcher(text);
          if(!type.find())throw new IllegalArgumentException();
          if(original.containsKey(type.group(1)))replacements.put(type.group(1),text);
        }
      }
      ArrayList<String> rows=new ArrayList<>();int patched=0;
      for(String type:original.keySet()) {
        String before=AdaptiveHudTool.dump(original.get(type)),after=AdaptiveHudTool.dump(actual.get(type));
        String expected=replacements.getOrDefault(type,before);
        if(!FeatureHookTool.normalized(expected).equals(FeatureHookTool.normalized(after)))
          throw new IllegalStateException("Reused DEX semantics differ: "+type);
        if(replacements.containsKey(type))patched++;
        else if(!before.equals(after))rows.add(type);
      }
      Files.write(Path.of(args[4]),rows,StandardCharsets.UTF_8);System.out.print(patched);return;
    }
    if(args.length!=2)throw new IllegalArgumentException();
    Path input=Path.of(args[0]),out=Path.of(args[1]);
    Files.createDirectory(out);ArrayList<String> rows=new ArrayList<>();int n=0;
    for(Map.Entry<String,ClassDef> e:AdaptiveHudTool.classes(input).entrySet()) {
      String name="class-"+(n++)+".smali";
      Files.writeString(out.resolve(name),AdaptiveHudTool.dump(e.getValue()),StandardCharsets.UTF_8);
      rows.add(e.getKey()+"\t"+name);
    }
    Files.write(out.resolve("classes.tsv"),rows,StandardCharsets.UTF_8);
    System.out.print(n);
  }
}
'''

PRESERVATION_HELPERS = r'''
    static String normalized(String text) {
        text=text.replace("\r\n", "\n");
        text=text.replaceAll("(?m)^[\\t ]*\\.line -?[0-9]+\\n", "");
        text=text.replaceAll("(?m)^[\\t ]*\\r?\\n", "");
        java.util.regex.Matcher methods=java.util.regex.Pattern.compile("(?ms)^\\.method [^\\n]*\\n.*?^\\.end method").matcher(text);
        StringBuffer result=new StringBuffer();
        while(methods.find())methods.appendReplacement(result,java.util.regex.Matcher.quoteReplacement(normalizedMethod(methods.group())));
        methods.appendTail(result);return result.toString();
    }
    static String normalizedMethod(String text) {
        text=text.replaceAll("(?m)^(\\s*)const-string/jumbo(?= )", "$1const-string");
        java.util.LinkedHashMap<String,String> labels=new java.util.LinkedHashMap<>();
        boolean inPackedSwitch=false;
        for(String line:text.split("\\n",-1)) {
            String stripped=line.trim();
            if(stripped.startsWith(".packed-switch ")){inPackedSwitch=true;continue;}
            if(stripped.equals(".end packed-switch")){inPackedSwitch=false;continue;}
            if(inPackedSwitch)continue;
            java.util.regex.Matcher declared=java.util.regex.Pattern.compile("^(:[A-Za-z0-9_$]+)$").matcher(stripped);
            if(!declared.matches())continue;
            String name=declared.group(1);
            if(labels.put(name,":label_"+labels.size())!=null)throw new IllegalArgumentException("Duplicate label declaration");
        }
        if(inPackedSwitch)throw new IllegalArgumentException("Unterminated packed switch");
        // A streaming scanner avoids Java regex recursion for large string
        // constants found in unchanged stock classes. Quoted bytes stay exact.
        StringBuilder output=new StringBuilder();int i=0;
        while(i<text.length()) {
            int start=i;char c=text.charAt(i++);
            if(c=='"') {
                boolean closed=false;
                while(i<text.length()) {
                    char q=text.charAt(i++);
                    if(q=='\\') {if(i>=text.length())throw new IllegalArgumentException("Unterminated quoted escape");i++;}
                    else if(q=='"'){closed=true;break;}
                }
                if(!closed)throw new IllegalArgumentException("Unterminated quoted string");
                output.append(text,start,i);
            } else if(c==':') {
                while(i<text.length()) {
                    char q=text.charAt(i);
                    if(!((q>='A'&&q<='Z')||(q>='a'&&q<='z')||(q>='0'&&q<='9')||q=='_'||q=='$'))break;
                    i++;
                }
                String value=text.substring(start,i);output.append(labels.getOrDefault(value,value));
            } else output.append(c);
        }
        return output.toString();
    }
    static void verifyUnrelated(String before,String after,String type,Path output) throws Exception {
        if(before.equals(after))return;
        if(!normalized(before).equals(normalized(after)))
            throw new IllegalStateException("Unrelated class semantics changed: "+type);
        Files.writeString(output.resolveSibling(output.getFileName()+".encoding-only.tsv"),type+"\n",
            StandardCharsets.UTF_8,java.nio.file.StandardOpenOption.CREATE,java.nio.file.StandardOpenOption.APPEND);
    }
'''


def normalize_smali_encoding(text: str) -> str:
    """Ignore only const-string index width and bind each label to its position.

    Every instruction operand, quoted literal, directive and branch destination
    remains part of the comparison. Changing a branch target still fails.
    """
    text = text.replace("\r\n", "\n")
    text = re.sub(r"(?m)^[\t ]*\.line -?[0-9]+\n", "", text)
    text = re.sub(r"(?m)^[\t ]*\r?\n", "", text)
    def method(match):
        body = re.sub(r"(?m)^(\s*)const-string/jumbo(?= )", r"\1const-string", match[0])
        labels = {}
        in_packed_switch = False
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(".packed-switch "):
                in_packed_switch = True
                continue
            if stripped == ".end packed-switch":
                in_packed_switch = False
                continue
            if in_packed_switch:
                continue
            label = re.fullmatch(r"(:[A-Za-z0-9_$]+)", stripped)
            if label is None:
                continue
            if label[1] in labels:
                raise ValueError("Duplicate smali label")
            labels[label[1]] = ":label_" + str(len(labels))
        if in_packed_switch:
            raise ValueError("Unterminated packed switch")
        return re.sub(r'"(?:\\.|[^"\\])*"|:[A-Za-z0-9_$]+',
                      lambda token: labels.get(token[0], token[0]), body)
    return re.sub(r"(?ms)^\.method [^\n]*\n.*?^\.end method", method, text)


def _json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _short_windows_path(path: Path) -> Path:
    # The pinned tool bundle has a 64-character cache component and long DLL
    # filenames. Use the same directory's native alias rather than another drive,
    # a symlink, or a global path/registry change on MAX_PATH-limited hosts.
    if os.name != "nt":
        return path
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise ValueError("Could not obtain a bounded Windows tool cache path")
    return Path(buffer.value)


def _dex_dump(java: Path, cp: str, dex: Path, output: Path) -> dict[str, str]:
    run(java, "-Xmx2560m", "-cp", cp, "Menu12116DexTool", dex, output)
    return {typ: (output / filename).read_text("utf-8")
            for typ, filename in (line.split("\t") for line in (output / "classes.tsv").read_text("utf-8").splitlines())}


def remap_resource_literals(text: str, bindings: dict[int, int]) -> tuple[str, list[dict]]:
    """Rewrite numeric tokens, preserving quoted strings and comments exactly."""
    changes = []
    output = []
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        pieces = re.split(r'("(?:\\.|[^"\\])*")', line)
        rewritten = []
        in_comment = False
        for index, piece in enumerate(pieces):
            if index % 2 or in_comment:
                rewritten.append(piece)
                continue
            before, separator, comment = piece.partition("#")
            def replace(match):
                old = int(match[0], 16)
                if old == 0x7fffffff:
                    return match[0]
                if old not in bindings:
                    raise ValueError(f"Unbound resource constant {match[0]} at line {number}")
                new = bindings[old]
                changes.append({"line": number, "old": hex(old), "new": hex(new)})
                return match[0] if new == old else hex(new)
            rewritten.append(RESOURCE.sub(replace, before) + separator + comment)
            in_comment = bool(separator)
        output.append("".join(rewritten))
    return "".join(output), changes


def _method(text: str, signature: str) -> str:
    matches = re.findall(r"(?ms)^\.method [^\n]* " + re.escape(signature) + r"\n.*?^\.end method", text)
    if len(matches) != 1 or " native " in matches[0].splitlines()[0]:
        raise ValueError("Expected one implemented method: " + signature)
    return matches[0]


def preserve_method_metadata(original: str, patched: str, signatures: list[str]) -> str:
    """Keep each original method/parameter metadata prefix before inserted code.

    Smali assembly serializes these declarations before instructions. Relocate
    the exact original prefix, including nested parameter annotations, rather
    than ignoring metadata during comparison or changing its target scope.
    """
    for signature in signatures:
        if " " + signature + "\n" not in original:
            continue  # A newly introduced override has no source metadata.
        before = _method(original, signature)
        after = _method(patched, signature)
        register = re.search(r"(?m)^    \.(?:registers|locals) [0-9]+[ \t]*\n", before)
        if register is None:
            raise ValueError("Method register declaration missing")
        lines = before[register.end():].splitlines(keepends=True)
        prefix, depth = [], []
        for line in lines:
            value = line.strip()
            if depth:
                prefix.append(line)
                if value.startswith(".annotation ") or value.startswith(".subannotation "):
                    depth.append("annotation" if value.startswith(".annotation ") else "subannotation")
                elif value in (".end annotation", ".end subannotation"):
                    expected = value.removeprefix(".end ")
                    if depth[-1] != expected:
                        raise ValueError("Annotation nesting differs")
                    depth.pop()
                elif value == ".end param":
                    if depth[-1] != "param":
                        raise ValueError("Parameter annotation scope differs")
                    depth.pop()
                continue
            if not value:
                prefix.append(line)
            elif value.startswith(".param "):
                prefix.append(line)
                # An unannotated .param has no .end param in baksmali output.
                remaining = lines[len(prefix):]
                next_nonempty = next((v.strip() for v in remaining if v.strip()), "")
                if next_nonempty.startswith(".annotation "):
                    depth.append("param")
            elif value.startswith(".annotation "):
                prefix.append(line)
                depth.append("annotation")
            else:
                break
        if depth:
            raise ValueError("Unterminated original metadata prefix")
        metadata = "".join(prefix)
        if not metadata.strip():
            continue
        if after.count(metadata) != 1:
            raise ValueError("Original method metadata prefix changed or became ambiguous")
        without = after.replace(metadata, "", 1)
        destination = re.search(r"(?m)^    \.(?:registers|locals) [0-9]+[ \t]*\n", without)
        if destination is None:
            raise ValueError("Patched method register declaration missing")
        canonical = without[:destination.end()] + metadata + without[destination.end():]
        if canonical.replace(metadata, "", 1) != without:
            raise ValueError("Method metadata relocation changed code")
        patched = patched.replace(after, canonical, 1)
    return patched


def assert_unique_methods(text: str) -> None:
    signatures = re.findall(r"(?m)^\.method [^\n]* (\S+\([^\n]+)$", text)
    if len(signatures) != len(set(signatures)):
        raise ValueError("Duplicate method signature")


def explicit_button_payload_padding(text: str, type_name: str) -> str:
    """Spell out the one padding NOP required by this exact source/profile.

    Its original switch payload is at 0x19e code units. The audited runButton
    entry adds 11 units, so one NOP aligns the payload at 0x1aa. The preceding
    return prevents fall-through into the padding/data. Keeping it explicit
    retains opcode-exact comparison instead of ignoring NOPs in the verifier.
    """
    if type_name != BUTTON_ROUTER:
        return text
    hook = ('    invoke-static {p0, p3}, Llocal/rc2/hud/PortHooks;->runButton(Ljava/lang/Object;Landroid/app/Activity;)Z\n'
            '    move-result v0\n    if-eqz v0, :rc2port_button_original\n'
            '    invoke-static {}, Lio/reactivex/Completable;->s()Lio/reactivex/Completable;\n'
            '    move-result-object v0\n    return-object v0\n    :rc2port_button_original\n')
    anchor = '    return-object p0\n\n    :pswitch_data_19e\n    .packed-switch 0x1\n'
    if text.count(hook) != 1 or text.count(anchor) != 1:
        raise ValueError("Exact 1.21.16 button switch padding anchors differ")
    return text.replace(anchor, '    return-object p0\n\n    nop\n\n    :pswitch_data_19e\n    .packed-switch 0x1\n', 1)


def _normal_method(text: str) -> str:
    text = re.sub(r"(?m)^(\.method [^\n]* )[^\s(]+(?=\()", r"\1METHOD", text)
    return "\n".join(line for line in text.splitlines() if line.strip()
                     and not re.match(r"\s*\.(?:line|local|end local|restart local)\b", line))


def _legacy_body_renames(typ: str) -> dict[str, str]:
    if typ == VIEW:
        return {VIEW + "->I0(" + EVENT + ")Z": VIEW + "->K0(" + EVENT + ")Z",
                VIEW + "->W()V": VIEW + "->Z()V",
                VIEW + "->Z(" + EVENT_TYPE + ")[I": VIEW + "->c0(" + EVENT_TYPE + ")[I",
                VIEW + "->M0(" + EVENT_TYPE + "I" + EVENT_PRIORITY + "IIII)V": VIEW + "->O0(" + EVENT_TYPE + "I" + EVENT_PRIORITY + "IIII)V",
                VIEW + "->N0()V": VIEW + "->P0()V"}
    if typ == VM:
        return {VM + "->K1()Z": VM + "->f2()Z", VM + "->b1()V": VM + "->v1()V",
                "Lcom/uav/fpv/leftbar/component/takeoffandland/s2;": "Lcom/uav/fpv/leftbar/component/takeoffandland/b3;",
                "Lcom/uav/fpv/leftbar/component/takeoffandland/t2;": "Lcom/uav/fpv/leftbar/component/takeoffandland/c3;"}
    return {}


def _verify_signature_renames(reference_defs: dict[str, str], source_defs: dict[str, str]) -> list[dict]:
    proofs = []
    for typ, changes in SIGNATURE_RENAMES.items():
        for old, new in changes.items():
            before, after = _method(reference_defs[typ], old), _method(source_defs[typ], new)
            normalized = before
            # The same AreaCodeAgent getter was renamed in the interface too.
            if typ == AREA:
                normalized = normalized.replace("Luav/infra/flymodel/api/business/areacode/AreaCodeAgent;->I0()Ljava/lang/String;",
                                                "Luav/infra/flymodel/api/business/areacode/AreaCodeAgent;->G0()Ljava/lang/String;")
            if _normal_method(normalized) != _normal_method(after):
                raise ValueError("Renamed host body differs from the independently audited reference: " + typ + " " + new)
            proofs.append({"class": typ, "reference_signature": old, "source_signature": new,
                           "reference_body_sha256": _hash(before.encode()), "source_body_sha256": _hash(after.encode()),
                           "body_equal_after_declared_renames_and_debug_removal": True})
    for typ, changes in LEGACY_METHODS.items():
        for old, new, mode in changes:
            before, after = _method(reference_defs[typ], old), _method(source_defs[typ], new)
            normalized = before
            for a, b in _legacy_body_renames(typ).items():
                normalized = normalized.replace(a, b)
            identical = _normal_method(normalized) == _normal_method(after)
            if typ == LAND:
                anchors = ["->getFlight()", "->getReturnToHome()", "->getReturnToHomeAction()", "->getStartRTH()"]
                if any(after.count(anchor) != 1 for anchor in anchors):
                    raise ValueError("1.21.16 manual RTH SDK chain differs")
                candidates = re.findall(r"(?ms)^\.method [^\n]*\n.*?^\.end method", source_defs[typ])
                if sum("->getStartRTH()" in candidate for candidate in candidates) != 1:
                    raise ValueError("Manual RTH SDK action is ambiguous")
            elif not identical:
                raise ValueError("Legacy RTH body differs after the declared member renames: " + typ + " " + new)
            proofs.append({"class": typ, "reference_signature": old, "source_signature": new, "guard_mode": mode,
                           "reference_body_sha256": _hash(before.encode()), "source_body_sha256": _hash(after.encode()),
                           "body_equal_after_declared_renames_and_debug_removal": identical,
                           "manual_sdk_action_chain_uniquely_verified": typ == LAND,
                           "original_12116_body_preserved_after_entry_hook": True})
    return proofs


def _legacy_hook(text: str, signature: str, mode: str) -> str:
    def transform(body):
        if "rc2port_" in body:
            raise ValueError("Legacy host already patched")
        register = re.search(r"(?m)^    \.(registers|locals) (\d+)[ \t]*$", body)
        params = 2 if mode == "suppress" else 1
        if register is None or int(register[2]) - (params if register[1] == "registers" else 0) < 1:
            raise ValueError("Legacy hook has no scratch local")
        local_count = int(register[2]) - (params if register[1] == "registers" else 0)
        required = 5 if mode == "suppress" else 4
        if local_count < required:
            # Parameter-register aliases would shift when adding locals. The
            # source's own locals and p0/p1 aliases are preserved; refuse a raw
            # v-register alias of a parameter instead of guessing its meaning.
            unquoted = re.sub(r'"(?:\\.|[^"\\])*"', '', body)
            if any(int(value) >= local_count for value in re.findall(r"\bv([0-9]+)\b", unquoted)):
                raise ValueError("Legacy source uses raw parameter-register aliases")
            count = required + (params if register[1] == "registers" else 0)
            body = body[:register.start(2)] + str(count) + body[register.end(2):]
            register = re.search(r"(?m)^    \.(registers|locals) (\d+)[ \t]*$", body)
        label = "rc2port_" + mode
        name = {"manual": "manual", "suppress": "suppressLegacy", "video": "blockVideo"}[mode]
        call = ('    const-string v0, "rthguard.Guard"\n'
                '    invoke-static {v0}, Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;\n'
                '    move-result-object v0\n'
                '    const-string v1, "' + name + '"\n')
        if mode == "suppress":
            call += ('    const/4 v3, 0x1\n    new-array v2, v3, [Ljava/lang/Class;\n'
                     '    const-class v3, Ljava/lang/Object;\n    const/4 v4, 0x0\n'
                     '    aput-object v3, v2, v4\n')
        else:
            call += '    const/4 v3, 0x0\n    new-array v2, v3, [Ljava/lang/Class;\n'
        call += ('    invoke-virtual {v0, v1, v2}, Ljava/lang/Class;->getMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;\n'
                 '    move-result-object v0\n')
        if mode == "suppress":
            call += ('    const/4 v3, 0x1\n    new-array v1, v3, [Ljava/lang/Object;\n'
                     '    aput-object p1, v1, v4\n    const/4 v3, 0x0\n')
        else:
            call += '    new-array v1, v3, [Ljava/lang/Object;\n'
        call += '    invoke-virtual {v0, v3, v1}, Ljava/lang/reflect/Method;->invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;\n'
        if mode != "manual":
            call += ('    move-result-object v0\n    check-cast v0, Ljava/lang/Boolean;\n'
                     '    invoke-virtual {v0}, Ljava/lang/Boolean;->booleanValue()Z\n')
        code = "\n    :" + label + "_start\n" + call
        if mode != "manual":
            code += "    move-result v0\n    if-eqz v0, :" + label + "_continue\n    return-void\n"
        code += ("    :" + label + "_end\n    .catch Ljava/lang/RuntimeException; {:" + label + "_start .. :" + label + "_end} :" + label + "_error\n"
                 "    .catch Ljava/lang/LinkageError; {:" + label + "_start .. :" + label + "_end} :" + label + "_error\n"
                 "    .catch Ljava/lang/ReflectiveOperationException; {:" + label + "_start .. :" + label + "_end} :" + label + "_error\n"
                 "    goto :" + label + "_done\n    :" + label + "_error\n    move-exception v0\n" +
                 ("    :" + label + "_continue\n" if mode != "manual" else "") + "    :" + label + "_done\n")
        patched = body[:register.end()] + code + body[register.end():]
        if patched.replace(code, "", 1) != body:
            raise ValueError("Original legacy host body was not preserved")
        return patched
    return patch_method(text, signature, transform)


def canonical_aop_patch(text: str, type_name: str, expected_methods: list[str]) -> tuple[str, list[str], list[dict]]:
    """Normalize a unique hash-only AOP method rename, then restore its name.

    The method prototype, the class and all body insertion anchors remain exact.
    No missing class/method/anchor is silently dropped.
    """
    renames = []
    normalized = text
    for old, new in SIGNATURE_RENAMES.get(type_name, {}).items():
        _method(normalized, new)
        normalized = normalized.replace(new, old)
        renames.append({"class": type_name, "reference_signature": old, "source_signature": new})
    for signature in expected_methods:
        if "$$AndroidAOP(" not in signature or " " + signature + "\n" in normalized:
            continue
        stem, prototype = signature.split("(", 1)
        base = stem.split("$$", 1)[0]
        candidates = re.findall(r"(?m)^\.method [^\n]* (" + re.escape(base)
                                + r"\$\$[0-9a-f]{32}\$\$AndroidAOP)\(" + re.escape(prototype) + r"\n", normalized)
        if len(candidates) != 1:
            raise ValueError("AOP host method is missing or ambiguous: " + type_name + " " + signature)
        current = candidates[0]
        if current == stem:
            raise ValueError("Unexpected AOP method normalization state")
        normalized = normalized.replace(current, stem)
        renames.append({"class": type_name, "old_reference_name": stem, "source_name": current,
                        "prototype": "(" + prototype})
    existing_intent = None
    intent_slot = "# rc2port_preserved_new_intent_slot"
    if type_name == MAIN_ACTIVITY:
        existing_intent = _method(normalized, "onNewIntent(Landroid/content/Intent;)V")
        if intent_slot in normalized:
            raise ValueError("Unexpected new-intent placeholder")
        normalized = normalized.replace(existing_intent, intent_slot, 1)
    patched, changes = patch_host(normalized, type_name)
    if existing_intent is not None:
        super_call = re.findall(r"(?m)^    invoke-super \{p0, p1\}, L[^;]+;->onNewIntent\(Landroid/content/Intent;\)V$", existing_intent)
        if len(super_call) != 1 or existing_intent.count("->handleTabSwitchIntent(Landroid/content/Intent;)V") != 1:
            raise ValueError("1.21.16 new-intent tab switching body differs")
        addition = "\n    invoke-static {p0, p1}, Llocal/rc2/hud/PortHooks;->noteIntent(Landroid/app/Activity;Landroid/content/Intent;)V"
        retained = existing_intent.replace(super_call[0], super_call[0] + addition, 1)
        if retained.replace(addition, "", 1) != existing_intent:
            raise ValueError("Original new-intent handler changed")
        generated = _method(patched, "onNewIntent(Landroid/content/Intent;)V")
        patched = patched.replace(generated, "", 1).replace(intent_slot, retained, 1)
    for rename in renames:
        patched = patched.replace(rename.get("reference_signature", rename.get("old_reference_name")),
                                  rename.get("source_signature", rename.get("source_name")))
    actual_methods = []
    for signature in changes:
        for rename in renames:
            signature = signature.replace(rename.get("reference_signature", rename.get("old_reference_name")),
                                          rename.get("source_signature", rename.get("source_name")))
        actual_methods.append(signature)
    return patched, actual_methods, renames


def _resource_bindings(reference: Path, source: Path, bundle: Path, stage: Path) -> tuple[dict, dict]:
    aapt = stage / "resource-aapt2.exe"
    with ZipFile(bundle / "lib/apktool.jar") as archive:
        aapt.write_bytes(archive.read("prebuilt/windows/aapt2_64.exe"))
    old_text = run(aapt, "dump", "resources", "--no-values", reference)
    new_text = run(aapt, "dump", "resources", "--no-values", source)
    (stage / "reference-resources.txt").write_text(old_text, "utf-8")
    (stage / "source-resources.txt").write_text(new_text, "utf-8")
    old, new = parse_resource_dump(old_text), parse_resource_dump(new_text)
    aliases: dict[int, list] = {}
    for key, old_id in old.items():
        aliases.setdefault(old_id, []).append(key)
    bindings = {}
    rows = {}
    for old_id, keys in aliases.items():
        mapped = {new[key] for key in keys if key in new}
        if len(mapped) == 1:
            bindings[old_id] = next(iter(mapped))
            rows[hex(old_id)] = {"target": hex(bindings[old_id]),
                                 "names": [kind + "/" + name for kind, name in keys if (kind, name) in new]}
    report = {"reference_resource_count": len(old), "source_resource_count": len(new),
              "bound_ids": len(bindings), "bindings": rows,
              "source_resource_table_sha256": _hash(ZipFile(source).read("resources.arsc")),
              "reference_resource_table_sha256": _hash(ZipFile(reference).read("resources.arsc"))}
    _json(stage / "resource-bindings.json", report)
    return bindings, report


def _verify_observable_getter(java: Path, cp: str, reference: Path, stockdex: Path, stage: Path) -> dict:
    """Bind the one renamed SDK getter through its generic type and seed flow."""
    reference_dex = stage / "reference-observable.dex"
    with ZipFile(reference) as archive:
        reference_dex.write_bytes(archive.read("classes17.dex"))
    if sha256_file(reference_dex) != "5c731066abec88d3b34fa1e1f693fbf0fff807781680097caa4e5ce24cabe99e":
        raise ValueError("Reference observable DEX provenance differs")
    old_types, new_types = stage / "old-observable-types.txt", stage / "new-observable-types.txt"
    old_types.write_text(OBSERVABLE + "\n" + OBSERVABLE_DEFAULT, "utf-8")
    new_types.write_text(OBSERVABLE, "utf-8")
    old_dir, new_dir = stage / "old-observable", stage / "new-observable"
    run(java, "-Xmx2560m", "-cp", cp, "FeatureAuditTool", "dump", old_dir, old_types, reference_dex)
    run(java, "-Xmx2560m", "-cp", cp, "FeatureAuditTool", "dump", new_dir, new_types, *sorted(stockdex.glob("*.dex")))
    def definitions(folder):
        return {line.split("\t")[0]: (folder / line.split("\t")[1]).read_text("utf-8")
                for line in (folder / "classes.tsv").read_text("utf-8").splitlines()}
    old_defs, new_defs = definitions(old_dir), definitions(new_dir)
    if set(old_defs) != {OBSERVABLE, OBSERVABLE_DEFAULT} or set(new_defs) != {OBSERVABLE}:
        raise ValueError("Observable API comparison inventory differs")
    old_getter = _method(old_defs[OBSERVABLE], "c()Ljava/lang/Object;")
    new_getter = _method(new_defs[OBSERVABLE], "d()Ljava/lang/Object;")
    for body in (old_getter, new_getter):
        annotation = re.search(r"(?ms)^    \.annotation system Ldalvik/annotation/Signature;\n.*?^    \.end annotation", body)
        generic_signature = "".join(json.loads(token) for token in re.findall(r'"(?:\\.|[^"\\])*"', annotation[0])) if annotation else None
        if " public abstract " not in body.splitlines()[0] or generic_signature != "()TT;":
            raise ValueError("Observable getter is not the original generic T contract")
    new_candidates = re.findall(r"(?m)^\.method [^\n]* ([^\s(]+\(\)Ljava/lang/Object;)\n", new_defs[OBSERVABLE])
    if new_candidates != ["d()Ljava/lang/Object;"]:
        raise ValueError("The 1.21.16 generic observable getter is ambiguous")
    old_seed = _method(old_defs[OBSERVABLE_DEFAULT], "p(" + OBSERVABLE + ")Lio/reactivex/Observable;")
    new_seed = _method(new_defs[OBSERVABLE], "a()Lio/reactivex/Observable;")
    old_calls = re.findall(r"(?m)^    invoke-interface [^\n]*, (L[^\n]+)$", old_seed)
    new_calls = re.findall(r"(?m)^    invoke-interface [^\n]*, (L[^\n]+)$", new_seed)
    if old_calls != [OBSERVABLE_OLD_GETTER, OBSERVABLE + "->d(Ljava/lang/Object;)Lio/reactivex/Observable;"]:
        raise ValueError("Reference observable default-seed data flow differs")
    if new_calls != [OBSERVABLE_NEW_GETTER, OBSERVABLE + "->f(Ljava/lang/Object;)Lio/reactivex/Observable;"]:
        raise ValueError("1.21.16 observable default-seed data flow differs")
    report = {"class": "Llanstream/LanTel;", "old_reference": OBSERVABLE_OLD_GETTER,
              "new_reference": OBSERVABLE_NEW_GETTER, "reference_source_sha256": REFERENCE_SHA256,
              "source_sha256": SOURCE_SHA256, "unique_generic_getter": True,
              "same_get_T_then_seed_Observable_flow": True,
              "old_getter_sha256": _hash(old_getter.encode()), "new_getter_sha256": _hash(new_getter.encode()),
              "old_seed_method_sha256": _hash(old_seed.encode()), "new_seed_method_sha256": _hash(new_seed.encode())}
    _json(stage / "observable-getter-proof.json", report)
    return report


def build(source: Path, reference: Path, java_home: Path, stage: Path, output: Path, resume_from: Path | None = None) -> dict:
    source, reference = source.resolve(strict=True), reference.resolve(strict=True)
    if sha256_file(source) != SOURCE_SHA256 or sha256_file(reference) != REFERENCE_SHA256:
        raise ValueError("Expected the independently pinned RC stock APKs")
    if stage.exists() or output.exists():
        raise ValueError("Work and published recipe directories must both be new")
    stage.mkdir(parents=True)
    tools = HudTools(ROOT / "assets", _short_windows_path(stage) / "t")
    bundle = tools.prepare()
    verify_stock_apk(tools, source, source_digest=SOURCE_SHA256, certificate_digest=CERTIFICATE_SHA256)
    baseline = ROOT / "assets/advanced12110"
    metadata = json.loads((baseline / "manifest.json").read_text("utf-8"))
    recipe_pin = sha256_file(baseline / "recipe.zip")
    if recipe_pin != metadata["recipe_sha256"]:
        raise ValueError("Reviewed r14.5 recipe hash mismatch")
    with ZipFile(baseline / "recipe.zip") as archive:
        for name, row in metadata["entries"].items():
            data = archive.read(name)
            if len(data) != row["bytes"] or _hash(data) != row["sha256"]:
                raise ValueError("Reviewed recipe payload hash mismatch: " + name)
        template = json.loads(archive.read("additions/" + PROFILE_ENTRY))
        helpers = {name: archive.read("additions/" + name) for name in ("classes23.dex", "classes24.dex")}
    if template.get("flight_overlay_policy") != POLICY or template.get("record_decryption_removed") is not True:
        raise ValueError("Expected the cleaned r14.5 menu policy")
    stockdex = stage / "stock-dex"
    stockdex.mkdir()
    with ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Source APK has duplicate ZIP entries")
        for name in names:
            if DEX.fullmatch(name):
                (stockdex / name).write_bytes(archive.read(name))
        if "classes23.dex" in names or "classes24.dex" in names:
            raise ValueError("Reviewed helper DEX positions conflict with stock")
        identity = inspect_application(archive.read("AndroidManifest.xml"))
    if identity["version"] != VERSION or identity["code"] != CODE or identity["package"] != "dji.go.v5":
        raise ValueError("Source identity does not match RC 1.21.16")
    libcp = os.pathsep.join(str(bundle / "lib" / name) for name in ("apktool.jar", "apksigner.jar"))
    classes = stage / "tools"
    classes.mkdir()
    tool_source = stage / "Menu12116DexTool.java"
    tool_source.write_text(DEX_TOOL, "utf-8")
    hook_source = (ROOT / "android-hud/FeatureHookTool.java").read_text("utf-8")
    hook_variant, count = re.subn(r"(?ms)^    static String patch\(String text,String type\) \{.*?(?=^    public static void main)",
                                 lambda _: PRESERVATION_HELPERS + "    static String patch(String text,String type) { return text; }\n", hook_source)
    if count != 1:
        raise ValueError("Host assembly utility source structure differs")
    old_check = ('if(!replacements.containsKey(type) && patch(before,type).equals(before)&&!before.equals(AdaptiveHudTool.dump(result.get(type))))\n'
                 '                throw new IllegalStateException("Unrelated class changed");')
    new_check = ('if(!replacements.containsKey(type))\n'
                 '                verifyUnrelated(before,AdaptiveHudTool.dump(result.get(type)),type,output);')
    if hook_variant.count(old_check) != 1:
        raise ValueError("Host assembly unrelated-class check source differs")
    hook_variant = hook_variant.replace(old_check, new_check)
    # Do not invoke that utility's 1.21.10-only automatic RTH hooks on 1.21.16.
    # The independently audited 1.21.16 entry hooks are supplied as exact class
    # replacements below. Its unrelated-class semantic preservation check stays.
    hook_file = stage / "FeatureHookTool.java"
    hook_file.write_text(hook_variant, "utf-8")
    run(java_home / "bin/javac.exe", "-encoding", "UTF-8", "-cp", libcp, "-d", classes,
        *[ROOT / "android-hud" / (name + ".java") for name in
          ("AdaptiveHudTool", "FeatureAssemblyTool", "FeatureAuditTool", "NestedMenuDexTool")], tool_source, hook_file)
    cp = str(classes) + os.pathsep + libcp
    java = java_home / "bin/java.exe"
    pool_file = stage / "classes4-original-method-pool.txt"
    run(java, "-Xmx2560m", "-cp", cp, "Menu12116DexTool", "methods", stockdex / "classes4.dex", pool_file)
    method_pool = set(pool_file.read_text("utf-8").splitlines())
    reflection_references = {
        "Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;",
        "Ljava/lang/Class;->getMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;",
        "Ljava/lang/reflect/Method;->invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;",
        "Ljava/lang/Boolean;->booleanValue()Z",
    }
    if not reflection_references <= method_pool:
        raise ValueError("A saturated source DEX lacks a pre-existing framework reflection method reference")
    _json(stage / "saturated-dex-hook-proof.json", {"source_dex": "classes4.dex", "original_method_ids": len(method_pool),
                                                 "all_hook_framework_method_refs_already_present": True,
                                                 "hook_method_references": sorted(reflection_references),
                                                 "stock_classes_relocated": False})
    bindings, resource_report = _resource_bindings(reference, source, bundle, stage)
    sdk_getter_proof = _verify_observable_getter(java, cp, reference, stockdex, stage)
    helper_paths = []
    helper_reports = {}
    for name, data in helpers.items():
        inp = stage / ("reviewed-" + name)
        inp.write_bytes(data)
        original = _dex_dump(java, cp, inp, stage / ("helper-before-" + name))
        patches = stage / ("helper-remapped-" + name)
        patches.mkdir()
        expected = {}
        refs = []
        for index, (typ, text) in enumerate(original.items()):
            changed, records = remap_resource_literals(text, bindings)
            if typ == "Llanstream/LanTel;":
                if changed.count(OBSERVABLE_OLD_GETTER) != 1 or OBSERVABLE_NEW_GETTER in changed:
                    raise ValueError("Expected exactly one reviewed LanTel getter call")
                changed = changed.replace(OBSERVABLE_OLD_GETTER, OBSERVABLE_NEW_GETTER)
            expected[typ] = changed
            refs.extend({"class": typ, **row} for row in records)
            (patches / ("class-" + str(index) + ".smali")).write_text(changed, "utf-8")
        result = stage / name
        run(java, "-Xmx2560m", "-cp", cp, "FeatureAssemblyTool", "assemble", result, patches)
        actual = _dex_dump(java, cp, result, stage / ("helper-after-" + name))
        if actual != expected:
            differing = sorted(set(actual) ^ set(expected) | {key for key in actual.keys() & expected.keys() if actual[key] != expected[key]})
            raise ValueError("Reassembled helper semantic dump differs: " + repr(differing[:10]))
        helpers[name] = result.read_bytes()
        helper_paths.append(result)
        helper_reports[name] = {"reviewed_sha256": _hash(data), "ported_sha256": _hash(helpers[name]),
                                "classes": len(actual), "resource_references": refs,
                                "resource_references_changed": sum(row["old"] != row["new"] for row in refs),
                                "all_other_smali_preserved": True,
                                "declared_sdk_reference_rebindings": [sdk_getter_proof] if name == "classes24.dex" else []}
    _json(stage / "helper-resource-audit.json", helper_reports)
    if helper_reports["classes24.dex"]["classes"] != 430:
        raise ValueError("Reviewed feature class count changed")
    # Recheck policies on actual final helper definitions, not only the profile.
    bridge_defs = _dex_dump(java, cp, stage / "classes23.dex", stage / "helper-policy-bridge")
    feature_defs = _dex_dump(java, cp, stage / "classes24.dex", stage / "helper-policy-feature")
    for signature in ("manual()V", "blockVideo()Z", "suppressLegacy(Ljava/lang/Object;)Z"):
        declaration = _method(feature_defs["Lrthguard/Guard;"], signature).splitlines()[0]
        if " public static " not in declaration:
            raise ValueError("The reviewed reflective guard target is not public static")
    integration = bridge_defs["Llocal/rc2/hud/PortIntegration;"]
    hooks_text = bridge_defs["Llocal/rc2/hud/PortHooks;"]
    if '"flyctl.Q"' in integration or '"addToggles"' in hooks_text or '"frtool.X"' in integration:
        raise ValueError("Removed flight controls were reattached")
    if "->frDecrypt()Z" in feature_defs["Lflysettings/S;"]:
        # The setting method may remain as a false stub; the removed row may not invoke it.
        show = re.search(r"(?ms)^\.method [^\n]* showSettings\([^\n]*\n.*?^\.end method", feature_defs["Lflysettings/S;"])
        if show and "->frDecrypt()Z" in show[0]:
            raise ValueError("Removed record decryption UI was reattached")
    expected_methods = {row["class"]: row["methods"] for row in template["method_hooks"]}
    types = LEGACY_TARGETS | set(expected_methods)
    typefile = stage / "host-types.txt"
    typefile.write_text("\n".join(sorted(types)), "utf-8")
    hosts = stage / "stock-hosts"
    print("Auditing original 1.21.16 host classes", flush=True)
    run(java, "-Xmx2560m", "-cp", cp, "FeatureAuditTool", "dump", hosts, typefile, *sorted(stockdex.glob("*.dex")))
    index = {row.split("\t")[0]: (row.split("\t")[1], row.split("\t")[2])
             for row in (hosts / "classes.tsv").read_text("utf-8").splitlines()}
    if set(index) != types:
        raise ValueError("Required 1.21.16 host classes are missing: " + repr(sorted(types - set(index))))
    source_defs = {typ: (hosts / filename).read_text("utf-8") for typ, (filename, _) in index.items()}
    reference_types = set(SIGNATURE_RENAMES) | LEGACY_TARGETS
    reference_typefile = stage / "reference-host-types.txt"
    reference_typefile.write_text("\n".join(sorted(reference_types)), "utf-8")
    reference_dex = stage / "reference-stock-dex"
    reference_dex.mkdir()
    reference_dex_names = {row["dex"] for row in template["method_hooks"] if row["class"] in reference_types} | {"classes20.dex"}
    with ZipFile(reference) as archive:
        for name in sorted(reference_dex_names):
            (reference_dex / name).write_bytes(archive.read(name))
    reference_hosts = stage / "reference-hosts"
    run(java, "-Xmx2560m", "-cp", cp, "FeatureAuditTool", "dump", reference_hosts,
        reference_typefile, *sorted(reference_dex.glob("*.dex")))
    reference_index = {line.split("\t")[0]: line.split("\t")[1]
                       for line in (reference_hosts / "classes.tsv").read_text("utf-8").splitlines()}
    if set(reference_index) != reference_types:
        raise ValueError("Reference method comparison class inventory differs")
    reference_defs = {typ: (reference_hosts / filename).read_text("utf-8") for typ, filename in reference_index.items()}
    signature_proofs = _verify_signature_renames(reference_defs, source_defs)
    _json(stage / "signature-rename-proof.json", {"proofs": signature_proofs,
                                                "reference_source_sha256": REFERENCE_SHA256, "source_sha256": SOURCE_SHA256})
    patches = stage / "host-patches"
    patches.mkdir()
    method_hooks, aop_renames = [], []
    for typ, (filename, dexname) in index.items():
        text = (hosts / filename).read_text("utf-8")
        patched, changes, renames = canonical_aop_patch(text, typ, expected_methods.get(typ, []))
        if typ in LEGACY_METHODS:
            for _, current, mode in LEGACY_METHODS[typ]:
                patched = _legacy_hook(patched, current, mode)
                changes.append(current)
        if typ in expected_methods:
            expected_names = list(expected_methods[typ])
            for rename in renames:
                expected_names = [value.replace(rename.get("reference_signature", rename.get("old_reference_name")),
                                                rename.get("source_signature", rename.get("source_name"))) for value in expected_names]
            if changes != expected_names:
                raise ValueError("Host method hook coverage differs: " + typ)
        if changes:
            patched = preserve_method_metadata(text, patched, changes)
            patched = explicit_button_payload_padding(patched, typ)
            assert_unique_methods(patched)
            (patches / filename).write_text(patched, "utf-8")
            method_hooks.append({"class": typ, "dex": dexname, "methods": changes})
        aop_renames.extend(renames)
    _json(stage / "host-anchor-audit.json", {"method_hooks": method_hooks, "aop_hash_renames": aop_renames,
                                           "source_index": index, "signature_proofs": signature_proofs,
                                           "all_expected_host_classes_present": True,
                                           "existing_12116_new_intent_body_preserved": True})
    planstage = stage / "plan"
    planstage.mkdir()
    plan = analyze(source, tools, planstage)
    if plan["identity"] != identity or plan["helper_entry"] != "classes23.dex" or not plan["retain_loader_v2"]:
        raise ValueError("Unexpected bootstrap or helper inventory in 1.21.16")
    with ZipFile(source) as archive:
        replacements = {"AndroidManifest.xml": add_adaptive_provider(archive.read("AndroidManifest.xml"))}
        bootstrap = stage / "bootstrap.dex"
        bootstrap.write_bytes(archive.read(plan["bootstrap"]["entry"]))
    patched = stage / "bootstrap-patched.dex"
    tools.patch_adaptive(bootstrap, patched, stage / "bootstrap-smali", plan["bootstrap"]["descriptor"])
    replacements[plan["bootstrap"]["entry"]] = patched.read_bytes()
    host_hooks = []
    dexnames = {index[typ][1] for typ in LEGACY_TARGETS} | {row["dex"] for row in method_hooks}
    _json(stage / "planned-replacement-entries.json", {"entries": sorted(set(replacements) | dexnames)})
    print("1.21.16 replacement entries: " + repr(sorted(set(replacements) | dexnames)), flush=True)
    for name in sorted(dexnames):
        print("Patching fresh 1.21.16 " + name, flush=True)
        result = stage / ("hooked-" + name)
        reused = resume_from / ("hooked-" + name) if resume_from else None
        if reused is not None and reused.is_file():
            # A prior run may have stopped at a later DEX. Reuse only after a
            # complete class-by-class comparison against THIS run's exact stock
            # and expected patched smali, never merely trusting its filename.
            reused_sha = sha256_file(reused)
            changed = int(run(java, "-Xmx2560m", "-cp", cp, "Menu12116DexTool", "verify",
                              stockdex / name, reused, patches, stage / ("hooked-" + name + ".encoding-only.tsv")))
            data = reused.read_bytes()
            if _hash(data) != reused_sha:
                raise ValueError("Resume DEX changed during semantic verification")
            result.write_bytes(data)
            _json(stage / ("resume-" + name + ".json"), {"source_dex_sha256": sha256_file(stockdex / name),
                                                      "reused_output_sha256": reused_sha,
                                                      "source_run": str(resume_from),
                                                      "every_class_verified_against_current_expected_bodies": True})
        else:
            changed = int(run(java, "-Xmx2560m", "-cp", cp, "FeatureHookTool", stockdex / name,
                              result, stage / ("host-smali-" + name), patches))
        replacements[name] = result.read_bytes()
        host_hooks.append({"dex": name, "classes_patched": changed})
    # Verify each assembled patched class against its complete expected smali,
    # including every unmodified method in that class. Unrelated classes were
    # already checked by the assembly utility with the same encoding-only rule.
    assembled_hosts = stage / "assembled-hosts"
    run(java, "-Xmx2560m", "-cp", cp, "FeatureAuditTool", "dump", assembled_hosts, typefile,
        *[stage / ("hooked-" + name) for name in sorted(dexnames)])
    assembled_index = {line.split("\t")[0]: line.split("\t")[1]
                       for line in (assembled_hosts / "classes.tsv").read_text("utf-8").splitlines()}
    if set(assembled_index) != types:
        raise ValueError("Assembled host type inventory differs")
    for typ, (filename, _) in index.items():
        expected = (patches / filename).read_text("utf-8")
        actual = (assembled_hosts / assembled_index[typ]).read_text("utf-8")
        if normalize_smali_encoding(expected) != normalize_smali_encoding(actual):
            raise ValueError("Assembled patched class differs from its expected complete body: " + typ)
    encoding_only = {name: (stage / ("hooked-" + name + ".encoding-only.tsv")).read_text("utf-8").splitlines()
                     for name in sorted(dexnames) if (stage / ("hooked-" + name + ".encoding-only.tsv")).is_file()}
    _json(stage / "class-preservation-audit.json", {"all_31_selected_classes_match_complete_expected_smali": True,
                                                 "all_unrelated_classes_preserved": True,
                                                 "encoding_only_classes": encoding_only,
                                                 "allowed_encoding_differences": ["const-string index-width", "position-bound label names", "blank/CRLF formatting", "debug line placement"]})
    audit = stage / "audit-dex"
    audit.mkdir()
    for path in stockdex.glob("*.dex"):
        (audit / path.name).write_bytes(replacements.get(path.name, path.read_bytes()))
    print("Auditing all retained menu API dependencies against 1.21.16", flush=True)
    run(java, "-Xmx2560m", "-cp", cp, "FeatureAuditTool", "check", stage / "dependencies.tsv", audit, *helper_paths)
    if (stage / "dependencies.tsv").read_text("utf-8").strip():
        raise ValueError("Unresolved 1.21.16 menu dependencies; see dependencies.tsv")
    profile = copy.deepcopy(template)
    profile.update(kind=KIND, source_sha256=SOURCE_SHA256, plan=plan, host_hooks=host_hooks,
                   method_hooks=method_hooks, runtime_verified=False, reviewed_menu_source_recipe_sha256=recipe_pin,
                   resource_ids_validated=sum(len(r["resource_references"]) for r in helper_reports.values()),
                   resource_ids_remapped=sum(r["resource_references_changed"] for r in helper_reports.values()))
    additions = {**helpers, PROFILE_ENTRY: json.dumps(profile, sort_keys=True, ensure_ascii=False).encode("utf-8")}
    payloads = {"replacements/" + key: data for key, data in replacements.items()}
    payloads.update({"additions/" + key: data for key, data in additions.items()})
    recipe = stage / "recipe.zip"
    with ZipFile(recipe, "x", ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            archive.writestr(name, data)
    with ZipFile(recipe) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(payloads):
            raise ValueError("Final recipe ZIP verification failed")
        if any(archive.read(name) != data for name, data in payloads.items()):
            raise ValueError("Final recipe payload differs from its audited bytes")
    result = {**metadata, "version": VERSION, "code": CODE, "source_sha256": SOURCE_SHA256,
              "profile_kind": KIND, "recipe_sha256": sha256_file(recipe), "compatible_installed": {},
              "entries": {name: {"sha256": _hash(data), "bytes": len(data)} for name, data in payloads.items()}}
    report = {"status": "PASS_RECIPE_STATIC_AUDIT", "version": VERSION, "code": CODE,
              "source_sha256": SOURCE_SHA256, "reviewed_menu_recipe_sha256": recipe_pin,
              "replacement_entries": sorted(replacements), "addition_entries": sorted(additions),
              "recipe_sha256": result["recipe_sha256"], "host_hooks": host_hooks, "method_hooks": method_hooks,
              "aop_hash_renames": aop_renames, "unresolved_dependencies": 0,
              "signature_rename_proofs": signature_proofs,
              "helper_resource_audits": helper_reports, "resource_audit": {k: v for k, v in resource_report.items() if k != "bindings"},
              "flight_overlay_policy": POLICY, "record_decryption_removed": True,
              "all_patched_and_unrelated_class_bodies_verified": True, "encoding_only_classes": encoding_only,
              "saturated_dex_uses_existing_framework_refs": True, "stock_classes_relocated": False,
              "runtime_verified": False, "device_commands_sent": False, "source_executed": False}
    if sha256_file(source) != SOURCE_SHA256 or sha256_file(reference) != REFERENCE_SHA256 or sha256_file(baseline / "recipe.zip") != recipe_pin:
        raise ValueError("An input changed during the recipe build; publish refused")
    _json(stage / "manifest.json", result)
    _json(stage / "report.json", report)
    output.mkdir(parents=True, exist_ok=False)
    (output / "recipe.zip").write_bytes(recipe.read_bytes())
    _json(output / "manifest.json", result)  # publish metadata only after all verification
    print(json.dumps({key: value for key, value in report.items() if key not in {"helper_resource_audits", "method_hooks"}}, ensure_ascii=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference-stock", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--resume-from", type=Path, help="Reuse prior successful DEX outputs only after full semantic revalidation")
    args = parser.parse_args()
    build(args.source, args.reference_stock, args.java_home, args.work.absolute(), ROOT / "assets/advanced12116", args.resume_from)


if __name__ == "__main__":
    main()
