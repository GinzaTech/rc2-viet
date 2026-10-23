"""Validate and stage the complete 1.21.16 semantic review without signing or USB.

Both output and work directories are explicit. Publishing staged assets is a
separate caller action; this command never chooses the live asset directory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PureWindowsPath
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rc2vi.resource_embed import Table, embed
from rc2vi.hud_tools import sha256_file
from rc2vi.reviewed_translation import apply_reviewed_table
from rc2vi.translation_build import TranslationBuilder

SOURCE_SHA256 = '9bec52ed4c43aad6c615b0a7a0650f0d35e842c4bf8a5e59d5da005a50d56b6a'
BASELINE_SHA256 = '60381bce71f307f92c847f2abb0025e66a6cab351ee510a92052077bc579c509'
DEFAULT_REVIEW = ROOT / 'assets/translation/fly12116-reviewed.json'
DEFAULT_BASELINE = ROOT / 'assets/auto-history/translations' / (BASELINE_SHA256 + '.arsc')

PUBLIC_BASELINE_FIELDS = frozenset({
    'schema', 'source_sha256', 'version', 'version_code', 'prior_translation_sha256',
    'reviewed', 'machine', 'unresolved', 'complete', 'raw_text_resources',
    'composition_text_resources', 'preserved_composition_resources',
    'excluded_integer_arrays', 'preserved_raw_resources', 'source_package',
    'embedded_resources', 'separate_overlay_required',
})


def coverage_complete(coverage):
    """Do not promote selection/composition counts into semantic review proof."""
    return (isinstance(coverage, dict) and coverage.get('complete') is True
            and type(coverage.get('reviewed_resources')) is int
            and coverage['reviewed_resources'] == 11994
            and type(coverage.get('reviewed_groups')) is int
            and coverage['reviewed_groups'] == 8786
            and type(coverage.get('unresolved')) is int and coverage['unresolved'] == 0)


def _public_evidence(value):
    if isinstance(value, dict):
        for child in value.values():
            _public_evidence(child)
    elif isinstance(value, list):
        for child in value:
            _public_evidence(child)
    elif isinstance(value, str) and (value.startswith('/') or PureWindowsPath(value).is_absolute()):
        raise ValueError('Public review metadata contains an absolute private path')


def reviewed_metadata(baseline, review, report, catalog_sha256):
    """Keep composition provenance while adding separately validated coverage."""
    coverage = review.get('coverage')
    if not coverage_complete(coverage):
        raise ValueError('Semantic review coverage is not complete: expected 11994 resources / 8786 groups')
    _public_evidence(coverage)
    if (baseline.get('source_sha256') != SOURCE_SHA256
            or baseline.get('resource_sha256') != BASELINE_SHA256
            or baseline.get('version') != '1.21.16' or baseline.get('version_code') != 3132286
            or report.get('status') != 'PASS' or report.get('source_sha256') != SOURCE_SHA256
            or report.get('baseline_translation_sha256') != BASELINE_SHA256
            or report.get('revision') != review.get('revision')
            or report.get('resource_ids_and_configurations_preserved') is not True
            or report.get('unrelated_values_and_styles_unchanged') is not True):
        raise ValueError('Reviewed metadata evidence mismatch')
    metadata = {key: copy.deepcopy(value) for key, value in baseline.items() if key in PUBLIC_BASELINE_FIELDS}
    metadata.update({'schema': 1, 'source_sha256': SOURCE_SHA256,
        'resource_sha256': report['translation_sha256'], 'bytes': report['bytes'],
        'translation_revision': review['revision'], 'semantic_review': copy.deepcopy(coverage),
        'semantic_review_catalog_sha256': catalog_sha256,
        'semantic_review_baseline_manifest_sha256': review['baseline_manifest_sha256'],
        'semantic_review_baseline_translation_sha256': BASELINE_SHA256,
        'semantic_review_corrected_resources': report['corrected_resources'],
        'all_machine_output_semantically_reviewed': True,
        'resource_ids_and_configurations_preserved': True,
        'aapt2_parse': 'PASS', 'aapt2_resource_id_inventory_identical': True,
        'separate_overlay_required': False, 'signed': False, 'installed': False})
    return metadata


def verify_locked_labels(table):
    from scripts.build_12116_translation import english, resource_ids
    from rc2vi.device_unbind_wording import TRANSLATIONS as unbind
    from rc2vi.cellular_wording import TRANSLATIONS as cellular
    from rc2vi.flyaway_wording import TRANSLATIONS as flyaway, FIRMWARE_TRANSLATIONS
    _, ids, _ = resource_ids(table)
    values = english(table, {value: key for key, value in ids.items()})
    expected = {**unbind, 'firmware_update_name_dongle': cellular['firmware_update_name_dongle'],
        **{name: {**flyaway, **FIRMWARE_TRANSLATIONS}[name] for name in ('me_device_info_value_added_loss_certification_btn',
            'firmware_update_click_check_upgrade_device_is_not_latest_version_dialog_content',
            'firmware_update_detail_new_firmware_version_title')}}
    for name, text in expected.items():
        if values.get(('string', name)) != [[None, 3, {'text': text, 'spans': []}]]:
            raise ValueError('User-approved label changed: ' + name)
    return {'status': 'PASS', 'labels_checked': len(expected)}


def _validate_paths(source, baseline, reviewed, output, work):
    inputs = {Path(path).resolve() for path in (source, baseline, reviewed)}
    output, work = Path(output).resolve(), Path(work).resolve()
    destinations = {output / 'vietnamese.arsc', output / 'manifest.json', work / 'build-report.json',
                    work / 'baseline-embedded.apk', work / 'reviewed-embedded.apk',
                    work / 'standalone-readback.apk'}
    if (destinations & inputs or output in inputs or work in inputs
            or any(path.is_relative_to(work) or path.is_relative_to(output) for path in inputs)):
        raise ValueError('Output/work would overwrite a verified input')


def _assert_inputs_unchanged(paths, before):
    after = {name: sha256_file(path) for name, path in paths.items()}
    if after != before:
        raise ValueError('An input changed while applying the semantic review')
    return {'status': 'PASS', 'before': before, 'after': after}


def _readback_apk(path, manifest, resources):
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('AndroidManifest.xml', manifest)
        archive.writestr('resources.arsc', resources)


def postcompile_review(source_resources, baseline, review_path=None):
    """Optional exact-baseline hook; a present but stale review always fails."""
    review_path = Path(review_path) if review_path is not None else DEFAULT_REVIEW
    if not review_path.is_file():
        return baseline, None
    raw = review_path.read_bytes()
    review = json.loads(raw)
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA256:
        raise ValueError('Generated translation differs from the reviewed 60381 baseline')
    if not coverage_complete(review.get('coverage')):
        raise ValueError('Semantic review coverage is incomplete')
    manifest_path = DEFAULT_BASELINE.with_suffix('.manifest.json')
    if sha256_file(manifest_path) != review.get('baseline_manifest_sha256'):
        raise ValueError('Pinned baseline manifest hash mismatch')
    translated, report = apply_reviewed_table(source_resources, baseline, review, source_sha256=SOURCE_SHA256)
    verify_locked_labels(Table(translated))
    return translated, {'catalog': review, 'catalog_sha256': hashlib.sha256(raw).hexdigest(),
                        'report': report, 'review_path': review_path}


def main(argv=None):
    from scripts.build_12116_translation import (snapshot, resource_ids, english,
        compare_resource_values, verify_untouched_values, atomic_json)
    from scripts.build_feature_candidate import parse_resource_dump
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--baseline-manifest', type=Path,
                        help='Pinned baseline provenance; defaults to BASELINE.manifest.json')
    parser.add_argument('--reviewed', type=Path, default=DEFAULT_REVIEW)
    parser.add_argument('--output', type=Path, required=True, help='Explicit staging output directory')
    parser.add_argument('--work', type=Path, required=True, help='Explicit host-only validation directory')
    args = parser.parse_args(argv)
    args.baseline_manifest = args.baseline_manifest or args.baseline.with_suffix('.manifest.json')
    _validate_paths(args.source, args.baseline, args.reviewed, args.output, args.work)
    _validate_paths(args.source, args.baseline_manifest, args.reviewed, args.output, args.work)
    paths = {'source_apk': args.source, 'baseline_translation': args.baseline,
             'baseline_manifest': args.baseline_manifest, 'review_catalog': args.reviewed}
    before = {name: sha256_file(path) for name, path in paths.items()}
    if before['source_apk'] != SOURCE_SHA256 or before['baseline_translation'] != BASELINE_SHA256:
        raise ValueError('Pinned stock APK or archived translation hash mismatch')
    source = snapshot(args.source, SOURCE_SHA256)
    if source['identity'] != {'package': 'dji.go.v5', 'application': source['identity']['application'],
                              'version': '1.21.16', 'code': 3132286}:
        raise ValueError('Unexpected official RC2 Fly 1.21.16 identity')
    baseline = args.baseline.read_bytes()
    review = json.loads(args.reviewed.read_text(encoding='utf-8'))
    if review.get('baseline_manifest_sha256') != before['baseline_manifest']:
        raise ValueError('Pinned baseline manifest hash mismatch')
    baseline_metadata = json.loads(args.baseline_manifest.read_text(encoding='utf-8'))
    if (baseline_metadata.get('resource_sha256') != BASELINE_SHA256
            or baseline_metadata.get('bytes') != len(baseline)):
        raise ValueError('Baseline manifest does not describe the archived translation')
    if not coverage_complete(review.get('coverage')):
        raise ValueError('Semantic review coverage is incomplete')
    translated, standalone = apply_reviewed_table(source['raw'], baseline, review, source_sha256=SOURCE_SHA256)
    old_table, new_table = Table(baseline), Table(translated)
    _, old_ids, old_configs = resource_ids(old_table)
    _, new_ids, new_configs = resource_ids(new_table)
    if old_ids != new_ids or old_configs != new_configs or len(old_ids) != 11994:
        raise ValueError('Standalone translated resource inventory changed')
    allowed = {(entry['kind'], entry['name']) for entry in review['entries']}
    standalone_global = compare_resource_values(old_table, new_table, allowed)
    locked = verify_locked_labels(new_table)
    old_embedded, old_embed = embed(source['raw'], baseline)
    new_embedded, new_embed = embed(source['raw'], translated)
    if old_embed['embedded_resources'] != 11994 or new_embed['embedded_resources'] != 11994:
        raise ValueError('Translated resource count changed during embedding')
    embedded_global = compare_resource_values(Table(old_embedded), Table(new_embedded), allowed)
    translated_keys = set(english(old_table, {value: key for key, value in old_ids.items()}))
    stock_preservation = verify_untouched_values(source['table'], Table(new_embedded), translated_keys)
    verify_locked_labels(Table(new_embedded))
    args.work.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.source) as archive:
        manifest = archive.read('AndroidManifest.xml')
    for name, resources in [('baseline-embedded.apk', old_embedded), ('reviewed-embedded.apk', new_embedded),
                            ('standalone-readback.apk', translated)]:
        _readback_apk(args.work / name, manifest, resources)
    stage = args.work / 'utilities'
    stage.mkdir(parents=True, exist_ok=True)
    builder = TranslationBuilder(ROOT / 'assets', args.work / 'toolchain')
    _, _, aapt, _ = builder._utilities(stage)
    inventories = {}
    for name, path in [('stock', args.source), ('baseline', args.work / 'baseline-embedded.apk'),
                        ('reviewed', args.work / 'reviewed-embedded.apk'),
                        ('standalone', args.work / 'standalone-readback.apk')]:
        inventories[name] = parse_resource_dump(builder._run(aapt, 'dump', 'resources', '--no-values', path))
        if not inventories[name]:
            raise ValueError('AAPT2 failed to parse ' + name)
    if inventories['stock'] != inventories['baseline'] or inventories['stock'] != inventories['reviewed']:
        raise ValueError('AAPT2 embedded resource ID inventory changed')
    if inventories['standalone'] != new_ids:
        raise ValueError('AAPT2 standalone resource ID inventory mismatch')
    standalone_inventory_count = len(inventories['standalone'])
    guard = _assert_inputs_unchanged(paths, before)
    metadata = reviewed_metadata({**baseline_metadata, 'source_package': source['package'],
        'embedded_resources': new_embed['embedded_resources']}, review, standalone, before['review_catalog'])
    report = {**metadata, 'status': 'PASS', 'standalone': standalone,
        'standalone_global_comparison': standalone_global, 'embedded_global_comparison': embedded_global,
        'baseline_embedding': old_embed, 'reviewed_embedding': new_embed,
        'stock_preservation': stock_preservation, 'locked_labels': locked,
        'aapt2': {'status': 'PASS', 'embedded_inventory_identical': True,
                  'standalone_inventory_count': standalone_inventory_count},
        'input_hash_guard': guard, 'current_device_verified': False, 'usb_opened': False,
        'signed': False, 'installed': False}
    target = args.output / 'vietnamese.arsc'
    if target.exists() and target.read_bytes() != translated:
        raise FileExistsError('Refusing to overwrite a different staged translation')
    args.output.mkdir(parents=True, exist_ok=True)
    target.write_bytes(translated)
    atomic_json(args.output / 'manifest.json', metadata)
    atomic_json(args.work / 'build-report.json', report)
    _assert_inputs_unchanged(paths, before)
    print(json.dumps({'state': 'REVIEW_STAGED', 'status': 'PASS', 'resource_sha256': metadata['resource_sha256'],
        'bytes': metadata['bytes'], 'corrected_resources': standalone['corrected_resources'],
        'reviewed_resources': 11994, 'aapt2_parse': 'PASS', 'current_device_verified': False}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
