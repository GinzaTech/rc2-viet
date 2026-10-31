"""Localize audited presentation sites while preserving identical protocol literals."""
from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path


_METHOD = re.compile(r'(?ms)^\.method ([^\n]+)\n(.*?)^\.end method')
_CONST = re.compile(r'^    const-string(?:/jumbo)? ([vp]\d+), ("(?:[^"\\]|\\.)*")$', re.M)
_FORMAT = re.compile(r'%(?:\d+\$)?[-+#0,(<]*(?:\d+)?(?:\.\d+)?[tT]?[bBhHsScCdoxXeEfgGaAn%]|\{[A-Za-z0-9_]+\}')
_INVOKE = re.compile(r'^    invoke-\S+ \{([^}]+)\}, (L[^;]+;)->([^\n]+)$', re.M)
_USER_LINE_BREAKS=frozenset({'ToF_OFF — hand landing','ToF_OFF — посадка в руку'})


@dataclass(frozen=True)
class LiteralSite:
    class_name: str
    method: str
    ordinal: int
    source: str
    register: str
    start: int
    end: int
    value_start: int
    value_end: int
    body_end: int


def literal_sites(text):
    class_match = re.search(r'^\.class (?:[^\n]* )?(L[^;]+;)', text, re.M)
    if not class_match:
        raise ValueError('Missing feature class identity')
    result = []
    for body in _METHOD.finditer(text):
        for ordinal, hit in enumerate(_CONST.finditer(body[2])):
            try:
                value = json.loads(hit[2].replace("\\'", "'"))
            except json.JSONDecodeError as error:
                raise ValueError('Invalid feature string literal') from error
            result.append(LiteralSite(class_match[1], body[1], ordinal, value, hit[1],
                                      body.start(2)+hit.start(), body.start(2)+hit.end(),
                                      body.start(2)+hit.start(2), body.start(2)+hit.end(2), body.end(2)))
    return result


def _display_sink(tail, register):
    for hit in _INVOKE.finditer(tail):
        args = [item.strip() for item in hit[1].split(',')]
        if len(args) < 2 or args[1] != register:
            continue
        owner, signature = hit[2], hit[3]
        android_ui = owner.startswith(('Landroid/widget/', 'Landroid/app/', 'Landroid/view/'))
        method = signature.split('(', 1)[0]
        if android_ui and method in {'setText', 'setTitle', 'setMessage', 'setHint', 'setSummary',
                                     'setContentDescription', 'setPositiveButton', 'setNegativeButton',
                                     'setNeutralButton', 'makeText'}:
            return True
    return False


def presentation_sites(text):
    from scripts.feature_host_patch import ui_const_sites
    paired = ui_const_sites(text)
    result = []
    for site in literal_sites(text):
        if site.start in paired:
            result.append(site)
            continue
        full_tail = text[site.end:site.body_end]
        assignment = re.search(r'^    (?:const[^ ]*|move[^ ]*|new-instance|new-array|sget[^ ]*|iget[^ ]*) '
                               + re.escape(site.register) + r'(?:,|$)', full_tail, re.M)
        tail = full_tail[:assignment.start()] if assignment else full_tail
        if _display_sink(tail, site.register):
            result.append(site)
            continue
        array = re.search(r'^    aput-object ' + re.escape(site.register)
                          + r', ([vp]\d+), [vp]\d+$', tail, re.M)
        if array:
            register = array[1]
            array_tail = full_tail[array.end():]
            overwrite = re.search(r'^    (?:new-array|move-object[^ ]*|sget-object|iget-object) '
                                  + re.escape(register) + r'(?:,|$)', array_tail, re.M)
            if overwrite:
                array_tail = array_tail[:overwrite.start()]
            if any(hit[2] == 'Landroid/widget/ArrayAdapter;' and hit[3].startswith('<init>(')
                   and register in [arg.strip() for arg in hit[1].split(',')][1:]
                   for hit in _INVOKE.finditer(array_tail)):
                result.append(site)
    return result


def validate_wording(source, target, allow_line_break=False):
    if not isinstance(target, str) or not target or '\x00' in target or len(target) > 16000:
        raise ValueError('Invalid feature translation')
    if _FORMAT.findall(source) != _FORMAT.findall(target):
        raise ValueError('Feature format placeholders differ')
    edge = lambda value: (re.match(r'^\s*', value)[0], re.search(r'\s*$', value)[0])
    if allow_line_break and source not in _USER_LINE_BREAKS:
        raise ValueError('Unsupported feature line-break override')
    if edge(source) != edge(target) or (not allow_line_break and source.count('\n') != target.count('\n')):
        raise ValueError('Feature whitespace or line structure differs')


def apply_sites(text, records):
    sites = literal_sites(text)
    class_name = re.search(r'^\.class (?:[^\n]* )?(L[^;]+;)', text, re.M)[1]
    indexed = {(site.method, site.ordinal): site for site in sites}
    edits = []
    seen = set()
    matched = 0
    for record in records:
        if record.get('class') != class_name:
            continue
        key = (record.get('method'), record.get('ordinal'))
        if key in seen or key not in indexed:
            raise ValueError('Duplicate or unmatched feature UI site')
        seen.add(key)
        site = indexed[key]
        digest = hashlib.sha256(site.source.encode()).hexdigest()
        if digest != record.get('source_sha256'):
            raise ValueError('Feature UI site source hash differs')
        target = record.get('translation')
        validate_wording(site.source, target,record.get('allow_line_break',False))
        matched += 1
        if target != site.source:
            edits.append((site.value_start, site.value_end, json.dumps(target, ensure_ascii=True)))
    for start, end, replacement in reversed(sorted(edits)):
        text = text[:start] + replacement + text[end:]
    return text, {'matched': matched, 'translated': len(edits), 'class': class_name}


def load_catalog(path, reference_sha256):
    path = Path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Oversized feature site catalog')
    document = json.loads(path.read_text('utf-8'))
    records = document.get('sites')
    if (document.get('schema') != 1 or document.get('reference_sha256') != reference_sha256
            or not isinstance(records, list) or not 1 <= len(records) <= 10000):
        raise ValueError('Invalid feature site catalog identity')
    seen = set()
    for item in records:
        if (not isinstance(item, dict) or not isinstance(item.get('class'), str)
                or not re.fullmatch(r'L[A-Za-z0-9_/$]+;', item['class'])
                or not isinstance(item.get('method'), str) or '\n' in item['method']
                or type(item.get('ordinal')) is not int or not 0 <= item['ordinal'] < 10000
                or not isinstance(item.get('source_sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', item['source_sha256'])
                or not isinstance(item.get('source'), str)
                or hashlib.sha256(item['source'].encode()).hexdigest() != item['source_sha256']):
            raise ValueError('Invalid feature site source binding')
        identity = (item['class'], item['method'], item['ordinal'])
        if identity in seen:
            raise ValueError('Duplicate feature site catalog entry')
        seen.add(identity)
        if type(item.get('allow_line_break',False)) is not bool:
            raise ValueError('Invalid feature line-break review')
        validate_wording(item['source'], item.get('translation'),item.get('allow_line_break',False))
    return records
