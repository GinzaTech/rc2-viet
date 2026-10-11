"""Keep the legacy v2 loader input alongside the independently signed v3 candidate.

The selected Android 11 v3 signature must be verified externally after this operation.
This does not claim the retained v2 signature is valid for changed APK content.
"""
import struct
from pathlib import Path

V2 = 0x7109871a


def _parts(data: bytes) -> tuple[int, int, int, list[tuple[int, bytes]]]:
    end = data.rfind(b'PK\x05\x06', max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        raise ValueError('Malformed ZIP end record')
    if end + 22 + struct.unpack_from('<H', data, end + 20)[0] != len(data):
        raise ValueError('Malformed ZIP comment length')
    central = struct.unpack_from('<I', data, end + 16)[0]
    if central < 24 or central > end or data[central - 16:central] != b'APK Sig Block 42':
        raise ValueError('Malformed APK signing block footer')
    size = struct.unpack_from('<Q', data, central - 24)[0]
    start = central - size - 8
    if start < 0 or struct.unpack_from('<Q', data, start)[0] != size:
        raise ValueError('Malformed APK signing block size')
    position, entries = start + 8, []
    while position < central - 24:
        length = struct.unpack_from('<Q', data, position)[0]
        position += 8
        if length < 4 or position + length > central - 24:
            raise ValueError('Malformed signing block entry')
        identifier = struct.unpack_from('<I', data, position)[0]
        if any(key == identifier for key, _ in entries):
            raise ValueError('Malformed duplicate signing block ID')
        entries.append((identifier, data[position + 4:position + length]))
        position += length
    if position != central - 24:
        raise ValueError('Malformed signing block alignment')
    return start, central, end, entries


def block_entries(data: bytes) -> dict[int, bytes]:
    return dict(_parts(data)[3])


def replace_v2_block(original: bytes, candidate: bytes) -> bytes:
    source = block_entries(original)
    if V2 not in source:
        raise ValueError('Original v2 signing entry missing')
    start, central, end, entries = _parts(candidate)
    if 0xf05368c0 not in dict(entries):
        raise ValueError('Candidate v3 signing entry missing')
    replaced = [(key, source[V2] if key == V2 else value) for key, value in entries]
    if V2 not in dict(replaced):
        replaced.insert(0, (V2, source[V2]))
    pairs = b''.join(struct.pack('<QI', len(value) + 4, key) + value for key, value in replaced)
    size = len(pairs) + 24
    block = struct.pack('<Q', size) + pairs + struct.pack('<Q', size) + b'APK Sig Block 42'
    output = bytearray(candidate[:start] + block + candidate[central:])
    delta = len(block) - (central - start)
    struct.pack_into('<I', output, end + delta + 16, start + len(block))
    return bytes(output)


def _path_parts(path: Path):
    """Read only the signing block and central directory, bounded to 64 MiB."""
    size = path.stat().st_size
    with path.open('rb') as stream:
        stream.seek(max(0,size-65557)); tail=stream.read()
        marker=tail.rfind(b'PK\x05\x06')
        if marker<0 or marker+22>len(tail): raise ValueError('Malformed ZIP end record')
        end=max(0,size-65557)+marker
        if end+22+struct.unpack_from('<H',tail,marker+20)[0]!=size:
            raise ValueError('Malformed ZIP comment')
        central=struct.unpack_from('<I',tail,marker+16)[0]
        if not 24<=central<=end: raise ValueError('Malformed signing offset')
        stream.seek(central-24); footer=stream.read(24)
        if footer[8:]!=b'APK Sig Block 42': raise ValueError('Signing block missing')
        length=struct.unpack_from('<Q',footer)[0]; start=central-length-8
        if start<0 or size-start>64*1024*1024: raise ValueError('Signing tail exceeds bound')
        stream.seek(start); data=bytearray(stream.read(size-start))
    struct.pack_into('<I',data,end-start+16,central-start)
    _,_,_,items=_parts(bytes(data))
    return start,central,end,items


def block_entries_path(path: Path) -> dict[int, bytes]:
    return dict(_path_parts(Path(path))[3])


def preserve_v2_file(original: Path, signed: Path, output: Path, cancel=None):
    """Keep the protected loader input without loading whole APKs in memory."""
    from rc2vi.hud_tools import check_cancel
    original,signed,output=map(Path,(original,signed,output))
    if output.exists(): raise FileExistsError('Signing output already exists')
    source=block_entries_path(original)
    if V2 not in source: raise ValueError('Original loader v2 missing')
    start,central,end,items=_path_parts(signed)
    if 0xf05368c0 not in dict(items): raise ValueError('Selected v3 signature missing')
    replaced=[(key,source[V2] if key==V2 else value) for key,value in items]
    if V2 not in dict(replaced): replaced.insert(0,(V2,source[V2]))
    pairs=b''.join(struct.pack('<QI',len(value)+4,key)+value for key,value in replaced)
    length=len(pairs)+24
    block=struct.pack('<Q',length)+pairs+struct.pack('<Q',length)+b'APK Sig Block 42'
    with signed.open('rb') as inp,output.open('xb') as out:
        remaining=start
        while remaining:
            check_cancel(cancel);chunk=inp.read(min(1024*1024,remaining))
            if not chunk: raise ValueError('Truncated signed APK')
            out.write(chunk);remaining-=len(chunk)
        out.write(block);inp.seek(central);tail=bytearray(inp.read())
        struct.pack_into('<I',tail,end-central+16,start+len(block));out.write(tail)
    return output
