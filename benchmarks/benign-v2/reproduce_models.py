"""Re-grade recorded benign model outputs offline, without repeating inference."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


def read(path): return json.loads(path.read_text())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def reproduce(root):
    artifact=read(root/'artifact-manifest.json')
    if artifact.get('benign') is not True: raise ValueError('Only explicitly benign archives')
    for name,expected in artifact['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts: raise ValueError('Unsafe archive member')
        source=root/relative; source.resolve().relative_to(root.resolve())
        if source.is_symlink() or digest(source)!=expected: raise ValueError('Evidence changed: '+name)
    protocol=read(root/'protocol.json'); scores=read(root/'scores.json')
    if protocol.get('benign') is not True or scores.get('benign') is not True: raise ValueError('Nonbenign evidence')
    expected=scores['records']
    with tempfile.TemporaryDirectory(prefix='repel-model-regrade-') as temporary:
        copy=Path(temporary)/'study'; copy.mkdir()
        for name in artifact['files']:
            path=copy/name; path.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(root/name,path)
        process=subprocess.run([sys.executable,str(copy/'runner/experiment.py'),'score',str(copy)],
                               capture_output=True,text=True,timeout=600)
        if process.returncode: raise RuntimeError('Regrading failed: '+process.stderr[-2000:])
        actual=read(copy/'scores.json')['records']
        fields=('id','accepted','strict_pass','grade','filter_only_accepted','filter_only_pass')
        select=lambda rows:sorted([tuple(json.dumps(r.get(key),sort_keys=True) for key in fields) for r in rows])
        if select(expected)!=select(actual): raise ValueError('Independent outcomes did not reproduce')
    return {'benign':True,'reproduced':True,'observations':len(expected),
            'protocol_sha256':digest(root/'protocol.json'),'exact_outcome_agreement':True,
            'original_evidence_preserved':True,'repeated_inference':False,
            'scope':'Recomputed native/document grades and filter-only decisions from saved model outputs. Acceptance is the original manifest decision, not a new generation.',
            'environment':{'python':platform.python_version(),'platform':platform.platform()}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('root',type=Path); parser.add_argument('--output',type=Path)
    args=parser.parse_args(); value=reproduce(args.root.resolve()); text=json.dumps(value,indent=2)+'\n'
    if args.output: args.output.write_text(text)
    print(text,end='')
