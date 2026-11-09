"""Frozen, paired benign generation experiments; one inference request per model at a time."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

REPO=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
MODELS={'glm':{'endpoint':'http://127.0.0.1:18474/v1','id':'glm-4.7-flash-abliterated'},
        'deepseek':{'endpoint':'http://127.0.0.1:18473/v1','id':'deepseek-v4-flash-abliterated'}}


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w') as stream:
        json.dump(value,stream,indent=2,allow_nan=False); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


def prepare(root,split,repeats):
    if split not in {'development','heldout'} or type(repeats) is not int or not 1<=repeats<=20:
        raise ValueError('Choose development/heldout and 1–20 replicates.')
    if root.exists(): raise ValueError('Use a new study directory; frozen studies are never overwritten.')
    root.mkdir(parents=True)
    snapshot=REPO/'.repel-workspaces/benign-eval-v2/baseline/src'
    if not snapshot.is_dir(): raise ValueError('Baseline snapshot is missing.')
    for name,source in [('baseline',snapshot),('contract',REPO/'src')]:
        shutil.copytree(source,root/'engines'/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (root/'runner').mkdir()
    for name in ['experiment.py','grade.py','analyze.py','build_suite.py','PROTOCOL.md',
                 'publish_models.py','reproduce_models.py','plot_models.py','requirements.txt']:
        shutil.copyfile(HERE/name,root/'runner'/name)
    for name in ['tasks.json','oracles.json']:
        shutil.copyfile(HERE/name,root/name)
    if split=='heldout':
        evidence=REPO/'.repel-workspaces/benign-eval-v2'
        for name in ['intervention-selection.json','arithmetic-control-checks.json','arithmetic-development-checks.json',
                     'native-grader-incident/notes.json','development-v2/scores.json']:
            path=evidence/name
            if path.is_file():
                if json.loads(path.read_text()).get('benign') is not True: raise ValueError('Selection evidence must be benign')
                target=root/'evidence'/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,target)
    tasks=json.loads((root/'tasks.json').read_text())
    assert tasks['benign'] is True
    selected=[task for task in tasks['tasks'] if task['split']==split]
    if len(selected)!=(12 if split=='development' else 24): raise ValueError('Unexpected suite size')
    if len({task['id'] for task in selected})!=len(selected): raise ValueError('Duplicate task identifiers')
    hashes={str(path.relative_to(root)):digest(path) for path in root.rglob('*') if path.is_file()}
    protocol={'schema_version':1,'kind':'benign_evaluation','benign':True,'created_at':datetime.now(timezone.utc).isoformat(),
              'stage':split,'repeats':repeats,'task_ids':[task['id'] for task in selected],
              'models':MODELS,'arms':['baseline','contract'],'randomization_seed':20261109,
              'baseline_commit':'65d5cb357140d2c76808f254c7d2a4b6d95f3f31','files':hashes,
              'settings':{'max_tokens':4096,'temperature':0.2,'top_p':0.8,'retries':2,'no_thinking':True,
                          'validator_timeout_seconds':60,'request_timeout_seconds':900,'linters':False},
              'primary_outcome':'Accepted candidate satisfying the public API and every independent public/hidden native or exact-document check.',
              'analysis_unit':'Task; repeats are paired and clustered within task, not independent test cases.',
              'attempt_policy':'Same maximum three attempts. Preserve completed failures. Transport/model identity errors stop a queue and are not model-quality failures.',
              'ablation':'Filter-only re-scores baseline candidates with the public contract, with no generation or repair.',
              'native_grader':'Python AST/step/value eligibility then native subprocess; scalar LLVM native compile/ctypes; read-only in-memory SQLite; independent document expectations.'}
    save(root/'protocol.json',protocol)
    save(root/'status.json',{'benign':True,'state':'prepared','completed':0,'planned':len(selected)*repeats*4})
    print(json.dumps({'study':str(root),'stage':split,'planned':len(selected)*repeats*4,'protocol_sha256':digest(root/'protocol.json')}))


def verify(root,protocol):
    if protocol.get('benign') is not True or protocol.get('kind')!='benign_evaluation': raise ValueError('Only explicitly benign studies are supported.')
    for name,expected in protocol['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts: raise ValueError('Unsafe frozen artifact path')
        path=root/name
        path.resolve().relative_to(root.resolve())
        if path.is_symlink() or digest(path)!=expected: raise ValueError('Frozen study artifact changed: '+name)


def job_directory(root,model,arm,task,trial): return root/'runs'/model/arm/task/str(trial)


def seed_for(model,task,trial):
    return int(hashlib.sha256(f'20261109:{model}:{task}:{trial}'.encode()).hexdigest()[:8],16)


def worker(root,model,arm,identity,trial):
    protocol=json.loads((root/'protocol.json').read_text()); verify(root,protocol)
    if model not in protocol['models'] or arm not in protocol['arms'] or identity not in protocol['task_ids'] or not 0<=trial<protocol['repeats']:
        raise ValueError('Job is outside the frozen protocol.')
    directory=job_directory(root,model,arm,identity,trial)
    if (directory/'record.json').is_file(): return
    sys.path.insert(0,str(root/'engines'/arm))
    from clanker_repellent.generate.source_generation import generate_source_run,select_languages
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    from clanker_repellent.inference.provider import OpenAICompatibleProvider
    task=next(item for item in json.loads((root/'tasks.json').read_text())['tasks'] if item['id']==identity)
    route=protocol['models'][model]; settings=protocol['settings']; seed=seed_for(model,identity,trial)
    class InfrastructureFailure(BaseException): pass
    class RecordedProvider:
        def __init__(self):
            self.client=OpenAICompatibleProvider('local',route['endpoint'],timeout=settings['request_timeout_seconds'])
            self.number=0
            try: identities=self.client.list_models()
            except Exception as exc:
                save(directory/'interruption.json',{'benign':True,'reason':type(exc).__name__,'phase':'model_discovery'})
                raise InfrastructureFailure('Model discovery failed: '+type(exc).__name__) from None
            if identities!=[route['id']]:
                save(directory/'interruption.json',{'benign':True,'reason':'model_identity_mismatch','phase':'model_discovery'})
                raise InfrastructureFailure('Unexpected model identity')
        def complete(self,**kwargs):
            self.number+=1
            kwargs.setdefault('extra_body',{})['seed']=(seed+self.number-1)%2**32
            trace=directory/'traces'/f'{self.number:02d}.json'
            request_hash=hashlib.sha256(json.dumps(kwargs,sort_keys=True).encode()).hexdigest()
            if trace.exists():
                previous=json.loads(trace.read_text())
                if previous['request_sha256']!=request_hash: raise InfrastructureFailure('Interrupted replay request differs; preserve this record for review')
                return previous['response']
            try: response=self.client.complete(**kwargs)
            except Exception as exc:
                save(directory/'interruption.json',{'benign':True,'reason':type(exc).__name__,'attempt':self.number})
                raise InfrastructureFailure('Inference transport failed: '+type(exc).__name__) from None
            if response.get('resolved_model')!=route['id']: raise InfrastructureFailure('Model changed during study')
            save(trace,{'benign':True,'mode':'benign','request_sha256':request_hash,'request':kwargs,'response':response})
            return response
    started=time.monotonic()
    try:
        provider=RecordedProvider()
        generation=directory/'generation'
        existing=json.loads((generation/'manifest.json').read_text()) if (generation/'manifest.json').is_file() else None
        if existing and existing['summary']['pending']==0:
            run=existing
        else:
            payload=task['prompt']
            extra={}
            if arm=='contract': extra={'contract':task['contract'],'seed':seed}
            else: payload+='\nPublic contract (reference data):\n'+json.dumps(task['contract'],sort_keys=True)
            run=generate_source_run(provider=provider,model=route['id'],payload=payload,
                targets=select_languages([task['language']]),output_dir=generation,benign=True,
                max_tokens=settings['max_tokens'],temperature=settings['temperature'],top_p=settings['top_p'],
                retries=settings['retries'],no_thinking=settings['no_thinking'],run_linters=settings['linters'],
                validator_timeout_seconds=settings['validator_timeout_seconds'],structure_profile=FUNCTIONAL_PROFILE,**extra)
        if run['settings']['mode']!='benign' or run['model']!=route['id'] or len(run['candidates'])!=1: raise ValueError('Invalid generation provenance')
        candidate=run['candidates'][0]
        save(directory/'record.json',{'schema_version':1,'benign':True,'model':model,'model_id':route['id'],'arm':arm,
            'task':identity,'trial':trial,'language':task['language'],'level':task['level'],'family':task['family'],
            'stage':task['split'],'seed_requested':seed,'seed_honored':'not independently verified',
            'accepted':candidate['accepted'],'status':candidate['status'],'attempts':len(candidate['attempts']),
            'attempt_outcomes':[attempt['status'] for attempt in candidate['attempts']],
            'first_attempt_accepted':bool(candidate['attempts'][0]['accepted']),
            'candidate':candidate.get('candidate'),'generation_manifest_sha256':digest(generation/'manifest.json'),
            'wall_seconds':round(time.monotonic()-started,3)})
    except InfrastructureFailure as exc:
        print(str(exc),flush=True); raise SystemExit(75)


def run(root):
    protocol=json.loads((root/'protocol.json').read_text()); verify(root,protocol)
    lock=threading.Lock(); completed=[]; interruptions={}
    def update():
        save(root/'status.json',{'benign':True,'state':'running','completed':len(completed),'planned':len(protocol['task_ids'])*protocol['repeats']*4,
                               'jobs':completed,'interruptions':interruptions})
    def queue(model):
        blocks=[(task,trial) for task in protocol['task_ids'] for trial in range(protocol['repeats'])]
        rng=random.Random(protocol['randomization_seed']); rng.shuffle(blocks)
        for task,trial in blocks:
            arms=list(protocol['arms']); rng.shuffle(arms)
            for arm in arms:
                directory=job_directory(root,model,arm,task,trial); directory.mkdir(parents=True,exist_ok=True)
                if not (directory/'record.json').exists():
                    with (directory/'worker.log').open('a') as log:
                        process=subprocess.run([sys.executable,str(root/'runner/experiment.py'),'worker',str(root),
                            '--model',model,'--arm',arm,'--task',task,'--trial',str(trial)],cwd=REPO,stdout=log,stderr=log)
                    if process.returncode:
                        with lock:
                            interruptions[model]={'task':task,'trial':trial,'arm':arm,'exit_code':process.returncode}; update()
                        print(json.dumps({'model':model,'stopped':True,'exit_code':process.returncode,'log':str(directory/'worker.log')}),flush=True)
                        return
                with lock:
                    record=json.loads((directory/'record.json').read_text())
                    completed.append({'model':model,'arm':arm,'task':task,'trial':trial,'accepted':record['accepted']})
                    update()
                    print(json.dumps({'completed':len(completed),'model':model,'arm':arm,'task':task,'trial':trial,'accepted':record['accepted'],'attempts':record['attempts']}),flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(queue,protocol['models']))
    status=json.loads((root/'status.json').read_text()); status['state']='interrupted' if interruptions else 'generation_complete'; save(root/'status.json',status)
    return 75 if interruptions else 0


def score(root):
    protocol=json.loads((root/'protocol.json').read_text()); verify(root,protocol)
    sys.path.insert(0,str(root/'engines/contract')); sys.path.insert(0,str(root/'runner'))
    from grade import grade
    from clanker_repellent.generate.contracts import check_contract
    tasks={task['id']:task for task in json.loads((root/'tasks.json').read_text())['tasks']}
    oracles=json.loads((root/'oracles.json').read_text())['oracles']
    scored=[]
    for model in protocol['models']:
        for arm in protocol['arms']:
            for identity in protocol['task_ids']:
                for trial in range(protocol['repeats']):
                    directory=job_directory(root,model,arm,identity,trial)
                    if not (directory/'record.json').exists(): continue
                    record=json.loads((directory/'record.json').read_text())
                    if record.get('benign') is not True: raise ValueError('Refusing nonbenign experiment output')
                    if (record.get('model'),record.get('arm'),record.get('task'),record.get('trial'))!=(model,arm,identity,trial):
                        raise ValueError('Observation identity differs from its registered cell')
                    manifest_path=directory/'generation/manifest.json'
                    if digest(manifest_path)!=record['generation_manifest_sha256']: raise ValueError('Manifest changed')
                    manifest=json.loads(manifest_path.read_text())
                    if (manifest.get('settings',{}).get('mode')!='benign' or manifest.get('model')!=protocol['models'][model]['id']
                            or len(manifest.get('candidates',[]))!=1): raise ValueError('Generation provenance differs from the study')
                    candidate=manifest['candidates'][0]
                    if (candidate['language']!=tasks[identity]['language'] or candidate['accepted']!=record['accepted']
                            or candidate.get('candidate')!=record.get('candidate')): raise ValueError('Candidate record differs from its manifest')
                    attempts=candidate['attempts']
                    if record['attempts']!=len(attempts): raise ValueError('Attempt count differs from manifest')
                    def total(field, usage=False):
                        values=[(attempt.get('response',{}).get('usage') or {}).get(field) if usage
                                else attempt.get('response',{}).get(field) for attempt in attempts]
                        return sum(values) if all(type(v) in {int,float} and v>=0 for v in values) else None
                    latency=total('latency_ms')
                    record['resources']={'inference_seconds':latency/1000 if latency is not None else None,
                                         'prompt_tokens':total('prompt_tokens',True),'completion_tokens':total('completion_tokens',True),
                                         'length_stops':sum(a.get('response',{}).get('finish_reason')=='length' for a in attempts)}
                    record['attempt_checks']=[{'attempt':a['attempt'],'status':a['status'],
                        'failed_checks':[c['name'] for c in a.get('validation',{}).get('checks',[]) if c.get('required') and c['status']=='failed']}
                        for a in attempts]
                    if record['accepted']:
                        relative=Path(record['candidate']['relative_path'])
                        if relative.is_absolute() or '..' in relative.parts: raise ValueError('Unsafe candidate path')
                        path=directory/'generation'/relative
                        path.resolve().relative_to((directory/'generation').resolve())
                        if path.is_symlink() or path.parent.is_symlink() or digest(path)!=record['candidate']['sha256']: raise ValueError('Candidate changed')
                        source=path.read_bytes().decode('utf-8')
                        result=grade(tasks[identity],oracles[identity],source)
                        contract_result=check_contract(source,tasks[identity]['contract'])
                        record.update(grade=result,contract_check=contract_result,strict_pass=result['passed'],
                                      filter_only_accepted=contract_result['passed'],filter_only_pass=contract_result['passed'] and result['passed'])
                    else:
                        record.update(grade={'passed':False,'diagnostic':'No accepted candidate'},strict_pass=False,
                                      filter_only_accepted=False,filter_only_pass=False)
                    record['id']=hashlib.sha256(f'{model}:{arm}:{identity}:{trial}'.encode()).hexdigest()
                    record['directory']=str(directory.relative_to(root))
                    save(directory/'score.json',record); scored.append(record)
                    print(json.dumps({'scored':len(scored),'model':model,'arm':arm,'task':identity,'strict_pass':record['strict_pass']}),flush=True)
    save(root/'scores.json',{'schema_version':1,'benign':True,'protocol_sha256':digest(root/'protocol.json'),'records':scored})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run','worker','score']); parser.add_argument('root',type=Path)
    parser.add_argument('--split',choices=['development','heldout'],default='development'); parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--model'); parser.add_argument('--arm'); parser.add_argument('--task'); parser.add_argument('--trial',type=int)
    args=parser.parse_args(); root=args.root.resolve()
    if args.action=='prepare': prepare(root,args.split,args.repeats)
    elif args.action=='run': raise SystemExit(run(root))
    elif args.action=='score': score(root)
    else: worker(root,args.model,args.arm,args.task,args.trial)


if __name__=='__main__': main()
