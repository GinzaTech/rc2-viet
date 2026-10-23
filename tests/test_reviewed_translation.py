"""Review patches must fail closed and must not change shared, unrelated strings."""
import copy
import hashlib

import pytest

from rc2vi.resource_embed import Table
from rc2vi.reviewed_translation import apply_reviewed_table
from rc2vi.reviewed_translation import _text_contract
from scripts.build_12116_translation import english, resource_ids
from test_resource_embed import table


SOURCE = 'a' * 64


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def selected(raw):
    parsed = Table(raw)
    _, ids, _ = resource_ids(parsed)
    return english(parsed, {value: key for key, value in ids.items()})


def inputs():
    configs = [(b'', [(0, 0), (1, 1)]), (b'en', [(0, 0), (1, 1)])]
    source = table('string', ['instruction', 'other_context'],
                   ['Keep aircraft powered off. Insert %1$s at 20 m', 'Other text'], configs)
    # Both names deliberately share the same target pool index.
    baseline = table('string', ['instruction', 'other_context'], ['Giữ máy bay cất cánh %1$s 20 m'],
                     [(b'', [(0, 0), (1, 0)]), (b'en', [(0, 0), (1, 0)])])
    old, original = selected(baseline), selected(source)
    row = {'kind': 'string', 'name': 'instruction', 'reason': 'Correct an inverted power instruction',
        'source_contract': original['string', 'instruction'],
        'previous_contract': old['string', 'instruction'],
        'translation_contract': [[None, 3, {'text': 'Giữ máy bay tắt nguồn. Lắp %1$s ở 20 m', 'spans': []}]]}
    review = {'schema': 1, 'revision': 'review-test', 'source_sha256': SOURCE,
        'source_resources_sha256': sha(source), 'baseline_translation_sha256': sha(baseline), 'entries': [row]}
    return source, baseline, review


def test_one_correction_does_not_modify_an_unrelated_shared_pool_value_or_any_configuration():
    source, baseline, review = inputs()
    updated, report = apply_reviewed_table(source, baseline, review, source_sha256=SOURCE)
    actual = selected(updated)
    assert actual['string', 'instruction'] == review['entries'][0]['translation_contract']
    assert actual['string', 'other_context'] == selected(baseline)['string', 'other_context']
    assert resource_ids(Table(updated)) == resource_ids(Table(baseline))
    assert report['corrected_resources'] == 1 and report['corrected_configurations'] == 2
    assert report['unrelated_values_and_styles_unchanged']


@pytest.mark.parametrize('change', ['source', 'baseline', 'english', 'previous', 'identity'])
def test_review_cannot_be_applied_to_changed_inputs_or_a_different_context(change):
    source, baseline, review = inputs()
    if change == 'source':
        source += b'changed'
    elif change == 'baseline':
        baseline += b'changed'
    elif change == 'english':
        review['entries'][0]['source_contract'][0][2]['text'] = 'Different instruction'
    elif change == 'previous':
        review['entries'][0]['previous_contract'][0][2]['text'] = 'Different previous value'
    else:
        review['entries'][0]['name'] = 'other_context'
    with pytest.raises(ValueError):
        apply_reviewed_table(source, baseline, review, source_sha256=SOURCE)


@pytest.mark.parametrize('text', [
    'Giữ máy bay tắt nguồn. Lắp ở 20 m',
    'Giữ máy bay tắt nguồn. Lắp %1$d ở 20 m',
    'Giữ máy bay tắt nguồn. Lắp %1$s ở 30 m',
    'Giữ máy bay tắt nguồn. Lắp %1$s ở 20 ft',
])
def test_correction_cannot_drop_or_change_format_arguments_numbers_or_units(text):
    source, baseline, review = inputs()
    review['entries'][0]['translation_contract'][0][2]['text'] = text
    with pytest.raises(ValueError):
        apply_reviewed_table(source, baseline, review, source_sha256=SOURCE)


def test_duplicate_corrections_are_rejected_instead_of_overwriting_one_another():
    source, baseline, review = inputs()
    review['entries'].append(copy.deepcopy(review['entries'][0]))
    with pytest.raises(ValueError, match='duplicate'):
        apply_reviewed_table(source, baseline, review, source_sha256=SOURCE)


def test_canonical_product_spelling_needs_an_explicit_reviewed_comparison_equivalent():
    original = {'text': 'not wifi, download %1$s at 20 m?', 'spans': []}
    translated = {'text': 'Không có Wi-Fi. Tải %1$s ở 20 m?', 'spans': []}
    with pytest.raises(ValueError, match='protected_tokens_changed'):
        _text_contract('network_message', original, translated)
    _text_contract('network_message', original, translated, [['wifi', 'Wi-Fi']])
    changed = dict(translated, text=translated['text'].replace('20 m', '30 m'))
    with pytest.raises(ValueError, match='protected_tokens_changed'):
        _text_contract('network_message', original, changed, [['wifi', 'Wi-Fi']])
    with pytest.raises(ValueError, match='Unapproved'):
        _text_contract('network_message', original, changed, [['20 m', '30 m']])


@pytest.mark.parametrize('original,translated', [
    ('<b><i>Warning</i></b>', '<b><i>Cảnh báo</b></i>'),
    ('<b>%1$s</b> %2$s', '<b>%2$s</b> %1$s'),
    ('<b>%s</b> %s', '<b></b> %s %s'),
    ('Read <a href="https://a.example">%1$s</a> and <a href="https://b.example">%2$s</a>',
     'Đọc <a href="https://a.example">%2$s</a> và <a href="https://b.example">%1$s</a>'),
])
def test_literal_html_cannot_change_nesting_or_placeholder_link_scopes(original, translated):
    with pytest.raises(ValueError, match='literal markup changed'):
        _text_contract('instruction', {'text': original, 'spans': []},
                       {'text': translated, 'spans': []})


@pytest.mark.parametrize('original,translated', [
    ('<b><i>Warning %1$s</i></b>', '<b><i>Cảnh báo %1$s</i></b>'),
    ('<b>Warning %1$s<br>Land now</b>', '<b>Cảnh báo %1$s<br>Hạ cánh ngay</b>'),
    ('Read <a href="https://a.example">%1$s</a> and <a href="https://b.example">%2$s</a>',
     'Đọc <a href="https://a.example">%1$s</a> và <a href="https://b.example">%2$s</a>'),
    # Keep source fragments compatible without silently fixing their syntax.
    ('<b>Warning %1$s', '<b>Cảnh báo %1$s'),
    ('<b><i>Warning %1$s</b></i>', '<b><i>Cảnh báo %1$s</b></i>'),
])
def test_literal_html_allows_translated_text_with_exact_source_tokens_and_scopes(original, translated):
    _text_contract('instruction', {'text': original, 'spans': []},
                   {'text': translated, 'spans': []})
