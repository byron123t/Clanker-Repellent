"""Expose completed benign observations while keeping an unfinished study explicit."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import time
from experiment import save,digest,verify
from publish import metrics,validate_record


def progress(root,output):
    protocol=verify(root); tasks=json.loads((root/'tasks.json').read_text())['tasks']; cases=[]
    if (output/'report.json').exists() and json.loads((output/'report.json').read_text()).get('state')=='complete':
        return True
    output.mkdir(parents=True,exist_ok=True); (output/'candidates').mkdir(exist_ok=True)
    for model in protocol['models']:
        for task in tasks:
            directory=root/'runs'/model/task['id']; path=directory/'record.json'
            if not path.exists(): continue
            record=json.loads(path.read_text()); manifest=directory/'generation/manifest.json'
            if record.get('benign') is not True or record['model']!=model or record['task']!=task['id'] or digest(manifest)!=record['manifest_sha256']:
                raise ValueError('Invalid completed observation')
            candidate_record=validate_record(record,json.loads(manifest.read_text()),task,protocol['models'][model])
            case={k:record[k] for k in ['model','task','language','family','level','track','arm','trial','accepted','strict_pass','grade','status','attempts','attempt_outcomes']}
            case.update(id=hashlib.sha256((digest(root/'protocol.json')+':'+model+':'+task['id']).encode()).hexdigest(),prompt=task['prompt'],source_sha256=None)
            case['attempt_checks']=[{'attempt':a['attempt'],'status':a['status'],'finish_reason':a.get('response',{}).get('finish_reason'),
                                    'checks':a.get('validation',{}).get('checks',[]),'formatting':a.get('formatting')}
                                   for a in candidate_record['attempts']]
            if record['accepted']:
                descriptor=record['candidate']; source=directory/'generation'/descriptor['relative_path']; source.resolve().relative_to((directory/'generation').resolve())
                if source.is_symlink() or digest(source)!=descriptor['sha256']: raise ValueError('Candidate hash differs')
                (output/'candidates'/(case['id']+'.txt')).write_bytes(source.read_bytes()); case['source_sha256']=descriptor['sha256']
            resources={'inference_seconds':0,'prompt_tokens':0,'completion_tokens':0,'length_stops':0}
            for trace in (directory/'traces').glob('*.json'):
                data=json.loads(trace.read_text())
                if data.get('benign') is not True: raise ValueError('Only benign traces are supported')
                response=data['response']; usage=response.get('usage') or {}
                resources['inference_seconds']+=data['seconds']; resources['prompt_tokens']+=usage.get('prompt_tokens',0) or 0
                resources['completion_tokens']+=usage.get('completion_tokens',0) or 0; resources['length_stops']+=response.get('finish_reason')=='length'
            case['resources']=resources; cases.append(case)
    old=json.loads((output/'report.json').read_text()) if (output/'report.json').exists() else None
    if old and old['counts']['completed']==len(cases): return len(cases)==protocol['planned']
    groups=[{'dimension':dimension,'value':value,'metrics':[metrics([c for c in cases if c[dimension]==value],model) for model in protocol['models']]}
            for dimension in ['language','level','family','track'] for value in sorted({t[dimension] for t in tasks})]
    save(output/'scores.json',{'benign':True,'interim':True,'cases':cases}); shutil.copyfile(root/'protocol.json',output/'protocol.json')
    report={'schema_version':1,'benign':True,'id':output.name,'title':'Language, format, and codebase breadth','stage':'breadth',
            'state':'awaiting-reproduction' if len(cases)==protocol['planned'] else 'running','created_at':protocol['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
            'design':{'tasks':len(tasks),'families':len({t['family'] for t in tasks}),'replicates':1,'formats':sorted({t['language'] for t in tasks}),
                      'models':list(protocol['models']),'arms':['current'],'settings':protocol['settings']},
            'counts':{'planned':protocol['planned'],'completed':len(cases),'accepted':sum(c['accepted'] for c in cases),
                      'verified':sum(c['strict_pass'] for c in cases),'hidden_checks':sum((c['grade'] or {}).get('hidden_cases',0) for c in cases)},
            'metrics':[metrics(cases,model) for model in protocol['models']],'effects':[],'groups':groups,'cases':cases,
            'findings':['This study is unfinished. Model queues contain different completed subsets; do not rank models from these interim rates.',
                        'Missing tasks are not counted as failures. Sources shown here are unchanged accepted artifacts from explicitly benign runs.',
                        'A source-escape bug was found during this frozen study. The live CLI is fixed; these primary observations remain unchanged. A separate offline audit will measure the fix.'],
            'methodology':[{'title':'Frozen design','body':'63 task-format units across 11 programming languages, eight document formats and six logical binary families. Two local model endpoints, one replicate, at most two attempts per unit. Tasks and independent expected values were frozen before inference.'},
                           {'title':'Quality checks','body':'Generic CLI acceptance and independent native or exact-document checks are recorded separately. Private expected values never enter model requests. Compiled/interpreted execution uses the registered macOS containment and resource limits.'},
                           {'title':'Publication gate','body':'Final publication requires the complete 126-observation grid, offline reproduction of every accepted candidate, and the declared consumer tests in pinned cJSON, zlib and curl builds. Interim observations do not satisfy that gate.'}],
            'limitations':protocol['limitations']+['INTERIM: incomplete and potentially unbalanced model queues; no confidence intervals or causal comparison.'],
            'references':[],'provenance':{'protocol_sha256':digest(root/'protocol.json'),'scores_sha256':digest(output/'scores.json'),'snapshot_files':len(protocol['files'])}}
    (output/'REPORT.md').write_text('# Interim benign breadth observations\n\n'+str(len(cases))+' / '+str(protocol['planned'])+' observations completed.\n\n'+'\n\n'.join(report['findings'])+'\n')
    save(output/'report.json',report)
    print(json.dumps({'completed':len(cases),'planned':protocol['planned'],'state':report['state']}),flush=True)
    return len(cases)==protocol['planned']


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('root',type=Path); parser.add_argument('output',type=Path); parser.add_argument('--watch',action='store_true')
    args=parser.parse_args()
    while True:
        done=progress(args.root.resolve(),args.output.resolve())
        if done or not args.watch: break
        time.sleep(30)
