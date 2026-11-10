"""Post hoc validation of saved final Python rejections; never repeat model inference.

This is a descriptive diagnostic, not a replay of the generation/retry process and
not a replacement for the registered study outcomes. Only complete model grids
are eligible. All model artifacts must be explicitly benign and checksum verified.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value): path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def selected_records(root,models):
    if not models or len(set(models))!=len(models): raise ValueError('Select distinct model grids')
    protocol=read(root/'protocol.json')
    if protocol.get('benign') is not True: raise ValueError('Only explicitly benign studies')
    for name,digest in protocol['files'].items():
        path=root/name
        path.resolve().relative_to(root.resolve())
        if path.is_symlink() or sha(path)!=digest: raise ValueError('Frozen source changed: '+name)
    records=[]
    for model in models:
        if model not in protocol['models']: raise ValueError('Unknown model')
        for arm in protocol['arms']:
            for task in protocol['task_ids']:
                if any(not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',value) for value in [model,arm,task]):
                    raise ValueError('Unsafe observation identifier')
                for trial in range(protocol['repeats']):
                    directory=root/'runs'/model/arm/task/str(trial)
                    directory.resolve().relative_to(root.resolve())
                    path=directory/'record.json'
                    if not path.exists(): raise ValueError('Complete model grid required: '+model)
                    record=read(path)
                    if (record.get('benign') is not True or
                            tuple(record.get(k) for k in ['model','arm','task','trial'])!=(model,arm,task,trial)):
                        raise ValueError('Invalid observation provenance')
                    manifest_path=directory/'generation/manifest.json'
                    if sha(manifest_path)!=record['generation_manifest_sha256']: raise ValueError('Manifest changed')
                    manifest=read(manifest_path)
                    if (manifest.get('settings',{}).get('mode')!='benign' or len(manifest.get('candidates',[]))!=1
                            or manifest.get('model')!=protocol['models'][model]['id']):
                        raise ValueError('Invalid generation provenance')
                    candidate=manifest['candidates'][0]
                    if (candidate['accepted']!=record['accepted'] or len(candidate['attempts'])!=record['attempts']
                            or candidate['language']!=record['language'] or candidate['status']!=record['status']):
                        raise ValueError('Observation differs from manifest')
                    records.append((directory,record,manifest))
    return protocol,records


def response_source(directory,record,manifest):
    attempt=manifest['candidates'][0]['attempts'][-1]
    trace_path=directory/'traces'/('%02d.json'%record['attempts'])
    trace=read(trace_path)
    if trace.get('benign') is not True or trace.get('mode')!='benign': raise ValueError('Nonbenign response')
    if hashlib.sha256(json.dumps(trace['request'],sort_keys=True).encode()).hexdigest()!=trace['request_sha256']:
        raise ValueError('Request checksum differs')
    response=trace['response']['response_text']
    if (hashlib.sha256(response.encode()).hexdigest()!=attempt['response']['sha256']
            or len(response.encode())!=attempt['response']['bytes']):
        raise ValueError('Response checksum differs')
    from clanker_repellent.generate.source_generation import extract_code_snippet
    return extract_code_snippet(response,normalize_escapes=True),trace_path


def native_worker(root,task_id,source_path):
    # Run in its own process so the primary frozen grader uses its original imports.
    metadata=read(source_path.with_suffix('.meta.json'))
    if (metadata.get('benign') is not True or read(root/'protocol.json').get('benign') is not True
            or metadata.get('source_protocol_sha256')!=sha(root/'protocol.json')
            or metadata.get('task')!=task_id or metadata.get('source_sha256')!=sha(source_path)):
        raise ValueError('Only hash-verified benign diagnostic inputs may be graded')
    sys.path.insert(0,str(root/'engines/contract'))
    spec=importlib.util.spec_from_file_location('primary_grade',root/'runner/grade.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    task=next(t for t in read(root/'tasks.json')['tasks'] if t['id']==task_id)
    oracle=read(root/'oracles.json')['oracles'][task_id]
    print(json.dumps(module.grade(task,oracle,source_path.read_text())))


def audit(root,output,models,engine):
    protocol,records=selected_records(root,models)
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(engine,output/'engine',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copyfile(Path(__file__),output/'audit_rejections.py')
    sys.path.insert(0,str(output/'engine'))
    from clanker_repellent.generate.source_generation import benign_policy_error,validate_snippet,select_languages
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    tasks={t['id']:t for t in read(root/'tasks.json')['tasks']}
    evidence={str(p.relative_to(root)):sha(p) for directory,_,_ in records
              for p in [directory/'record.json',directory/'generation/manifest.json']}
    snapshot={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    design={'benign':True,'post_hoc':True,'recorded_at':datetime.now(timezone.utc).isoformat(),
            'source_protocol_sha256':sha(root/'protocol.json'),'models':models,'observations_screened':len(records),
            'scope':'Only the final saved attempt of completed, rejected Python candidates with a benign_policy_failed status. No new inference or changed retries; primary results remain unchanged.',
            'selection':'All matching records in each complete selected model grid, including failures.',
            'evidence':evidence,'snapshot':snapshot}
    save(output/'protocol.json',design)
    results=[]
    for directory,record,manifest in records:
        attempts=manifest['candidates'][0]['attempts']
        if record['accepted'] or record['language']!='python' or attempts[-1]['status']!='benign_policy_failed': continue
        source,trace_path=response_source(directory,record,manifest)
        name='-'.join(str(record[k]) for k in ['model','arm','task','trial'])
        path=output/(name+'.py'); path.write_text(source)
        save(path.with_suffix('.meta.json'),{'benign':True,'task':record['task'],
            'source_protocol_sha256':design['source_protocol_sha256'],'source_sha256':sha(path)})
        row={k:record[k] for k in ['model','arm','task','trial','language']}
        row.update(benign=True,source_path=path.name,source_sha256=sha(path),trace_sha256=sha(trace_path),
                   previous_diagnostic=attempts[-1].get('error'),new_diagnostic=benign_policy_error(source,language='python'),
                   validation_passed=False,verified=False)
        if row['new_diagnostic'] is None:
            task=tasks[record['task']]
            result=validate_snippet(select_languages(['python'])[0],source,run_linters=protocol['settings']['linters'],
                timeout_seconds=protocol['settings']['validator_timeout_seconds'],require_structure=True,
                structure_profile=FUNCTIONAL_PROFILE,contract=task['contract'] if record['arm']=='contract' else None)
            row['validation_passed']=result['accepted']
            row['failed_checks']=[c['name'] for c in result['checks'] if c.get('required') and c['status']!='passed']
            if result['accepted']:
                process=subprocess.run([sys.executable,str(output/'audit_rejections.py'),str(root),str(output),
                    '--native-worker',record['task'],'--source',str(path)],text=True,capture_output=True,timeout=120)
                if process.returncode: raise RuntimeError('Frozen grading unavailable: '+process.stderr[-500:])
                row['grade']=json.loads(process.stdout); row['verified']=row['grade']['passed']
        results.append(row)
    for name,digest in evidence.items():
        if sha(root/name)!=digest: raise ValueError('Original evidence changed during diagnostic')
    if sha(root/'protocol.json')!=design['source_protocol_sha256']:
        raise ValueError('Source protocol changed during diagnostic')
    for name,digest in protocol['files'].items():
        if sha(root/name)!=digest: raise ValueError('Frozen engine changed during diagnostic')
    for name,digest in snapshot.items():
        if sha(output/name)!=digest: raise ValueError('Diagnostic engine changed during diagnostic')
    groups=[]
    for model in models:
        for arm in protocol['arms']:
            rows=[r for r in results if r['model']==model and r['arm']==arm]
            groups.append({'model':model,'arm':arm,'terminal_rejections':len(rows),
                'policy_cleared':sum(r['new_diagnostic'] is None for r in rows),
                'validation_passed':sum(r['validation_passed'] for r in rows),
                'verified':sum(r['verified'] for r in rows),
                'newly_accepted_incorrect':sum(r['validation_passed'] and not r['verified'] for r in rows)})
    report={'benign':True,'state':'complete','post_hoc':True,'repeated_inference':False,'primary_results_changed':False,
            'source_protocol_sha256':design['source_protocol_sha256'],'scope':design['scope'],
            'groups':groups,'cases':results,'protocol_sha256':sha(output/'protocol.json')}
    save(output/'report.json',report)
    print(json.dumps({k:report[k] for k in ['scope','groups','primary_results_changed']},indent=2))
    return report


def verify_against(report,original,output):
    expected=read(original)
    if (expected.get('benign') is not True or expected.get('post_hoc') is not True
            or expected.get('source_protocol_sha256')!=report['source_protocol_sha256']
            or expected['groups']!=report['groups'] or expected['cases']!=report['cases']):
        raise ValueError('Diagnostic outcomes differ from the saved report')
    proof={'benign':True,'post_hoc':True,'reproduced':True,'exact_case_agreement':True,'cases':len(report['cases']),
        'repeated_inference':False,'source_protocol_sha256':report['source_protocol_sha256'],
        'report_sha256':sha(original),'scope':'Offline rerun using the saved engine; no new model observations.',
        'environment':{'python':platform.python_version(),'platform':platform.platform(),'isolated_interpreter':bool(sys.flags.isolated)}}
    save(output/'reproduction-check.json',proof)
    print(json.dumps(proof))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study',type=Path); parser.add_argument('output',type=Path)
    parser.add_argument('--models',nargs='+',default=['glm','deepseek'])
    parser.add_argument('--engine',type=Path,default=Path(__file__).resolve().parents[2]/'src')
    parser.add_argument('--native-worker'); parser.add_argument('--source',type=Path)
    parser.add_argument('--verify-against',type=Path)
    args=parser.parse_args()
    if args.native_worker: native_worker(args.study.resolve(),args.native_worker,args.source.resolve())
    else:
        report=audit(args.study.resolve(),args.output.resolve(),args.models,args.engine.resolve())
        if args.verify_against: verify_against(report,args.verify_against.resolve(),args.output.resolve())
