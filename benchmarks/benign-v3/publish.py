"""Export only complete, hash-verified benign breadth results for the dashboard."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
if (Path(__file__).resolve().parent.parent/'runner').is_dir():
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'runner'))
from experiment import digest,save,verify


def metrics(cases,model):
    selected=[c for c in cases if c['model']==model]; n=len(selected)
    accepted=sum(c['accepted'] for c in selected); verified=sum(c['strict_pass'] for c in selected)
    return {'model':model,'arm':'current','n':n,'accepted':accepted,'verified':verified,'false_acceptance':accepted-verified,
            'acceptance_rate':accepted/n if n else None,'verified_rate':verified/n if n else None,'ci95':None,
            'attempts':sum(c['attempts'] for c in selected),'inference_seconds':sum(c['resources']['inference_seconds'] for c in selected),
            'prompt_tokens':sum(c['resources']['prompt_tokens'] for c in selected),'completion_tokens':sum(c['resources']['completion_tokens'] for c in selected),
            'length_stops':sum(c['resources']['length_stops'] for c in selected)}


def validate_record(record,manifest,task,route):
    if type(record.get('accepted')) is not bool or type(record.get('strict_pass')) is not bool:
        raise ValueError('Recorded decisions must be Boolean')
    if (manifest.get('settings',{}).get('mode')!='benign' or manifest.get('model')!=route['id']
            or len(manifest.get('candidates',[]))!=1):
        raise ValueError('Generation provenance differs')
    candidate=manifest['candidates'][0]
    if type(candidate.get('accepted')) is not bool:
        raise ValueError('Manifest acceptance must be Boolean')
    if any(record.get(key)!=task[key] for key in ['family','level','track']):
        raise ValueError('Recorded task grouping differs from the frozen design')
    prompt=task['prompt'].encode()
    if manifest.get('payload')!={'sha256':hashlib.sha256(prompt).hexdigest(),'bytes':len(prompt)}:
        raise ValueError('Manifest task text differs from the frozen task')
    if record.get('arm')!='current' or record.get('trial')!=0:
        raise ValueError('Recorded arm or replicate differs from the frozen design')
    for key in ['accepted','status','candidate']:
        if record.get(key)!=candidate.get(key): raise ValueError('Record disagrees with manifest: '+key)
    if record['language']!=task['language'] or candidate['language']!=task['language']:
        raise ValueError('Record target differs from task')
    if record['attempts']!=len(candidate['attempts']) or record['attempt_outcomes']!=[a['status'] for a in candidate['attempts']]:
        raise ValueError('Recorded attempts differ from manifest')
    if record['strict_pass']!=bool(record['accepted'] and record['grade'] and record['grade'].get('passed')):
        raise ValueError('Recorded verdict disagrees with independent grade')
    return candidate


def publish(root,output):
    from evidence import enrich,markdown
    protocol=verify(root); tasks={t['id']:t for t in json.loads((root/'tasks.json').read_text())['tasks']}; cases=[]
    output.mkdir(parents=True,exist_ok=True); (output/'candidates').mkdir(exist_ok=True)
    for model in protocol['models']:
        for identity in protocol['task_ids']:
            directory=root/'runs'/model/identity; record=json.loads((directory/'record.json').read_text())
            if record.get('benign') is not True or record['model']!=model or record['task']!=identity: raise ValueError('Invalid record identity')
            manifest_path=directory/'generation/manifest.json'
            if digest(manifest_path)!=record['manifest_sha256']: raise ValueError('Generation manifest changed')
            manifest=json.loads(manifest_path.read_text())
            manifest_candidate=validate_record(record,manifest,tasks[identity],protocol['models'][model])
            case_id=hashlib.sha256((digest(root/'protocol.json')+':'+model+':'+identity).encode()).hexdigest()
            case={k:record[k] for k in ['model','task','language','family','level','track','arm','trial','accepted','strict_pass','grade','status','attempts','attempt_outcomes']}
            case.update(id=case_id,prompt=tasks[identity]['prompt'],source_sha256=None)
            case['attempt_checks']=[{'attempt':a['attempt'],'status':a['status'],'finish_reason':a.get('response',{}).get('finish_reason'),
                                    'checks':a.get('validation',{}).get('checks',[]),'formatting':a.get('formatting')}
                                   for a in manifest_candidate['attempts']]
            if record['accepted']:
                candidate=record['candidate']; path=directory/'generation'/candidate['relative_path']; path.resolve().relative_to((directory/'generation').resolve())
                if path.is_symlink() or digest(path)!=candidate['sha256']: raise ValueError('Candidate hash differs')
                (output/'candidates'/(case_id+'.txt')).write_bytes(path.read_bytes()); case['source_sha256']=candidate['sha256']
            resources={'inference_seconds':0,'prompt_tokens':0,'completion_tokens':0,'length_stops':0}
            traces=sorted((directory/'traces').glob('*.json'))
            if len(traces)!=len(manifest_candidate['attempts']): raise ValueError('Missing or extra inference traces')
            for trace,attempt in zip(traces,manifest_candidate['attempts']):
                value=json.loads(trace.read_text())
                if value.get('benign') is not True: raise ValueError('Nonbenign trace')
                if hashlib.sha256(json.dumps(value['request'],sort_keys=True).encode()).hexdigest()!=value['request_sha256']: raise ValueError('Trace request hash differs')
                response=value['response']; usage=response.get('usage') or {}
                raw=response['response_text'].encode()
                if (hashlib.sha256(raw).hexdigest()!=attempt['response']['sha256'] or len(raw)!=attempt['response']['bytes']
                        or response['resolved_model']!=protocol['models'][model]['id']):
                    raise ValueError('Response trace differs from generation manifest')
                resources['inference_seconds']+=value['seconds']; resources['prompt_tokens']+=usage.get('prompt_tokens',0) or 0
                resources['completion_tokens']+=usage.get('completion_tokens',0) or 0; resources['length_stops']+=response.get('finish_reason')=='length'
            case['resources']=resources; cases.append(case)
    if len(cases)!=protocol['planned']: raise ValueError('Study incomplete')
    integration=json.loads((root/'integration/report.json').read_text())
    proof=json.loads((root/'reproduction-check.json').read_text())
    if proof.get('passed') is not True or proof['protocol_sha256']!=digest(root/'protocol.json'): raise ValueError('Independent offline reproduction required')
    expected={(case['model'],case['task'],case['source_sha256']) for case in cases if case['accepted']}
    observed={(row['model'],row['task'],row['source_sha256']) for row in proof['outcomes'] if row['matched']}
    if observed!=expected or len(proof['outcomes'])!=len(expected) or proof['accepted_candidates']!=len(expected):
        raise ValueError('Offline reproduction does not cover the exact accepted source grid')
    if integration.get('benign') is not True or integration['protocol_sha256']!=digest(root/'protocol.json'):
        raise ValueError('Integration belongs to a different study')
    expected_integrations={(repo['id'],case['model'],case['task'],case['source_sha256'])
        for repo in json.loads((root/'repositories.json').read_text())['repositories']
        for case in cases if case['accepted'] and case['language'] in repo['formats']}
    actual_integrations={(row['repository'],row['model'],row['task'],row['source_sha256']) for row in integration['outcomes']}
    if actual_integrations!=expected_integrations or len(integration['outcomes'])!=len(expected_integrations):
        raise ValueError('Integration grid is incomplete or duplicated')
    for repository in integration['repositories']:
        for step in repository['steps']:
            path=root/'integration/logs'/repository['id']/step['log']
            path.resolve().relative_to((root/'integration/logs').resolve())
            if path.is_symlink() or digest(path)!=step['log_sha256']:
                raise ValueError('Pinned build log is missing or changed')
    save(output/'scores.json',{'benign':True,'protocol_sha256':digest(root/'protocol.json'),'cases':cases})
    shutil.copyfile(root/'protocol.json',output/'protocol.json')
    groups=[]
    for dimension in ['language','level','family','track']:
        for value in sorted({c[dimension] for c in cases}):
            groups.append({'dimension':dimension,'value':value,'metrics':[metrics([c for c in cases if c[dimension]==value],model) for model in protocol['models']]})
    report={'schema_version':1,'benign':True,'id':output.name,'title':'Language, format, and codebase breadth','stage':'breadth','state':'complete',
            'created_at':protocol['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),'design':{'tasks':len(tasks),'families':len({t['family'] for t in tasks.values()}),'replicates':1,
              'formats':sorted({t['language'] for t in tasks.values()}),'models':list(protocol['models']),'arms':['current'],'settings':protocol['settings']},
            'counts':{'planned':protocol['planned'],'completed':len(cases),'accepted':sum(c['accepted'] for c in cases),'verified':sum(c['strict_pass'] for c in cases),
                      'hidden_checks':sum((c['grade'] or {}).get('hidden_cases',0) for c in cases)},
            'metrics':[metrics(cases,model) for model in protocol['models']],'effects':[],'groups':groups,'cases':cases,
            'integration':integration,'methodology':[
                {'title':'Frozen breadth design','body':'63 task-format units × two live model endpoints × one replicate = 126 generations. Eleven source languages share three behavioral families; eight document formats share three transformation tasks; six binary descriptions check typed metadata graphs. Tasks, private expected values, engine and runner hashes were frozen before inference.'},
                {'title':'Equal attempt budget','body':'Both models use 8,192 output tokens, temperature 0.2, top_p 0.8, no-thinking requested, and at most two attempts. One serial queue per model, queues concurrent. Retries receive only CLI acceptance diagnostics. Completed failures are retained; infrastructure interruptions are separate. Requested seeds are recorded but backend determinism is not independently verified.'},
                {'title':'Behavior, semantics, and acceptance','body':'Accepted helpers are compiled or interpreted by native toolchains in restricted subprocesses. Ceiling division, increasing contiguous runs, and bounded ASCII decimal parsing include empty, invalid, boundary, Unicode, embedded-NUL and deterministic randomized inputs. Documents must preserve exact inputs and compute correct temperature, invoice, and schedule results. Private expected outputs never enter model requests. Generic CLI acceptance does not imply these task-specific checks passed.'},
                {'title':'Reference controls and containment','body':'All 63 authored correct controls passed direct validation and independent grading before freezing. Those controls did not exercise extraction; the later full-pipeline audit is reported separately. Native processes deny network, home reads except the Python runtime, and writes outside temporary work directories, with CPU, file-size and wall-time limits. Three denial probes passed.'},
                {'title':'Pinned repository interfaces','body':'Clean cJSON, zlib and curl releases are built from exact commits. cJSON consumes every accepted JSON candidate; zlib round-trips every accepted YAML/TOML/XML/CSV/INI candidate; curl consumes every accepted HTTP response over an authored loopback server. Selection includes semantically failing accepted files. Upstream tests and consumer results are recorded separately. Tracked source hashes are verified unchanged.'},
                {'title':'Reproduction','body':'Every accepted candidate was regraded from unchanged bytes without model inference, with exact per-case agreement. The downloadable archive includes frozen runner, engine, tasks, private oracles, requests/responses, manifests, source files, toolchain versions and SHA-256 inventory. Rebuilding the upstream projects requires their public pinned revisions; native reproduction currently requires macOS and the listed toolchains.'}],
            'limitations':protocol['limitations']+['No baseline arm: this extension measures current-system breadth and does not estimate improvement over the earlier study. Studies are not pooled.',
                  'No confidence intervals are shown: one replicate and seven reused task families do not support treating 63 units or thousands of assertions as independent population samples.',
                  'Successful native examples are bounded tests, not all-input correctness or a proof of purity. No memory address-space limit is enforced on macOS.',
                  'Integration covers three C projects and selected consumer interfaces. It does not establish arbitrary placement/restoration, all build configurations, Windows/Linux behavior, or decompilation retention.'],
            'references':[{'title':'cJSON pinned source','url':'https://github.com/DaveGamble/cJSON/tree/c859b25da02955fef659d658b8f324b5cde87be3'},
                          {'title':'zlib pinned source','url':'https://github.com/madler/zlib/tree/51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf'},
                          {'title':'curl pinned source','url':'https://github.com/curl/curl/tree/7eb8c048470ed2cc14dca75be9c1cdae7ac8498b'}],
            'provenance':{'protocol_sha256':digest(root/'protocol.json'),'scores_sha256':digest(output/'scores.json'),'snapshot_files':len(protocol['files']),
                          'reproduction':proof,'environment':json.loads((root/'environment.json').read_text())}}
    report['findings']=[f"{row['model']}: {row['verified']}/{row['n']} candidates passed every registered check; {row['accepted']} passed CLI acceptance." for row in report['metrics']]
    report['findings'].append(f"{integration['passed']}/{integration['total']} selected consumer integrations passed. This measures compatibility of specific interfaces, separately from semantic correctness.")
    enrich(report,root,protocol)
    text='# Benign breadth evaluation\n\n'+'\n\n'.join(report['findings'])+'\n\n'
    text+='| Model | Accepted | Verified | Accepted but not verified | Attempts |\n| --- | --- | --- | --- | --- |\n'
    for row in report['metrics']: text+=f"| {row['model']} | {row['accepted']}/{row['n']} | {row['verified']}/{row['n']} | {row['false_acceptance']} | {row['attempts']} |\n"
    text+='\n'+ '\n\n'.join('## '+m['title']+'\n\n'+m['body'] for m in report['methodology'])
    text+='\n\n## Repository sizes\n\n| Repository | Tracked files | Source lines | Commit |\n| --- | --- | --- | --- |\n'
    for row in integration['repositories']: text+=f"| {row['id']} | {row['inventory']['tracked_files']} | {row['inventory']['source_lines']} | {row['revision']} |\n"
    text+='\nSource lines count physical lines in the registered C/C++/Python/Perl/shell/CMake extensions; comments and blank lines are included.\n\n## Limitations\n\n'+'\n'.join('- '+s for s in report['limitations'])+'\n'
    text+=markdown(report)
    (output/'REPORT.md').write_text(text)
    archive=output/'reproduction.zip'
    files=[p for p in root.rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts and p.suffix!='.pyc'
           and (p.suffix!='.log' or root/'integration/logs' in p.parents or root/'supplement/retention' in p.parents)
           and not (p.parent==root/'integration' and p.name=='json-consumer')]
    members={str(p.relative_to(root)):digest(p) for p in files}
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in files: bundle.write(path,str(path.relative_to(root)))
        # Publication integrity checks may be strengthened after freezing without
        # changing the frozen generation engine, grader, or experimental outcomes.
        name='publication/publish.py'; data=Path(__file__).read_bytes(); bundle.writestr(name,data)
        members[name]=hashlib.sha256(data).hexdigest()
        for extra in ['reproduce.py','audit_extraction.py','audit_controls.py','evidence.py','retention_check.py','plot.py']:
            path=Path(__file__).parent/extra; name='publication/'+extra; data=path.read_bytes()
            bundle.writestr(name,data); members[name]=hashlib.sha256(data).hexdigest()
        bundle.writestr('ARTIFACTS.json',json.dumps({'benign':True,'files':members},indent=2)+'\n')
    report['provenance']['publication_source_sha256']=digest(Path(__file__))
    report['provenance']['reproduction_sha256']=digest(archive)
    save(output/'report.json',report)
    print(json.dumps({'study':str(output),'counts':report['counts'],'metrics':report['metrics'],'archive_bytes':archive.stat().st_size}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('root',type=Path); parser.add_argument('output',type=Path); args=parser.parse_args(); publish(args.root.resolve(),args.output.resolve())
