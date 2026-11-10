"""Frozen benign breadth study: one serial queue per endpoint, exact replay."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
MODELS={'glm':{'endpoint':'http://127.0.0.1:18474/v1','id':'glm-4.7-flash-abliterated'},
        'deepseek':{'endpoint':'http://127.0.0.1:18473/v1','id':'deepseek-v4-flash-abliterated'}}


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    tmp.replace(path)


def verify(root):
    protocol=json.loads((root/'protocol.json').read_text())
    if protocol.get('benign') is not True or protocol.get('kind')!='benign_breadth_evaluation': raise ValueError('Not a benign breadth study')
    for name,expected in protocol['files'].items():
        path=root/name
        path.resolve().relative_to(root.resolve())
        if path.is_symlink() or digest(path)!=expected: raise ValueError('Frozen study file changed: '+name)
    return protocol


def prepare(root):
    if root.exists(): raise ValueError('Choose a new study directory; never overwrite a frozen study')
    controls=json.loads((HERE/'controls.json').read_text())
    from check_controls import engine_digest
    if (controls.get('tasks_sha256')!=digest(HERE/'tasks.json') or controls.get('oracles_sha256')!=digest(HERE/'oracles.json')
            or controls.get('engine_sha256')!=engine_digest(REPO/'src') or controls.get('grader_sha256')!=digest(HERE/'grade.py')):
        raise ValueError('Reference controls are stale; run check_controls.py before freezing a new study')
    if controls.get('benign') is not True or len(controls['outcomes'])!=63 or not all(row['accepted'] and row['grade']['passed'] for row in controls['outcomes']):
        raise ValueError('All 63 authored controls must pass acceptance and independent grading before freezing')
    if not (HERE/'containment.json').is_file() or json.loads((HERE/'containment.json').read_text()).get('passed') is not True:
        raise ValueError('Containment checks must pass before freezing')
    root.mkdir(parents=True)
    shutil.copytree(REPO/'src',root/'engine',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['experiment.py','grade.py','build_suite.py','publish.py','integration.py','check_controls.py','README.md']:
        destination=root/'runner'/name; destination.parent.mkdir(exist_ok=True); shutil.copyfile(HERE/name,destination)
    for name in ['tasks.json','oracles.json','controls.json','containment.json','repositories.json']:
        shutil.copyfile(HERE/name,root/name)
    packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)
    (root/'requirements-environment.txt').write_text(packages)
    environment={'benign':True,'platform':sys.platform,'python':sys.version,'tools':{}}
    for name,args in {'clang':['--version'],'node':['--version'],'tsc':['--version'],'go':['version'],'rustc':['--version'],'ruby':['--version'],'lua':['-v'],'javac':['-version'],'swiftc':['--version']}.items():
        p=subprocess.run([name]+args,text=True,capture_output=True)
        environment['tools'][name]={'path':shutil.which(name),'version':(p.stdout+p.stderr).strip()}
    save(root/'environment.json',environment)
    tasks=json.loads((root/'tasks.json').read_text())['tasks']
    hashes={str(p.relative_to(root)):digest(p) for p in root.rglob('*') if p.is_file()}
    protocol={'schema_version':1,'kind':'benign_breadth_evaluation','benign':True,'created_at':datetime.now(timezone.utc).isoformat(),
              'task_ids':[task['id'] for task in tasks],'models':MODELS,'arms':['current'],'repeats':1,'planned':len(tasks)*len(MODELS),
              'randomization_seed':20261110,'files':hashes,
              'settings':{'max_tokens':8192,'temperature':0.2,'top_p':0.8,'retries':1,'no_thinking':True,'validator_timeout_seconds':90,'request_timeout_seconds':900,'linters':False},
              'primary_outcome':'Accepted candidate passing every frozen native behavior or exact document check.',
              'analysis_unit':'Descriptive task-format units; related algorithms and documents are reused across languages. No population confidence interval or causal model ranking.',
              'attempt_policy':'Two attempts maximum; CLI syntax/structure feedback only. Private grader never feeds back into generation. Completed failures never rerolled.',
              'containment':'macOS sandbox-exec denies network, home reads except Python runtime libraries, and writes outside temporary runtime directory. CPU/file/wall limits; no macOS address-space limit.',
              'integration':'Pinned cJSON JSON parse/serialize, zlib exact compression round-trip, curl local HTTP consumption; upstream builds/tests separately. All compatible accepted candidates, including semantically failing ones. Source trees remain unchanged.',
              'limitations':['Authored corpus, one generation per model/task-format, shared families and parsers; descriptive capability coverage only.',
                             'Static markup/data fixtures do not compute at runtime. Binary descriptions are logical schemas, not real executable serialization or decompilation evidence.',
                             'Codebase integration measures specific interfaces, not arbitrary whole-repository insertion or all platform/build configurations.']}
    save(root/'protocol.json',protocol)
    save(root/'status.json',{'benign':True,'state':'prepared','completed':0,'planned':protocol['planned']})
    print(json.dumps({'study':str(root),'planned':protocol['planned'],'protocol_sha256':digest(root/'protocol.json')}))


def worker(root,model,identity):
    protocol=verify(root)
    if model not in protocol['models'] or identity not in protocol['task_ids']: raise ValueError('Job outside protocol')
    directory=root/'runs'/model/identity
    if (directory/'record.json').exists(): return
    sys.path.insert(0,str(root/'engine'))
    from clanker_repellent.generate.source_generation import generate_source_run,select_languages
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    from clanker_repellent.inference.provider import OpenAICompatibleProvider
    from grade import grade
    task=next(t for t in json.loads((root/'tasks.json').read_text())['tasks'] if t['id']==identity)
    oracle=json.loads((root/'oracles.json').read_text())['oracles'][identity]
    route=protocol['models'][model]; settings=protocol['settings']
    seed=int(hashlib.sha256(('20261110:'+model+':'+identity).encode()).hexdigest()[:8],16)
    class InfrastructureFailure(BaseException): pass
    class Provider:
        def __init__(self):
            self.client=OpenAICompatibleProvider('local',route['endpoint'],timeout=settings['request_timeout_seconds']); self.number=0
            try: identities=self.client.list_models()
            except Exception as exc: raise InfrastructureFailure(type(exc).__name__) from None
            if identities!=[route['id']]: raise InfrastructureFailure('Model identity mismatch')
        def complete(self,**kwargs):
            self.number+=1; kwargs.setdefault('extra_body',{})['seed']=(seed+self.number-1)%2**32
            trace=directory/'traces'/('%02d.json'%self.number)
            request_hash=hashlib.sha256(json.dumps(kwargs,sort_keys=True).encode()).hexdigest()
            if trace.exists():
                saved=json.loads(trace.read_text())
                if saved.get('benign') is not True or saved['request_sha256']!=request_hash: raise InfrastructureFailure('Trace replay differs')
                return saved['response']
            started=time.monotonic()
            try: response=self.client.complete(**kwargs)
            except Exception as exc: raise InfrastructureFailure(type(exc).__name__) from None
            if response.get('resolved_model')!=route['id']: raise InfrastructureFailure('Model identity changed')
            save(trace,{'benign':True,'mode':'benign','request_sha256':request_hash,'request':kwargs,'response':response,'seconds':time.monotonic()-started})
            return response
    started=time.monotonic()
    try:
        provider=Provider(); generation=directory/'generation'
        existing=json.loads((generation/'manifest.json').read_text()) if (generation/'manifest.json').is_file() else None
        run=existing if existing and existing['summary']['pending']==0 else generate_source_run(provider=provider,model=route['id'],payload=task['prompt'],
            targets=select_languages([task['language']]),output_dir=generation,benign=True,structure_profile=FUNCTIONAL_PROFILE,seed=seed,
            max_tokens=settings['max_tokens'],temperature=settings['temperature'],top_p=settings['top_p'],retries=settings['retries'],
            no_thinking=settings['no_thinking'],run_linters=settings['linters'],validator_timeout_seconds=settings['validator_timeout_seconds'])
        if run['settings']['mode']!='benign' or run['model']!=route['id'] or len(run['candidates'])!=1: raise ValueError('Invalid benign provenance')
        item=run['candidates'][0]; candidate=item.get('candidate'); result=None
        if item['accepted']:
            path=generation/candidate['relative_path']; path.resolve().relative_to(generation.resolve())
            if path.is_symlink() or digest(path)!=candidate['sha256']: raise ValueError('Candidate hash differs')
            result=grade(task,oracle,path.read_bytes().decode())
        save(directory/'record.json',{'benign':True,'model':model,'model_id':route['id'],'task':identity,'language':task['language'],
             'family':task['family'],'level':task['level'],'track':task['track'],'arm':'current','trial':0,'accepted':item['accepted'],
             'strict_pass':bool(item['accepted'] and result and result['passed']),'grade':result,'status':item['status'],
             'attempts':len(item['attempts']),'attempt_outcomes':[a['status'] for a in item['attempts']], 'candidate':candidate,
             'manifest_sha256':digest(generation/'manifest.json'),'seed_requested':seed,'wall_seconds':time.monotonic()-started})
    except InfrastructureFailure as exc:
        save(directory/'interruption.json',{'benign':True,'reason':str(exc)}); raise SystemExit(75)


def run(root):
    protocol=verify(root); lock=threading.Lock(); completed=[]; interrupted={}
    def update(state='running'):
        save(root/'status.json',{'benign':True,'state':state,'completed':len(completed),'planned':protocol['planned'],'interruptions':interrupted})
    def queue(model):
        tasks=list(protocol['task_ids']); random.Random(protocol['randomization_seed']).shuffle(tasks)
        for identity in tasks:
            directory=root/'runs'/model/identity; directory.mkdir(parents=True,exist_ok=True)
            if not (directory/'record.json').exists():
                with (directory/'worker.log').open('a') as log:
                    p=subprocess.run([sys.executable,str(root/'runner/experiment.py'),'worker',str(root),'--model',model,'--task',identity],stdout=log,stderr=log)
                if p.returncode:
                    with lock: interrupted[model]={'task':identity,'exit_code':p.returncode}; update()
                    print(json.dumps({'model':model,'task':identity,'stopped':p.returncode}),flush=True); return
            record=json.loads((directory/'record.json').read_text())
            with lock: completed.append(record); update()
            print(json.dumps({k:record[k] for k in ['model','task','accepted','strict_pass','attempts']}),flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(queue,protocol['models']))
    update('complete' if len(completed)==protocol['planned'] else 'interrupted')


def regrade(root):
    protocol=verify(root); sys.path.insert(0,str(root/'engine'))
    from grade import grade
    tasks={t['id']:t for t in json.loads((root/'tasks.json').read_text())['tasks']}
    oracles=json.loads((root/'oracles.json').read_text())['oracles']; outcomes=[]
    for model in protocol['models']:
        for identity in protocol['task_ids']:
            directory=root/'runs'/model/identity; record=json.loads((directory/'record.json').read_text())
            if record.get('benign') is not True or digest(directory/'generation/manifest.json')!=record['manifest_sha256']:
                raise ValueError('Generation provenance changed')
            manifest=json.loads((directory/'generation/manifest.json').read_text())
            if manifest['settings']['mode']!='benign': raise ValueError('Only benign generation is inspected')
            if not record['accepted']: continue
            candidate=record['candidate']; path=directory/'generation'/candidate['relative_path']; path.resolve().relative_to((directory/'generation').resolve())
            if path.is_symlink() or digest(path)!=candidate['sha256']: raise ValueError('Candidate hash changed')
            current=grade(tasks[identity],oracles[identity],path.read_bytes().decode())
            # Compiler diagnostics can include temporary paths; compare all actual outcomes.
            def stable(value): return {k:v for k,v in value.items() if k!='diagnostic'}
            matched=stable(current)==stable(record['grade'])
            outcomes.append({'model':model,'task':identity,'source_sha256':candidate['sha256'],'matched':matched})
            if not matched: print(json.dumps({'mismatch':identity,'model':model,'expected':record['grade'],'actual':current}),flush=True)
    proof={'benign':True,'protocol_sha256':digest(root/'protocol.json'),'passed':all(o['matched'] for o in outcomes),
           'accepted_candidates':len(outcomes),'outcomes':outcomes,'inference_requests':0,'timestamp':datetime.now(timezone.utc).isoformat()}
    save(root/'reproduction-check.json',proof)
    print(json.dumps({k:v for k,v in proof.items() if k!='outcomes'}),flush=True)
    if not proof['passed']: raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['prepare','run','worker','regrade']); parser.add_argument('root',type=Path)
    parser.add_argument('--model'); parser.add_argument('--task'); args=parser.parse_args(); root=args.root.resolve()
    if args.command=='worker': worker(root,args.model,args.task)
    else: globals()[args.command](root)
