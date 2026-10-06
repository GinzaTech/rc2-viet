"""Extract and validate text-only localization without modifying app logic."""
import argparse
import copy
import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
SOURCE = ROOT / "fly-1.21.8-source" / "res"
FORMAT = r"%(?:\d+\$)?[-#+ 0,(]*\d*(?:\.\d+)?(?:[tT][A-Za-z]|[bBhHsScCdoxXeEfgGaAn%])"
TAG = r"</?[A-Za-z][^>]*>"
ESCAPE = r"\\+u[0-9a-fA-F]{4}|\\[nrt\\]|\n|\r|\t"
UNIT = r"(?<![\w])[-+]?\d+(?:[.,]\d+)?\s?(?:m/s|km/h|mph|km|ft|ms|fps|s|m|°C|°F|V|A|Hz|GHz|MB|GB|%)\b"
NUMBER = r"(?<!\w)[-+]?\d+(?:[.,:]\d+)*(?!\w)"
URL = r"https?://[^\s<>]+"
PATH_OR_CODE = r"\b0x[0-9a-fA-F]+\b|\b[A-Za-z]:(?:\\+[^\\\s\"']+)+"
IDENTIFIER = r"\b(?:DJI Fly|DJI Assistant 2|DJI Care Refresh|DJI RC(?: Pro)?(?: 2)?|DJI|Mavic(?: \d)?(?: Pro)?|Mini \d(?: Pro)?|Air \d(?:S)?|Avata(?: \d)?|Neo(?: \d)?|RTH|APAS|GPS|GNSS|IMU|ESC|FPV|ISO|EV|RAW|JPEG|MP4|DNG|C1|C2|H\.264|H\.265|D-Log(?: M)?|D-Cinelike|SkyPixel|GEO)\b"
GLOSSARY = json.loads((ROOT / "terminology.json").read_text(encoding="utf-8"))
GLOSSARY_CASEFOLD = {key.casefold(): value for key, value in GLOSSARY.items()}
GLOSSARY_PATTERN = r"\b(?:" + "|".join(re.escape(k) for k in sorted(GLOSSARY, key=len, reverse=True)) + r")\b"
PROTECTED = re.compile("|".join(f"(?:{p})" for p in [FORMAT, TAG, PATH_OR_CODE, ESCAPE, URL, UNIT, NUMBER, IDENTIFIER]), re.I)
SECRET_NAME = re.compile(r"(?:api_?key|access_?token|secret|google_app_id|gcm_defaultSenderId|client_?id|mapbox_access_token)", re.I)
SAFETY = re.compile(r"\b(?:warning|danger|emergency|crash|collision|obstacle|propeller|motor|battery|return.to.home|landing|land aircraft|unable|cannot|do not|never|not safe|disconnect|signal lost|strong wind|altitude|geozone|restricted|GPS|RTH)\b", re.I)

def format_tokens(text):
    return re.findall(FORMAT, text)

def split_protected(text):
    text = re.sub(r"\\([\"'])", r"\1", text)
    result = []
    start = 0
    for match in PROTECTED.finditer(text):
        if start < match.start():
            result.append((False, text[start:match.start()]))
        result.append((True, match.group()))
        start = match.end()
    if start < len(text):
        result.append((False, text[start:]))
    return result

def should_translate(name, text):
    value = text.strip()
    if not value or SECRET_NAME.search(name):
        return False
    if value.startswith(("{", "[")):
        try:
            json.loads(re.sub(r"\\([\"'])", r"\1", value))
            return False
        except (ValueError, TypeError):
            pass
    if value.startswith("@") or re.fullmatch(URL, value):
        return False
    if re.fullmatch(r"(?:[A-Za-z_]\w*\.){2,}[A-Za-z_]\w*", value):
        return False
    if re.fullmatch(r"[A-Fa-f0-9]{16,}|[A-Za-z0-9+/=_-]{48,}", value):
        return False
    if re.fullmatch(r"[A-Z][A-Z0-9_+.-]*\d[A-Z0-9_+.-]*", value):
        return False
    if value.casefold() in GLOSSARY_CASEFOLD:
        return True
    stripped = PROTECTED.sub("", value).strip(" /:;.,()[]{}+-\"'")
    if not re.search(r"[A-Za-z]{2,}", stripped):
        return False
    if re.fullmatch(r"(?:m|km|ft|s|ms|V|A|Hz|GHz|MB|GB|km/h|m/s)", stripped):
        return False
    return True

def validate_translation(source, target):
    if not isinstance(target, str) or not target.strip():
        return False
    if format_tokens(source) != format_tokens(target):
        return False
    for pattern in [TAG, ESCAPE, URL, UNIT, NUMBER]:
        if re.findall(pattern, source) != re.findall(pattern, target):
            return False
    return True

def android_escape(text):
    return re.sub(r"(?<!\\)([\"'])", r"\\\1", text)

def normalize_source(text):
    text = re.sub(r"\\([\"'])", r"\1", text)
    return text[1:-1] if len(text) >= 2 and text.startswith('"') and text.endswith('"') else text

def lexical_parts(text):
    match = re.match(r"^([^A-Za-z]*)(.*?[A-Za-z])([^A-Za-z]*)$", text, re.S)
    return match.groups() if match else ("", text, "")

def entries():
    for filename in ["strings.xml", "plurals.xml", "arrays.xml"]:
        path = SOURCE / "values" / filename
        if not path.exists():
            continue
        effective = {(e.tag, e.get("name")): e for e in ET.parse(path).getroot()}
        for locale in ["values-en", "values-en-rUS"]:
            alternative = SOURCE / locale / filename
            if alternative.exists():
                for override in ET.parse(alternative).getroot():
                    key = (override.tag, override.get("name"))
                    if key in effective:
                        effective[key] = override
        for elem in effective.values():
            if elem.tag not in {"string", "plurals", "string-array"}:
                continue
            name = elem.attrib["name"]
            yield filename, name, elem

def text_slots(elem):
    for node in elem.iter():
        if node.text:
            yield node, "text", node.text
        if node is not elem and node.tail:
            yield node, "tail", node.tail

def make_catalog():
    catalog = []
    segments = set()
    for filename, name, elem in entries():
        strings = [text for _, _, text in text_slots(elem)]
        eligible = elem.attrib.get("translatable") != "false" and any(should_translate(name, text) for text in strings)
        catalog.append({"file": filename, "name": name, "kind": elem.tag, "texts": strings,
                        "eligible": eligible, "safety_review": bool(SAFETY.search(" ".join(strings)))})
        if eligible:
            for text in strings:
                if should_translate(name, text):
                    for fixed, part in split_protected(text):
                        if not fixed and should_translate("visible_text", part):
                            segments.add(lexical_parts(part)[1])
    (ROOT / "translation-catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "translation-segments.json").write_text(json.dumps(sorted(segments, key=lambda x: (len(x), x)), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"resources": len(catalog), "eligible": sum(x["eligible"] for x in catalog),
                      "unique_segments": len(segments), "safety_review": sum(x["eligible"] and x["safety_review"] for x in catalog)}))

def compose(text, cache):
    normalized = normalize_source(text)
    if normalized.casefold() in GLOSSARY_CASEFOLD:
        return GLOSSARY_CASEFOLD[normalized.casefold()]
    parts = []
    for fixed, part in split_protected(text):
        if fixed or not should_translate("visible_text", part):
            parts.append(part)
        else:
            leading, key, trailing = lexical_parts(part)
            if key.casefold() in GLOSSARY_CASEFOLD:
                parts.append(leading + GLOSSARY_CASEFOLD[key.casefold()] + trailing)
                continue
            if key not in cache:
                raise KeyError(key)
            target = cache[key].strip()
            for old, new in [("trở về nhà", "quay về"), ("quay về nhà", "quay về"),
                             ("ngăn trở việc tránh xa", "tránh chướng ngại vật"), ("phi cơ", "máy bay")]:
                target = re.sub(re.escape(old), new, target, flags=re.I)
            parts.append(leading + target + trailing)
    return "".join(parts)

def write_translations():
    cache = json.loads((ROOT / "translation-cache.json").read_text(encoding="utf-8"))
    manual = json.loads((ROOT / "reviewed-overrides.json").read_text(encoding="utf-8")) if (ROOT / "reviewed-overrides.json").exists() else {}
    reviewed_text = json.loads((ROOT / "reviewed-text-overrides.json").read_text(encoding="utf-8"))
    rows = []
    for filename in ["strings.xml", "plurals.xml", "arrays.xml"]:
        destination = SOURCE / "values-vi" / filename
        baseline = ROOT / ("original-vi-" + filename)
        if not baseline.exists():
            original_names = set()
            config = None
            with (ROOT / "fly-resources.txt").open(encoding="utf-8-sig") as stream:
                for line in stream:
                    m = re.match(r"\s+config ([^:]+):", line)
                    if m:
                        config = m.group(1)
                    if config == "vi":
                        m = re.search(r"\bresource .*?:((?:string|plurals|array))/([^:]+):", line)
                        if m:
                            original_names.add(m.group(2))
            native = ET.Element("resources")
            if destination.exists():
                for existing_element in ET.parse(destination).getroot():
                    if existing_element.get("name") in original_names:
                        native.append(copy.deepcopy(existing_element))
            ET.ElementTree(native).write(baseline, encoding="utf-8", xml_declaration=True)
        base = ET.parse(baseline).getroot()
        existing = {(e.tag, e.get("name")) for e in base}
        for srcfile, name, elem in entries():
            if srcfile != filename or (elem.tag, name) in existing:
                continue
            source_text = " ".join(text for _, _, text in text_slots(elem))
            if elem.attrib.get("translatable") == "false" or not any(should_translate(name, t) for _, _, t in text_slots(elem)):
                rows.append({"name": name, "source": source_text, "target": "", "status": "excluded", "safety_review": False})
                continue
            clone = copy.deepcopy(elem)
            fully_reviewed = True
            try:
                for node, attr, text in list(text_slots(clone)):
                    if not should_translate(name, text):
                        continue
                    if name in manual and elem.tag == "string" and len(list(text_slots(elem))) == 1:
                        target = manual[name]
                    elif normalize_source(text) in reviewed_text:
                        target = reviewed_text[normalize_source(text)]
                    else:
                        target = compose(text, cache)
                        fully_reviewed = False
                    if not validate_translation(text, target):
                        raise ValueError("format or structural mismatch")
                    setattr(node, attr, android_escape(target))
                base.append(clone)
                rows.append({"name": name, "source": source_text, "target": " ".join(t for _, _, t in text_slots(clone)),
                             "status": "reviewed" if fully_reviewed else "machine_draft", "safety_review": bool(SAFETY.search(source_text))})
            except (KeyError, ValueError) as exc:
                rows.append({"name": name, "source": source_text, "target": "", "status": "rejected: " + str(exc), "safety_review": bool(SAFETY.search(source_text))})
        destination.parent.mkdir(parents=True, exist_ok=True)
        ET.indent(base, space="    ")
        ET.ElementTree(base).write(destination, encoding="utf-8", xml_declaration=True)
    with (ROOT / "translation-review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["name", "source", "target", "status", "safety_review"])
        writer.writeheader()
        writer.writerows(rows)
    stats = {"total_catalog_resources": len(list(entries())), "generated": sum(r["status"] in {"reviewed", "machine_draft"} for r in rows),
             "reviewed": sum(r["status"] == "reviewed" for r in rows), "rejected": sum(r["status"].startswith("rejected") for r in rows),
             "excluded": sum(r["status"] == "excluded" for r in rows), "unreviewed_safety": sum(r["safety_review"] and r["status"] == "machine_draft" for r in rows)}
    (ROOT / "translation-statistics.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["catalog", "write"])
    args = ap.parse_args()
    make_catalog() if args.action == "catalog" else write_translations()
