"""Independent native/data grading for the frozen, explicitly benign benchmark.

Generated Python is restricted by an AST allowlist before a resource-limited subprocess.
LLVM is restricted to the existing no-memory/no-call profile before native compilation.
The production contract interpreter is not used to compute primary behavior outcomes.
"""
import ast
import ctypes
import http.client
import io
import json
import os
from pathlib import Path
import re
import resource
import sqlite3
import subprocess
import sys
import tempfile

from clanker_repellent.generate.pure_evaluation import IntegerProgram
from clanker_repellent.generate.llvm_structure import llvm_metrics
from clanker_repellent.generate.sql_structure import inspect_sql, _PURE_FUNCTIONS


def limits():
    resource.setrlimit(resource.RLIMIT_CPU,(4,4))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024*1024,16*1024*1024))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    # macOS rejects these address-space limits; do not claim they are enforced there.
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))


def same(left,right):
    if type(left) is not type(right): return False
    if isinstance(left,dict): return left.keys()==right.keys() and all(same(left[key],right[key]) for key in left)
    if isinstance(left,list): return len(left)==len(right) and all(same(a,b) for a,b in zip(left,right))
    return left==right


def _native(task,source,cases):
    language=task['language']; function=task['contract']['function']; name=function['name']
    arguments=[case['inputs'] for case in cases]
    if language=='sql':
        inspect_sql(source)
        database=sqlite3.connect(':memory:')
        database.set_authorizer(lambda action,a,b,_db,_trigger: sqlite3.SQLITE_OK
            if action==sqlite3.SQLITE_SELECT or action==sqlite3.SQLITE_FUNCTION and (b or a or '').lower() in _PURE_FUNCTIONS else sqlite3.SQLITE_DENY)
        actual=[]
        try:
            for args in arguments:
                budget=[10000]
                def progress():
                    budget[0]-=100
                    return int(budget[0]<=0)
                database.set_progress_handler(progress,100)
                cursor=database.execute(source,dict(zip(function['parameters'],args)))
                if [field[0] for field in cursor.description]!=[name]: raise ValueError('SQL result alias does not match the public API')
                rows=cursor.fetchall()
                if len(rows)!=1 or len(rows[0])!=1: raise ValueError('SQL result shape is not scalar')
                actual.append(rows[0][0])
            return actual
        finally: database.close()
    with tempfile.TemporaryDirectory(prefix='repel-benign-native-') as directory:
        path=Path(directory)
        (path/'cases.json').write_text(json.dumps(arguments))
        if language=='python':
            # Structural eligibility only; no production interpreter result enters this score.
            eligibility=IntegerProgram(source,name,function['parameters'])
            for args in arguments:
                eligibility.evaluate(args)  # Bound work/value growth; do not use results as the oracle.
            tree=ast.parse(source)
            functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
            if len(functions)!=1 or functions[0].name!=name: raise ValueError('Python helper name differs')
            body=source+'\nimport json as __benchmark_json\nwith open("cases.json") as __benchmark_f:\n    __benchmark_cases=__benchmark_json.load(__benchmark_f)\n'
            body+='__benchmark_answers=['+name+'(*__benchmark_args) for __benchmark_args in __benchmark_cases]\n'
            body+='print(__benchmark_json.dumps(__benchmark_answers))\n'
            (path/'check.py').write_text(body)
        else:
            llvm_metrics(source)
            code='\n'.join(line.split(';',1)[0] for line in source.splitlines())
            headers=re.findall(r'define\s+(i\d+)\s+@([A-Za-z_][A-Za-z_0-9]*)\s*\(([^)]*)\)',code)
            if len(headers)!=1 or headers[0][1]!=name or headers[0][0]!=function['return_type']:
                raise ValueError('LLVM helper name/return type differs')
            params=[re.fullmatch(r'\s*(i\d+)\s+%([A-Za-z_][A-Za-z_0-9]*)\s*',p) for p in headers[0][2].split(',')]
            if any(p is None for p in params) or [p.groups() for p in params]!=list(zip(function['parameter_types'],function['parameters'])):
                raise ValueError('LLVM parameter API differs')
            opcodes=[]
            for line in code.splitlines():
                line=line.strip()
                if not line or line.startswith('define ') or line=='}' or line.endswith(':'): continue
                opcodes.append(line.split('=',1)[-1].strip().split()[0])
            if set(opcodes)-set(task['contract']['llvm']['instructions']):
                raise ValueError('LLVM uses instructions excluded by the task')
            (path/'candidate.ll').write_text(source)
            compile_run=subprocess.run(['clang','-dynamiclib','-O0','-Wno-override-module','candidate.ll','-o','candidate.dylib'],
                                       cwd=directory,text=True,capture_output=True,timeout=60)
            if compile_run.returncode: raise ValueError('LLVM native compilation failed: '+compile_run.stderr[-300:])
            return_kind='ctypes.c_bool' if function['return_type']=='i1' else 'ctypes.c_int32'
            body='import ctypes,json\nlibrary=ctypes.CDLL("'+str(path/'candidate.dylib')+'")\n'
            body+='function=getattr(library,'+repr(name)+')\nfunction.argtypes=[ctypes.c_int32]*'+str(len(function['parameters']))+'\n'
            body+='function.restype='+return_kind+'\nwith open("cases.json") as stream: cases=json.load(stream)\n'
            body+='print(json.dumps([function(*args) for args in cases]))\n'
            (path/'check.py').write_text(body)
        process=subprocess.run([sys.executable,'-I',str(path/'check.py')],cwd=directory,stdin=subprocess.DEVNULL,
                               text=True,capture_output=True,timeout=8,preexec_fn=limits)
        if process.returncode: raise ValueError('Native helper failed or exceeded resource limits: '+process.stderr[-300:])
        actual=json.loads(process.stdout)
        if not isinstance(actual,list) or len(actual)!=len(cases): raise ValueError('Native answer count differs')
        return actual


def grade(task,oracle,source):
    try:
        if oracle['kind']=='numeric':
            public=task['contract']['examples']; hidden=oracle['cases']; cases=public+hidden
            actual=_native(task,source,cases)
            incorrect=[index for index,(value,case) in enumerate(zip(actual,cases)) if not same(value,case['expected'])]
            return {'passed':not incorrect,'public_passed':sum(index not in incorrect for index in range(len(public))),
                    'public_cases':len(public),'hidden_passed':sum(index not in incorrect for index in range(len(public),len(cases))),
                    'hidden_cases':len(hidden),'behavior_checked':True,
                    'failures':[{'index':index,'inputs':cases[index]['inputs'],'expected':cases[index]['expected'],'actual':actual[index]} for index in incorrect[:5]]}
        if oracle['kind']=='html':
            import html5lib
            root=html5lib.parse(source,namespaceHTMLElements=False)
            tables=list(root.iter('table'))
            if len(tables)!=1: raise ValueError('Expected exactly one table')
            rows=[[' '.join(''.join(cell.itertext()).split()) for cell in row if cell.tag in {'td','th'}] for row in tables[0].iter('tr')]
            ids=[node.get('id') for node in root.iter() if node.get('id')]
            if len(ids)!=len(set(ids)) or set(task['contract']['html'].get('required_ids',[]))-set(ids): raise ValueError('HTML identity mismatch')
            if rows!=[oracle['columns']]+oracle['rows']: raise ValueError('HTML numeric results, inputs, labels, or row ordering differ')
            return {'passed':True,'rows_checked':len(oracle['rows'])}
        if task['language']=='http':
            data=source.encode('utf-8')
            class Socket:
                def makefile(self,*args,**kwargs): return io.BytesIO(data)
            response=http.client.HTTPResponse(Socket()); response.begin(); body=response.read()
            separator=data.partition(b'\r\n\r\n')
            if not separator[1] or body!=separator[2] or response.getheader('Content-Length')!=str(len(body)):
                raise ValueError('HTTP byte framing differs')
            if response.status!=task['contract']['http']['status']: raise ValueError('HTTP status differs')
            for key,value in task['contract']['http'].get('headers',{}).items():
                if response.getheader(key)!=value: raise ValueError('HTTP required header differs')
            value=json.loads(body)
        else: value=json.loads(source)
        if oracle['kind']=='binary':
            expected=oracle['expected']
            if not isinstance(value,dict) or value.keys()!=expected.keys(): raise ValueError('Binary root schema differs')
            if any(not same(value.get(key),expected[key]) for key in expected if key!='strings'):
                raise ValueError('Binary format, architecture, sections, symbols, ordering, or references differ')
            if not isinstance(value['strings'],list) or not value['strings'] or not all(isinstance(v,str) and v.strip() for v in value['strings']):
                raise ValueError('Binary description strings are empty')
        elif not same(value,oracle['expected']):
            raise ValueError('Document calculation, input preservation, or exact field structure differs')
        return {'passed':True,'document_checked':True}
    except subprocess.TimeoutExpired:
        return {'passed':False,'diagnostic':'Native helper or compilation timed out','behavior_checked':False}
    except (ValueError,TypeError,KeyError,IndexError,SyntaxError,sqlite3.Error) as exc:
        return {'passed':False,'diagnostic':str(exc)[:500],'behavior_checked':False}


def main():
    tasks=json.loads((Path(__file__).parent/'tasks.json').read_text())['tasks']
    oracles=json.loads((Path(__file__).parent/'oracles.json').read_text())['oracles']
    from clanker_repellent.generate.contracts import check_contract
    from clanker_repellent.generate.source_generation import validate_snippet,select_languages
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    outcomes=[]
    for task in tasks:
        source=oracles[task['id']]['control']
        validation=validate_snippet(select_languages([task['language']])[0],source,run_linters=False,
                                    timeout_seconds=60,require_structure=True,structure_profile=FUNCTIONAL_PROFILE,contract=task['contract'])
        result=grade(task,oracles[task['id']],source)
        outcomes.append({'id':task['id'],'validation':validation['accepted'],'grade':result})
        print(json.dumps(outcomes[-1]),flush=True)
    destination=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).parent/'control-checks.json'
    destination.write_text(json.dumps({'benign':True,'controls':outcomes},indent=2)+'\n')
    if not all(item['validation'] and item['grade']['passed'] for item in outcomes): raise SystemExit(1)


if __name__=='__main__': main()
