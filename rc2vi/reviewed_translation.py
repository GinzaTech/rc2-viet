"""Apply exact-source semantic review without rebuilding resource identities.

The review catalog changes string values only. Shared pool entries are appended,
never edited in place, so an unrelated resource cannot inherit a correction.
"""
from collections import Counter
from bisect import bisect_left
import hashlib
from html.parser import HTMLParser
import re
import struct
import xml.etree.ElementTree as ET

from . import translation_catalog as tc
from .gmail_wording import approved_equivalent as approved_gmail_equivalent
from .resource_embed import Table
from .translation_complete import _escape, _validate, _literal_offsets

# Explicit comparison-only equivalents for reviewed product spelling and UI
# abbreviations. Raw English guards are still compared before these are used.
TOKEN_EQUIVALENTS = frozenset({
    ('wifi', 'Wi-Fi'), ('Quick Shot', 'QuickShots'),
    ('HyperLapse', 'Hyperlapse'), ('hyperlapse', 'Hyperlapse'),
    ('N/A', 'không khả dụng'), ('焦点跟随', 'FocusTrack'), ('大疆', 'DJI'),
})


class _Markup(HTMLParser):
    VOID = frozenset({'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                      'link', 'meta', 'param', 'source', 'track', 'wbr'})

    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.line_offsets = [0] + [match.end() for match in re.finditer('\n', text)]
        literals = _literal_offsets(text, True)
        neutral = ''.join('\ue001' if index in literals else char for index, char in enumerate(text))
        self.formats = tc._formats(neutral)
        self.format_offsets = [row[0] for row in self.formats]
        self.tokens = []
        self.stack = []
        self.scopes = Counter()

    def _offset(self):
        line, column = self.getpos()
        return self.line_offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        self.tokens.append(('start', self.get_starttag_text()))
        if tag not in self.VOID:
            self.stack.append((tag, tuple(sorted(attrs))))

    def handle_startendtag(self, tag, attrs):
        self.tokens.append(('single', self.get_starttag_text()))

    def handle_endtag(self, tag):
        start = self._offset()
        self.tokens.append(('end', self.text[start:self.text.find('>', start) + 1]))
        # Existing fragments may be unclosed or mismatched. Keep their exact
        # token sequence and a deterministic recovered scope; do not repair the
        # original HTML or permit a translation to introduce a different tree.
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        start = self._offset()
        end = start + len(data)
        for left, right, argument, spec in self.formats[
                bisect_left(self.format_offsets, start):bisect_left(self.format_offsets, end)]:
            if right <= end:
                self.scopes[tuple(self.stack), argument, spec] += 1

    def handle_comment(self, data):
        self.tokens.append(('comment', data))

    def handle_decl(self, decl):
        self.tokens.append(('declaration', decl))

    def handle_pi(self, data):
        self.tokens.append(('processing_instruction', data))


def _markup(text):
    parser = _Markup(text)
    parser.feed(text)
    parser.close()
    return tuple(parser.tokens), parser.scopes if parser.tokens else Counter()


def _scope(text, spans):
    """Keep the same styles/links and the formatted arguments inside each span."""
    encoded = text.encode('utf-16le')
    result = Counter()
    for tag, first, last in spans:
        if (not isinstance(tag, str) or type(first) is not int or type(last) is not int
                or first < 0 or last < first or 2 * (last + 1) > len(encoded)):
            raise ValueError('Invalid reviewed style bounds')
        selected = encoded[2 * first:2 * (last + 1)].decode('utf-16le')
        formats = Counter((arg, spec) for _, _, arg, spec in tc._formats(selected))
        result[tag, tuple(sorted(formats.items()))] += 1
    return result


def _text_contract(name, original, translated, token_equivalents=()):
    if (set(original) != {'text', 'spans'} or set(translated) != {'text', 'spans'}
            or not isinstance(translated['text'], str) or not isinstance(translated['spans'], list)):
        raise ValueError('Invalid reviewed string content')
    before, after = original['text'], translated['text']
    normalized = before
    if not isinstance(token_equivalents, (tuple, list)) or len(token_equivalents) > 8:
        raise ValueError('Invalid reviewed lexical equivalents')
    for pair in token_equivalents:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or not all(isinstance(value, str) for value in pair)
                or (tuple(pair) not in TOKEN_EQUIVALENTS
                    and not approved_gmail_equivalent(name, before, pair))
                or pair[0] not in before):
            raise ValueError('Unapproved reviewed lexical equivalent')
        normalized = normalized.replace(pair[0], pair[1])
    source = ET.Element('string', {'name': name})
    candidate = ET.Element('string', {'name': name})
    source.text = '"' + _escape(normalized) + '"'
    candidate.text = '"' + _escape(after) + '"'
    _validate(source, candidate, strict=True, allow_unchanged=True)
    if _markup(before) != _markup(after):
        raise ValueError('Reviewed literal markup changed')
    if _scope(before, original['spans']) != _scope(after, translated['spans']):
        raise ValueError('Reviewed styles or link scopes changed')


def _values(table, positions, id_names):
    result = []
    for key, (typ, index) in table.values(positions).items():
        if typ == 3:
            value = {'text': table.pool.strings[index], 'spans': [
                [table.pool.strings[tag], first, last] for tag, first, last in table.pool.styles[index]]}
        elif typ in (1, 2, 7, 8) and index in id_names:
            value = {'reference': list(id_names[index])}
        else:
            value = {'value': index}
        result.append([key, typ, value])
    return result


def _shape(value):
    if not isinstance(value, list) or not value:
        raise ValueError('Missing reviewed resource values')
    keys = []
    for row in value:
        if (not isinstance(row, list) or len(row) != 3 or
                (row[0] is not None and type(row[0]) is not int) or type(row[1]) is not int
                or not isinstance(row[2], dict)):
            raise ValueError('Invalid reviewed resource values')
        keys.append(row[0])
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate reviewed bag key')
    return [(row[0], row[1]) for row in value]


def apply_reviewed_table(source_bytes, baseline_bytes, review, *, source_sha256):
    """Return a corrected table and a bounded report from a verified stock input.

    The caller verifies the complete source APK digest before passing its resource
    bytes and digest here. Every corrected name also has an exact English guard.
    """
    from scripts.build_12116_translation import resource_ids, english, compare_resource_values
    if (not isinstance(review, dict) or review.get('schema') != 1
            or review.get('source_sha256') != source_sha256
            or review.get('source_resources_sha256') != hashlib.sha256(source_bytes).hexdigest()
            or review.get('baseline_translation_sha256') != hashlib.sha256(baseline_bytes).hexdigest()
            or not isinstance(review.get('revision'), str)
            or not isinstance(review.get('entries'), list) or not 0 < len(review['entries']) <= 25000):
        raise ValueError('Review source, baseline or catalog envelope mismatch')
    source, table = Table(source_bytes), Table(baseline_bytes)
    _, ids, _ = resource_ids(source)
    source_values = english(source, {value: key for key, value in ids.items()})
    _, baseline_ids, _ = resource_ids(table)
    baseline_names = {value: key for key, value in baseline_ids.items()}
    changes = {}
    for row in review['entries']:
        if not isinstance(row, dict):
            raise ValueError('Invalid review entry')
        key = row.get('kind'), row.get('name')
        if (key[0] not in {'string', 'array', 'plurals'} or not isinstance(key[1], str)
                or not tc.NAME.fullmatch(key[1]) or key in changes
                or not isinstance(row.get('reason'), str) or not row['reason'].strip()):
            raise ValueError('Invalid or duplicate reviewed identity')
        original, previous, translated = (row.get(name) for name in (
            'source_contract', 'previous_contract', 'translation_contract'))
        if source_values.get(key) != original:
            raise ValueError('Reviewed English contract changed: ' + key[1])
        old_shape, new_shape = _shape(previous), _shape(translated)
        if old_shape != new_shape or _shape(original) != new_shape:
            raise ValueError('Reviewed resource shape changed: ' + key[1])
        for before, old, after in zip(original, previous, translated):
            if before[1] == 3:
                _text_contract(key[1], before[2], after[2], row.get('token_equivalents', ()))
            elif old != after:
                raise ValueError('Non-string reviewed value changed: ' + key[1])
        if previous == translated:
            raise ValueError('Review contains an unchanged correction: ' + key[1])
        changes[key] = (previous, translated)
    existing = {value: i for i, value in enumerate(table.pool.strings)}
    appended = {}

    def add_string(text, spans):
        identity = text, tuple(tuple(span) for span in spans)
        if identity in appended:
            return appended[identity]
        compiled = []
        for tag, first, last in spans:
            if tag not in existing:
                existing[tag] = len(table.pool.strings)
                table.pool.strings.append(tag)
                table.pool.styles.append(())
            compiled.append((existing[tag], first, last))
        index = len(table.pool.strings)
        table.pool.strings.append(text)
        table.pool.styles.append(tuple(compiled))
        appended[identity] = index
        return index

    found, configurations, value_count = set(), 0, 0
    for key, config, positions in table.entries():
        if key not in changes:
            continue
        previous, translated = changes[key]
        if _values(table, positions, baseline_names) != previous:
            raise ValueError('Previous reviewed value/config changed: ' + key[1])
        for bag, typ, content in translated:
            if typ == 3:
                pos = positions[bag]
                struct.pack_into('<I', table.data, pos + 4, add_string(content['text'], content['spans']))
                value_count += 1
        found.add(key)
        configurations += 1
    if found != set(changes):
        raise ValueError('Reviewed names missing from baseline')
    result = table.build()
    rebuilt = Table(result)
    verified = set()
    for key, _, positions in rebuilt.entries():
        if key in changes:
            if _values(rebuilt, positions, baseline_names) != changes[key][1]:
                raise ValueError('Reviewed compiled readback failed: ' + key[1])
            verified.add(key)
    if verified != found:
        raise ValueError('Reviewed compiled inventory changed')
    comparison = compare_resource_values(Table(baseline_bytes), rebuilt, found)
    return result, {'status': 'PASS', 'revision': review['revision'],
        'corrected_resources': len(found), 'corrected_configurations': configurations,
        'corrected_string_values': value_count, 'source_sha256': source_sha256,
        'baseline_translation_sha256': review['baseline_translation_sha256'],
        'translation_sha256': hashlib.sha256(result).hexdigest(), 'bytes': len(result),
        'resource_ids_and_configurations_preserved': comparison['resource_ids_and_configurations_preserved'],
        'unrelated_values_and_styles_unchanged': comparison['unrelated_values_and_styles_unchanged'],
        'resource_configurations_checked': comparison['resource_configurations_checked']}
