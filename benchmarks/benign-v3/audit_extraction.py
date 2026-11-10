"""Post hoc paired extraction audit of changed, complete FIRST responses only.

No inference and no revised retry trajectory. All validation/grading uses the
frozen engine; the sole intervention is preserving source escape sequences.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from experiment import digest,save,verify


def audit(root,output,allow_incomplete=False):
    protocol=verify(root); sys.path.insert(0,str(root/'engine')); sys.path.insert(0,str(root/'runner'))
    from clanker_repellent.generate import source_generation as generation
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    from clanker_repellent.generate.document_formats import DOCUMENT_TARGETS,normalize_http
    from grade import grade
    tasks={t['id']:t for t in json.loads((root/'tasks.json').read_text())['tasks']}
    oracles=json.loads((root/'oracles.json').read_text())['oracles']; cases=[]; completed=truncated=unchanged=unextractable=0
    output.mkdir(parents=True,exist_ok=False)
    for model in protocol['models']:
        for identity in protocol['task_ids']:
            directory=root/'runs'/model/identity; record_path=directory/'record.json'
            if not record_path.exists():
                if allow_incomplete: continue
                raise ValueError('Complete model grid required')
            record=json.loads(record_path.read_text()); manifest_path=directory/'generation/manifest.json'
            if record.get('benign') is not True or digest(manifest_path)!=record['manifest_sha256']: raise ValueError('Generation provenance differs')
            manifest=json.loads(manifest_path.read_text())
            if manifest['settings']['mode']!='benign': raise ValueError('Only benign responses may be inspected')
            trace=json.loads((directory/'traces/01.json').read_text())
            if trace.get('benign') is not True or trace.get('mode')!='benign': raise ValueError('Trace is not benign')
            if hashlib.sha256(json.dumps(trace['request'],sort_keys=True).encode()).hexdigest()!=trace['request_sha256']:
                raise ValueError('Trace request hash differs')
            if trace['response']['resolved_model']!=protocol['models'][model]['id'] or record['model']!=model or record['task']!=identity:
                raise ValueError('Trace model or task differs')
            raw=trace['response']['response_text']; response_hash=hashlib.sha256(raw.encode()).hexdigest()
            first=manifest['candidates'][0]['attempts'][0]
            if first['response']['sha256']!=response_hash: raise ValueError('Response hash differs')
            completed+=1
            if trace['response']['finish_reason']=='length': truncated+=1; continue
            if trace['response'].get('provider_refusal'):
                unextractable+=1; continue
            task=tasks[identity]; language=task['language']; target=generation.select_languages([language])[0]
            try:
                before=generation.extract_code_snippet(raw,normalize_escapes=language not in DOCUMENT_TARGETS|{'llvm'})
                after=generation.extract_code_snippet(raw,normalize_escapes=False)
            except generation.ExtractionError: unextractable+=1; continue
            if before==after: unchanged+=1; continue
            results={}
            for arm,source in [('before',before),('preserve_escapes',after)]:
                if language in {'go','rust'}: source,_=generation._format_candidate(language,source,90)
                if language=='http': source=normalize_http(source)
                policy=generation.benign_policy_error(source,language=language)
                validation=generation.validate_snippet(target,source,run_linters=False,require_structure=True,structure_profile=FUNCTIONAL_PROFILE,timeout_seconds=90) if not policy else None
                accepted=bool(validation and validation['accepted'])
                result=grade(task,oracles[identity],source) if accepted else None
                relative=Path('sources')/(model+'-'+identity+'-'+arm+'.txt'); path=output/relative; path.parent.mkdir(exist_ok=True); path.write_bytes(source.encode())
                results[arm]={'accepted':accepted,'strict_pass':bool(accepted and result and result['passed']),'grade':result,
                              'source':str(relative),'source_sha256':digest(path),'validation_status':validation['status'] if validation else 'benign_policy_failed'}
            if results['before']['accepted']!=first['accepted']: raise ValueError('Frozen first-attempt acceptance did not reproduce')
            cases.append({'model':model,'task':identity,'language':language,'response_sha256':response_hash,'arms':results})
    report={'benign':True,'kind':'post_hoc_extraction_audit','protocol_sha256':digest(root/'protocol.json'),'planned_candidates':protocol['planned'],
            'screened_completed':completed,'complete_grid':completed==protocol['planned'],'excluded_token_limit':truncated,'excluded_unextractable':unextractable,
            'unchanged_extraction':unchanged,'changed_first_responses':len(cases),'inference_requests':0,'cases':cases,
            'method':'Paired offline evaluation of changed complete first responses; identical frozen validators and grader. Preserving escapes is the only intervention. This does not estimate revised retry behavior.'}
    for arm in ['before','preserve_escapes']:
        report[arm]={'accepted':sum(c['arms'][arm]['accepted'] for c in cases),'verified':sum(c['arms'][arm]['strict_pass'] for c in cases)}
    save(output/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('root',type=Path); parser.add_argument('output',type=Path); parser.add_argument('--allow-incomplete',action='store_true'); args=parser.parse_args()
    audit(args.root.resolve(),args.output.resolve(),args.allow_incomplete)
