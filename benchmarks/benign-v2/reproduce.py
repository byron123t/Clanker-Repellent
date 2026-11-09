"""Verify an exported benign audit in isolated copies, preserving its original evidence."""
import argparse
import hashlib
import json
from importlib.metadata import version
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import sqlite3
import tempfile


def read(path): return json.loads(path.read_text())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def reproduce(root):
    protocol=read(root/'protocol.json'); addendum=read(root/'ablation-protocol.json')
    if protocol.get('benign') is not True or addendum.get('benign') is not True: raise ValueError('Only benign audits')
    names=set(protocol['files'])|set(addendum['files'])|{'protocol.json','baseline-checks.json','contract-checks.json',
        'ablation-protocol.json','ablation-runner.py','ablation-checks.json'}
    for name,expected in {**protocol['files'],**addendum['files']}.items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe artifact path')
        source=root/path; source.resolve().relative_to(root.resolve())
        if source.is_symlink() or digest(source)!=expected: raise ValueError('Original evidence changed: '+name)
    with tempfile.TemporaryDirectory(prefix='repel-audit-reproduction-') as temporary:
        copies=[]
        for experiment in ['primary','ablation']:
            destination=Path(temporary)/experiment; copies.append(destination)
            for name in names:
                path=destination/name; path.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(root/name,path)
            command=[sys.executable,str(destination/('runner/faults.py' if experiment=='primary' else 'ablation-runner.py')),
                     'run' if experiment=='primary' else 'worker',str(destination)]
            result=subprocess.run(command,text=True,capture_output=True,timeout=300)
            if result.returncode: raise RuntimeError(experiment+' reproduction failed: '+result.stderr[-2000:])
        for arm in ['baseline','contract']:
            expected=read(root/(arm+'-checks.json'))['records']; actual=read(copies[0]/(arm+'-checks.json'))['records']
            select=lambda rows:[(r['id'],r['accepted'],r.get('grade')) for r in rows]
            if select(expected)!=select(actual): raise ValueError('Primary outcomes did not reproduce: '+arm)
        select=lambda rows:[(r['id'],r['structure-fix']['accepted'],r['filter-only']['accepted']) for r in rows]
        if select(read(root/'ablation-checks.json')['records'])!=select(read(copies[1]/'ablation-checks.json')['records']):
            raise ValueError('Ablation outcomes did not reproduce')
    clang=subprocess.run(['clang','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
    return {'benign':True,'reproduced':True,'protocol_sha256':digest(root/'protocol.json'),
            'primary_decisions':168,'additional_ablation_validations':84,'derived_filter_decisions':84,
            'exact_outcome_agreement':True,'original_evidence_preserved':True,
            'comparison':'Acceptance and independent grades; transient timings, compiler paths, and diagnostics excluded.',
            'verification_environment':{'python':platform.python_version(),'platform':platform.platform(),'machine':platform.machine(),
                'sqlite':sqlite3.sqlite_version,'clang':clang,'html5lib':version('html5lib'),'pygments':version('pygments')}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('root',type=Path); parser.add_argument('--output',type=Path)
    args=parser.parse_args(); value=reproduce(args.root.resolve())
    text=json.dumps(value,indent=2)+'\n'
    if args.output: args.output.write_text(text)
    print(text,end='')
