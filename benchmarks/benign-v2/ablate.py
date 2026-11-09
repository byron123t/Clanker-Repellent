"""Post hoc mechanism check on the frozen authored audit; no model generations."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path): return json.loads(path.read_text())
def save(path,value):
    temporary=path.with_suffix('.tmp'); temporary.write_text(json.dumps(value,indent=2)+'\n'); temporary.replace(path)


def prepare(root):
    destination=root/'ablation-protocol.json'
    if destination.exists(): raise ValueError('Preserve the existing ablation protocol')
    shutil.copyfile(__file__,root/'ablation-runner.py')
    names=['protocol.json','corpus.json','baseline-checks.json','contract-checks.json','ablation-runner.py']
    save(destination,{'schema_version':1,'benign':True,'stage':'post-hoc-ablation',
        'files':{name:digest(root/name) for name in names},
        'design':'After observing the primary audit, isolate the structure fix and task filter on the same fixed sources. No new faults or model outputs.',
        'structure_fix':'Run the frozen enhanced engine without a task contract: 84 additional validations.',
        'filter_only':'Combine each recorded baseline decision with its recorded public-contract check: 84 derived decisions, no generation or new validation.',
        'primary_unchanged':'The original two-arm experiment, paired interval, and all source bytes remain unchanged. This exploratory addendum does not increase the number of independent tasks.'})


def worker(root):
    protocol=read(root/'protocol.json'); addendum=read(root/'ablation-protocol.json')
    if protocol.get('benign') is not True or addendum.get('benign') is not True: raise ValueError('Only benign audits')
    for name,expected in {**protocol['files'],**addendum['files']}.items():
        if (root/name).is_symlink() or digest(root/name)!=expected: raise ValueError('Frozen artifact changed: '+name)
    sys.path.insert(0,str(root/'engines/contract'))
    from clanker_repellent.generate.source_generation import validate_snippet,select_languages,validation_metadata
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    baseline={r['id']:r for r in read(root/'baseline-checks.json')['records']}
    enhanced={r['id']:r for r in read(root/'contract-checks.json')['records']}
    records=[]
    for item in read(root/'corpus.json')['records']:
        report=validate_snippet(select_languages([item['language']])[0],item['source'],run_linters=False,timeout_seconds=60,
                                require_structure=True,structure_profile=FUNCTIONAL_PROFILE)
        if any(c['required'] and c['status'] in {'unavailable','error','timeout'} for c in report['checks']): raise RuntimeError('Validator infrastructure error')
        contract=next(c for c in enhanced[item['id']]['validation']['checks'] if c['name']=='task_contract')
        filter_report=copy.deepcopy(baseline[item['id']]['validation']); filter_report['checks'].append(contract)
        filter_report['accepted']=filter_report['accepted'] and contract['status']=='passed'
        filter_report['status']='passed' if filter_report['accepted'] else 'failed'
        records.append({'id':item['id'],'structure-fix':validation_metadata(report),'filter-only':filter_report})
        save(root/'ablation-checks.json',{'schema_version':1,'benign':True,'protocol_sha256':digest(root/'ablation-protocol.json'),'records':records})
        print(json.dumps({'completed':len(records),'structure_fix_accepted':report['accepted'],'filter_only_accepted':filter_report['accepted']}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('action',choices=['prepare','run','worker']); parser.add_argument('root',type=Path)
    args=parser.parse_args(); root=args.root.resolve()
    if args.action=='prepare': prepare(root)
    elif args.action=='worker': worker(root)
    else: subprocess.run([sys.executable,str(root/'ablation-runner.py'),'worker',str(root)],check=True)


if __name__=='__main__': main()
