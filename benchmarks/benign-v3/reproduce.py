"""Checksum-gated extraction and inference-free replay of a breadth archive."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile


def extract(archive,destination,expected):
    if not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:
        raise ValueError('Archive checksum differs from the published report')
    if destination.exists(): raise ValueError('Choose a new extraction directory')
    with zipfile.ZipFile(archive) as bundle:
        infos=bundle.infolist(); names=[info.filename for info in infos]
        if len(names)!=len(set(names)) or len(names)>10000 or 'ARTIFACTS.json' not in names:
            raise ValueError('Invalid archive inventory')
        if sum(info.file_size for info in infos)>128*1024*1024 or any(info.file_size>16*1024*1024 for info in infos):
            raise ValueError('Archive exceeds extraction bounds')
        for info in infos:
            path=PurePosixPath(info.filename)
            if (path.is_absolute() or '..' in path.parts or str(path)!=info.filename or '\\' in info.filename
                    or any(ord(char)<32 for char in info.filename) or info.is_dir()
                    or stat.S_ISLNK(info.external_attr>>16)):
                raise ValueError('Unsafe archive path or entry kind')
        inventory=json.loads(bundle.read('ARTIFACTS.json'))
        if inventory.get('benign') is not True or not isinstance(inventory.get('files'),dict): raise ValueError('Not a benign artifact inventory')
        if set(inventory['files'])!=set(names)-{'ARTIFACTS.json'}: raise ValueError('Archive members differ from inventory')
        for name,sha in inventory['files'].items():
            if not re.fullmatch('[0-9a-f]{64}',sha) or hashlib.sha256(bundle.read(name)).hexdigest()!=sha:
                raise ValueError('Artifact checksum differs: '+name)
        destination.mkdir(parents=True)
        for name in names:
            path=destination/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(bundle.read(name))
    return len(inventory['files'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('archive',type=Path); parser.add_argument('destination',type=Path)
    parser.add_argument('--sha256',required=True); parser.add_argument('--python',default=sys.executable); parser.add_argument('--extract-only',action='store_true')
    args=parser.parse_args(); destination=args.destination.resolve()
    count=extract(args.archive.resolve(),destination,args.sha256)
    print(json.dumps({'verified_artifacts':count,'directory':str(destination),'inference_requests':0}),flush=True)
    if not args.extract_only:
        subprocess.run([args.python,str(destination/'runner/experiment.py'),'regrade',str(destination)],check=True)
