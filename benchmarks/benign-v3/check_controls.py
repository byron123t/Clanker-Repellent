"""Validate authored controls through the complete benign generation pipeline."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from experiment import digest,save
from grade import grade

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def engine_digest(root):
    values={str(p.relative_to(root)):digest(p) for p in root.rglob('*.py') if '__pycache__' not in p.parts}
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()


def check(output):
    if output.exists(): raise ValueError('Choose a new controls output directory')
    sys.path.insert(0,str(REPO/'src'))
    from clanker_repellent.generate.source_generation import generate_source_run,select_languages,_format_candidate
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    tasks=json.loads((HERE/'tasks.json').read_text())['tasks']; corpus=json.loads((HERE/'oracles.json').read_text())
    if corpus.get('benign') is not True: raise ValueError('Only authored benign controls are supported')
    outcomes=[]
    for task in tasks:
        oracle=corpus['oracles'][task['id']]; source=oracle['control']
        if task['language'] in {'go','rust'}:
            source,_=_format_candidate(task['language'],source,90); oracle['control']=source
        class AuthoredProvider:
            def complete(self,**_kwargs):
                return {'response_text':'```'+task['language']+'\n'+source+'```','finish_reason':'stop','resolved_model':'authored-control'}
        directory=output/task['id']
        run=generate_source_run(provider=AuthoredProvider(),model='authored-control',payload=task['prompt'],
            targets=select_languages([task['language']]),output_dir=directory,benign=True,structure_profile=FUNCTIONAL_PROFILE,
            retries=0,run_linters=False,validator_timeout_seconds=90)
        if run['settings']['mode']!='benign': raise ValueError('Expected benign generation provenance')
        candidate=run['candidates'][0]; result=None; unchanged=False
        if candidate['accepted']:
            path=directory/candidate['candidate']['relative_path']
            if digest(path)!=candidate['candidate']['sha256']: raise ValueError('Control source hash differs')
            content=path.read_bytes().decode(); unchanged=content==source; result=grade(task,oracle,content)
        row={'task':task['id'],'accepted':candidate['accepted'],'source_unchanged':unchanged,'control_sha256':hashlib.sha256(source.encode()).hexdigest(),'grade':result}
        outcomes.append(row); print(json.dumps({k:row[k] for k in ['task','accepted','source_unchanged']}),flush=True)
    passed=all(row['accepted'] and row['source_unchanged'] and row['grade']['passed'] for row in outcomes)
    if passed: save(HERE/'oracles.json',corpus)
    proof={'benign':True,'kind':'authored_full_pipeline_controls','passed':passed,'inference_requests':0,'outcomes':outcomes,
           'tasks_sha256':digest(HERE/'tasks.json'),'oracles_sha256':digest(HERE/'oracles.json'),
           'engine_sha256':engine_digest(REPO/'src'),'grader_sha256':digest(HERE/'grade.py')}
    save(output/'report.json',proof)
    if not passed: raise SystemExit('At least one authored pipeline control failed; preparation is blocked')
    save(HERE/'controls.json',proof)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('output',type=Path); args=parser.parse_args(); check(args.output.resolve())
