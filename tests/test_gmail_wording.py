"""Gmail wording applies only to the three requested display hints."""
import hashlib
import json
from pathlib import Path

import pytest

from rc2vi import gmail_wording as wording
from rc2vi.reviewed_translation import _text_contract, apply_reviewed_table
from test_resource_embed import table
from test_reviewed_translation import selected


@pytest.mark.parametrize('name', tuple(wording.ENGLISH))
def test_requested_gmail_display_hint_has_an_exact_source_only_exception(name):
    before = {'text': wording.ENGLISH[name], 'spans': []}
    after = {'text': wording.TRANSLATIONS[name], 'spans': []}
    pair = [list(wording.TOKEN_EQUIVALENTS[name])]
    _text_contract(name, before, after, pair)
    with pytest.raises(ValueError, match='Unapproved'):
        _text_contract(name, dict(before, text=before['text'] + ' now'), after, pair)


@pytest.mark.parametrize('name', tuple(wording.ENGLISH))
def test_gmail_hint_cannot_inject_numbers_urls_or_format_arguments(name):
    before = {'text': wording.ENGLISH[name], 'spans': []}
    pair = [list(wording.TOKEN_EQUIVALENTS[name])]
    for extra in (' 20 m', ' %1$s', ' https://mail.example'):
        with pytest.raises(ValueError):
            _text_contract(name, before,
                           {'text': wording.TRANSLATIONS[name] + extra, 'spans': []}, pair)


def test_display_hints_do_not_change_unrelated_shared_pool_email_instructions():
    names = list(wording.ENGLISH) + ['activation_email_message']
    source_texts = list(wording.ENGLISH.values()) + ['Enter email']
    source = table('string', names, source_texts, [(b'', [(i, i) for i in range(4)])])
    # Last sign-in hint and activation instruction share their old pool value.
    baseline = table('string', names,
                     ['Nhập số điện thoại hay thư điện tử', 'Nhập thư điện tử'],
                     [(b'', [(0, 0), (1, 0), (2, 1), (3, 1)])])
    originals, previous = selected(source), selected(baseline)
    entries = [{
        'kind': 'string', 'name': name, 'reason': 'User-selected display label',
        'source_contract': originals['string', name],
        'previous_contract': previous['string', name],
        'translation_contract': [[None, 3, {'text': text, 'spans': []}]],
        'token_equivalents': [list(wording.TOKEN_EQUIVALENTS[name])],
    } for name, text in wording.TRANSLATIONS.items()]
    review = {
        'schema': 1, 'revision': wording.REVISION, 'source_sha256': wording.SOURCE_SHA256,
        'source_resources_sha256': hashlib.sha256(source).hexdigest(),
        'baseline_translation_sha256': hashlib.sha256(baseline).hexdigest(), 'entries': entries,
    }
    result, report = apply_reviewed_table(source, baseline, review,
                                          source_sha256=wording.SOURCE_SHA256)
    actual = selected(result)
    assert report['corrected_resources'] == 3
    assert actual['string', 'activation_email_message'] == previous['string', 'activation_email_message']
    assert {name: actual['string', name][0][2]['text'] for name in wording.TRANSLATIONS} == wording.TRANSLATIONS
    assert report['unrelated_values_and_styles_unchanged']


def test_public_catalog_records_user_labels_separately_from_semantic_review():
    path = Path(__file__).resolve().parents[1] / 'assets/translation/fly12116-reviewed.json'
    review = json.loads(path.read_text('utf-8'))
    assert review['revision'] == wording.REVISION
    assert review['generic_email_input_still_supported'] is True
    assert review['user_wording_overrides'] == list(wording.ENGLISH)
    assert review['coverage']['reviewed_resources'] == 11994
    assert review['coverage']['reviewed_groups'] == 8786
    assert review['coverage']['unresolved'] == 0
    rows = {row['name']: row for row in review['entries'] if row['name'] in wording.ENGLISH}
    assert len(rows) == 3
    for name, row in rows.items():
        assert row['source_contract'] == [[None, 3, {'text': wording.ENGLISH[name], 'spans': []}]]
        assert row['translation_contract'] == [[None, 3, {'text': wording.TRANSLATIONS[name], 'spans': []}]]
        assert row['token_equivalents'] == [list(wording.TOKEN_EQUIVALENTS[name])]
        assert row['change_origin'] == 'user_wording_override'
