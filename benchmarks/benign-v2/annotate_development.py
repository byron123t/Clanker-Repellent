"""Add clearly labeled development diagnostics without changing frozen primary outcomes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile


def read(path): return json.loads(path.read_text())


def annotate(root,destination):
    report=read(destination/'report.json'); scores=read(root/'scores.json')
    if root.name!='development-v2' or report['id']!=root.name or report['state']!='complete' or not scores['benign']:
        raise ValueError('This addendum is specific to the completed development-v2 study')
    original={key:report[key] for key in ['counts','effects','groups']}
    observed={(r['model'],r['arm']):(r['accepted'],r['verified']) for r in report['metrics'] if r['arm']!='filter-only'}
    if observed!={('glm','baseline'):(9,2),('glm','contract'):(8,6),('deepseek','baseline'):(10,10),('deepseek','contract'):(12,12)}:
        raise ValueError('This explanatory addendum does not match the measured development outcomes')
    verification=read(root.parent/'development-reproduction-check.json')
    if not verification['benign'] or not verification['reproduced'] or verification['observations']!=48:
        raise ValueError('Completed offline reproduction is required')
    for row in report['metrics']:
        arm='baseline' if row['arm']=='filter-only' else row['arm']
        selected=[r for r in scores['records'] if r['model']==row['model'] and r['arm']==arm]
        for field in ['prompt_tokens','completion_tokens','inference_seconds','length_stops']:
            values=[r['resources'][field] for r in selected]
            row[field]=sum(values) if all(v is not None for v in values) else None
    by_id={r['id']:r for r in scores['records']}
    for case in report['cases']:
        case.update(resources=by_id[case['id']]['resources'],attempt_checks=by_id[case['id']]['attempt_checks'])
    report['findings']=[
        'All 48 planned development candidates are recorded. These exploratory outcomes are excluded from held-out estimates.',
        'GLM verified success: 2/12 baseline, 6/12 task contracts (+33.3 pp; 95% paired task interval +8.3 to +58.3). Accepted-but-incorrect outputs fell from 7 to 2.',
        'DeepSeek verified success: 10/12 baseline, 12/12 task contracts (+16.7 pp; 95% paired task interval 0.0 to +41.7). The interval includes no improvement; the 12/12 result does not establish universal correctness.',
        'The two remaining GLM contract false acceptances were nested JSON and HTML arithmetic. A post hoc revision rejects both unchanged outputs while all 36 correct reference controls pass. That revision is evaluated prospectively in heldout-v1.',
        'All 48 independent grades and filter-only decisions reproduced exactly from the exported archive, without new inference.'
    ]
    addendum=[
        {'title':'Development revision · exploratory','body':'Aggregate totals and table shape did not guarantee correct item arithmetic. The GLM JSON output used 430 where the requested calculation gives 434; the HTML output used 51 where it gives 55. The selected revision preserves supplied inputs and checks bounded integer equations. It was selected before any held-out output was collected. The original development engine and primary outcomes remain unchanged.'},
        {'title':'Native grading incident','body':'One interim re-scoring invocation abruptly failed on unchanged DeepSeek LLVM minimum bytes with empty stderr. The same source passed earlier and in 12 immediate repetitions of all 323 cases. A full final re-score and separate archive reproduction agree on every outcome. No inference was repeated. The held-out grader now treats child termination and timeouts as infrastructure interruptions, not wrong answers.'},
        {'title':'Observed inference cost · descriptive addendum','body':'Provider-reported token totals and inference seconds include all attempts. Hardware and server load were uncontrolled; timing is not a causal model-speed comparison. Filter-only reuses baseline inference.'},
        {'title':'Offline verification','body':verification['scope']+' All 48 outcomes agreed exactly on '+verification['environment']['platform']+' with Python '+verification['environment']['python']+'.'}
    ]
    titles={item['title'] for item in addendum}
    report['methodology']=[item for item in report['methodology'] if item['title'] not in titles]+addendum
    with zipfile.ZipFile(destination/'reproduction.zip') as archive:
        contents={name:archive.read(name) for name in archive.namelist() if name!='artifact-manifest.json'}
    for name in ['development-reproduction-check.json','arithmetic-development-checks.json','arithmetic-control-checks.json',
                 'intervention-selection.json','native-grader-incident/notes.json','native-grader-incident/provisional-scores.json']:
        data=(root.parent/name).read_bytes()
        if json.loads(data).get('benign') is not True: raise ValueError('Only benign addendum evidence')
        contents['addendum/'+name]=data
    contents['addendum/methodology.json']=json.dumps({'benign':True,'kind':'posthoc-development-addendum','sections':addendum},indent=2).encode()
    contents['runner/annotate_development.py']=Path(__file__).read_bytes()
    manifest={'schema_version':1,'benign':True,'files':{name:hashlib.sha256(data).hexdigest() for name,data in contents.items()}}
    with zipfile.ZipFile(destination/'reproduction.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in contents.items():
            item=zipfile.ZipInfo(name,date_time=(2026,11,9,0,0,0)); item.compress_type=zipfile.ZIP_DEFLATED; archive.writestr(item,data)
        archive.writestr('artifact-manifest.json',json.dumps(manifest,indent=2)+'\n')
    report['provenance']['reproduction_sha256']=hashlib.sha256((destination/'reproduction.zip').read_bytes()).hexdigest()
    report['provenance']['offline_verification']=verification
    if original!={key:report[key] for key in original}: raise ValueError('Primary results changed')
    (destination/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    spec=importlib.util.spec_from_file_location('display_analysis',Path(__file__).with_name('analyze.py'))
    analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)
    text=analysis.markdown(report)
    text+='\n## Development findings\n\n'+'\n\n'.join(report['findings'])+'\n'
    (destination/'REPORT.md').write_text(text)
    print(json.dumps({'study':root.name,'primary_outcomes_unchanged':True,'archive_sha256':report['provenance']['reproduction_sha256']}))


if __name__=='__main__': annotate(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
