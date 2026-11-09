"""Export the completed, explicitly benign November 7 pilot without changing its scores."""
import hashlib
import json
from pathlib import Path
import sys


def read(path): return json.loads(path.read_text())
def sha(data): return hashlib.sha256(data).hexdigest()
def save(path, value): path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def publish(root, destination):
    protocol=read(root/'protocol.json'); summary=read(root/'summary.json')
    identity=destination.name
    if summary['planned_per_model']!=26: raise ValueError('Unexpected pilot denominator')
    destination.mkdir(parents=True,exist_ok=True); (destination/'candidates').mkdir(exist_ok=True)
    jobs={job['name']:job for job in protocol['jobs']}
    cases=[]; metrics=[]; evidence={}
    issues={('glm','range','go'):'Correct tested behavior, but CheckValue does not match the requested API name.',
            ('glm','range','swift'):'Correct tested behavior, but isInclusive does not match the requested API name.',
            ('glm','range','rust'):'Unfinished and misleading parameter documentation.',
            ('glm','range','ruby'):'Nonidiomatic triple-quoted documentation string.',
            ('glm','range','lua'):'Redundant min/max operations; tested behavior is correct.',
            ('glm','range','html'):'Three misleading row labels; actual lower-bound, upper-bound, and reversed-bound examples are missing.',
            ('glm','range','json'):'Correct example arithmetic inside the wrong root and example layout.',
            ('glm','catalog-response','json'):'Unrequested catalog wrapper and HTTP metadata.',
            ('deepseek','clamp-helper','llvm'):'Correct tested behavior, but two br instructions violate the comparisons/selects-only request.',
            ('deepseek','range','bash'):'Missing requested explanatory documentation.'}
    for model in ['glm','deepseek']:
        behavior=read(root/(model+'-behavior.json'))
        documents=read(root/(model+'-documents.json'))
        evidence[model]={'behavior':behavior,'documents':documents,'javadoc':read(root/(model+'-javadoc.json'))}
        for row in summary['models'][model]['records']:
            job,language=row['job'],row['language']; run=root/model/job
            manifest=read(run/'manifest.json')
            if manifest.get('kind')!='repel_source_generation' or manifest.get('settings',{}).get('mode')!='benign':
                raise ValueError('Only explicitly benign generation can be exported')
            candidate=next(c for c in manifest['candidates'] if c['language']==language)
            if candidate['accepted']!=row['accepted'] or len(candidate['attempts'])!=row['attempts']: raise ValueError('Pilot summary mismatch')
            case_id=sha(f'{model}:original:{job}:{language}:0'.encode())
            checksum=None
            if row['accepted']:
                relative=Path(candidate['candidate']['relative_path'])
                if relative.is_absolute() or '..' in relative.parts: raise ValueError('Unsafe candidate path')
                path=run/relative; path.resolve().relative_to(run.resolve())
                if path.is_symlink() or path.parent.is_symlink(): raise ValueError('Symlinked candidate')
                data=path.read_bytes(); checksum=sha(data)
                if checksum!=row['sha256'] or checksum!=candidate['candidate']['sha256']: raise ValueError('Candidate changed')
                (destination/'candidates'/(case_id+'.txt')).write_bytes(data)
            prompt_path=root/jobs[job]['input']
            if sha(prompt_path.read_bytes())!=protocol['inputs'][jobs[job]['input']]: raise ValueError('Pilot input changed')
            grade={'scope':'Exploratory diagnostic checks; no preregistered aggregate correctness score.'}
            native=behavior.get(job+'/'+language)
            if native: grade['native_behavior']=native
            document=next((d for d in documents['checks'] if d['job']==job and d['language']==language),None)
            if document: grade['document_checks']=document
            diagnostic=issues.get((model,job,language),'')
            if language=='java': diagnostic='Behavior passes, but Javadoc fails with two malformed-HTML errors from unescaped comparisons.'
            if document and document.get('task_fields_match') is False: diagnostic='Symbolic metadata does not match requested section/symbol names or references.'
            if not row['accepted']: diagnostic='No accepted candidate after the three-attempt budget; rejected implementations were not saved as source.'
            cases.append({'id':case_id,'model':model,'arm':'original','task':job+'/'+language,'trial':0,'language':language,
                'level':None,'accepted':row['accepted'],'strict_pass':None,'attempts':row['attempts'],'status':row['status'],
                'source_sha256':checksum,'prompt':prompt_path.read_text(),'public_contract':None,'grade':grade,'diagnostic':diagnostic})
        records=summary['models'][model]['records']; accepted=sum(row['accepted'] for row in records)
        metrics.append({'model':model,'arm':'original','n':len(records),'accepted':accepted,'acceptance_rate':accepted/len(records),
            'verified':None,'verified_rate':None,'false_acceptance':None,'accepted_precision':None,'ci95':None,
            'first_attempt_accepted':sum(row['first_attempt_accepted'] for row in records),'attempts':sum(row['attempts'] for row in records)})
    report={'schema_version':1,'benign':True,'id':identity,'stage':'pilot','state':'complete','title':'18 formats · GLM / DeepSeek pilot',
        'created_at':protocol['created_at'],'updated_at':'2026-11-09T00:00:00Z',
        'design':{'tasks':26,'replicates':1,'formats':sorted({row['language'] for row in cases}),'levels':[],
                  'models':['glm','deepseek'],'arms':['original'],'settings':protocol['settings']},
        'counts':{'planned':52,'completed':52,'accepted':45,'verified':None,'hidden_checks':18225},
        'metrics':metrics,'effects':[],'groups':[],'cases':cases,
        'findings':['DeepSeek was accepted in 25/26 targets, versus GLM in 20/26; it used 29 attempts versus 49.',
            'All 25 accepted executable helpers passed 729 inputs each (18,225 checks). Those correlated checks are not 18,225 independent samples.',
            'Task compliance remained weaker than syntax acceptance: GLM had wrong API names, document layouts, and metadata references. Both Java documentation builds failed.',
            'These observations motivated explicit public contracts and an independent, harder benchmark. This pilot does not measure the effect of the new system.'],
        'methodology':[
            {'title':'Design','body':'One shared range-check task across all 18 formats, five additional binary-description variants, a clamp task, and a catalog task in JSON/HTTP: 26 task/format units per model, one run each.'},
            {'title':'Generation','body':'Both models used identical inputs and the functional structure profile, temperature 0.2, top-p 0.8, 2,048 output tokens, no-thinking request, two retries, and a 60-second validator limit. Required checks were retained; unavailable optional linters were disclosed.'},
            {'title':'Independent review','body':'All 45 accepted sources were manually reviewed after benign provenance and SHA-256 verification. Native tests used all 729 triples from nine integers, including signed 32-bit extremes. Actual helper names were used; name compliance was recorded separately. Documents were checked for arithmetic, structure, labels, references, and HTTP framing.'},
            {'title':'Preservation','body':'Original outputs are unchanged. A full-disk interruption occurred before the first GLM clamp attempt was checkpointed; that job was restarted after recovery. Completed failures were preserved. The 49 GLM attempts count checkpointed attempts, not unrecorded interrupted work.'},
            {'title':'Interpretation','body':'Acceptance is reported separately from correctness. The pilot has no preregistered aggregate strict score or confidence interval. Behavioral checks, API naming, documentation, and document defects remain visible as separate evidence.'}],
        'limitations':['One small task family translated across many formats; these are correlated task/format units, not diverse independent programming problems.',
            'One run per model/target, fixed model order, and uncontrolled serving load; no causal speed or general model-ranking claim.',
            'Rejected source was not preserved. Review concerns only accepted outputs.',
            'Symbolic binary schemas are not assembled artifacts. No compilation/decompilation-retention or actual network-traffic claim.',
            'Manual and post hoc diagnostics are exploratory; they are not a preregistered correctness endpoint.'],
        'provenance':{'protocol_sha256':sha((root/'protocol.json').read_bytes()),'baseline_commit':protocol['commit'],
                      'snapshot_files':len(protocol['framework_files']),'models':protocol['models']},'references':[]}
    (destination/'protocol.json').write_bytes((root/'protocol.json').read_bytes())
    save(destination/'scores.json',{'schema_version':1,'benign':True,'summary':summary,'evidence':evidence,'cases':cases})
    report['provenance']['scores_sha256']=sha((destination/'scores.json').read_bytes())
    save(destination/'report.json',report)
    (destination/'REPORT.md').write_text('# Benign multi-format pilot\n\n'+ '\n\n'.join(report['findings'])+'\n\n## Methodology\n\n'+
        '\n\n'.join('### '+item['title']+'\n\n'+item['body'] for item in report['methodology'])+'\n\n## Limitations\n\n'+
        '\n'.join('- '+item for item in report['limitations'])+'\n\nSee `scores.json` for per-candidate evidence and `protocol.json` for the recorded settings and hashes.\n')
    print(json.dumps({'study':identity,'cases':len(cases),'accepted':45,'behavior_checks':18225}))


if __name__=='__main__': publish(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
