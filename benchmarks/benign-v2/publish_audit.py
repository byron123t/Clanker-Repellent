"""Publish the complete authored fault audit, with paired task-cluster uncertainty."""
from collections import defaultdict
import hashlib
import importlib.util
import json
from datetime import datetime,timezone
from pathlib import Path
import sys
import zipfile

from faults import read, save, sha, verify


def publish(root,destination):
    protocol=verify(root); corpus=read(root/'corpus.json')['records']; tasks={t['id']:t for t in read(root/'tasks.json')['tasks']}
    specification=importlib.util.spec_from_file_location('frozen_audit_analysis',root/'runner/analyze.py')
    analysis=importlib.util.module_from_spec(specification); specification.loader.exec_module(analysis)
    outcomes={arm:{r['id']:r for r in read(root/(arm+'-checks.json'))['records']} for arm in protocol['arms']}
    if any(set(rows)!={r['id'] for r in corpus} for rows in outcomes.values()): raise ValueError('Audit is incomplete or duplicated')
    grades={key:value['grade'] for key,value in outcomes['contract'].items()}
    if any(grades[r['id']]['passed']==r['known_fault'] for r in corpus): raise ValueError('Independent ground truth differs')
    trial=defaultdict(int); paired=[]
    for item in corpus:
        if not item['known_fault']: continue
        index=trial[item['task']]; trial[item['task']]+=1
        for arm in protocol['arms']:
            paired.append({'model':'authored','arm':arm,'task':item['task'],'trial':index,'strict_pass':not outcomes[arm][item['id']]['accepted']})
    effect=analysis.paired_bootstrap(paired,'authored',4,list(trial))
    effect['outcome']='Reduction in false acceptance on authored faults'; effect['replicates']=None; effect['variants_per_task']=4
    ablation=None
    if (root/'ablation-checks.json').is_file():
        ablation=read(root/'ablation-checks.json'); addendum=read(root/'ablation-protocol.json')
        if ablation.get('benign') is not True or ablation['protocol_sha256']!=sha((root/'ablation-protocol.json').read_bytes()):
            raise ValueError('Ablation provenance changed')
        for name,expected in addendum['files'].items():
            if sha((root/name).read_bytes())!=expected: raise ValueError('Ablation input changed')
        if {r['id'] for r in ablation['records']}!={r['id'] for r in corpus} or len(ablation['records'])!=84:
            raise ValueError('Ablation incomplete or duplicated')
        for arm in ['structure-fix','filter-only']:
            outcomes[arm]={r['id']:{'accepted':r[arm]['accepted']} for r in ablation['records']}
    def metrics(items,arm):
        bad=[r for r in items if r['known_fault']]; good=[r for r in items if not r['known_fault']]
        false_accept=sum(outcomes[arm][r['id']]['accepted'] for r in bad)
        false_reject=sum(not outcomes[arm][r['id']]['accepted'] for r in good)
        n=len(items); accepted=len(good)-false_reject+false_accept
        ci=effect.get(arm+'_ci95') if len(items)==len(corpus) else None
        return {'model':'authored','arm':arm,'n':n,'accepted':accepted,'verified':len(good)-false_reject,
                'acceptance_rate':accepted/n,'verified_rate':(len(good)-false_reject)/n,
                'false_acceptance':false_accept,'false_acceptance_rate':false_accept/len(bad),
                'faults':len(bad),'controls':len(good),'false_rejection':false_reject,'attempts':0,
                'accepted_precision':(len(good)-false_reject)/accepted if accepted else None,
                'ci95':[1-ci[1],1-ci[0]] if ci else None}
    rows=[metrics(corpus,arm) for arm in protocol['arms']]
    groups=[{'dimension':dimension,'value':value,'metrics':[metrics([r for r in corpus if r[dimension]==value],arm) for arm in protocol['arms']]}
            for dimension in ['level','language'] for value in sorted({r[dimension] for r in corpus},key=str)]
    destination.mkdir(parents=True,exist_ok=True); (destination/'candidates').mkdir(exist_ok=True)
    cases=[]
    for item in corpus:
        for arm in protocol['arms']:
            outcome=outcomes[arm][item['id']]; grade=grades[item['id']]; case_id=sha((item['id']+':'+arm).encode())
            diagnostic=('Known fault accepted: '+item['variant'] if outcome['accepted'] else 'Known fault correctly rejected: '+item['variant']) if item['known_fault'] else (
                'Correct authored control accepted.' if outcome['accepted'] else 'False rejection of a correct authored control.')
            data=item['source'].encode()
            if sha(data)!=item['source_sha256']: raise ValueError('Source checksum mismatch')
            (destination/'candidates'/(case_id+'.txt')).write_bytes(data)
            cases.append({'id':case_id,'model':'authored','arm':arm,'task':item['task']+'/'+item['variant'],'trial':0,
                'language':item['language'],'level':item['level'],'known_fault':item['known_fault'],'variant':item['variant'],
                'accepted':outcome['accepted'],'strict_pass':outcome['accepted'] and grade['passed'],'attempts':0,
                'status':'accepted' if outcome['accepted'] else 'rejected','source_sha256':item['source_sha256'],
                'prompt':tasks[item['task']]['prompt'],'public_contract':tasks[item['task']]['contract'],
                'grade':grade,'diagnostic':diagnostic,'validation':outcome['validation']})
    with zipfile.ZipFile(destination/'reproduction.zip','w',zipfile.ZIP_DEFLATED) as archive:
        archive.write(Path(__file__).with_name('reproduce.py'),'runner/reproduce.py')
        for name in ['plot.py','requirements.txt','publish_audit.py']: archive.write(Path(__file__).with_name(name),'runner/'+name)
        for relative in sorted(protocol['files']): archive.write(root/relative,relative)
        archive.write(root/'protocol.json','protocol.json')
        for arm in protocol['arms']: archive.write(root/(arm+'-checks.json'),arm+'-checks.json')
        if ablation:
            for name in ['ablation-protocol.json','ablation-runner.py','ablation-checks.json']: archive.write(root/name,name)
        proof=root.parent/'reproduction-check.json'
        if proof.is_file() and read(proof).get('benign') is True and read(proof).get('protocol_sha256')==sha((root/'protocol.json').read_bytes()):
            archive.write(proof,'reproduction-check.json')
    report={'schema_version':1,'benign':True,'id':destination.name,'stage':'audit','state':'complete',
        'title':'Controlled faults · what validation catches','created_at':protocol['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
        'design':{'tasks':12,'replicates':None,'variants_per_task':7,'formats':sorted({r['language'] for r in corpus}),
                  'levels':[1,2,3],'models':['authored'],'arms':protocol['arms'],'settings':protocol['settings']},
        'counts':{'planned':168,'completed':168,'accepted':sum(r['accepted'] for r in rows),'verified':sum(r['verified'] for r in rows),
                  'hidden_checks':sum(g.get('hidden_cases',0) for g in grades.values()),'unique_sources':84,'controls':36,'faults':48},
        'metrics':rows,'effects':[effect],'groups':groups,'cases':cases,
        'findings':[f"False acceptance fell from {rows[0]['false_acceptance']}/48 to {rows[1]['false_acceptance']}/48 on fixed authored faults; this is validator sensitivity, not a model-generation result.",
            f"The paired reduction is {effect['difference']*100:.1f} percentage points (95% task-bootstrap interval {effect['ci95'][0]*100:.1f}–{effect['ci95'][1]*100:.1f}; 12 task clusters).",
            'Correct-control false rejections fell from 3/36 to 0/36. All three affected variants use the same Python accumulator pattern.',
            'All 18 remaining false acceptances expose incomplete specifications: 14 unseen-input/memorization faults, three internally consistent documents with altered inputs, and one incorrect HTML calculation.'],
        'methodology':[
            {'title':'Fixed corpus','body':'Twelve development tasks across seven formats and three authored complexity levels. Each has three correct whitespace/serialization variants and four deterministic faults: 84 unique sources, evaluated by both systems. No model was called; no held-out task was used.'},
            {'title':'Fault construction','body':protocol['mutation_policy']},
            {'title':'Comparison and truth','body':'The baseline is the original parser/compiler/functional checker. The enhanced system adds public contracts and the accumulator-dependency fix. Every correct/fault label was confirmed against native Python/LLVM, read-only SQLite, or independent exact-document outcomes. Both systems saw identical source bytes.'},
            {'title':'Denominators','body':'False acceptance divides accepted faulty candidates by 48 faulty candidates. False rejection divides rejected correct candidates by 36 correct variants. The 168 validations are 84 paired sources, grouped in 12 tasks, not 168 independent samples. Public examples intentionally leave some faults detectable only by the independent grader.'},
            {'title':'Uncertainty','body':'A paired percentile bootstrap resamples the 12 tasks 10,000 times, retaining all four faulty variants and both systems within each task. The interval describes sensitivity on this authored development corpus; it is not a population guarantee. The protocol specified this analysis before validation; no external preregistration is claimed.'},
            {'title':'Reproduce','body':'The downloadable archive contains both frozen source trees, the runner, corpus, contracts, oracles, protocol hashes, and raw checks. On macOS with the repo dependencies and Clang, extract to a new directory and run the driver: python runner/reproduce.py . (the final dot names the extracted directory). It verifies hashes, re-runs primary and ablation checks in separate temporary copies, compares outcomes, and preserves the original evidence. Transient timings and compiler paths are excluded from outcome comparison.'}],
        'limitations':['Faults were deliberately authored to exercise known contract mechanisms and omissions; this is not an estimate of real model error frequency.',
            'Only 12 development task clusters and 36 formatting controls. Formatting variants do not add semantic diversity.',
            'The baseline does not consume task requirements; this measures the value of providing/enforcing those requirements, not a universal code verifier.',
            'Public examples can be memorized and can miss unseen-input faults. Passing a contract is not a proof of correctness.',
            'Exact-document grading and native grading share parser/eligibility dependencies with production checks.',
            'No new GLM/DeepSeek generation, assembled-binary retention, deployment, or traffic-replay outcome is measured.'],
        'provenance':{'protocol_sha256':sha((root/'protocol.json').read_bytes()),'baseline_commit':protocol['baseline_commit'],
                      'snapshot_files':len(protocol['files']),'reproduction_sha256':sha((destination/'reproduction.zip').read_bytes())},
        'references':[{'title':'EvalPlus (NeurIPS 2023)','url':'https://arxiv.org/abs/2305.01210'}]}
    if ablation:
        report['ablations']=[metrics(corpus,arm) for arm in ['baseline','structure-fix','filter-only','contract']]
        report['methodology'].append({'title':'Post hoc mechanism check','body':'A separately frozen addendum evaluates the enhanced engine without contracts on all 84 original sources, then derives baseline-plus-contract filtering from recorded checks. Structure-only accepts 48/48 faulty sources and rejects 0/36 correct controls; filter-only accepts 18/48 faults and rejects 3/36 controls. The combined system accepts 18/48 faults and rejects 0/36 controls. This separates the control-recovery fix from semantic rejection without adding tasks or measuring generation quality. The reproduction archive includes this addendum and a driver that re-runs it without overwriting its frozen inputs.'})
        report['findings'].append('The mechanism check separates the gains: the accumulator fix recovers correct controls; task contracts reject semantic faults. Filtering alone does not recover the controls rejected by the original structure check.')
    verification_path=root.parent/'reproduction-check.json'
    if verification_path.is_file():
        verification=read(verification_path)
        if verification.get('benign') is True and verification.get('reproduced') is True and verification.get('protocol_sha256')==report['provenance']['protocol_sha256']:
            report['reproduction_check']=verification
            report['methodology'].append({'title':'Reproduction verification','body':'All 168 primary decisions and independent grades, 84 additional structure-only validations, and 84 derived filtering decisions reproduced exactly in isolated copies. Original evidence remained unchanged. Runtime versions are included in the machine-readable report.'})
    save(destination/'scores.json',{'schema_version':1,'benign':True,'cases':cases,'metrics':rows,'effects':[effect],
                                   'ablations':report.get('ablations',[]),'ablation_records':ablation})
    report['provenance']['scores_sha256']=sha((destination/'scores.json').read_bytes())
    (destination/'protocol.json').write_bytes((root/'protocol.json').read_bytes())
    lines=['# Controlled benign fault audit','']
    for finding in report['findings']: lines += [finding,'']
    lines += ['## Results','', '| System | Faults accepted | Correct controls rejected |','| --- | ---: | ---: |']
    lines += [f"| {r['arm']} | {r['false_acceptance']}/48 | {r['false_rejection']}/36 |" for r in rows]
    if (destination/'figure.png').is_file():
        lines += ['','![False acceptance and the mechanism check](figure.png)','', '[PDF figure](figure.pdf) · [SVG figure](figure.svg)','']
    if ablation:
        lines += ['','## Post hoc mechanism check','', '| System | Faults accepted | Correct controls rejected |','| --- | ---: | ---: |']
        lines += [f"| {r['arm']} | {r['false_acceptance']}/48 | {r['false_rejection']}/36 |" for r in report['ablations']]
    lines += ['','## Methodology','']
    for item in report['methodology']: lines+=['### '+item['title'],'',item['body'],'']
    lines += ['## Limitations','']+['- '+item for item in report['limitations']]+['','## Integrity','',json.dumps(report['provenance'],indent=2),'']
    (destination/'REPORT.md').write_text('\n'.join(lines))
    save(destination/'report.json',report)
    print(json.dumps({'metrics':rows,'effect':effect},indent=2))


if __name__=='__main__': publish(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
