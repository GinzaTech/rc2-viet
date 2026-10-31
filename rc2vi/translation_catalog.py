"""Pure, exact-source translation reuse; no APK version, build, or device access.

Schema 1 entries contain kind, name, source (canonical JSON text), translation_xml.
Both catalog creation and selection report integer matched/skipped/total counts
and reason counts. Unsafe individual resources are skipped; malformed XML,
duplicate identities and invalid catalog envelopes raise ValueError. Selection also
reports target_total, target_untranslated and catalog_total (no whole-version claim).
Only values, values-en, values-en-rUS are merged, in that precedence order.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from collections.abc import Mapping
import copy
import json
from pathlib import Path
import re
from typing import TypedDict
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_XML_DEPTH = 32
MAX_XML_NODES = 100_000
MAX_FILES = 512
MAX_ENTRIES = 100_000
MAX_ENTRY_CHARS = 256 * 1024
KINDS = {"string", "string-array", "plurals"}
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\Z")
XLIFF = "{urn:oasis:names:tc:xliff:document:1.2}g"
META = {"formatted", "styled", "translatable"}
MARKUP = {tag: set() for tag in "b i u s strike del em cite dfn big small tt sup sub li ul br p div marquee".split()}
MARKUP.update({"font": {"color", "face", "size"}, "a": {"href"}, XLIFF: {"id", "example", "equiv-text"}})
FORMAT = re.compile(r"%(?:(\d+)\$)?([-#+ 0,(<]*+)(\d*+)(\.\d+)?([tT][HIklMSLNpzZsQBbhAaCYyjmdeRTrDFc]|[bBhHsScCdoxXeEfgGaAn%])")
MarkupPath = tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
Span = tuple[MarkupPath, int, int]


class Entry(TypedDict):
    kind: str
    name: str
    source: str
    translation_xml: str


class Report(TypedDict):
    matched: int
    skipped: int
    total: int
    reasons: dict[str, int]


class Catalog(TypedDict):
    schema: int
    entries: list[Entry]
    report: Report


class SelectionReport(Report):
    target_total: int
    target_untranslated: int
    catalog_total: int


class _BoundedBuilder(ET.TreeBuilder):
    def __init__(self) -> None:
        super().__init__()
        self.depth = self.nodes = 0

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        self.depth += 1
        self.nodes += 1
        if self.depth > MAX_XML_DEPTH or self.nodes > MAX_XML_NODES:
            raise ValueError("XML depth/node limit exceeded")
        return super().start(tag, attrs)

    def end(self, tag: str) -> ET.Element:
        self.depth -= 1
        return super().end(tag)

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise ValueError("DTD/entities are forbidden")

    def pi(self, target: str, text: str | None = None) -> None:
        raise ValueError("Processing instructions are forbidden")


def _xml(raw: bytes) -> ET.Element:
    if len(raw) > MAX_XML_BYTES:
        raise ValueError("XML byte limit exceeded")
    try:
        return ET.fromstring(raw, parser=ET.XMLParser(target=_BoundedBuilder()))
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML: {exc}") from exc


def load_resources(res_dir: Path) -> dict[tuple[str, str], ET.Element]:
    """Merge supported resource types with explicit English preferred; never resolve refs."""
    if not res_dir.is_dir():
        raise ValueError(f"Resource directory does not exist: {res_dir}")
    result: dict[tuple[str, str], ET.Element] = {}
    size = count = 0
    for config in ("values", "values-en", "values-en-rUS"):
        current: dict[tuple[str, str], ET.Element] = {}
        for path in sorted((res_dir / config).glob("*.xml")):
            count += 1
            if count > MAX_FILES:
                raise ValueError("Resource file limit exceeded")
            with path.open("rb") as stream:
                raw = stream.read(MAX_XML_BYTES + 1)
            size += len(raw)
            if size > MAX_TOTAL_BYTES:
                raise ValueError("Total resource byte limit exceeded")
            root = _xml(raw)
            if root.tag != "resources":
                raise ValueError(f"Expected resources root: {path}")
            for element in root:
                if element.tag not in KINDS:
                    continue
                name = element.get("name", "")
                if not NAME.fullmatch(name):
                    raise ValueError(f"Invalid resource name: {path}")
                key = element.tag, name
                if key in current:
                    raise ValueError(f"Duplicate resource {key} in {config}")
                current[key] = element
        result.update(current)
        if len(result) > MAX_ENTRIES:
            raise ValueError("Resource count limit exceeded")
    return result


def _attrs(element: ET.Element, allowed: set[str]) -> None:
    if set(element.attrib) - allowed:
        raise ValueError("Unsupported attributes")
    if any(element.get(key) not in (None, "true", "false") for key in META):
        raise ValueError("Invalid resource metadata")


def _parts(element: ET.Element) -> list[tuple[str, ET.Element]]:
    if element.tag not in KINDS or not NAME.fullmatch(element.get("name", "")):
        raise ValueError("Unsupported resource identity")
    _attrs(element, META | {"name"})
    if element.tag == "string":
        return [("", element)]
    if (element.text or "").strip():
        raise ValueError("Unexpected collection text")
    parts: dict[str, ET.Element] = {}
    for index, item in enumerate(element):
        plural = element.tag == "plurals"
        key = item.get("quantity", "") if plural else str(index)
        _attrs(item, {"quantity"} if plural else set())
        if item.tag != "item" or (item.tail or "").strip() or key in parts:
            raise ValueError("Invalid collection item")
        if plural and key not in {"zero", "one", "two", "few", "many", "other"}:
            raise ValueError("Invalid plural quantity")
        parts[key] = item
    if element.tag == "plurals" and "other" not in parts:
        raise ValueError("Plural requires other")
    return sorted(parts.items()) if element.tag == "plurals" else list(parts.items())


def _content(element: ET.Element) -> tuple[str, list[Span]]:
    """Decode Android quoting/escapes once, carrying whitespace state across markup."""
    if "".join(element.itertext()).lstrip().startswith(("@", "?")):
        raise ValueError("Unresolved reference")
    chars: list[str] = []
    spans: list[Span] = []
    quoted = space = False

    def text(raw: str) -> None:
        nonlocal quoted, space
        index = 0
        while index < len(raw):
            char = raw[index]
            index += 1
            if char == "\\":
                if index == len(raw):
                    raise ValueError("Incomplete Android escape")
                char = raw[index]
                index += 1
                if char == "u":
                    digits = raw[index:index + 4]
                    if not re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                        raise ValueError("Invalid Unicode escape")
                    char = chr(int(digits, 16))
                    index += 4
                    if 0xD800 <= ord(char) <= 0xDBFF:
                        low = raw[index:index + 6]
                        if not re.fullmatch(r"\\u[dD][c-fC-F][0-9a-fA-F]{2}", low):
                            raise ValueError("Unpaired Unicode surrogate")
                        char = chr(0x10000 + ((ord(char) - 0xD800) << 10) + int(low[2:], 16) - 0xDC00)
                        index += 6
                    elif 0xDC00 <= ord(char) <= 0xDFFF:
                        raise ValueError("Unpaired Unicode surrogate")
                else:
                    char = {"n": "\n", "t": "\t", "r": "\r"}.get(char, char)
                chars.append(char)
                space = False
            elif char == '"':
                quoted = not quoted
            elif char.isspace() and not quoted:
                if not space:
                    chars.append(" ")
                space = True
            else:
                chars.append(char)
                space = False

    def walk(node: ET.Element, ancestors: MarkupPath = ()) -> None:
        text(node.text or "")
        for child in node:
            if child.tag not in MARKUP:
                raise ValueError("Unsupported markup")
            _attrs(child, MARKUP[child.tag])
            if any(v.lstrip().startswith(("@", "?")) for v in child.attrib.values()):
                raise ValueError("Unresolved markup reference")
            if child.tag == XLIFF and not child.get("id"):
                raise ValueError("XLIFF requires id")
            if child.tag == "a" and not re.fullmatch(r"(?:https?://|mailto:)[^\s]+", child.get("href", "")):
                raise ValueError("Unsupported link")
            attrs = tuple(sorted((k, v) for k, v in child.attrib.items()
                                 if child.tag != XLIFF or k == "id"))
            path = ancestors + ((child.tag, attrs),)
            start = len(chars)
            walk(child, path)
            spans.append((path, start, len(chars)))
            text(child.tail or "")

    walk(element)
    if quoted:
        raise ValueError("Unclosed Android quote")
    return "".join(chars), spans


def _formats(text: str) -> list[tuple[int, int, int, str]]:
    """Java ordinary, explicit and relative argument indexing, including format flags."""
    result: list[tuple[int, int, int, str]] = []
    ordinary = previous = cursor = 0
    while (offset := text.find("%", cursor)) >= 0:
        match = FORMAT.match(text, offset)
        cursor = match.end() if match else offset + 1
        argument, spec = 0, "%literal"
        if match:
            explicit, flags, width, precision, conversion = match.groups()
            if conversion not in ("%", "n"):
                if "<" in flags:
                    if explicit or not previous:
                        raise ValueError("Invalid relative placeholder")
                    argument = previous
                elif explicit:
                    argument = int(explicit)
                else:
                    ordinary += 1
                    argument = ordinary
                if argument < 1:
                    raise ValueError("Invalid placeholder argument")
                previous = argument
            elif explicit or "<" in flags:
                raise ValueError("Invalid non-argument placeholder")
            spec = flags.replace("<", "") + width + (precision or "") + conversion
        result.append((offset, cursor, argument, spec))
    return result


def _canonical(element: ET.Element) -> str:
    return json.dumps([(key, _content(item)) for key, item in _parts(element)], ensure_ascii=True, separators=(",", ":"))


def _compatible(source: ET.Element, translation: ET.Element) -> None:
    if (source.tag, source.get("name")) != (translation.tag, translation.get("name")):
        raise ValueError("Translation identity differs")
    before, after = _parts(source), _parts(translation)
    if [key for key, _ in before] != [key for key, _ in after]:
        raise ValueError("Translation collection shape differs")
    for (_, original), (_, translated) in zip(before, after):
        def contract(item: ET.Element) -> tuple:
            text, spans = _content(item)
            tokens = _formats(text)
            offsets = [token[0] for token in tokens]
            markup = Counter((path, tuple(sorted(Counter((arg, spec) for _, stop, arg, spec in
                              tokens[bisect_left(offsets, start):bisect_left(offsets, end)] if stop <= end).items())),
                              text[start:end] if path[-1][0] == XLIFF else "")
                             for path, start, end in spans)
            return Counter((arg, spec) for _, _, arg, spec in tokens), markup
        if contract(original) != contract(translated):
            raise ValueError("Translation placeholders/markup differ")


def _report(matched: int, total: int, reasons: Counter[str]) -> Report:
    return {"matched": matched, "skipped": total - matched, "total": total, "reasons": dict(reasons)}


def make_catalog(source_res_dir: Path, translated_res_dir: Path) -> Catalog:
    """Build schema 1 from trusted source/translation pairs; exclude incompatible entries."""
    sources, translations = load_resources(source_res_dir), load_resources(translated_res_dir)
    entries: list[Entry] = []
    reasons: Counter[str] = Counter()
    for key, translation in sorted(translations.items()):
        if key not in sources:
            reasons["missing_source"] += 1
            continue
        try:
            _compatible(sources[key], translation)
            clone = copy.deepcopy(translation)
            clone.tail = None
            original, xml = _canonical(sources[key]), ET.tostring(clone, encoding="unicode")
            if max(len(original), len(xml)) > MAX_ENTRY_CHARS:
                raise ValueError("Catalog entry limit exceeded")
            entries.append({"kind": key[0], "name": key[1], "source": original, "translation_xml": xml})
        except ValueError:
            reasons["unsafe_or_incompatible"] += 1
    if sum(len(e["source"]) + len(e["translation_xml"]) for e in entries) > MAX_TOTAL_BYTES:
        raise ValueError("Total catalog character limit exceeded")
    return {"schema": 1, "entries": entries, "report": _report(len(entries), len(translations), reasons)}


def select_resources(catalog: Mapping[str, object], target_res_dir: Path) -> tuple[list[ET.Element], SelectionReport]:
    """Return fresh elements; total/skipped/reasons are catalog-relative, target_* are not."""
    if not isinstance(catalog, dict) or type(catalog.get("schema")) is not int or catalog["schema"] != 1:
        raise ValueError("Unsupported catalog schema")
    entries = catalog.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ValueError("Invalid catalog entries/limit")
    targets = load_resources(target_res_dir)
    selected: list[ET.Element] = []
    seen: set[tuple[str, str]] = set()
    reasons: Counter[str] = Counter()
    size = 0
    for entry in entries:
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or len(entry[k]) > MAX_ENTRY_CHARS
                                              for k in ("kind", "name", "source", "translation_xml")):
            raise ValueError("Invalid catalog entry/limit")
        size += sum(len(entry[k]) for k in ("source", "translation_xml"))
        if size > MAX_TOTAL_BYTES:
            raise ValueError("Total catalog character limit exceeded")
        key = entry["kind"], entry["name"]
        if key[0] not in KINDS or not NAME.fullmatch(key[1]):
            raise ValueError("Invalid catalog identity")
        if key in seen:
            raise ValueError("Duplicate catalog identity")
        seen.add(key)
        if key not in targets:
            reasons["missing_or_changed_type"] += 1
            continue
        try:
            if _canonical(targets[key]) != entry["source"]:
                reasons["source_changed"] += 1
                continue
            translation = _xml(entry["translation_xml"].encode("utf-8"))
            _compatible(targets[key], translation)
            selected.append(translation)
        except (ValueError, UnicodeError):
            reasons["unsafe_or_incompatible"] += 1
    return selected, {**_report(len(selected), len(entries), reasons), "target_total": len(targets),
                      "target_untranslated": len(targets) - len(selected), "catalog_total": len(entries)}
