"""Create a small deterministic recovery template from the exact supported stock APK."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED

from rc2vi import hud_stock as api
from rc2vi.hud_backup import guard_path
from rc2vi.hud_tools import sha256_file


def bundle_stock(stock,output):
    stock,output=map(guard_path,(stock,output))
    if output.exists():raise FileExistsError('Recovery template already exists')
    if sha256_file(stock)!=api.SUPPORTED_APK:raise ValueError('Only exact supported stock accepted')
    literals=bytearray();rows=[]
    def literal(data):
        offset=len(literals);literals.extend(data)
        if len(literals)>api.MAX_LITERAL:raise ValueError('Stock template too large')
        return offset
    with ZipFile(stock) as archive:
        entries=sorted(api.entries(archive),key=lambda e:e.header_offset)
        archive.fp.seek(0);prefix_size=entries[0].header_offset
        literal(archive.fp.read(prefix_size))
        for index,entry in enumerate(entries):
            payload=api.compressed_offset(archive,entry)
            archive.fp.seek(entry.header_offset);header=archive.fp.read(payload-entry.header_offset)
            row={'name':entry.filename,'header_offset':entry.header_offset,'header_size':len(header),
                 'header_literal':literal(header),'compressed_size':entry.compress_size,
                 'file_size':entry.file_size,'crc':entry.CRC,'method':entry.compress_type,
                 'payload_literal':len(literals) if entry.filename in api.CHANGED else -1}
            digest=hashlib.sha256();remaining=entry.compress_size
            while remaining:
                part=archive.fp.read(min(api.CHUNK,remaining))
                if not part:raise ValueError('Truncated stock compressed payload')
                digest.update(part);remaining-=len(part)
                if entry.filename in api.CHANGED:literal(part)
            row['compressed_sha256']=digest.hexdigest()
            end=payload+entry.compress_size
            next_offset=entries[index+1].header_offset if index+1<len(entries) else stock.stat().st_size
            if next_offset<end:raise ValueError('Overlapping stock entries')
            row['suffix_size']=next_offset-end;row['suffix_literal']=literal(archive.fp.read(next_offset-end))
            rows.append(row)
    recipe={'schema':1,'stock_sha256':api.SUPPORTED_APK,'stock_size':stock.stat().st_size,
            'literal_size':len(literals),'entries':rows,'prefix_size':prefix_size,'prefix_literal':0}
    with ZipFile(output,'x',ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in [('recipe.json',json.dumps(recipe,sort_keys=True,separators=(',',':')).encode()),
                          ('literals.bin',bytes(literals))]:
            info=ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
            archive.writestr(info,data,compresslevel=9)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stock',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();bundle_stock(args.stock,args.output)
    print(json.dumps({'sha256':sha256_file(args.output),'bytes':args.output.stat().st_size}))


if __name__=='__main__':main()
