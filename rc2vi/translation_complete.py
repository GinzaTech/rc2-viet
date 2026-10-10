"""Target-driven, fail-closed Vietnamese resource composition (no build/device I/O).

Memory is optional schema-1 translation_catalog data. Counts are *resources*,
not array items or sentences. Preserved resources fall through to the target;
preserved items in a translated collection remain verbatim. Completeness means
structural coverage, never machine semantic review. Exactly one primary engine
batch and at most one segmented fallback batch are used, independent of size.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
import copy
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET

from . import translation_catalog as tc

# Conservative character budget for the 512-token OPUS-MT worker, including
# markers. Whitespace and sentence boundaries are retained outside each request.
MAX_SENTENCE_CHARS = 320
MARKER = re.compile(r"__RC2VI_\d+__")
UNITS = r"(?:km/h|m/s|mAh|MHz|GHz|kHz|Mbps|kbps|fps|rpm|mph|km|cm|mm|ms|kg|MB|GB|KB|MP|Hz|dB|EV|°C|°F|ft|m|s|h|g|V|W|A)"
UNIT_END = r"(?=$|[^\w]|[\u4e00-\u9fff])"
FORMAT_UNIT = re.compile(r"[ \t]*(" + UNITS + r")" + UNIT_END)
MODEL_ID = re.compile(r"(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]+\Z")
PROTOCOLS = r"(?:CAN_SOCKET|UART|CAN|ICC|BULK|SHM|MBUS|LOCAL|IP|WL)"
PRODUCTS = (r"(?:DJI(?:\s+(?:Mini|Mavic|Air|Avata|Neo|Flip|RC|Fly|Goggles|FPV|O3|O4|"
            r"Osmo|Pocket|Action|Inspire|Phantom|Spark|Pro|Enterprise|Classic|Cine|Zoom|SE|N[123]|\d+[A-Z]?))*|"
            r"OcuSync|QuickShots|MasterShots|ActiveTrack|FocusTrack|Hyperlapse|SkyPixel|Wi-Fi|WiFi|SSID|Bluetooth|GPS|GNSS|USB|ISO|HDR|4K|8K|"
            r"N/A|H\.26[45]|ProRes|D-Log(?: M)?|D-Cinelike|D-Cine|HLG|JPEG|RAW|MP4|MOV|OSV|CBR|VBR|ALL-I)")
TECH_NAME = re.compile(r"(?:^|[_.])(?:(?:api|app|sdk|client|access|auth|secret|private|public|google)[_.]?(?:key|secret|token)|"
                       r"(?:api_key|client_secret|access_token|private_key)|credential|password|secret|token)$", re.I)
LEXICAL = re.compile(
    r"(?:https?://|mailto:|ftp://)[^\s<>]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"(?:[@?](?:[\w.]+:)?(?:[\w]+/)[\w.]+)|"
    r"\b(?:[A-Za-z0-9+/=_-]{32,})\b|\b0x[0-9A-Fa-f]+\b|#[0-9A-Fa-f]{6,8}\b|"
    r"(?<![A-Za-z0-9_])" + PROTOCOLS + r"(?![A-Za-z0-9_])|"
    r"(?<=[\u4e00-\u9fff])(?i:" + PROTOCOLS + r")(?![A-Za-z0-9_])|"
    r"(?<![A-Za-z0-9_])(?i:" + PROTOCOLS + r")(?=[\u4e00-\u9fff])|"
    r"(?<![A-Za-z0-9_])(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]+(?![A-Za-z0-9_])|"
    r"(?<![A-Za-z0-9_])v\d+(?:\.\d+)+(?![A-Za-z0-9_])|"
    r"(?<![A-Za-z0-9_])(?:[a-z][A-Za-z0-9_]*\.){2,}[A-Za-z][A-Za-z0-9_]*(?![A-Za-z0-9_])|\b[a-z]\w*(?:_[A-Za-z0-9]+)+\b|"
    r"(?<![A-Za-z0-9_])[A-Za-z0-9_-]+\.(?i:json|xml|yaml|yml|apk|bin|txt|csv|pdf|jpg|jpeg|png|mp4|mov|fit|srt|dng|zip|log|dat|kml|gpx|wav|html|so|jar|ttf|db)(?![A-Za-z0-9_])|"
    r"(?<![A-Za-z0-9_])" + PRODUCTS + r"(?![A-Za-z0-9_])|"
    r"\d+(?:[.,:]\d+)*(?:[pKx]\b|\s*" + UNITS + UNIT_END + r")?|[\n\r\t]"
)
ASSIGNMENT = re.compile(r"\b(?:api[_-]?key|secret|token|password|authorization)\s*[:=]\s*(?P<value>\S+)", re.I)
COMPARATOR_UP = re.compile(
    r"\b(?:above|over|at\s+least|more\s+than|greater\s+than|higher\s+than|minimum|"
    r"trên|ít\s+nhất|tối\s+thiểu|lớn\s+hơn|cao\s+hơn|trở\s+lên)\b|"
    r"以上|之上|高[于於]|至少|(?<=\d)上|[>≥]")
COMPARATOR_DOWN = re.compile(
    r"\b(?:below|under|at\s+most|less\s+than|lower\s+than|maximum|"
    r"dưới|nhiều\s+nhất|tối\s+đa|nhỏ\s+hơn|thấp\s+hơn|ít\s+hơn|trở\s+xuống)\b|"
    r"以下|之下|低[于於]|至多|(?<=\d)下|[<≤]")
COMPARATOR_NEGATION = re.compile(
    r"\b(?:not|no|never|without|neither|nor|cannot|\w+n['’]t|không|chưa|chẳng|đừng|chớ)\b|[不未无無勿别別没沒非]")
TECH_LITERALS = {
    "unset_quantity": re.compile(r"(?:[-–—]\s*){2,}" + UNITS),
    "release_stamp": re.compile(r"(?:19|20)\d{2} (?=[IVXLCDM])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"),
    "java_class": re.compile(r"(?:[a-z_][A-Za-z0-9_]*\.)+[A-Z_$][A-Za-z0-9_$]*"),
    "firebase_app_id": re.compile(r"\d+:\d+:android:[0-9a-fA-F]{16,64}"),
    "hostname": re.compile(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}", re.I),
    "device_format_label": re.compile(r"IMU(?: \d+)?|RTH(?: \(C[12]\))?:?|FPV|M\.M|J\+R|RAW\+JPEG|[AC]/N/S|_D|f-stop|f/\d+(?:\.\d+)?"),
    "product_name": re.compile(PRODUCTS),
}
PATH_ARITY = dict(zip("MmZzLlHhVvCcSsQqTtAa", (2, 2, 0, 0, 2, 2, 1, 1, 1, 1, 6, 6, 4, 4, 4, 4, 2, 2, 7, 7)))
PATH_TOKEN = re.compile(r"[MmZzLlHhVvCcSsQqTtAa]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


class IncompleteTranslation(ValueError):
    """No partial elements are returned; .report contains safe diagnostic counts."""

    def __init__(self, report: dict):
        self.report = report
        super().__init__(f"Incomplete translation: {report['unresolved']} unresolved resources; "
                         + ", ".join(report["reasons"]))


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
            .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))


def _reference(item: ET.Element) -> bool:
    return not len(item) and bool(re.fullmatch(r"(?:[@?](?:[\w.]+:)?[\w]+/[\w.]+|@null|@empty)", (item.text or "").strip()))


def _path_data(text: str) -> bool:
    matches = list(PATH_TOKEN.finditer(text))
    if not matches or matches[0].group() not in ("M", "m"):
        return False
    cursor, tokens = 0, []
    for match in matches:
        if text[cursor:match.start()].strip(" ,\t\r\n"):
            return False
        tokens.append(match.group())
        cursor = match.end()
    if text[cursor:].strip(" ,\t\r\n"):
        return False
    index = 0
    while index < len(tokens):
        arity = PATH_ARITY.get(tokens[index])
        index += 1
        start = index
        while index < len(tokens) and tokens[index] not in PATH_ARITY:
            index += 1
        count = index - start
        if arity is None or (count != 0 if arity == 0 else count == 0 or count % arity != 0):
            return False
    return True


def _technical_literal(text: str, name: str) -> str | None:
    for reason, pattern in TECH_LITERALS.items():
        if pattern.fullmatch(text):
            return reason
    if _path_data(text):
        return "path_data"
    if "country_code" in name and re.fullmatch(r"\d{1,3},[A-Z]{2}", text):
        return "country_code"
    template = tc.FORMAT.sub("0", text)
    if re.fullmatch(r"(?:\d+(?:\.\d+)?-)?\d+(?:\.\d+)?[xX]", template):
        return "rate_label"
    if "version" in name and re.fullmatch(r"(?:DJI Fly )?v\d+(?:\.\d+)*(?:\(\d+\))?", template):
        return "version_template"
    context = r"flight_(?:cine|normal|sport)_mode|_(?:distance|height)(?:_logogram|$)|_text_size_[lms]$|tracking_direction_setting_|double_control_.*_list_b$"
    if re.search(context, name) and re.fullmatch(r"[ACNSBDHLMFR](?: \d+(?:\.\d+)?)?", template):
        return "instrument_label"
    return None


def _technical_reason(item: ET.Element, name: str = "") -> str | None:
    name = name or item.get("name", "")
    raw = "".join(item.itertext()).strip()
    credential_label = raw.casefold() in {"password", "secret", "token", "api key", "client secret", "access token"}
    if _reference(item):
        return "resource_reference"
    if TECH_NAME.search(name) and not credential_label:
        return "credential"
    try:
        if isinstance(json.loads(raw), (dict, list, bool, int, float)) or raw == "null":
            return "json_value"
    except (ValueError, RecursionError):
        pass
    text = tc._content(item)[0].strip()
    try:
        if isinstance(json.loads(text), (dict, list)):
            return "json_value"
    except (ValueError, RecursionError):
        pass
    if not text or re.fullmatch(r"[\W\d_]+", text):
        return "numeric_or_symbols"
    literal = _technical_literal(text, name)
    if literal:
        return literal
    if name.endswith("_path_data") or name.startswith("path_"):
        return None
    if re.fullmatch(r"(?:[a-z][a-z0-9]*_)+[a-z0-9]+", text):
        return "identifier"
    if re.fullmatch(UNITS, text):
        return "unit"
    if MODEL_ID.fullmatch(text):
        return "model_id"
    # ASCII prose, title case and upper-case sentences are NOT technical by default.
    remainder = text
    for start, end in reversed(_protected(text, item.get("formatted") != "false")):
        remainder = remainder[:start] + remainder[end:]
    return "protected_only" if not any(char.isalpha() for char in remainder) else None


def _technical(item: ET.Element, name: str = "") -> bool:
    return _technical_reason(item, name) is not None


def _literal_offsets(text: str, formatted: bool) -> set[int]:
    result: set[int] = set()
    previous_end = -1
    for match in re.finditer("%", text):
        index = match.start()
        if index < previous_end:
            continue
        spec = tc.FORMAT.match(text, index)
        # In "100% full" Java's permissive regex reads "% f" as a float.
        # A digit/argument immediately before a single percent is literal.
        numeric = index > 0 and (text[index - 1].isdigit() or previous_end == index)
        literal_context = not spec or index + 1 == len(text) or text[index + 1].isspace()
        if not formatted or (numeric and literal_context and not text.startswith("%%", index)) or not spec:
            result.add(index)
        if spec and index not in result:
            previous_end = spec.end()
    return result


def _format_tokens(text: str, formatted: bool) -> list[tuple[int, int]]:
    literals = _literal_offsets(text, formatted)
    cursor = 0
    result = []
    while (offset := text.find("%", cursor)) >= 0:
        match = tc.FORMAT.match(text, offset)
        # formatted=false still shields syntactic tokens, without Formatter validation.
        usable = match and (offset not in literals or (not formatted and " " not in match.group()))
        cursor = match.end() if usable else offset + 1
        result.append((offset, cursor))
    return result


def _protected(text: str, formatted: bool) -> list[tuple[int, int]]:
    ranges = _format_tokens(text, formatted)
    # A unit is contextual: "drone's" and "License(s)" contain no seconds.
    # Keep this separate from the format range so reviewed %s -> %1$s reuse works.
    units = []
    for start, end in ranges:
        if tc.FORMAT.fullmatch(text[start:end]) and text[end - 1] not in "%n":
            match = FORMAT_UNIT.match(text, end)
            if match:
                units.append(match.span(1))
    ranges += units
    ranges += [(m.start(), m.end()) for regex in (LEXICAL, ASSIGNMENT) for m in regex.finditer(text)
               if regex is not ASSIGNMENT or not (tc.FORMAT.fullmatch(m.group("value"))
                                                  and m.group("value")[-1] not in "%n")]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _contract(item: ET.Element, formatted: bool) -> tuple:
    if _reference(item):
        return (item.text,)
    text, spans = tc._content(item)
    positions = _literal_offsets(text, formatted)
    neutral = "".join("\ue001" if i in positions else c for i, c in enumerate(text))
    tokens = tc._formats(neutral)
    markup = Counter((path, tuple(sorted(Counter((arg, spec) for left, right, arg, spec in tokens
                      if start <= left and right <= end).items())),
                      text[start:end] if path[-1][0] == tc.XLIFF else "") for path, start, end in spans)
    return Counter((arg, spec) for _, _, arg, spec in tokens), markup


def _guard_numeric_comparator(before: str, after: str) -> None:
    """Catch known direction inversions only; this is not semantic verification.

    Skip negations or mixed directions in either text instead of inferring scope.
    Normalize only this comparison view; original resource tokens stay untouched.
    """
    def comparison_text(text):
        text = unicodedata.normalize("NFKC", text).casefold()
        text = re.sub(r"(?:https?://|mailto:|ftp://)\S+", " ", text)
        for start, end in reversed(_format_tokens(text, True)):
            if tc.FORMAT.fullmatch(text[start:end]) and text[end - 1] not in "%n":
                text = text[:start] + " 0 " + text[end:]
        return text
    source, target = comparison_text(before), comparison_text(after)
    if not re.search(r"(?<![a-z0-9_])\d", source):
        return
    if COMPARATOR_NEGATION.search(source) or COMPARATOR_NEGATION.search(target):
        return
    def directions(text):
        return {index for index, pattern in enumerate((COMPARATOR_UP, COMPARATOR_DOWN)) if pattern.search(text)}
    original, translated = directions(source), directions(target)
    if len(original) == len(translated) == 1 and original != translated:
        raise ValueError("numeric_comparator_inverted")


def _validate(source: ET.Element, translated: ET.Element, strict: bool = False, allow_unchanged: bool = False) -> None:
    formatted = source.get("formatted") != "false"
    before_parts, after_parts = tc._parts(source), tc._parts(translated)
    if ((source.tag, source.get("name")) != (translated.tag, translated.get("name"))
            or [k for k, _ in before_parts] != [k for k, _ in after_parts]):
        raise ValueError("identity_or_collection_shape_changed")
    for (_, original), (_, candidate) in zip(before_parts, after_parts):
        if _contract(original, formatted) != _contract(candidate, formatted):
            raise ValueError("format_or_markup_changed")
        if _reference(original) or _technical(original, source.get("name", "")):
            if ET.tostring(original) != ET.tostring(candidate):
                raise ValueError("preserved_item_changed")
            continue
        before, after = tc._content(original)[0], tc._content(candidate)[0]
        if not after.strip() or not any(c.isalpha() for c in after):
            raise ValueError("empty_translation")
        if before == after and not allow_unchanged:
            raise ValueError("unchanged_human_text")
        _guard_numeric_comparator(before, after)
        def tokens(text):
            formats = set(_format_tokens(text, formatted)) if not strict and formatted else set()
            return Counter(text[a:b] for a, b in _protected(text, formatted) if (a, b) not in formats)
        expected, observed = tokens(before), tokens(after)
        # Lowercase protocol spellings are shielded only beside Han in the
        # source, but must still match exactly after translation to Latin text.
        for token in expected:
            if token.islower() and re.fullmatch(PROTOCOLS, token, re.I):
                observed[token] = len(re.findall(r"(?<![A-Za-z0-9_])" + re.escape(token)
                                                + r"(?![A-Za-z0-9_])", after))
        if expected != observed:
            raise ValueError("protected_tokens_changed")
        if len(_literal_offsets(before, formatted)) != len(_literal_offsets(after, formatted)):
            raise ValueError("literal_percent_changed")


def _memory(catalogs: list[dict]) -> tuple[dict, dict, int]:
    exact, shared = defaultdict(list), defaultdict(list)
    size = count = 0
    for catalog in catalogs:
        if not isinstance(catalog, dict) or type(catalog.get("schema")) is not int or catalog["schema"] != 1:
            raise ValueError("Unsupported catalog schema")
        entries = catalog.get("entries")
        if not isinstance(entries, list):
            raise ValueError("Invalid catalog entries")
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or len(entry[k]) > tc.MAX_ENTRY_CHARS
                                                 for k in ("kind", "name", "source", "translation_xml")):
                raise ValueError("Invalid catalog entry/limit")
            kind, name, source = entry["kind"], entry["name"], entry["source"]
            if kind not in tc.KINDS or not tc.NAME.fullmatch(name) or (kind, name) in seen:
                raise ValueError("Invalid or duplicate catalog identity")
            seen.add((kind, name))
            count += 1
            size += len(source) + len(entry["translation_xml"])
            if count > tc.MAX_ENTRIES or size > tc.MAX_TOTAL_BYTES:
                raise ValueError("Catalog aggregate limit exceeded")
            exact[kind, name, source].append(entry)
            shared[kind, source].append(entry)
    return exact, shared, count


def _reuse(source: ET.Element, entries: list[dict]) -> ET.Element | None:
    candidates = {}
    for entry in entries:
        try:
            candidate = tc._xml(entry["translation_xml"].encode("utf-8"))
            if (candidate.tag, candidate.get("name")) != (entry["kind"], entry["name"]):
                continue
            candidate.attrib = dict(source.attrib)
            candidate.tail = source.tail
            _validate(source, candidate, allow_unchanged=True)
            candidates[tc._canonical(candidate)] = candidate
        except (ValueError, UnicodeError):
            continue
    return next(iter(candidates.values())) if len(candidates) == 1 else None


@dataclass
class _Token:
    kind: str
    value: str | ET.Element


@dataclass
class _Sentence:
    item: ET.Element
    pieces: list[str | _Token]
    formatted: bool
    rendered: str = ""
    tokens: list[_Token] = field(default_factory=list)
    output: ET.Element | None = None

    def __post_init__(self):
        pieces = []
        for part in self.pieces:
            if isinstance(part, _Token):
                pieces.append(f"__RC2VI_{len(self.tokens):04d}__")
                self.tokens.append(part)
            else:
                if "__RC2VI_" in part:
                    raise ValueError("reserved_marker_in_source")
                pieces.append(part)
        self.rendered = "".join(pieces)

    def restore(self, text: str) -> ET.Element:
        if MARKER.findall(text) != MARKER.findall(self.rendered):
            raise ValueError("marker_changed")
        source_marks = list(MARKER.finditer(self.rendered))
        def separate(match):
            index = int(match.group()[8:-2])
            token, original = self.tokens[index], source_marks[index]
            if token.kind != "text" or not re.fullmatch(
                    r"(?=.*[A-Za-z])[A-Za-z0-9_]+(?:[. -][A-Za-z0-9_]+)*", token.value):
                return match.group()
            def gap(source_char, translated_char):
                return bool(source_char and "\u4e00" <= source_char <= "\u9fff"
                            and unicodedata.name(translated_char, "").startswith("LATIN ")) if translated_char else False
            left = gap(self.rendered[max(0, original.start() - 1):original.start()],
                       text[max(0, match.start() - 1):match.start()])
            right = gap(self.rendered[original.end():original.end() + 1], text[match.end():match.end() + 1])
            return (" " if left else "") + match.group() + (" " if right else "")
        # Separate Latin translations only at original Han/ASCII word edges.
        # Adjacent markers and formatter/unit/operator bindings remain untouched.
        text = MARKER.sub(separate, text)
        result = ET.Element(self.item.tag, dict(self.item.attrib))
        result.tail = self.item.tail
        stack = [result]
        def append(value):
            node = stack[-1]
            if len(node):
                node[-1].tail = (node[-1].tail or "") + _escape(value)
            else:
                node.text = (node.text or "") + _escape(value)
        cursor = 0
        for match in MARKER.finditer(text):
            append(text[cursor:match.start()])
            token = self.tokens[int(match.group()[8:-2])]
            if token.kind == "text":
                append(token.value)
            elif token.kind == "open":
                node = ET.Element(token.value.tag, dict(token.value.attrib))
                stack[-1].append(node)
                stack.append(node)
            elif token.kind == "close":
                stack.pop()
            else:
                node = copy.deepcopy(token.value)
                node.tail = None
                stack[-1].append(node)
            cursor = match.end()
        append(text[cursor:])
        return result


def _sentence(item: ET.Element, formatted: bool) -> _Sentence:
    text, spans = tc._content(item)
    protected = _protected(text, formatted)
    positions = {}
    def postorder(node):
        for child in node:
            postorder(child)
        if node is not item:
            positions[id(node)] = spans[len(positions)][1:]
    postorder(item)
    pieces = []
    def plain(start, end):
        cursor = start
        for left, right in protected:
            if right <= start or left >= end:
                continue
            left, right = max(start, left), min(end, right)
            pieces.extend([text[cursor:left], _Token("text", text[left:right])])
            cursor = right
        pieces.append(text[cursor:end])
    def walk(node, start, end):
        cursor = start
        for child in node:
            left, right = positions[id(child)]
            plain(cursor, left)
            if child.tag == tc.XLIFF:
                # Preserve the full XLIFF subtree, including examples/IDs and text.
                pieces.append(_Token("opaque", child))
            else:
                pieces.append(_Token("open", child))
                walk(child, left, right)
                pieces.append(_Token("close", child))
            cursor = right
        plain(cursor, end)
    walk(item, 0, len(text))
    return _Sentence(item, pieces, formatted)


def _chunks(text: str) -> list[str]:
    result = []
    while len(text) > MAX_SENTENCE_CHARS:
        window = text[:MAX_SENTENCE_CHARS]
        boundaries = list(re.finditer(r"(?<=[.!?])\s+|\n+", window)) or list(re.finditer(r"\s+", window))
        end = boundaries[-1].end() if boundaries else MAX_SENTENCE_CHARS
        for marker in MARKER.finditer(text):
            if marker.start() < end < marker.end():
                end = marker.start() or marker.end()
                break
        result.append(text[:end])
        text = text[end:]
    return result + [text]


def _human(text: str) -> bool:
    return any(c.isalpha() for c in MARKER.sub("", text))


def _call(texts: list[str], translate: Callable[[list[str]], list[str]]) -> dict[str, str | None]:
    unique = list(dict.fromkeys(t.strip() for t in texts if _human(t)))
    if not unique:
        return {}
    try:
        result = translate(list(unique))
        if not isinstance(result, list) or len(result) != len(unique):
            return dict.fromkeys(unique)
        return {key: value if isinstance(value, str) and 0 < len(value) <= tc.MAX_ENTRY_CHARS else None
                for key, value in zip(unique, result)}
    except Exception:
        # Exception messages can contain worker input or credentials. Never echo them.
        return dict.fromkeys(unique)


def _translated(text: str, results: dict[str, str | None]) -> str:
    if not _human(text):
        return text
    output = results.get(text.strip())
    if not output or output.strip() == text.strip() or not _human(output):
        raise ValueError("engine_failed_or_unchanged")
    if MARKER.findall(output) != MARKER.findall(text) or "__RC2VI_" in MARKER.sub("", output):
        raise ValueError("marker_changed")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in output):
        raise ValueError("invalid_output_character")
    return text[:len(text) - len(text.lstrip())] + output.strip() + text[len(text.rstrip()):]


def _fragment_translated(text: str, results: dict[str, str | None]) -> str:
    output = _translated(text, results)
    if not _human(text):
        return text
    # Keep original callable/cache keys. Only restore edges after translation;
    # exclude protected syntax such as percent, references and path separators.
    edges = " \t\r\n.,;:!?…，。；：！？、()[]{}\"'“”‘’–—-"
    core = output.strip(edges)
    if not _human(core) or core == text.strip(edges):
        raise ValueError("engine_failed_or_unchanged")
    return text[:len(text) - len(text.lstrip(edges))] + core + text[len(text.rstrip(edges)):]


def _check_sentence(sentence: _Sentence, output: ET.Element, allow_unchanged: bool = False) -> None:
    original = ET.Element("string", {"name": "check", "formatted": str(sentence.formatted).lower()})
    candidate = copy.deepcopy(original)
    for node, part in ((original, sentence.item), (candidate, output)):
        node.text = part.text
        node.extend(copy.deepcopy(list(part)))
    _validate(original, candidate, strict=True, allow_unchanged=allow_unchanged)


def _approved(sentence: _Sentence, overrides: dict[str, str]) -> ET.Element | None:
    text, spans = tc._content(sentence.item)
    if not spans and text in overrides:
        output = copy.deepcopy(sentence.item)
        output.text = _escape(overrides[text])
        _check_sentence(sentence, output, allow_unchanged=True)
        return output
    return None


def _run(sentences: list[_Sentence], translate: Callable[[list[str]], list[str]]) -> None:
    chunks = [[chunk for chunk in _chunks(s.rendered)] for s in sentences]
    primary = _call([chunk for group in chunks for chunk in group], translate)
    fallback = []
    for sentence, group in zip(sentences, chunks):
        try:
            output = sentence.restore("".join(_translated(t, primary) for t in group))
            _check_sentence(sentence, output)
            sentence.output = output
        except (ValueError, UnicodeError):
            fallback.append(sentence)
    fragments = [chunk for s in fallback for p in s.pieces if isinstance(p, str) for chunk in _chunks(p)]
    secondary = _call(fragments, translate)
    for sentence in fallback:
        try:
            parts, index = [], 0
            for piece in sentence.pieces:
                if isinstance(piece, _Token):
                    parts.append(f"__RC2VI_{index:04d}__")
                    index += 1
                else:
                    parts.append("".join(_fragment_translated(t, secondary) for t in _chunks(piece)))
            output = sentence.restore("".join(parts))
            _check_sentence(sentence, output)
            sentence.output = output
        except (ValueError, UnicodeError):
            pass


def _base_report() -> dict:
    return dict(matched=0, skipped=0, total=0, target_total=0, target_untranslated=0,
                catalog_total=0, complete=False, eligible_total=0, reviewed=0, machine=0,
                preserved=0, unresolved=0, reasons={}, preserved_reasons={}, unresolved_resources=[],
                machine_meaning_verified=False, readback_samples=[])


def _supported_source(text: str, allow_chinese: bool) -> bool:
    """Permit Latin text and opt-in basic Han; do not silently enable other scripts."""
    return all(not char.isalpha() or unicodedata.name(char, "").startswith("LATIN ")
               or (allow_chinese and "\u4e00" <= char <= "\u9fff") for char in text)


def compose_complete(target_res_dir: Path, catalogs: list[dict],
                     translate: Callable[[list[str]], list[str]],
                     overrides: dict[str, str] | None = None, *,
                     allow_chinese: bool = False) -> tuple[list[ET.Element], dict]:
    """Compose every eligible target resource or raise IncompleteTranslation(report).

    Overrides map exact decoded English item text to approved Vietnamese text.
    Output elements are fresh and omit wholly technical resources. Reports count
    mixed collections once (machine if any item needed the engine). The caller
    must still compile/sign/read back the RRO; readback_samples are only candidates.
    Set allow_chinese=True only with a callable that also translates Han to Vietnamese.
    """
    if type(allow_chinese) is not bool:
        raise ValueError("allow_chinese must be a boolean")
    report = _base_report()
    try:
        targets = tc.load_resources(Path(target_res_dir))
    except (ValueError, OSError, UnicodeError):
        report["reasons"] = {"target_read_failed": 1}
        raise IncompleteTranslation(report) from None
    report["total"] = report["target_total"] = len(targets)
    exact, shared, report["catalog_total"] = _memory(catalogs)
    overrides = overrides or {}
    if not isinstance(overrides, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in overrides.items()):
        raise ValueError("Overrides must map text to text")
    selected, pending, sentences = {}, {}, []
    def unresolved(key, reason):
        report["unresolved_resources"].append({"kind": key[0], "name": key[1], "reason": reason})
        report["reasons"][reason] = report["reasons"].get(reason, 0) + 1
    for key, source in sorted(targets.items()):
        try:
            parts = tc._parts(source)
            technical = ["nontranslatable"] if source.get("translatable") == "false" else [
                _technical_reason(p, key[1]) for _, p in parts]
            if all(technical):
                report["preserved"] += 1
                reason = technical[0] if technical and len(set(technical)) == 1 else "technical_collection"
                report["preserved_reasons"][reason] = report["preserved_reasons"].get(reason, 0) + 1
                continue
            report["eligible_total"] += 1
            try:
                canonical = tc._canonical(source)
            except ValueError:
                canonical = None  # Mixed reference collections are composed item by item.
            candidate = _reuse(source, exact.get((*key, canonical), []))
            if candidate is None:
                candidate = _reuse(source, shared.get((key[0], canonical), []))
            if candidate is not None:
                selected[key] = candidate
                report["reviewed"] += 1
                continue
            jobs = []
            for part_key, part in parts:
                if _technical(part, key[1]):
                    continue
                sentence = _sentence(part, source.get("formatted") != "false")
                try:
                    sentence.output = _approved(sentence, overrides)
                except (ValueError, UnicodeError):
                    sentence.output = None
                jobs.append((part_key, sentence))
            if any(s.output is None and not _supported_source(s.rendered, allow_chinese)
                   for _, s in jobs):
                unresolved(key, "unsupported_source_language")
                continue
            pending[key] = (source, jobs, any(s.output is None for _, s in jobs))
            sentences.extend(s for _, s in jobs if s.output is None)
        except (ValueError, UnicodeError):
            unresolved(key, "unsafe_source_contract")
    _run(sentences, translate)
    for key, (source, jobs, machine) in pending.items():
        if any(s.output is None for _, s in jobs):
            unresolved(key, "translation_failed_contract_or_engine")
            continue
        result = copy.deepcopy(source)
        replacements = {part_key: s.output for part_key, s in jobs}
        if source.tag == "string":
            result = replacements[""]
        else:
            for index, item in enumerate(list(result)):
                part_key = item.get("quantity") if source.tag == "plurals" else str(index)
                if part_key in replacements:
                    result[index] = replacements[part_key]
        try:
            _validate(source, result, strict=True, allow_unchanged=True)
            tc._xml(ET.tostring(result, encoding="utf-8"))
            selected[key] = result
            report["machine" if machine else "reviewed"] += 1
        except (ValueError, UnicodeError):
            unresolved(key, "composition_contract_failed")
    report["unresolved"] = len(report["unresolved_resources"])
    report["eligible_total"] = report["total"] - report["preserved"]
    report["matched"] = report["reviewed"] + report["machine"]
    report["skipped"] = report["preserved"]
    report["target_untranslated"] = report["unresolved"]
    elements = [selected[key] for key in sorted(selected)]
    report["readback_samples"] = [{"name": e.get("name"), "value": e.text} for e in elements
        if e.tag == "string" and not len(e) and e.text and e.text == e.text.strip()
        and not any(c in e.text for c in '\\%\n\r\t"\'@?')][:3]
    if not targets:
        report["reasons"]["empty_target"] = 1
    if not report["readback_samples"]:
        report["reasons"]["no_readback_sample"] = 1
    report["complete"] = bool(targets) and not report["reasons"] and report["matched"] == report["eligible_total"]
    if not report["complete"]:
        raise IncompleteTranslation(report)
    return elements, report
