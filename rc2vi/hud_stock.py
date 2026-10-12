"""Recover exact stock bytes using unchanged APK payloads and a pinned small template."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED

from .core import SUPPORTED_APK, RC_12110_APK
from .hud_backup import guard_path
from .hud_tools import HudCancelled, check_cancel, sha256_file, _json_object

SOURCE_RECOVERY_SHA256 = '746b41562bc1a48aa59285b8eb2a46b55ac180567cd7627b880dd26c4728d4d6'
SOURCE_RECOVERY_12110_SHA256 = 'c296e4f326c7a3c80e2bba5474d986a1d5287457eca8e5e021fefcd0aa8ff9e7'
CHANGED = frozenset({'AndroidManifest.xml','classes.dex'})
CHUNK=1024*1024
MAX_LITERAL=32*1024*1024
ROW_KEYS={'name','header_offset','header_size','header_literal','compressed_size',
          'file_size','crc','method','compressed_sha256','payload_literal',
          'suffix_literal','suffix_size'}


def safe_name(name):
    if (not isinstance(name,str) or not name or len(name)>4096 or '\\' in name
            or ':' in name or name.startswith('/') or '\0' in name
            or '..' in name.split('/')):
        raise ValueError('Unsafe APK entry name')
    return name


def entries(archive):
    result=archive.infolist();names=[safe_name(e.filename) for e in result]
    if not result or len(result)>50000 or len(names)!=len(set(names)):
        raise ValueError('Invalid or duplicate APK entries')
    for entry in result:
        if (entry.flag_bits&1 or entry.volume or entry.compress_type not in (0,8)
                or entry.header_offset<0 or entry.header_offset>=0xffffffff
                or entry.compress_size>=0xffffffff or entry.file_size>=0xffffffff):
            raise ValueError('Encrypted, multidisk, ZIP64 or unsupported APK entry')
    return result


def compressed_offset(archive,entry):
    archive.fp.seek(entry.header_offset);head=archive.fp.read(30)
    if len(head)!=30 or head[:4]!=b'PK\x03\x04':raise ValueError('Invalid local ZIP header')
    flags,method=struct.unpack_from('<HH',head,6)
    if flags&1 or method!=entry.compress_type:raise ValueError('Invalid local ZIP method')
    name_size,extra_size=struct.unpack_from('<HH',head,26)
    name=archive.fp.read(name_size);extra=archive.fp.read(extra_size)
    expected=entry.filename.encode('utf-8' if flags&0x800 else 'cp437')
    if name!=expected or len(extra)!=extra_size:raise ValueError('Invalid local ZIP name')
    pos=0
    while pos<len(extra):
        if not any(extra[pos:]):pos=len(extra);break
        if pos+4>len(extra):raise ValueError('Invalid local extra field')
        identifier,size=struct.unpack_from('<HH',extra,pos)
        if identifier==1:raise ValueError('ZIP64 APK entry unsupported')
        pos+=4+size
    if pos!=len(extra):raise ValueError('Invalid local extra size')
    offset=entry.header_offset+30+name_size+extra_size
    if offset+entry.compress_size>archive.start_dir:raise ValueError('Overlapping ZIP payload')
    return offset


def recipe_value(template, *, expected_digest=None, changed=CHANGED,
                 max_literal=MAX_LITERAL, schema=1):
    if expected_digest is None: expected_digest = SUPPORTED_APK
    if template.namelist()!=['recipe.json','literals.bin']:
        raise ValueError('Invalid source recovery template entries')
    if template.getinfo('recipe.json').file_size>8*1024*1024:
        raise ValueError('Oversized source recovery template recipe')
    value=_json_object(template.read('recipe.json'))
    required={'schema','stock_sha256','stock_size','literal_size','entries','prefix_size','prefix_literal'}
    if schema == 2: required |= {'changed'}
    if set(value)!=required or type(value['schema']) is not int or value['schema']!=schema:
        raise ValueError('Invalid stock recovery recipe schema')
    if value['stock_sha256']!=expected_digest:raise ValueError('Unpinned stock recovery source')
    if schema == 2 and value['changed'] != sorted(changed): raise ValueError('Invalid changed inventory')
    for key,limit in [('stock_size',1536*1024*1024 if schema == 2 else 1024*1024*1024),('literal_size',max_literal),('prefix_size',max_literal)]:
        if type(value[key]) is not int or not 0<=value[key]<=limit:raise ValueError('Invalid recipe size')
    if not value['stock_size'] or value['literal_size']!=template.getinfo('literals.bin').file_size:
        raise ValueError('Invalid template literal size')
    rows=value['entries']
    if not isinstance(rows,list) or not 1<=len(rows)<=50000:raise ValueError('Invalid recipe entries')
    seen=set();output=value['prefix_size'];literal=0
    if value['prefix_literal']!=0:raise ValueError('Invalid recipe prefix')
    literal+=value['prefix_size']
    for row in rows:
        if not isinstance(row,dict) or set(row)!=ROW_KEYS:raise ValueError('Invalid recipe entry')
        name=safe_name(row['name'])
        if name in seen:raise ValueError('Duplicate recipe entry')
        seen.add(name)
        for key in ROW_KEYS-{'name','compressed_sha256'}:
            if type(row[key]) is not int:raise ValueError('Invalid recipe integer')
        if (row['header_offset']!=output or row['header_literal']!=literal
                or not 30<=row['header_size']<=131100 or not 0<=row['compressed_size']<0xffffffff
                or not 0<=row['file_size']<0xffffffff or not 0<=row['crc']<2**32
                or row['method'] not in (0,8) or row['suffix_size']<0
                or not isinstance(row['compressed_sha256'],str)
                or not re.fullmatch('[0-9a-f]{64}',row['compressed_sha256'])):
            raise ValueError('Invalid recipe layout or metadata')
        literal+=row['header_size']
        if name in changed:
            if row['payload_literal']!=literal:raise ValueError('Invalid changed payload literal')
            literal+=row['compressed_size']
        elif row['payload_literal']!=-1:raise ValueError('Unexpected payload literal')
        if row['suffix_literal']!=literal:raise ValueError('Invalid recipe suffix')
        literal+=row['suffix_size']
        output+=row['header_size']+row['compressed_size']+row['suffix_size']
    if output!=value['stock_size'] or literal!=value['literal_size'] or not changed<=seen:
        raise ValueError('Invalid completed recipe layout')
    return value


def stream_copy(source,target,size,cancel=None,expected=None):
    digest=hashlib.sha256();remaining=size
    while remaining:
        check_cancel(cancel);part=source.read(min(CHUNK,remaining))
        if not part:raise ValueError('Truncated recovery input')
        target.write(part);digest.update(part);remaining-=len(part)
    if expected and digest.hexdigest()!=expected:raise ValueError('Changed compressed APK payload')


def recover_stock(installed_apk,template,output,cancel=None,expected_digest=None):
    check_cancel(cancel)
    if expected_digest is None:expected_digest=SUPPORTED_APK
    installed_apk,template,output=map(guard_path,(installed_apk,template,output))
    if output.exists():raise FileExistsError('Stock recovery never overwrites existing files')
    pins={SUPPORTED_APK:SOURCE_RECOVERY_SHA256,RC_12110_APK:SOURCE_RECOVERY_12110_SHA256}
    if expected_digest not in pins or sha256_file(template,cancel)!=pins[expected_digest]:
        raise ValueError('Source recovery template hash mismatch')
    temporary=None
    try:
        with ZipFile(template) as capsule,ZipFile(installed_apk) as current:
            recipe=recipe_value(capsule,expected_digest=expected_digest);source_entries=entries(current)
            expected={row['name'] for row in recipe['entries']}
            if set(current.namelist()) not in (expected,expected|{'classes23.dex'}):
                raise ValueError('Unexpected APK entry set')
            spans=[]
            for entry in source_entries:
                start=compressed_offset(current,entry)
                spans.append((entry.header_offset,start+entry.compress_size))
            spans.sort()
            if any(left[1]>right[0] for left,right in zip(spans,spans[1:])):
                raise ValueError('Overlapping APK entries')
            for row in recipe['entries']:
                if row['name'] in CHANGED:continue
                entry=current.getinfo(row['name'])
                if (entry.compress_size,entry.file_size,entry.CRC,entry.compress_type)!=(
                        row['compressed_size'],row['file_size'],row['crc'],row['method']):
                    raise ValueError('Changed compressed entry metadata')
            with tempfile.NamedTemporaryFile(prefix='.stock-recovery-',dir=output.parent,delete=False) as target:
                temporary=Path(target.name)
                with capsule.open('literals.bin') as literals:
                    stream_copy(literals,target,recipe['prefix_size'],cancel)
                    for row in recipe['entries']:
                        stream_copy(literals,target,row['header_size'],cancel)
                        if row['name'] in CHANGED:
                            stream_copy(literals,target,row['compressed_size'],cancel,row['compressed_sha256'])
                        else:
                            current.fp.seek(compressed_offset(current,current.getinfo(row['name'])))
                            stream_copy(current.fp,target,row['compressed_size'],cancel,row['compressed_sha256'])
                        stream_copy(literals,target,row['suffix_size'],cancel)
                    if literals.read(1):raise ValueError('Trailing recovery literals')
            check_cancel(cancel)
            if temporary.stat().st_size!=recipe['stock_size'] or sha256_file(temporary,cancel)!=expected_digest:
                raise ValueError('Recovered stock APK hash mismatch')
            guard_path(output);guard_path(temporary);check_cancel(cancel)
            os.link(temporary,output)
            return output
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
