"""Controlled benign fault audit: fixed authored sources, not model generations.

Only development tasks are used. Four faults and three formatting controls per task
are fixed before either validator is evaluated. Private-trigger faults deliberately
illustrate incomplete public examples; they do not estimate natural fault frequency.
"""
import argparse
import copy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_text())
def save(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n'); temporary.replace(path)
def wrong(value): return not value if type(value) is bool else value+1


def numeric_faults(task,oracle):
    source=oracle['control']; function=task['contract']['function']; name=function['name']; parameters=function['parameters']
    language=task['language']; public=task['contract']['examples']; private=oracle['cases'][0]
    def condition(args,prefix=''): return ' and '.join(prefix+p+' == '+repr(v) for p,v in zip(parameters,args))
    if language=='python':
        renamed=source.replace('def '+name+'(', 'def alternate_'+name+'(',1)
        def triggered(case):
            lines=source.splitlines(keepends=True)
            lines.insert(1,'    if '+condition(case['inputs'])+': return '+repr(wrong(case['expected']))+'\n')
            return ''.join(lines)
        memorized='def '+name+'('+', '.join(parameters)+'):\n'
        for case in public: memorized+='    if '+condition(case['inputs'])+': return '+repr(case['expected'])+'\n'
        memorized+='    return '+repr(wrong(private['expected']))+'\n'
    elif language=='sql':
        match=re.fullmatch(r'\s*SELECT\s+(.*?)\s+AS\s+'+re.escape(name)+r'\s*;\s*',source,re.I|re.S)
        if not match: raise ValueError('Authored SQL control shape changed')
        expression=match[1]; renamed=re.sub(r'\bAS\s+'+name+r'\b','AS alternate_'+name,source,flags=re.I)
        def triggered(case):
            cond=condition(case['inputs'],':').replace(' and ',' AND ').replace(' == ',' = ')
            return 'SELECT CASE WHEN '+cond+' THEN '+str(wrong(case['expected']))+' ELSE ('+expression+') END AS '+name+';\n'
        memorized='SELECT CASE '
        for case in public:
            cond=condition(case['inputs'],':').replace(' and ',' AND ').replace(' == ',' = ')
            memorized+='WHEN '+cond+' THEN '+str(case['expected'])+' '
        memorized+='ELSE '+str(wrong(private['expected']))+' END AS '+name+';\n'
    else:
        kind=function['return_type']; renamed=source.replace('@'+name+'(', '@alternate_'+name+'(',1)
        literal=lambda value: str(value).lower() if type(value) is bool else str(value)
        def ir_guard(args,prefix):
            lines=[]; previous=None
            for i,(parameter,value) in enumerate(zip(parameters,args)):
                current=f'%{prefix}c{i}'; lines.append(f'  {current} = icmp eq i32 %{parameter}, {value}')
                if previous:
                    merged=f'%{prefix}m{i}'; lines.append(f'  {merged} = select i1 {previous}, i1 {current}, i1 false'); current=merged
                previous=current
            return lines,previous
        def triggered(case):
            match=re.search(r'(?m)^\s*ret\s+'+kind+r'\s+(\S+)\s*$',source)
            if not match: raise ValueError('Authored LLVM return changed')
            lines,guard=ir_guard(case['inputs'],'audit')
            lines += [f'  %auditresult = select i1 {guard}, {kind} {literal(wrong(case["expected"]))}, {kind} {match[1]}',f'  ret {kind} %auditresult']
            return source[:match.start()]+'\n'+'\n'.join(lines)+'\n'+source[match.end():]
        lines=[f'define {kind} @{name}('+', '.join('i32 %'+p for p in parameters)+') {','entry:']
        previous=literal(wrong(private['expected']))
        for i,case in enumerate(public):
            guards,guard=ir_guard(case['inputs'],f'example{i}'); lines+=guards
            result=f'%result{i}'; lines.append(f'  {result} = select i1 {guard}, {kind} {literal(case["expected"])}, {kind} {previous}'); previous=result
        lines += [f'  ret {kind} {previous}','}']; memorized='\n'.join(lines)+'\n'
    return [('api-name',renamed),('public-trigger',triggered(public[0])),('private-trigger',triggered(private)),('public-memorizer',memorized)]


def serialize(task,value,indent=2,sort=False):
    body=json.dumps(value,indent=indent,sort_keys=sort)+'\n'
    if task['language']!='http': return body
    contract=task['contract']['http']
    headers=[f'HTTP/1.1 {contract["status"]} Example','Content-Type: application/json']
    headers += [key+': '+value for key,value in contract['headers'].items()]
    headers += ['Content-Length: '+str(len(body.encode()))]
    return '\r\n'.join(headers)+'\r\n\r\n'+body


def document_faults(task,oracle):
    if task['language']=='html':
        source=oracle['control']; identity=task['id']; rows=list(re.finditer(r'<tr>.*?</tr>',source))
        return [('required-id',source.replace('id="'+identity+'"','id="alternate"')),
                ('column-label',source.replace('<th>Amount</th>','<th>Incorrect label</th>')),
                ('computed-value',source.replace('<td>'+oracle['rows'][-1][-1]+'</td>','<td>999999</td>')),
                ('row-count',source[:rows[-1].start()]+source[rows[-1].end():])]
    expected=oracle['expected']; variants=[]
    if task['language']=='binary-info':
        item=copy.deepcopy(expected); item['symbols'][0]['name']='alternate_name'; variants.append(('symbol-name',item))
        item=copy.deepcopy(expected); item['sections'].reverse(); variants.append(('section-order',item))
        item=copy.deepcopy(expected); item['architecture']='x86_64'; variants.append(('architecture',item))
        item=copy.deepcopy(expected); item['symbols'][0]['section']=item['sections'][1]['name']; variants.append(('section-reference',item))
    else:
        item=copy.deepcopy(expected); item['denomination']=item.pop('currency'); variants.append(('root-field',item))
        item=copy.deepcopy(expected); item['total']+=1; variants.append(('aggregate-total',item))
        item=copy.deepcopy(expected); collection=item.get('items',item.get('groups')); collection[1]['id']=collection[0]['id']; variants.append(('duplicate-id',item))
        item=copy.deepcopy(expected); group=item['groups'][0] if 'groups' in item else item
        record=group['items'][0]; record['unit_price']+=1
        record['amount']=record['quantity']*record['unit_price']*(100-record.get('discount',0))//100
        if 'groups' in item:
            group['subtotal']=sum(row['amount'] for row in group['items']); group['tax']=group['subtotal']*group['tax_percent']//100
            group['total']=group['subtotal']+group['tax']; item['total']=sum(g['total'] for g in item['groups'])
        else: item['total']=sum(row['amount'] for row in item['items'])
        variants.append(('consistent-wrong-input',item))
    return [(name,serialize(task,item)) for name,item in variants]


def corpus():
    tasks=read(HERE/'tasks.json')['tasks']; oracles=read(HERE/'oracles.json')['oracles']; records=[]
    for task in tasks:
        if task['split']!='development': continue
        oracle=oracles[task['id']]; original=oracle['control']
        if task['language'] in {'json','http','binary-info'}:
            controls=[original,serialize(task,oracle['expected'],indent=None),serialize(task,oracle['expected'],indent=4,sort=True)]
        else: controls=[original,'\n'+original+'\n','\n'.join(line.rstrip()+'  ' if line.strip() else '' for line in original.splitlines())+'\n']
        variants=[('control-'+str(i),source,False) for i,source in enumerate(controls)]
        variants += [(name,source,True) for name,source in (numeric_faults(task,oracle) if oracle['kind']=='numeric' else document_faults(task,oracle))]
        for variant,source,fault in variants:
            records.append({'id':sha((task['id']+':'+variant).encode()),'task':task['id'],'variant':variant,'known_fault':fault,
                            'language':task['language'],'level':task['level'],'source':source,'source_sha256':sha(source.encode())})
    if len(records)!=84: raise ValueError('Unexpected audit size')
    return records


def prepare(root):
    if root.exists(): raise ValueError('Use a new directory; audits are never overwritten')
    root.mkdir(parents=True)
    for arm,source in [('baseline',REPO/'.repel-workspaces/benign-eval-v2/baseline/src'),('contract',REPO/'src')]:
        shutil.copytree(source,root/'engines'/arm,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (root/'runner').mkdir()
    for name in ['faults.py','grade.py','analyze.py']: shutil.copyfile(HERE/name,root/'runner'/name)
    for name in ['tasks.json','oracles.json']: shutil.copyfile(HERE/name,root/name)
    save(root/'corpus.json',{'benign':True,'origin':'authored-controls-and-deterministic-faults','records':corpus()})
    files={str(p.relative_to(root)):sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    save(root/'protocol.json',{'schema_version':1,'benign':True,'stage':'audit','created_at':datetime.now(timezone.utc).isoformat(),
        'baseline_commit':'65d5cb357140d2c76808f254c7d2a4b6d95f3f31','files':files,'tasks':12,'variants_per_task':7,
        'correct_controls':36,'faults':48,'arms':['baseline','contract'],'source':'Authored, not model generated',
        'primary':'False acceptance among independently confirmed faulty candidates; control false rejection reported separately.',
        'design':'Three whitespace/serialization controls and four fixed faults per development task. Twelve task clusters; seven formats; three authored complexity levels.',
        'selection':'All development tasks. No held-out task or new model response is used.',
        'mutation_policy':'Numeric API rename, one public-trigger error, one private-trigger error, and public-example memorization. Documents use schema/reference/count/label/calculation mutations. Private fixtures deliberately construct difficult omissions; this is not a natural-error distribution.',
        'comparison':'Baseline parser/compiler/functionality checks versus the changed checker plus public contracts. No model calls, generation retries, or prompt changes are measured.',
        'analysis':'Task-clustered paired bootstrap, 10,000 draws, seed 20261109; variants within a task remain paired. Descriptive on an authored development corpus.',
        'settings':{'linters':False,'validator_timeout_seconds':60,'structure_profile':'functional-v1'}})
    print(json.dumps({'audit':str(root),'sources':84,'faults':48,'controls':36,'protocol_sha256':sha((root/'protocol.json').read_bytes())}))


def verify(root):
    protocol=read(root/'protocol.json')
    if protocol.get('benign') is not True: raise ValueError('Only benign audits are supported')
    for relative,expected in protocol['files'].items():
        path=root/relative
        if path.is_symlink() or sha(path.read_bytes())!=expected: raise ValueError('Frozen audit changed: '+relative)
    return protocol


def worker(root,arm):
    verify(root); sys.path.insert(0,str(root/'engines'/arm)); sys.path.insert(0,str(root/'runner'))
    from clanker_repellent.generate.source_generation import validate_snippet,select_languages,validation_metadata
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    tasks={t['id']:t for t in read(root/'tasks.json')['tasks']}; oracles=read(root/'oracles.json')['oracles']
    if arm=='contract':
        from grade import grade
    outcomes=[]
    for record in read(root/'corpus.json')['records']:
        task=tasks[record['task']]; extra={'contract':task['contract']} if arm=='contract' else {}
        result=validate_snippet(select_languages([task['language']])[0],record['source'],run_linters=False,timeout_seconds=60,
                                require_structure=True,structure_profile=FUNCTIONAL_PROFILE,**extra)
        if any(c['required'] and c['status'] in {'unavailable','error','timeout'} for c in result['checks']):
            raise RuntimeError('Infrastructure/validator error; audit stopped without treating it as a quality outcome')
        outcome={'id':record['id'],'arm':arm,'accepted':result['accepted'],'validation':validation_metadata(result)}
        if arm=='contract':
            outcome['grade']=grade(task,oracles[task['id']],record['source'])
            if outcome['grade']['passed']==record['known_fault']:
                raise ValueError('Authored ground-truth assumption failed: '+record['task']+'/'+record['variant'])
        outcomes.append(outcome)
        save(root/(arm+'-checks.json'),{'benign':True,'records':outcomes})
        print(json.dumps({'arm':arm,'completed':len(outcomes),'task':record['task'],'variant':record['variant'],'accepted':result['accepted']}),flush=True)


def run(root):
    verify(root)
    for arm in ['baseline','contract']:
        subprocess.run([sys.executable,str(root/'runner/faults.py'),'worker',str(root),'--arm',arm],check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('action',choices=['prepare','run','worker'])
    parser.add_argument('root',type=Path); parser.add_argument('--arm',choices=['baseline','contract'])
    args=parser.parse_args(); root=args.root.resolve()
    if args.action=='prepare': prepare(root)
    elif args.action=='run': run(root)
    else: worker(root,args.arm)


if __name__=='__main__': main()
