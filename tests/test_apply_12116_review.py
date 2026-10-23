"""Boundaries for staging reviewed translations and publishing review claims."""
import hashlib
import json

import pytest

from scripts import apply_12116_review as apply


def evidence():
    baseline = {'source_sha256': apply.SOURCE_SHA256, 'resource_sha256': apply.BASELINE_SHA256,
        'version': '1.21.16', 'version_code': 3132286, 'reviewed': 11425, 'machine': 569,
        'unresolved': 0, 'complete': True, 'private_path': r'C:\Users\someone\private'}
    review = {'revision': 'r14.6.2-12116-semantic-review', 'baseline_manifest_sha256': 'a' * 64,
        'coverage': {'complete': True, 'reviewed_resources': 11994,
                     'reviewed_groups': 8786, 'unresolved': 0}}
    report = {'status': 'PASS', 'source_sha256': apply.SOURCE_SHA256,
        'baseline_translation_sha256': apply.BASELINE_SHA256, 'revision': review['revision'],
        'translation_sha256': 'b' * 64, 'bytes': 2000000, 'corrected_resources': 123,
        'resource_ids_and_configurations_preserved': True, 'unrelated_values_and_styles_unchanged': True}
    return baseline, review, report


def test_metadata_keeps_machine_origin_and_adds_full_semantic_review():
    baseline, review, report = evidence()
    result = apply.reviewed_metadata(baseline, review, report, 'c' * 64)
    assert (result['reviewed'], result['machine']) == (11425, 569)
    assert result['all_machine_output_semantically_reviewed'] is True
    assert result['semantic_review']['reviewed_resources'] == 11994
    assert result['resource_sha256'] == report['translation_sha256']
    assert result['translation_revision'] == review['revision']
    assert result['semantic_review_baseline_translation_sha256'] == apply.BASELINE_SHA256
    assert 'private_path' not in result
    result['semantic_review']['reviewed_resources'] = 1
    assert review['coverage']['reviewed_resources'] == 11994


@pytest.mark.parametrize('field,value', [
    ('complete', False), ('complete', 1), ('reviewed_resources', 11993),
    ('reviewed_groups', 8785), ('unresolved', 1), ('unresolved', False),
])
def test_partial_or_boolean_coverage_cannot_claim_all_machine_output_reviewed(field, value):
    baseline, review, report = evidence()
    review['coverage'][field] = value
    with pytest.raises(ValueError, match='coverage'):
        apply.reviewed_metadata(baseline, review, report, 'c' * 64)


@pytest.mark.parametrize('field,value', [
    ('baseline_translation_sha256', 'd' * 64), ('source_sha256', 'd' * 64),
    ('status', 'FAIL'), ('resource_ids_and_configurations_preserved', False),
    ('unrelated_values_and_styles_unchanged', False), ('revision', 'other-review'),
])
def test_metadata_rejects_unverified_or_wrong_input_result(field, value):
    baseline, review, report = evidence()
    report[field] = value
    with pytest.raises(ValueError, match='evidence mismatch'):
        apply.reviewed_metadata(baseline, review, report, 'c' * 64)


def test_public_coverage_cannot_leak_absolute_review_paths():
    baseline, review, report = evidence()
    review['coverage']['reviewer_shards'] = [{'ledger': r'C:\Users\someone\review\ledger.json'}]
    with pytest.raises(ValueError, match='private path'):
        apply.reviewed_metadata(baseline, review, report, 'c' * 64)


def test_input_hash_guard_detects_changed_catalog(tmp_path):
    source, catalog = tmp_path / 'source', tmp_path / 'review.json'
    source.write_bytes(b'original source')
    catalog.write_bytes(b'original catalog')
    paths = {'source_apk': source, 'review_catalog': catalog}
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    assert apply._assert_inputs_unchanged(paths, before)['status'] == 'PASS'
    catalog.write_bytes(b'changed catalog')
    with pytest.raises(ValueError, match='input changed'):
        apply._assert_inputs_unchanged(paths, before)


def test_work_cannot_contain_an_input_that_tools_would_overwrite(tmp_path):
    work = tmp_path / 'work'
    source = work / 'utilities' / 'aapt2.exe'
    with pytest.raises(ValueError, match='overwrite'):
        apply._validate_paths(source, tmp_path / 'baseline', tmp_path / 'review', tmp_path / 'output', work)


def test_cli_requires_explicit_source_and_staging_paths():
    with pytest.raises(SystemExit) as error:
        apply.main([])
    assert error.value.code == 2


def test_cli_rejects_unpinned_stock_before_creating_output(tmp_path):
    inputs = [tmp_path / name for name in ('source.apk', 'baseline.arsc', 'review.json', 'manifest.json')]
    for path in inputs:
        path.write_bytes(b'not an authorized input')
    output, work = tmp_path / 'out', tmp_path / 'work'
    with pytest.raises(ValueError, match='Pinned stock APK'):
        apply.main(['--source', str(inputs[0]), '--baseline', str(inputs[1]),
            '--reviewed', str(inputs[2]), '--baseline-manifest', str(inputs[3]),
            '--output', str(output), '--work', str(work)])
    assert not output.exists() and not work.exists()


def test_no_review_catalog_keeps_existing_postcompile_pipeline(tmp_path):
    raw = b'existing compiled translation'
    assert apply.postcompile_review(b'stock resources', raw, tmp_path / 'missing.json') == (raw, None)


def test_present_review_cannot_apply_to_another_generated_baseline(tmp_path):
    path = tmp_path / 'review.json'
    path.write_text(json.dumps(evidence()[1]), encoding='utf-8')
    with pytest.raises(ValueError, match='differs from the reviewed'):
        apply.postcompile_review(b'stock resources', b'another compiled table', path)
