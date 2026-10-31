"""Host-only catalog contracts; every resource tree is synthetic."""
import copy
import json
from pathlib import Path

import pytest

from rc2vi import translation_catalog as catalog


def resources(root: Path, body: str, config: str = "values", file: str = "strings.xml") -> Path:
    directory = root / config
    directory.mkdir(parents=True, exist_ok=True)
    (directory / file).write_text(f"<resources>{body}</resources>", encoding="utf-8")
    return root


def select(tmp_path: Path, source: str, translation: str, target: str | None = None):
    original = resources(tmp_path / "source", source)
    translated = resources(tmp_path / "vi", translation)
    current = resources(tmp_path / "target", source if target is None else target)
    data = json.loads(json.dumps(catalog.make_catalog(original, translated)))
    return catalog.select_resources(data, current)


def string(text: str, attrs: str = "", name: str = "message") -> str:
    return f'<string name="{name}" {attrs}>{text}</string>'


def test_load_merges_all_xml_files_and_english_precedence(tmp_path):
    resources(tmp_path, string("Default") + string("Fallback", name="fallback"))
    resources(tmp_path, string("English"), "values-en")
    resources(tmp_path, string("US English"), "values-en-rUS")
    resources(tmp_path, string("Ignored French"), "values-fr")
    resources(tmp_path, string("Ignored night"), "values-night")
    resources(tmp_path, '<string-array name="list"><item>A</item></string-array>'
              '<color name="black">#000000</color>', file="arrays.xml")
    loaded = catalog.load_resources(tmp_path)
    assert set(loaded) == {("string", "message"), ("string", "fallback"), ("string-array", "list")}
    assert loaded[("string", "message")].text == "US English"
    assert loaded[("string", "fallback")].text == "Fallback"


@pytest.mark.parametrize("other_file", [False, True])
def test_duplicate_resource_in_configuration_fails(tmp_path, other_file):
    resources(tmp_path, string("A") if other_file else string("A") + string("B"))
    if other_file:
        resources(tmp_path, string("B"), file="other.xml")
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        catalog.load_resources(tmp_path)


def test_same_name_different_types_is_not_a_duplicate(tmp_path):
    resources(tmp_path, string("A") + '<plurals name="message"><item quantity="other">B</item></plurals>')
    assert len(catalog.load_resources(tmp_path)) == 2


def test_exact_meaning_type_and_name_required_and_counts_partition_catalog(tmp_path):
    source = string("Enable %1$s", name="changed") + string("Hello", name="ok")
    source += string("Old", name="removed") + string("Text", name="type")
    vi = string("Bật %1$s", name="changed") + string("Xin chào", name="ok")
    vi += string("Cũ", name="removed") + string("Chữ", name="type")
    target = string("Disable %1$s", name="changed") + string("Hello", name="ok")
    target += '<string-array name="type"><item>Text</item></string-array>'
    selected, report = select(tmp_path, source, vi, target)
    assert [(e.tag, e.get("name"), e.text) for e in selected] == [("string", "ok", "Xin chào")]
    assert {k: report[k] for k in ("matched", "skipped", "total")} == {"matched": 1, "skipped": 3, "total": 4}


@pytest.mark.parametrize("source,target", [
    ("Fish &amp; chips", "Fish &#38; chips"),
    (r"Don\'t fly", '"Don\'t fly"'),
    (r"Caf\u00e9", "Café"),
    ('"Hello world"', "Hello   world"),
    ("Hello\nworld", "Hello world"),
    (r'"Line\nnext"', '"Line\nnext"'),
    (r'Path C:\\fly', r'Path C:\u005cfly'),
    ("<![CDATA[Fish & chips]]>", "Fish &amp; chips"),
])
def test_equivalent_android_and_xml_decoding_matches(tmp_path, source, target):
    selected, report = select(tmp_path, string(source), string("Bản dịch"), string(target))
    assert len(selected) == report["matched"] == 1


@pytest.mark.parametrize("source,target", [
    (r"Line\nnext", "Line next"),
    ('"Hello  world"', "Hello world"),
    ("Hello!", "Hello?"),
    ("Hello", "hello"),
    ("<b>Fly</b> safely", "<b>Fly</b> dangerously"),
    ("<b>Fly</b>", "Fly"),
    (r'\"Hello\"', '"Hello"'),
])
def test_meaning_whitespace_and_style_changes_are_not_normalized_away(tmp_path, source, target):
    translated = "<b>Bay</b> an toàn" if "<b>" in source else "Bản dịch"
    selected, report = select(tmp_path, string(source), string(translated), string(target))
    assert selected == [] and report["skipped"] == report["total"] == 1


def test_harmless_attributes_do_not_block_reuse_or_disable_placeholder_checks(tmp_path):
    selected, _ = select(tmp_path, string("Hello %s", 'formatted="false" styled="true"'),
                         string("Chào %s", 'formatted="false"'),
                         string("Hello %s", 'translatable="true"'))
    assert len(selected) == 1


@pytest.mark.parametrize("source,translation,accepted", [
    ("Hello %s", "Chào %1$s", True),
    ("%1$s: %2$02d", "%2$02d: %1$s", True),
    ("%s: %d", "%2$d: %1$s", True),
    ("%s: %d", "%d: %s", False),
    ("Hello %s", "Chào %d", False),
    ("Hello %1$s", "Chào %2$s", False),
    ("Hello %s", "Chào", False),
    ("%1$s %1$s", "%1$s", False),
    ("%.2f", "%.1f", False),
    ("%02d", "%d", False),
    ("%1$tY-%1$tm", "%1$tm-%1$tY", True),
    ("%s %&lt;s", "%1$s %1$s", True),
    ("%2$s %s", "%2$s %1$s", True),
    ("%1$d%% done%n", "Đã xong %1$d%%%n", True),
    ("%d%%", "%d%", False),
    ("100%", "100%", True),
    ("%0$s", "%0$s", False),
    ("%&lt;s", "%&lt;s", False),
])
def test_placeholder_argument_binding_and_formatting(tmp_path, source, translation, accepted):
    selected, _ = select(tmp_path, string(source), string(translation))
    assert bool(selected) is accepted


def test_xliff_and_styled_text_preserve_structure_and_translation_xml(tmp_path):
    attrs = 'xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2"'
    source = '<b>Hello</b> <xliff:g id="user" example="Alice">%1$s</xliff:g>!'
    vi = '<b>Xin chào</b> <xliff:g id="user" example="An">%1$s</xliff:g>!'
    selected, _ = select(tmp_path, string(source, attrs), string(vi, attrs),
                         string(source.replace('example="Alice"', 'example="Bob"'), attrs))
    assert len(selected) == 1
    assert selected[0][0].tag == "b" and selected[0][0].text == "Xin chào"
    assert selected[0][1].tag == "{urn:oasis:names:tc:xliff:document:1.2}g"
    assert selected[0][1].tail == "!"


@pytest.mark.parametrize("translation", [
    '<b onclick="bad()">Chào</b> %s', '<script>bad()</script> %s',
    'Chào <img src="https://invalid.example"/> %s', '<i>Chào</i> %s',
    '<b>Chào %s</b>',
])
def test_unsupported_or_changed_translation_markup_is_excluded(tmp_path, translation):
    selected, _ = select(tmp_path, string("<b>Hello</b> %s"), string(translation))
    assert selected == []


@pytest.mark.parametrize("body", [
    '<string name="message">@string/other</string>',
    '<string name="message">?android:attr/text</string>',
    '<string name="message">@null</string>',
    '<string-array name="message"><item>@string/other</item></string-array>',
    '<plurals name="message"><item quantity="other">@string/other</item></plurals>',
])
def test_unresolved_source_and_translation_references_excluded(tmp_path, body):
    assert select(tmp_path, body, body)[0] == []


@pytest.mark.parametrize("literal", [r"\@string/other", r"\?attr/text", '"@string/other"', "Email a@b.example"])
def test_literal_reference_like_text_is_allowed(tmp_path, literal):
    assert len(select(tmp_path, string(literal), string(literal))[0]) == 1


def test_reference_target_is_skipped(tmp_path):
    selected, report = select(tmp_path, string("Hello"), string("Chào"), string("@string/other"))
    assert selected == [] and report["skipped"] == 1


def test_array_order_length_and_each_item_placeholder_are_checked(tmp_path):
    source = '<string-array name="list"><item>First %s</item><item>Second %d</item></string-array>'
    vi = '<string-array name="list"><item>Đầu %s</item><item>Sau %d</item></string-array>'
    assert len(select(tmp_path, source, vi)[0]) == 1
    swapped = '<string-array name="list"><item>Second %d</item><item>First %s</item></string-array>'
    assert select(tmp_path, source, vi, swapped)[0] == []
    assert select(tmp_path, source, vi.replace("Sau %d", "Sau %s"))[0] == []
    assert select(tmp_path, source, vi.replace("<item>Sau %d</item>", ""))[0] == []


def test_plural_order_is_irrelevant_but_keys_and_item_contents_are_not(tmp_path):
    source = '<plurals name="count"><item quantity="one">One %d</item><item quantity="other">Many %d</item></plurals>'
    vi = '<plurals name="count"><item quantity="other">Nhiều %d</item><item quantity="one">Một %d</item></plurals>'
    target = '<plurals name="count"><item quantity="other">Many %d</item><item quantity="one">One %d</item></plurals>'
    assert len(select(tmp_path, source, vi, target)[0]) == 1
    assert select(tmp_path, source, vi, target.replace("Many", "At least"))[0] == []
    assert select(tmp_path, source, vi.replace('quantity="one"', 'quantity="few"'))[0] == []
    assert select(tmp_path, source, vi.replace("Một %d", "Một %s"))[0] == []


@pytest.mark.parametrize("body", [
    '<plurals name="x"><item quantity="one">One</item></plurals>',
    '<plurals name="x"><item quantity="other">A</item><item quantity="other">B</item></plurals>',
    '<plurals name="x"><item quantity="invalid">A</item><item quantity="other">B</item></plurals>',
    '<string-array name="x"><string>Oops</string></string-array>',
    '<string-array name="x">Unexpected<item>A</item></string-array>',
    '<string-array name="x"><item>A</item>Unexpected</string-array>',
])
def test_invalid_collection_shapes_are_excluded(tmp_path, body):
    assert select(tmp_path, body, body)[0] == []


@pytest.mark.parametrize("xml", [
    '<!DOCTYPE resources [<!ENTITY x "boom">]><resources><string name="x">&x;</string></resources>',
    '<!DOCTYPE resources SYSTEM "file:///nonexistent"><resources/>',
    '<resources><string name="x">&unknown;</string></resources>',
    '<resources><string name="x"></resources>',
    '<wrong/>',
    '<?custom process?><resources/>',
])
def test_unsafe_or_malformed_xml_fails_closed(tmp_path, xml):
    resources(tmp_path, "")
    (tmp_path / "values" / "strings.xml").write_text(xml, encoding="utf-8")
    with pytest.raises(ValueError):
        catalog.load_resources(tmp_path)


def test_utf16_doctype_cannot_bypass_parser(tmp_path):
    resources(tmp_path, "")
    xml = '<!DOCTYPE resources [<!ENTITY x "boom">]><resources><string name="x">&x;</string></resources>'
    (tmp_path / "values" / "strings.xml").write_bytes(xml.encode("utf-16"))
    with pytest.raises(ValueError):
        catalog.load_resources(tmp_path)


@pytest.mark.parametrize("limit,value,body", [
    ("MAX_XML_BYTES", 20, string("Hello")),
    ("MAX_XML_DEPTH", 3, string("<b><b><b>Deep</b></b></b>")),
    ("MAX_XML_NODES", 2, string("A") + string("B", name="b")),
    ("MAX_TOTAL_BYTES", 20, string("Hello")),
    ("MAX_FILES", 0, string("Hello")),
])
def test_xml_limits_are_enforced(tmp_path, monkeypatch, limit, value, body):
    resources(tmp_path, body)
    monkeypatch.setattr(catalog, limit, value)
    with pytest.raises(ValueError, match="[Ll]imit"):
        catalog.load_resources(tmp_path)


def test_json_roundtrip_determinism_and_fresh_results(tmp_path):
    source = resources(tmp_path / "source", string("Hello %s"))
    translated = resources(tmp_path / "vi", string("Chào %s"))
    data = catalog.make_catalog(source, translated)
    assert data["schema"] == 1 and isinstance(data["entries"], list)
    assert data == catalog.make_catalog(source, translated)
    snapshot = copy.deepcopy(data)
    selected, report = catalog.select_resources(json.loads(json.dumps(data)), source)
    selected[0].text = "mutated"
    assert catalog.select_resources(data, source)[0][0].text == "Chào %s"
    assert data == snapshot and report["total"] == 1


@pytest.mark.parametrize("translation", [
    '<string name="other">Chào %s</string>', '<string name="message">Chào %d</string>',
    '<string name="message">@string/other</string>', '<string name="message"><script>Bad</script> %s</string>',
    '<!DOCTYPE string [<!ENTITY x "boom">]><string name="message">&x; %s</string>',
])
def test_catalog_translations_are_revalidated_at_selection(tmp_path, translation):
    source = resources(tmp_path / "source", string("Hello %s"))
    data = catalog.make_catalog(source, resources(tmp_path / "vi", string("Chào %s")))
    data["entries"][0]["translation_xml"] = translation
    selected, report = catalog.select_resources(data, source)
    assert selected == [] and report["skipped"] == report["total"] == 1


@pytest.mark.parametrize("data", [{}, {"schema": 2, "entries": []}, {"schema": True, "entries": []},
                                  {"schema": 1, "entries": "wrong"}, {"schema": 1, "entries": [{}]}])
def test_malformed_catalog_is_rejected(tmp_path, data):
    with pytest.raises(ValueError):
        catalog.select_resources(data, resources(tmp_path, ""))


def test_duplicate_catalog_identity_is_rejected(tmp_path):
    source = resources(tmp_path / "source", string("Hello"))
    data = catalog.make_catalog(source, resources(tmp_path / "vi", string("Chào")))
    data["entries"].append(copy.deepcopy(data["entries"][0]))
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        catalog.select_resources(data, source)


def test_absent_source_is_not_catalogued_and_empty_selection_is_valid(tmp_path):
    source = resources(tmp_path / "source", "")
    data = catalog.make_catalog(source, resources(tmp_path / "vi", string("Chào")))
    assert data["entries"] == []
    selected, report = catalog.select_resources(data, source)
    assert selected == [] and all(report[k] == 0 for k in ("matched", "skipped", "total"))


def test_missing_directory_fails_instead_of_silently_producing_empty_catalog(tmp_path):
    with pytest.raises(ValueError):
        catalog.load_resources(tmp_path / "missing")


def test_report_distinguishes_catalog_matches_from_target_coverage(tmp_path):
    selected, report = select(tmp_path, string("Old", name="old") + string("Hello"),
                              string("Cũ", name="old") + string("Chào"),
                              string("Hello") + string("New", name="new") + string("Newer", name="newer"))
    assert len(selected) == report["matched"] == 1
    assert report["catalog_total"] == report["total"] == 2
    assert report["target_total"] == 3 and report["target_untranslated"] == 2
    assert sum(report["reasons"].values()) == report["skipped"] == 1


@pytest.mark.parametrize("source,target", [
    (r"Fly \uD83D\uDE80", "Fly 🚀"),
    (r"<b>\uD83D\uDE80</b> launch", "<b>🚀</b> launch"),
])
def test_utf16_surrogate_escapes_equal_decoded_codepoints(tmp_path, source, target):
    vi = "<b>🚀</b> bay" if "<b>" in source else "Bay 🚀"
    assert len(select(tmp_path, string(source), string(vi), string(target))[0]) == 1


@pytest.mark.parametrize("body", [
    string("Hello", 'formatted="invalid"'), string("Hello", 'product="tablet"'),
    string("trailing\\"), string(r"bad \u00zz"), string('"Unclosed'),
    string(r"bad \uD83D"), string(r"bad \uDE80"),
    string('<font color="@color/red">Hello</font>'),
    string('<a href="javascript:bad()">Hello</a>'),
    string('<xliff:g xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">%s</xliff:g>'),
    string("%1$%"),
])
def test_unsafe_resource_metadata_escapes_and_markup_are_excluded(tmp_path, body):
    assert select(tmp_path, body, body)[0] == []


@pytest.mark.parametrize("change", ["id", "text", "namespace"])
def test_xliff_protected_content_and_identity_cannot_change(tmp_path, change):
    source = '<xliff:g xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2" id="model">RC 2</xliff:g> %s'
    vi = source.replace('id="model"', 'id="other"') if change == "id" else source
    vi = vi.replace("RC 2", "RC 3") if change == "text" else vi
    vi = vi.replace("document:1.2", "document:2.0") if change == "namespace" else vi
    assert select(tmp_path, string(source), string(vi))[0] == []


def test_preserved_markup_allows_positionalizing_arguments_inside_spans(tmp_path):
    source = string('<a href="https://example.org">%s</a> <b>%d</b>')
    vi = string('<b>%2$d</b> <a href="https://example.org">%1$s</a>')
    assert len(select(tmp_path, source, vi)[0]) == 1


def test_invalid_resource_name_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="name"):
        catalog.load_resources(resources(tmp_path, string("Hello", name="../unsafe")))


def test_catalog_entry_and_total_limits(tmp_path, monkeypatch):
    source = resources(tmp_path / "source", string("Hello"))
    vi = resources(tmp_path / "vi", string("Chào"))
    data = catalog.make_catalog(source, vi)
    monkeypatch.setattr(catalog, "MAX_ENTRY_CHARS", 5)
    assert catalog.make_catalog(source, vi)["entries"] == []
    with pytest.raises(ValueError, match="limit"):
        catalog.select_resources(data, source)
    monkeypatch.setattr(catalog, "MAX_ENTRY_CHARS", 1000)
    monkeypatch.setattr(catalog, "MAX_TOTAL_BYTES", 50)
    with pytest.raises(ValueError, match="limit"):
        catalog.select_resources(data, source)


def test_invalid_catalog_kind_is_rejected(tmp_path):
    source = resources(tmp_path / "source", string("Hello"))
    data = catalog.make_catalog(source, resources(tmp_path / "vi", string("Chào")))
    data["entries"][0]["kind"] = "color"
    with pytest.raises(ValueError, match="identity"):
        catalog.select_resources(data, source)


def test_aggregate_catalog_limit_includes_canonical_source(tmp_path, monkeypatch):
    source = resources(tmp_path / "source", string("界" * 100))
    vi = resources(tmp_path / "vi", string("Chào"))
    data = catalog.make_catalog(source, vi)
    monkeypatch.setattr(catalog, "MAX_TOTAL_BYTES", 500)
    with pytest.raises(ValueError, match="catalog.*limit"):
        catalog.select_resources(data, source)
    with pytest.raises(ValueError, match="catalog.*limit"):
        catalog.make_catalog(source, vi)


def test_resource_and_catalog_entry_counts_are_bounded(tmp_path, monkeypatch):
    source = resources(tmp_path / "source", string("Hello"))
    data = catalog.make_catalog(source, resources(tmp_path / "vi", string("Chào")))
    monkeypatch.setattr(catalog, "MAX_ENTRIES", 0)
    with pytest.raises(ValueError, match="limit"):
        catalog.select_resources(data, source)
    with pytest.raises(ValueError, match="limit"):
        catalog.load_resources(source)
