"""Synthetic host-only contracts for target-driven complete composition."""
import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from rc2vi import translation_catalog as catalog
from rc2vi import translation_complete as complete
from rc2vi.translation_complete import IncompleteTranslation, compose_complete


def resources(root: Path, body: str, config="values", file="strings.xml"):
    directory = root / config
    directory.mkdir(parents=True, exist_ok=True)
    (directory / file).write_text(f"<resources>{body}</resources>", encoding="utf-8")
    return root


def string(text, name="message", attrs=""):
    return f'<string name="{name}" {attrs}>{text}</string>'


def memory(source, translation):
    before, after = ET.fromstring(source), ET.fromstring(translation)
    return {"schema": 1, "entries": [{"kind": before.tag, "name": before.get("name"),
            "source": catalog._canonical(before), "translation_xml": ET.tostring(after, encoding="unicode")}]}


def never(_):
    pytest.fail("Engine must not be called")


def translate(texts):
    pairs = [("Hello", "Xin chào"), ("Ready", "Sẵn sàng"), ("Fly safely", "Bay an toàn"),
             ("Distance", "Khoảng cách"), ("Connect", "Kết nối"), ("First", "Đầu tiên"),
             ("Second", "Thứ hai"), ("One", "Một"), ("Many", "Nhiều"), ("Battery", "Pin"),
             ("full", "đầy"), ("done", "xong"), ("Use", "Dùng"), ("Contact", "Liên hệ")]
    result = []
    for text in texts:
        for english, vietnamese in pairs:
            text = text.replace(english, vietnamese)
        result.append(text)
    return result


def values(elements):
    return {e.get("name"): e for e in elements}


def test_all_target_files_qualifiers_and_empty_memory(tmp_path):
    resources(tmp_path, string("Old"))
    resources(tmp_path, string("Hello"), "values-en")
    resources(tmp_path, string("Ready"), "values-en-rUS")
    resources(tmp_path, string("Fly safely", "new"), file="extra.xml")
    resources(tmp_path, string("Ignored", "french"), "values-fr")
    elements, report = compose_complete(tmp_path, [], translate)
    assert {k: e.text for k, e in values(elements).items()} == {"message": "Sẵn sàng", "new": "Bay an toàn"}
    assert report["complete"] is True
    assert report["machine"] == report["matched"] == report["eligible_total"] == report["total"] == 2
    assert report["catalog_total"] == report["reviewed"] == report["unresolved"] == report["target_untranslated"] == 0
    assert report["machine_meaning_verified"] is False


def test_exact_context_wins_then_unambiguous_renamed_source(tmp_path):
    first = memory(string("Hello"), string("Xin chào"))
    alternate = memory(string("Hello", "other"), string("Chào bạn", "other"))
    snapshot = copy.deepcopy([first, alternate])
    resources(tmp_path, string("Hello"))
    elements, report = compose_complete(tmp_path, [first, alternate], never, {"Hello": "Bị ghi đè"})
    assert elements[0].text == "Xin chào" and report["reviewed"] == 1
    assert [first, alternate] == snapshot
    resources(tmp_path, string('"Hello"', "renamed"))
    elements, report = compose_complete(tmp_path, [first, first], never)
    assert elements[0].get("name") == "renamed" and elements[0].text == "Xin chào"


def test_ambiguity_changed_source_and_invalid_memory_go_to_engine(tmp_path):
    catalogs = [memory(string("Hello", "a"), string("Chào", "a")),
                memory(string("Hello", "b"), string("Chào bạn", "b")),
                memory(string("Old"), string("Cũ"))]
    resources(tmp_path, string("Hello"))
    elements, report = compose_complete(tmp_path, catalogs, translate)
    assert elements[0].text == "Xin chào" and report["machine"] == 1
    invalid = memory(string("Hello %s"), string("Xin chào %d"))
    resources(tmp_path, string("Hello %s") + string("Ready", "ready"))
    elements, report = compose_complete(tmp_path, [invalid], translate)
    assert "%s" in values(elements)["message"].text
    assert report["reviewed"] == 0


def test_conflicting_exact_memory_does_not_choose_catalog_order(tmp_path):
    resources(tmp_path, string("Hello"))
    memories = [memory(string("Hello"), string("Chào")), memory(string("Hello"), string("Xin chào"))]
    for entries in (memories, memories[::-1]):
        assert compose_complete(tmp_path, entries, translate)[1]["machine"] == 1


def test_approved_overrides_are_per_text_and_validated(tmp_path):
    resources(tmp_path, string("Hello") + string("Distance %1$d m", "distance"))
    elements, report = compose_complete(tmp_path, [], never,
        {"Hello": "Xin chào", "Distance %1$d m": "Khoảng cách %1$d m"})
    assert report["reviewed"] == 2 and report["machine"] == 0
    assert values(elements)["distance"].text == "Khoảng cách %1$d m"
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], lambda x: x, {"Hello": "Xin chào", "Distance %1$d m": "Khoảng cách"})
    assert caught.value.report["unresolved"] == 1


def test_machine_shields_tokens_and_nested_markup(tmp_path):
    body = string('Connect <b>DJI Mini 4 Pro <i>Distance %1$02d m</i></b> '
                  '<xliff:g id="name">%2$s</xliff:g> https://example.test/private?k=secret '
                  '120 m', attrs='xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2"')
    resources(tmp_path, body + string("Ready", "ready"))
    calls = []
    def engine(texts):
        calls.extend(texts)
        return translate(texts)
    elements, report = compose_complete(tmp_path, [], engine)
    target = values(elements)["message"]
    catalog._compatible(ET.fromstring(body), target)
    joined = " ".join(calls)
    assert not any(secret in joined for secret in ("DJI", "%1$02d", "%2$s", "secret", "https://", "120", "<b>"))
    assert target[0][0].text == "Khoảng cách %1$02d m"
    assert "DJI Mini 4 Pro" in "".join(target.itertext())
    assert report["machine"] == 2


def test_marker_corruption_falls_back_to_translating_only_text(tmp_path):
    resources(tmp_path, string("Distance %1$d m") + string("Ready", "ready"))
    calls = []
    def engine(texts):
        calls.extend(texts)
        return ["marker lost" if "__RC2VI_" in t else translate([t])[0] for t in texts]
    elements, report = compose_complete(tmp_path, [], engine)
    assert values(elements)["message"].text == "Khoảng cách %1$d m"
    assert "Distance" in calls and report["machine"] == 2


def test_arrays_plurals_mixed_references_and_technical_items(tmp_path):
    body = '<string-array name="choices"><item>First</item><item>@string/ready</item>'
    body += '<item>https://example.test/x</item><item>Second %s</item></string-array>'
    body += '<plurals name="count"><item quantity="one">One %d</item><item quantity="other">Many %d</item></plurals>'
    resources(tmp_path, body + string("Ready", "ready"))
    elements, report = compose_complete(tmp_path, [], translate)
    chosen = values(elements)
    assert [e.text for e in chosen["choices"]] == ["Đầu tiên", "@string/ready", "https://example.test/x", "Thứ hai %s"]
    assert [e.text for e in chosen["count"]] == ["Một %d", "Nhiều %d"]
    assert report["matched"] == 3


@pytest.mark.parametrize("text,name,attrs", [
    ("Never send this", "private", 'translatable="false"'),
    ("AIzaSyVeryPrivateCredential123456789012345", "google_api_key", ""),
    ("wordlikeSecret", "client_secret", ""), ("true", "flag", ""),
    ('{&quot;token&quot;:&quot;DoNotSend&quot;}', "config", ""),
    ("https://example.test/private?token=abc", "endpoint", ""),
    ("0xDEADBEEF", "mask", ""), ("0123456789abcdef0123456789abcdef", "hash", ""),
    ("m/s", "unit", ""), ("120 m", "limit", ""), ("DJI Mini 4 Pro", "product", ""),
    ("@string/ready", "alias", ""), ("?android:attr/text", "attr", ""),
    ("flight_mode_auto", "identifier", ""), ("dji.go.v5", "package", ""),
])
def test_technical_resources_preserved_without_model_or_overlay(tmp_path, text, name, attrs):
    resources(tmp_path, string(text, name, attrs) + string("Ready", "ready"))
    calls = []
    def engine(texts):
        calls.extend(texts)
        return translate(texts)
    elements, report = compose_complete(tmp_path, [], engine)
    assert calls == ["Ready"] and list(values(elements)) == ["ready"]
    assert report["preserved"] == report["skipped"] == 1 and report["total"] == 2


def test_plain_ascii_prose_is_not_technical(tmp_path):
    resources(tmp_path, string("Flight cannot start until the aircraft is connected"))
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], lambda x: x)
    assert caught.value.report["eligible_total"] == caught.value.report["unresolved"] == 1
    assert caught.value.report["preserved"] == 0


@pytest.mark.parametrize("source,vi,attrs", [
    ("Battery 100% full", "Pin 100% đầy", ""),
    ("Battery %1$d% full", "Pin %1$d% đầy", ""),
    ("Use 50% of battery", "Dùng 50% pin", ""),
    ("Battery 100% full", "Pin 100% đầy", 'formatted="false"'),
    ("Use %&lt;s", "Dùng %&lt;s", 'formatted="false"'),
])
def test_literal_percent_and_formatted_false_locally_compatible(tmp_path, source, vi, attrs):
    resources(tmp_path, string(source, attrs=attrs) + string("Ready", "ready"))
    data = memory(string(source, attrs=attrs), string(vi, attrs=attrs))
    elements, report = compose_complete(tmp_path, [data], translate)
    assert report["reviewed"] == 1
    assert values(elements)["message"].text == ET.fromstring(string(vi)).text


@pytest.mark.parametrize("output", [[], [None], "not a list", [""], ["123"], ["Hello"], ["a", "b"]])
def test_bad_engine_results_never_report_complete(tmp_path, output):
    resources(tmp_path, string("Hello"))
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], lambda _: output)
    report = caught.value.report
    assert report["complete"] is False and report["unresolved"] == report["target_untranslated"] == 1
    assert report["matched"] == report["machine"] == 0 and report["reasons"]


def test_engine_exception_is_sanitized_and_keeps_truthful_partial_report(tmp_path):
    resources(tmp_path, string("Hello") + string("Ready", "ready"))
    def broken(_):
        raise RuntimeError("secret-key-must-not-appear")
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [memory(string("Ready", "ready"), string("Sẵn sàng", "ready"))], broken)
    report = caught.value.report
    assert report["reviewed"] == 1 and report["unresolved"] == 1 and not report["complete"]
    assert "secret-key" not in str(caught.value) + str(report)


@pytest.mark.parametrize("body", ["", string("120 m"), '<string-array name="a"><item>Hello</item></string-array>'])
def test_empty_or_no_independent_readback_fails(tmp_path, body):
    resources(tmp_path, body)
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], translate)
    assert not caught.value.report["complete"]


def test_missing_directory_and_malformed_xml_fail_closed(tmp_path):
    with pytest.raises(IncompleteTranslation):
        compose_complete(tmp_path / "absent", [], never)
    resources(tmp_path, "<string>")
    with pytest.raises(IncompleteTranslation):
        compose_complete(tmp_path, [], never)


def test_escaping_and_roundtrip_readback(tmp_path):
    resources(tmp_path, string(r"Hello\nReady") + string("Ready", "ready"))
    elements, _ = compose_complete(tmp_path, [], translate)
    again = catalog._xml(ET.tostring(elements[0]))
    assert catalog._content(again)[0] == "Xin chào\nSẵn sàng"


def test_all_unresolved_reasons_are_counted_per_resource(tmp_path):
    resources(tmp_path, string("Unknown", "first") + string("Unknown too", "second") + string("Ready", "ready"))
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], translate)
    report = caught.value.report
    assert report["total"] == 3 and report["machine"] == 1 and report["unresolved"] == 2
    assert len(report["unresolved_resources"]) == 2


def test_primary_and_fallback_are_global_batches_not_per_resource(tmp_path):
    resources(tmp_path, "".join(string(f"Distance {i} m", f"d{i}") for i in range(120)) + string("Ready", "ready"))
    calls = []
    def engine(texts):
        calls.append(texts)
        return ["broken" if "__RC2VI_" in t else translate([t])[0] for t in texts]
    elements, report = compose_complete(tmp_path, [], engine)
    assert len(calls) == 2 and calls[1] == ["Distance"]
    assert len(elements) == report["machine"] == 121


def test_very_long_text_split_without_truncation_or_losing_boundary_spaces(tmp_path):
    text = "Hello. " * 160 + "Ready"
    resources(tmp_path, string(text))
    calls = []
    def engine(texts):
        calls.append(texts)
        assert all(len(t) <= 320 for t in texts)
        return translate(texts)
    elements, _ = compose_complete(tmp_path, [], engine)
    assert len(calls) == 1
    assert catalog._content(elements[0])[0] == "Xin chào. " * 160 + "Sẵn sàng"


def test_long_paragraph_with_markers_and_newlines_preserves_every_token(tmp_path):
    text = (r"Distance %1$d m.\n" * 70) + "Ready"
    resources(tmp_path, string(text) + string("Ready", "ready"))
    calls = []
    def engine(texts):
        calls.append(texts)
        assert all(len(t) <= 320 for t in texts)
        return translate(texts)
    elements, _ = compose_complete(tmp_path, [], engine)
    decoded = catalog._content(values(elements)["message"])[0]
    assert decoded == ("Khoảng cách %1$d m.\n" * 70) + "Sẵn sàng"
    assert len(calls) == 1


@pytest.mark.parametrize("text", ["%1$s", "%d%%", "%1$d/%2$d", "H.264", "1080p", "12MP", "N/A",
                                      "com.example.widget.Behavior", r'{\"token\":\"hidden\"}'])
def test_format_only_and_additional_technical_values_never_reach_engine(tmp_path, text):
    resources(tmp_path, string(text) + string("Ready", "ready"))
    calls = []
    def engine(texts):
        calls.extend(texts)
        return translate(texts)
    _, report = compose_complete(tmp_path, [], engine)
    assert calls == ["Ready"] and report["preserved"] == 1


def test_reviewed_loan_word_may_be_unchanged_but_machine_identity_cannot(tmp_path):
    resources(tmp_path, string("Video"))
    elements, report = compose_complete(tmp_path, [memory(string("Video"), string("Video"))], never)
    assert elements[0].text == "Video" and report["reviewed"] == 1
    with pytest.raises(IncompleteTranslation):
        compose_complete(tmp_path, [], lambda x: x)


def test_exact_conflict_can_be_resolved_by_valid_approved_override(tmp_path):
    resources(tmp_path, string("Hello"))
    data = [memory(string("Hello"), string("Chào")), memory(string("Hello"), string("Xin chào"))]
    elements, report = compose_complete(tmp_path, data, never, {"Hello": "Chào bạn"})
    assert report["reviewed"] == 1 and elements[0].text == "Chào bạn"


def test_non_english_human_source_remains_unresolved_not_technical(tmp_path):
    resources(tmp_path, string("请连接飞机"))
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], never)
    assert caught.value.report["preserved"] == 0
    assert caught.value.report["reasons"]["unsupported_source_language"] == 1


def test_do_not_treat_adjacent_number_as_literal_formatter(tmp_path):
    resources(tmp_path, string("Hello 2%s") + string("Ready", "ready"))
    bad = memory(string("Hello 2%s"), string("Chào 2%d"))
    elements, report = compose_complete(tmp_path, [bad], translate)
    assert report["reviewed"] == 0 and values(elements)["message"].text == "Xin chào 2%s"


@pytest.mark.parametrize("bad", [{}, {"schema": True, "entries": []}, {"schema": 1, "entries": {}},
                               {"schema": 1, "entries": [{}]}])
def test_invalid_catalog_envelopes_rejected(tmp_path, bad):
    resources(tmp_path, string("Ready"))
    with pytest.raises(ValueError):
        compose_complete(tmp_path, [bad], never)


def test_unknown_markup_and_invalid_resource_shape_are_unresolved(tmp_path):
    resources(tmp_path, string("Hello <script>bad</script>") + '<plurals name="count"><item quantity="one">One</item></plurals>')
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], never)
    assert caught.value.report["unresolved"] == caught.value.report["eligible_total"] == 2


def test_machine_cannot_inject_or_change_numbers_product_or_urls(tmp_path):
    resources(tmp_path, string("Hello") + string("Ready", "ready"))
    def engine(texts):
        return ["Xin chào 777" if t == "Hello" else "Sẵn sàng" for t in texts]
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], engine)
    assert caught.value.report["machine"] == 1 and caught.value.report["unresolved"] == 1


@pytest.mark.parametrize("original,bad", [("Distance 120 m", "Khoảng cách 121 m"),
    ("Connect DJI Mini 4 Pro", "Kết nối DJI Mini 3 Pro"),
    ("Contact https://example.test/legal", "Liên hệ https://different.test/legal")])
def test_reviewed_memory_must_preserve_numbers_products_and_links(tmp_path, original, bad):
    resources(tmp_path, string(original) + string("Ready", "ready"))
    elements, report = compose_complete(tmp_path, [memory(string(original), string(bad))], translate)
    assert report["reviewed"] == 0 and report["machine"] == 2
    assert values(elements)["message"].text != bad


def test_reviewed_implicit_to_explicit_formatter_binding_still_accepted(tmp_path):
    resources(tmp_path, string("Hello %s") + string("Ready", "ready"))
    _, report = compose_complete(tmp_path, [memory(string("Hello %s"), string("Xin chào %1$s"))], translate)
    assert report["reviewed"] == 1


def test_password_label_is_human_while_password_value_stays_private(tmp_path):
    resources(tmp_path, string("Password", "password") + string("VerySecretValue", "api_key"))
    calls = []
    def engine(texts):
        calls.extend(texts)
        return ["Mật khẩu" for _ in texts]
    _, report = compose_complete(tmp_path, [], engine)
    assert calls == ["Password"] and report["preserved"] == report["machine"] == 1


def test_literal_percent_across_markup_boundary_uses_decoded_context(tmp_path):
    resources(tmp_path, string("Battery 100<b>% full</b>") + string("Ready", "ready"))
    _, report = compose_complete(tmp_path,
        [memory(string("Battery 100<b>% full</b>"), string("Pin 100<b>% đầy</b>"))], translate)
    assert report["reviewed"] == 1


@pytest.mark.parametrize("mode", ["memory", "override", "machine"])
@pytest.mark.parametrize("english,vietnamese", [
    ("License(s) deleted", "Đã xóa giấy phép"),
    (r"drone\'s position", "Vị trí máy bay"),
])
def test_english_suffixes_are_not_shielded_as_units(tmp_path, mode, english, vietnamese):
    body = string(english)
    resources(tmp_path, body)
    decoded = catalog._content(ET.fromstring(body))[0]
    calls = []
    def engine(texts):
        calls.append(texts)
        assert texts == [decoded]
        return [vietnamese]
    data = [memory(body, string(vietnamese))] if mode == "memory" else []
    overrides = {decoded: vietnamese} if mode == "override" else None
    elements, report = compose_complete(tmp_path, data, engine if mode == "machine" else never, overrides)
    assert elements[0].text == vietnamese
    assert report["machine" if mode == "machine" else "reviewed"] == 1
    assert len(calls) == (1 if mode == "machine" else 0)


@pytest.mark.parametrize("unit", ["s", "m", "h", "m/s", "MHz", "V"])
def test_standalone_unit_value_stays_technical(tmp_path, unit):
    resources(tmp_path, string(unit) + string("Ready", "ready"))
    calls = []
    def engine(texts):
        calls.extend(texts)
        return translate(texts)
    elements, report = compose_complete(tmp_path, [], engine)
    assert calls == ["Ready"] and list(values(elements)) == ["ready"]
    assert report["preserved"] == 1


@pytest.mark.parametrize("amount", ["120", "%1$d", "%s"])
@pytest.mark.parametrize("unit", ["s", "m", "h", "m/s", "MHz", "V"])
@pytest.mark.parametrize("separator", ["", " "])
def test_units_remain_shielded_after_numbers_or_placeholders(tmp_path, amount, unit, separator):
    resources(tmp_path, string(f"Distance {amount}{separator}{unit}") + string("Ready", "ready"))
    def engine(texts):
        assert all(unit not in text.split() for text in texts)
        return translate(texts)
    elements, report = compose_complete(tmp_path, [], engine)
    assert values(elements)["message"].text == f"Khoảng cách {amount}{separator}{unit}"
    assert report["machine"] == 2


def test_changed_placeholder_unit_still_rejects_memory_and_override(tmp_path):
    body = string("Distance %1$d m")
    resources(tmp_path, body + string("Ready", "ready"))
    data = memory(body, string("Khoảng cách %1$d s"))
    elements, report = compose_complete(tmp_path, [data], translate, {"Distance %1$d m": "Khoảng cách %1$d h"})
    assert values(elements)["message"].text == "Khoảng cách %1$d m" and report["reviewed"] == 0


@pytest.mark.parametrize("identifier", ["WA341", "WA345", "ABC123", "123ABC", "AB12CD34"])
def test_entire_uppercase_alphanumeric_model_id_is_technical(tmp_path, identifier):
    resources(tmp_path, string(identifier) + string("Ready", "ready"))
    def engine(texts):
        assert texts == ["Ready"]
        return translate(texts)
    elements, report = compose_complete(tmp_path, [], engine)
    assert list(values(elements)) == ["ready"] and report["preserved"] == 1


@pytest.mark.parametrize("text", ["WA341 unavailable", "PLEASE WAIT", "Chapter 12"])
def test_model_id_rule_does_not_preserve_whole_human_sentences(tmp_path, text):
    resources(tmp_path, string(text))
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], lambda x: x)
    assert caught.value.report["preserved"] == 0 and caught.value.report["unresolved"] == 1


def test_allow_chinese_routes_han_and_english_in_one_batch(tmp_path):
    resources(tmp_path, string("请连接飞机") + string("Ready", "ready"))
    calls = []
    def engine(texts):
        calls.append(texts)
        return ["Vui lòng kết nối máy bay" if t == "请连接飞机" else translate([t])[0] for t in texts]
    elements, report = compose_complete(tmp_path, [], engine, allow_chinese=True)
    assert calls == [["请连接飞机", "Ready"]]
    assert values(elements)["message"].text == "Vui lòng kết nối máy bay"
    assert report["machine"] == report["eligible_total"] == 2 and report["complete"]


def test_allow_chinese_retains_markup_format_and_unit_contracts(tmp_path):
    body = string("距离 <b>%1$d</b> m后")
    resources(tmp_path, body + string("Ready", "ready"))
    def engine(texts):
        assert all(" m" not in t for t in texts)
        return [t.replace("距离", "Khoảng cách").replace("后", " sau").replace("Ready", "Sẵn sàng") for t in texts]
    elements, report = compose_complete(tmp_path, [], engine, allow_chinese=True)
    catalog._compatible(ET.fromstring(body), values(elements)["message"])
    assert report["machine"] == 2


@pytest.mark.parametrize("allow_chinese", [False, True])
@pytest.mark.parametrize("text", ["يرجى الاتصال", "请连接飞机 يرجى الاتصال"])
def test_chinese_flag_does_not_enable_other_scripts(tmp_path, allow_chinese, text):
    resources(tmp_path, string(text))
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], never, allow_chinese=allow_chinese)
    assert caught.value.report["reasons"]["unsupported_source_language"] == 1


def test_extended_latin_is_not_rejected_by_a_codepoint_cutoff(tmp_path):
    resources(tmp_path, string("Connect to Nguyễn"))
    elements, report = compose_complete(tmp_path, [], lambda texts: [t.replace("Connect to", "Kết nối với") for t in texts])
    assert elements[0].text == "Kết nối với Nguyễn" and report["machine"] == 1


@pytest.mark.parametrize("source,target", [
    ("请保持飞机和眼镜电量在30％以上", "Vui lòng giữ máy bay và kính ở dưới 30%."),
    ("请保持飞机和眼镜电量在30％以上", "Vui lòng giữ máy bay và kính ở dưới 30％."),
    ("Keep battery above 30", "Giữ pin dưới 30"),
    ("Keep battery at least 30", "Giữ pin tối đa 30"),
    ("Keep battery below 30", "Giữ pin trên 30"),
    ("Keep battery at most %1$d", "Giữ pin ít nhất %1$d"),
    ("保持电量在30％以下", "Giữ pin từ 30％ trở lên"),
    ("Keep battery above %s", "Giữ pin dưới %s"),
    ("Keep battery above %1$d (repeat %&lt;d)", "Giữ pin dưới %1$d (lặp lại %&lt;d)"),
])
def test_numeric_comparator_inversions_fail_validation(source, target):
    with pytest.raises(ValueError, match="numeric_comparator_inverted"):
        complete._validate(ET.fromstring(string(source)), ET.fromstring(string(target)), strict=True)


@pytest.mark.parametrize("source,target", [
    ("Keep battery above 30", "Giữ pin trên 30"),
    ("Keep battery above 30", "Giữ pin ít nhất 30"),
    ("Keep battery above 30", "Giữ pin tối thiểu 30"),
    ("Keep battery above 30", "Giữ pin &gt; 30"),
    ("Keep battery above 30", "Giữ pin &gt;= 30"),
    ("Keep battery at least 30", "Giữ pin ≥ 30"),
    ("Keep battery below 30", "Giữ pin &lt;= 30"),
    ("Keep battery at most 30", "Giữ pin từ 30 trở xuống"),
    ("请保持飞机和眼镜电量在30％以上", "Vui lòng giữ pin máy bay và kính ở mức 30％ trở lên."),
])
def test_equivalent_comparator_families_remain_valid(source, target):
    complete._validate(ET.fromstring(string(source)), ET.fromstring(string(target)), strict=True)


@pytest.mark.parametrize("source,target", [
    ("Do not keep battery below 30", "Giữ pin trên 30"),
    (r"Don\'t keep battery below 30", "Giữ pin trên 30"),
    ("Keep battery above 30", "Không để pin dưới 30"),
    ("电量不得低于30％", "Giữ pin trên 30％"),
    ("Battery above 30 and below 80", "Pin dưới 80 và trên 30"),
    ("Battery above 30 and below 80", "Pin dưới 30 đến 80"),
    ("Battery above 30", "Pin trên 30. Xem hướng dẫn bên dưới."),
    ("See above", "Xem bên dưới"),
    ("Keep battery above 30", "Giữ pin ở mức 30"),
    ("Version 30: https://example.test/above", "Phiên bản 30: xem dưới https://example.test/above"),
])
def test_negated_mixed_or_non_numeric_comparisons_are_not_guessed(source, target):
    complete._validate(ET.fromstring(string(source)), ET.fromstring(string(target)), strict=True)


def test_correct_approved_chinese_battery_override_passes(tmp_path):
    source = "请保持飞机和眼镜电量在30％以上"
    target = "Vui lòng giữ pin máy bay và kính ở mức 30％ trở lên."
    resources(tmp_path, string(source))
    elements, report = compose_complete(tmp_path, [], never, {source: target}, allow_chinese=True)
    assert elements[0].text == target and report["reviewed"] == 1
    assert report["machine_meaning_verified"] is False


def test_comparator_guard_applies_to_memory_override_and_machine(tmp_path):
    source = "Keep battery above 30"
    wrong = "Giữ pin dưới 30"
    resources(tmp_path, string(source) + string("Ready", "ready"))
    def inverted(texts):
        return [t.replace("Keep battery above", "Giữ pin dưới").replace("Ready", "Sẵn sàng") for t in texts]
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [memory(string(source), string(wrong))], inverted, {source: wrong})
    report = caught.value.report
    assert not report["complete"] and report["reviewed"] == 0
    assert report["unresolved"] == 1 and report["machine"] == 1


@pytest.mark.parametrize("name,text,reason", json.loads(
    Path(__file__).with_name("test_translation_complete_fixtures.json").read_text(encoding="utf-8")))
def test_real_unresolved_technical_shapes_are_preserved(tmp_path, name, text, reason):
    resources(tmp_path, string(text, name) + string("Ready", "ready"))
    def engine(texts):
        assert texts == ["Ready"]
        return translate(texts)
    elements, report = compose_complete(tmp_path, [], engine)
    assert list(values(elements)) == ["ready"] and report["preserved"] == 1
    assert report["preserved_reasons"] == {reason: 1}


def test_country_code_table_preserved_as_one_resource(tmp_path):
    resources(tmp_path, '<string-array name="country_code_2_country_str"><item>20,AD</item>'
              '<item>704,VN</item><item>840,US</item></string-array>' + string("Ready", "ready"))
    elements, report = compose_complete(tmp_path, [], translate)
    assert list(values(elements)) == ["ready"] and report["preserved"] == 1
    assert report["preserved_reasons"] == {"country_code": 1}


@pytest.mark.parametrize("name,text", [
    ("message", "PLEASE WAIT"), ("message", "2026 I am ready"),
    ("message", "CANCEL"), ("message", "WARNING"), ("message", "local cache unavailable"),
    ("message", "20,GO"), ("message", "IMU 1 failed"), ("message", "RAW+JPEG is unavailable"),
    ("message", "Move up to 30 m"), ("path_description", "M 0,0 means start"),
    ("reflection_error", "Cannot load com.example.Widget$Inner"),
    ("firmware_update_dialogue_wifi_download", "Auto Download (Wi-Fi Only)"),
    ("light_editor_redo_sticker_hide_toast", "Hiding stickers redone"),
    ("fpv_checklist_embeded_system_inner_hms10", "UART通道消息解析失败率过高，检查该uart通道两端服务配置"),
    ("stream_observer_desc_online_transcoder_run", "X264转码器转码线程"),
])
def test_technical_patterns_do_not_hide_human_failures(tmp_path, name, text):
    resources(tmp_path, string(text, name))
    with pytest.raises(IncompleteTranslation) as caught:
        compose_complete(tmp_path, [], lambda texts: texts, allow_chinese=True)
    assert caught.value.report["unresolved"] == 1 and caught.value.report["preserved"] == 0


@pytest.mark.parametrize("text", ["M0,0 C1,2", "M0,0 Z 3", "L0,0"])
def test_incomplete_vector_syntax_is_not_silently_preserved(text):
    assert not complete._technical(ET.fromstring(string(text, "motion_path_data")))


@pytest.mark.parametrize("target", ["Máy bay, kính, v.v", "Máy bay, kính, v.v..."])
def test_vietnamese_etc_abbreviation_is_not_a_protected_path(tmp_path, target):
    body = string("Aircraft, goggles, etc.")
    resources(tmp_path, body)
    elements, report = compose_complete(tmp_path, [memory(body, string(target))], never)
    assert elements[0].text == target and report["reviewed"] == 1
    assert complete._protected("v.v...", True) == []


def test_real_namespaces_filenames_and_identifiers_stay_shielded():
    for text in ("com.example.Widget", "dji.json", "settings.xml", "flight_mode_auto"):
        assert complete._protected(text, True) == [(0, len(text))]
    text = "检查dji.json中消息"
    assert [text[a:b] for a, b in complete._protected(text, True)] == ["dji.json"]


@pytest.mark.parametrize("source,fragment,translated,expected", [
    ("DJI Fly. Connect", ". Connect", "Kết nối", "DJI Fly. Kết nối"),
    ("DJI Fly, and connect", ", and connect", "và kết nối", "DJI Fly, và kết nối"),
    ("DJI Fly (Connect)", "(Connect)", "Kết nối.", "DJI Fly (Kết nối)"),
    ("Use DJI Fly, and connect.", ", and connect.", "và kết nối", "Dùng DJI Fly, và kết nối."),
])
def test_fallback_restores_edges_without_changing_cached_call_keys(tmp_path, source, fragment, translated, expected):
    resources(tmp_path, string(source))
    calls = []
    cache = {fragment: translated, "Use": "Dùng"}
    def engine(texts):
        calls.append(texts)
        return ["lost markers" if "__RC2VI_" in t else cache[t] for t in texts]
    elements, report = compose_complete(tmp_path, [], engine)
    assert elements[0].text == expected and report["machine"] == 1
    assert len(calls) == 2 and fragment in calls[1]


def test_fallback_cannot_hide_injected_percent_or_unchanged_human_core(tmp_path):
    resources(tmp_path, string("DJI Fly. Connect"))
    for output in ("Kết nối%", "Connect"):
        def engine(texts):
            return ["lost markers" if "__RC2VI_" in t else output for t in texts]
        with pytest.raises(IncompleteTranslation):
            compose_complete(tmp_path, [], engine)

@pytest.mark.parametrize("code", ["UART", "CAN", "ICC", "BULK", "CAN_SOCKET", "SHM", "MBUS", "LOCAL", "IP", "WL", "uart", "can_socket", "local", "X264", "WA341", "DJI Fly", "dji.json"])
@pytest.mark.parametrize("mode", ["primary", "fallback"])
@pytest.mark.parametrize("spacing", ["", " "])
def test_protocol_and_model_tokens_beside_han_do_not_hide_human_text(tmp_path, code, mode, spacing):
    source = "检查" + code + "通道"
    assert [source[a:b] for a, b in complete._protected(source, True)] == [code]
    resources(tmp_path, string(source))
    def engine(texts):
        assert all(code not in t for t in texts)
        return ["lost markers" if mode == "fallback" and "__RC2VI_" in t else
                t.replace("检查", "Kiểm tra" + spacing).replace("通道", spacing + "kênh") for t in texts]
    elements, report = compose_complete(tmp_path, [], engine, allow_chinese=True)
    assert elements[0].text == "Kiểm tra " + code + " kênh"
    assert report["machine"] == 1 and report["preserved"] == 0
    sentence = complete._sentence(ET.fromstring(string("检查" + code + ">%ss")), True)
    assert sentence.restore(sentence.rendered.replace("检查", "Kiểm tra")).text == "Kiểm tra " + code + ">%ss"

@pytest.mark.parametrize("value", ["%s", "%1$s", "example-private-123", "%s-private"])
def test_wifi_password_placeholder_label_translates_but_credentials_stay_shielded(tmp_path, value):
    source = "Connect WiFi SSID:%s\nWiFi Password:" + value
    resources(tmp_path, string(complete._escape(source)) + string("Ready", "ready"))
    calls = []
    def engine(texts):
        calls.extend(texts)
        return [t.replace("Password", "Mật khẩu") for t in translate(texts)]
    elements, report = compose_complete(tmp_path, [], engine)
    sent = " ".join(calls)
    assert not any(t in sent for t in ("WiFi", "SSID", "example-private-123", "%s", "%1$s"))
    assert ("Password" in sent) == bool(catalog.FORMAT.fullmatch(value))
    result = catalog._content(values(elements)["message"])[0]
    assert ("Mật khẩu:" in result) == bool(catalog.FORMAT.fullmatch(value)) and report["machine"] == 2

@pytest.mark.parametrize("version", ["v1.1", "v2.10.3"])
def test_inline_version_header_preserved_while_prose_translates(tmp_path, version):
    assert complete._protected(version, True) == [(0, len(version))]
    resources(tmp_path, string(f"—— {version} ——\\nHello") + string("Ready", "ready"))
    def engine(texts):
        assert all(version not in t for t in texts)
        return [t.replace("v", "@") for t in translate(texts)]
    elements, _ = compose_complete(tmp_path, [], engine)
    assert catalog._content(values(elements)["message"])[0] == f"—— {version} ——\nXin chào"
