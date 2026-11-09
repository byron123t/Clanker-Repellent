"""Task-clustered paired analysis and a portable, explicitly benign dashboard report."""
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys


def quantile(values,p):
    ordered=sorted(values); position=(len(ordered)-1)*p; index=int(position); fraction=position-index
    return ordered[index]*(1-fraction)+ordered[min(index+1,len(ordered)-1)]*fraction


def paired_bootstrap(records,model,repeats,task_ids,draws=10000):
    grouped=defaultdict(dict)
    for record in records:
        if record['model']==model: grouped[(record['task'],record['trial'])][record['arm']]=record
    task_values=[]
    for task in task_ids:
        pairs=[grouped[(task,trial)] for trial in range(repeats)]
        if any(set(pair)!={'baseline','contract'} for pair in pairs): return None
        baseline=sum(pair['baseline']['strict_pass'] for pair in pairs)/repeats
        enhanced=sum(pair['contract']['strict_pass'] for pair in pairs)/repeats
        task_values.append((baseline,enhanced))
    if not task_values: return None
    rng=random.Random(20261109)
    samples=[[],[],[]]
    n=len(task_values)
    for _ in range(draws):
        chosen=[task_values[rng.randrange(n)] for _ in range(n)]
        before=sum(pair[0] for pair in chosen)/n; after=sum(pair[1] for pair in chosen)/n
        samples[0].append(before); samples[1].append(after); samples[2].append(after-before)
    return {'model':model,'paired_tasks':n,'replicates':repeats,'bootstrap_draws':draws,
            'difference':sum(after-before for before,after in task_values)/n,
            'ci95':[quantile(samples[2],.025),quantile(samples[2],.975)],
            'baseline_ci95':[quantile(samples[0],.025),quantile(samples[0],.975)],
            'contract_ci95':[quantile(samples[1],.025),quantile(samples[1],.975)],
            'method':'Paired percentile bootstrap over tasks, retaining all replicates and arms within each task.'}


def metrics(records,model,arm):
    source_arm='baseline' if arm=='filter-only' else arm
    selected=[r for r in records if r['model']==model and r['arm']==source_arm]
    n=len(selected)
    accepted=sum(r['filter_only_accepted'] if arm=='filter-only' else r['accepted'] for r in selected)
    correct=sum(r['filter_only_pass'] if arm=='filter-only' else r['strict_pass'] for r in selected)
    def resource(name):
        values=[r.get('resources',{}).get(name) for r in selected]
        return sum(values) if values and all(type(v) in {int,float} for v in values) else None
    return {'model':model,'arm':arm,'n':n,'accepted':accepted,'verified':correct,
            'acceptance_rate':accepted/n if n else None,'verified_rate':correct/n if n else None,
            'false_acceptance':accepted-correct,'accepted_precision':correct/accepted if accepted else None,
            'first_attempt_accepted':sum(r['first_attempt_accepted'] and (arm!='filter-only' or r['filter_only_accepted']) for r in selected),
            'verified_after_retry':sum(r['attempts']>1 and (r['filter_only_pass'] if arm=='filter-only' else r['strict_pass']) for r in selected),
            'attempts':sum(r['attempts'] for r in selected),
            'inference_seconds':resource('inference_seconds'),'prompt_tokens':resource('prompt_tokens'),
            'completion_tokens':resource('completion_tokens'),'length_stops':resource('length_stops'),
            'description':'Offline baseline filtering; no new generation' if arm=='filter-only' else 'Generated with the registered attempt budget'}


def family_interval(records, model, draws=10000):
    """Sensitivity to related format/task instances sharing an authored family."""
    grouped=defaultdict(list)
    for record in records:
        if record['model']==model:
            grouped[record['family']].append((1 if record['arm']=='contract' else -1)*record['strict_pass'])
    clusters=list(grouped.values()); rng=random.Random(20261109); samples=[]
    for _ in range(draws):
        chosen=[clusters[rng.randrange(len(clusters))] for _ in clusters]
        samples.append(2*sum(sum(cluster) for cluster in chosen)/sum(len(cluster) for cluster in chosen))
    return {'family_clusters':len(clusters),'family_ci95':[quantile(samples,.025),quantile(samples,.975)]}


def report(root):
    protocol=json.loads((root/'protocol.json').read_text()); scores=json.loads((root/'scores.json').read_text())
    if protocol.get('benign') is not True or scores.get('benign') is not True: raise ValueError('Only benign studies can be published')
    if hashlib.sha256((root/'protocol.json').read_bytes()).hexdigest()!=scores['protocol_sha256']: raise ValueError('Protocol changed after scoring')
    records=scores['records']; expected=len(protocol['task_ids'])*protocol['repeats']*len(protocol['models'])*2
    grid={(model,arm,task,trial) for model in protocol['models'] for arm in protocol['arms']
          for task in protocol['task_ids'] for trial in range(protocol['repeats'])}
    observed={(r['model'],r['arm'],r['task'],r['trial']) for r in records}
    if len(observed)!=len(records): raise ValueError('Duplicate experiment cells')
    if observed-grid: raise ValueError('Observation outside the registered experiment')
    complete=observed==grid
    tasks={task['id']:task for task in json.loads((root/'tasks.json').read_text())['tasks']}
    rows=[metrics(records,model,arm) for model in protocol['models'] for arm in ['baseline','contract','filter-only']]
    effects=[paired_bootstrap(records,model,protocol['repeats'],protocol['task_ids']) for model in protocol['models']]
    effects=[effect for effect in effects if effect is not None]
    for effect in effects:
        if all('family' in r for r in records): effect.update(family_interval(records,effect['model']))
    for row in rows:
        effect=next((e for e in effects if e['model']==row['model']),None)
        row['ci95']=effect.get(row['arm']+'_ci95') if effect else None
    groups=[]
    for dimension in ['level','language']:
        for value in sorted({r[dimension] for r in records},key=str):
            subset=[r for r in records if r[dimension]==value]
            groups.append({'dimension':dimension,'value':value,
                           'metrics':[metrics(subset,model,arm) for model in protocol['models'] for arm in ['baseline','contract']]})
    cases=[]
    for record in records:
        task=tasks[record['task']]
        cases.append({key:record[key] for key in ['id','model','arm','task','trial','language','level','accepted','strict_pass','attempts','status','grade']})
        cases[-1].update(prompt=task['prompt'],public_contract=task['contract'],
                         resources=record.get('resources'),attempt_checks=record.get('attempt_checks'),
                         source_sha256=record['candidate']['sha256'] if record.get('candidate') else None,
                         diagnostic=record.get('grade',{}).get('diagnostic') or record.get('contract_check',{}).get('diagnostic') or '')
    stage=protocol['stage']
    status_path=root/'status.json'
    status=json.loads(status_path.read_text()) if status_path.is_file() else {}
    awaiting=not records and status.get('state')=='interrupted'
    findings=[]
    if awaiting:
        findings=['No model observations have completed. The inference queues are interrupted.',
                  'The study is frozen and ready to resume when the inference tunnels are available. Missing observations are not quality failures.',
                  'The completed authored audit and historical model pilot are separate studies; neither substitutes for this model comparison.']
    else:
        findings=['All planned observations are recorded.' if complete else 'The study is incomplete; missing observations are not model-quality failures.',
                  'Filter-only rows describe rejection of existing baseline outputs, not repair or additional generation.']
        for model in protocol['models']:
            before=next(row for row in rows if row['model']==model and row['arm']=='baseline')
            after=next(row for row in rows if row['model']==model and row['arm']=='contract')
            if before['n'] and after['n']:
                findings.append(f"{model}: {before['verified']}/{before['n']} baseline candidates and {after['verified']}/{after['n']} contract candidates passed every independent check. Accepted-but-incorrect outputs: {before['false_acceptance']} versus {after['false_acceptance']}.")
                findings.append(f"{model}: {after['verified_after_retry']} contract candidates became verified successes after a rejected attempt; {after['n']-after['accepted']} ended without an accepted candidate.")
    return {'schema_version':1,'benign':True,'id':root.name,'stage':stage,'state':'complete' if complete else 'incomplete',
            'title':('Held-out' if stage=='heldout' else 'Development')+' · task-contract evaluation',
            'created_at':protocol['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
            'design':{'tasks':len(protocol['task_ids']),'replicates':protocol['repeats'],
                      'formats':sorted({tasks[t]['language'] for t in protocol['task_ids']}),'levels':[1,2,3],
                      'models':list(protocol['models']),'arms':['baseline','contract','filter-only'],'settings':protocol['settings']},
            'counts':{'planned':expected,'completed':len(records),'accepted':sum(r['accepted'] for r in records),
                      'verified':sum(r['strict_pass'] for r in records),'hidden_checks':sum(r['grade'].get('hidden_cases',0) for r in records)},
            'metrics':rows,'effects':effects,'groups':groups,'cases':cases,'findings':findings,
            'infrastructure':{'state':status.get('state','unknown'),'interruptions':status.get('interruptions',{})},
            'methodology':[
                {'title':'Question','body':'Does task-aware acceptance and retry feedback improve verified benign generation over parser/compiler/structure checks? The intervention includes the accumulator-dependency fix.'},
                {'title':'Design','body':f"{len(protocol['task_ids'])} {stage} task/format units; {protocol['repeats']} replicates, two models, two generation arms. Randomized block and arm order; equal token/attempt budgets. Filter-only is a post hoc re-scoring ablation, not a generation arm."},
                {'title':'Independent outcomes','body':'Acceptance and correctness are separate. Each numeric program must pass three public and 320 private cases. Documents must match independently computed records, fields, references, ordering, and framing. The model worker never loads the private oracle file as prompt data.'},
                {'title':'Uncertainty','body':'95% paired task-bootstrap intervals use 10,000 draws. Tasks are resampled with all replicates and both arms retained; individual test inputs are not independent observations. Intervals appear only for complete paired data. Boundary intervals can degenerate and do not prove universal correctness.'},
                {'title':'Related-task sensitivity','body':'Some authored task instances share calculation families across formats. An additional 10,000-draw paired bootstrap resamples entire named families, retaining all member tasks, arms, and replicates, and weights the rate by the sampled candidate count. Its interval is reported separately from the registered task-unit interval.'},
                {'title':'Resource accounting','body':'Provider-reported prompt/completion tokens and inference latency include all attempts, including failed and truncated responses. Missing usage remains unknown. Filter-only reuses the baseline cost and adds no inference. Latencies describe this run, not an intrinsic model speed comparison; server load and hardware are uncontrolled.'},
                {'title':'Reproduction','body':'Engine, corpus, private fixture, and runner snapshots are pinned by SHA-256. Seeds are requested, not assumed to guarantee server determinism. Completed failures are preserved. Infrastructure interruptions are disclosed, not counted as model failures.'}],
            'limitations':['Synthetic, narrow integer/data tasks across seven formats; not a general software-engineering benchmark.',
                           'Authored complexity levels are not calibrated difficulty measurements.',
                           'Held-out means new task instances, not wholly unseen algorithm families. JSON/HTTP calculations and HTML tables share templates; related-family intervals are a sensitivity analysis, not evidence of generalization to arbitrary software.',
                           'The generator and grader share parsing/eligibility dependencies, although primary native results and reference outcomes are separate.',
                           'Symbolic binary metadata does not demonstrate compilation/decompilation survival; HTTP fixtures are never replayed.',
                           'Model training/fine-tuning provenance and serving hardware/load are not controlled. No contamination-free or causal speed claim.',
                           'Development results are exploratory and excluded from held-out inference.' if stage=='development' else 'Inference is conditional on 24 authored task units; format/level slices are descriptive and exploratory.'],
            'provenance':{'protocol_sha256':scores['protocol_sha256'],'baseline_commit':protocol['baseline_commit'],'models':protocol['models'],
                          'snapshot_files':len(protocol['files']),'study_directory':root.name},
            'references':[{'title':'EvalPlus (NeurIPS 2023)','url':'https://arxiv.org/abs/2305.01210'},
                          {'title':'LiveCodeBench (ICLR 2025)','url':'https://arxiv.org/abs/2403.07974'}]}


def publish(root,destination):
    value=report(root); destination.mkdir(parents=True,exist_ok=True)
    (destination/'candidates').mkdir(exist_ok=True)
    scores=json.loads((root/'scores.json').read_text())['records']
    for record in scores:
        if not record.get('candidate'): continue
        relative=Path(record['candidate']['relative_path'])
        if relative.is_absolute() or '..' in relative.parts: raise ValueError('Unsafe source path')
        directory=Path(record['directory'])
        if directory.is_absolute() or '..' in directory.parts: raise ValueError('Unsafe run path')
        source=root/directory/'generation'/relative
        source.resolve().relative_to(root.resolve())
        if source.is_symlink() or source.parent.is_symlink(): raise ValueError('Symlinked candidate')
        data=source.read_bytes()
        if hashlib.sha256(data).hexdigest()!=record['candidate']['sha256']: raise ValueError('Candidate integrity failure')
        (destination/'candidates'/(record['id']+'.txt')).write_bytes(data)
    (destination/'protocol.json').write_bytes((root/'protocol.json').read_bytes())
    (destination/'scores.json').write_bytes((root/'scores.json').read_bytes())
    value['provenance']['scores_sha256']=hashlib.sha256((destination/'scores.json').read_bytes()).hexdigest()
    (destination/'REPORT.md').write_text(markdown(value))
    temporary=destination/'report.json.tmp'
    with temporary.open('w') as stream:
        json.dump(value,stream,indent=2,allow_nan=False); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(destination/'report.json')
    print(json.dumps({'published':str(destination),'state':value['state'],'counts':value['counts'],'effects':value['effects']},indent=2))


def markdown(value):
    lines=['# '+value['title'],'',f"State: **{value['state']}**. {value['counts']['completed']}/{value['counts']['planned']} planned observations.",'',
           '| Model | System | Accepted | Verified | False acceptances | Attempts |','| --- | --- | ---: | ---: | ---: | ---: |']
    for row in value['metrics']:
        lines.append(f"| {row['model']} | {row['arm']} | {row['accepted']}/{row['n']} | {row['verified']}/{row['n']} | {row['false_acceptance']} | {row['attempts']} |")
    for effect in value['effects']:
        lines+=['',f"{effect['model']}: paired change {effect['difference']*100:+.1f} percentage points (95% task-bootstrap interval {effect['ci95'][0]*100:+.1f} to {effect['ci95'][1]*100:+.1f}; {effect['paired_tasks']} tasks)."]
        if 'family_ci95' in effect:
            lines += [f"Related-family sensitivity: {effect['family_ci95'][0]*100:+.1f} to {effect['family_ci95'][1]*100:+.1f} pp ({effect['family_clusters']} family clusters)."]
    if any(row.get('inference_seconds') is not None for row in value['metrics']):
        lines+=['','## Observed inference cost','',
                '| Model | System | Prompt tokens | Completion tokens | Inference seconds | Token-limit stops |',
                '| --- | --- | ---: | ---: | ---: | ---: |']
        for row in value['metrics']:
            if row['arm']=='filter-only': continue
            fields=[str(row.get(key)) if row.get(key) is not None else 'unknown'
                    for key in ('prompt_tokens','completion_tokens','inference_seconds','length_stops')]
            lines.append('| '+row['model']+' | '+row['arm']+' | '+' | '.join(fields)+' |')
    lines+=['','## Methodology','']
    for item in value['methodology']: lines+=['### '+item['title'],'',item['body'],'']
    lines+=['## Limitations','']+['- '+item for item in value['limitations']]
    lines+=['','## Provenance','', '```json',json.dumps(value['provenance'],indent=2),'```','',
            'Reproduce with the frozen runner and source snapshots. `scores.json` contains every completed observation; `protocol.json` pins the design and SHA-256 hashes.','']
    return '\n'.join(lines)


if __name__=='__main__': publish(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
