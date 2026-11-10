"""Native behavior and semantic document checks, separate from CLI acceptance.

Only explicitly benign, hash-verified sources enter this runner. On macOS runtime
processes are contained by sandbox-exec: no network, no home reads, no writes
outside their temporary directory. Resource limits supplement that profile.
This is a local evaluation harness, not a service for executing arbitrary code.
"""
import configparser
import csv
import http.client
import io
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def limits():
    resource.setrlimit(resource.RLIMIT_CPU,(8,8))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(4*1024*1024,4*1024*1024))
    resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))


def sandbox(directory):
    if sys.platform!='darwin' or not shutil.which('sandbox-exec'):
        raise RuntimeError('This frozen native evaluation requires macOS sandbox-exec; do not silently run uncontained.')
    profile='(version 1)(allow default)(deny network*)(deny file-write*)(deny file-read* (subpath "/Users"))'
    profile+='(allow file-read* file-write* (subpath '+json.dumps(str(directory.resolve()))+'))'
    profile+='(allow file-write* (literal "/dev/null"))'
    runtime=Path(sys.executable).resolve().parent.parent
    if str(runtime).startswith('/Users/'):
        profile+='(allow file-read* (subpath '+json.dumps(str(runtime/'bin'))+') (subpath '+json.dumps(str(runtime/'lib'))+'))'
    return ['sandbox-exec','-p',profile]


def command(args, directory, *, execute=False, timeout=90):
    env=dict(os.environ)
    # Do not expose caller secrets through inherited environment values.
    env={k:v for k,v in env.items() if k in {'PATH','SDKROOT','DEVELOPER_DIR','LANG','LC_ALL','SYSTEMROOT'}}
    env.update(TMPDIR=str(directory),GOCACHE=str(directory/'go-cache'),GOPATH=str(directory/'go-path'),
               GOPROXY='off',GOTOOLCHAIN='local',PYTHONDONTWRITEBYTECODE='1')
    if not execute:
        env['RUSTUP_HOME']=os.environ.get('RUSTUP_HOME',str(Path.home()/'.rustup'))
        env['CARGO_HOME']=os.environ.get('CARGO_HOME',str(Path.home()/'.cargo'))
    with (directory/'stdout.log').open('w+') as stdout, (directory/'stderr.log').open('w+') as stderr:
        try:
            process=subprocess.run((sandbox(directory) if execute else [])+args,cwd=directory,env=env,
                stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=timeout,
                preexec_fn=limits if execute else None)
        except subprocess.TimeoutExpired:
            return {'ok':False,'reason':'runtime_timeout' if execute else 'compiler_timeout','output':''}
        stdout.seek(0); stderr.seek(0)
        output=stdout.read(1024*1024); error=stderr.read(1000)
    return {'ok':process.returncode==0,'reason':None if process.returncode==0 else 'runtime_exit' if execute else 'compiler_exit',
            'returncode':process.returncode,'output':output,'diagnostic':error}


def native(task, oracle, source):
    language=task['language']; family=oracle['family']; values=oracle['public']+oracle['private']
    names={'ceil_div':'CeilDiv','longest_run':'LongestRun','parse_decimal':'ParseDecimal'}
    with tempfile.TemporaryDirectory(prefix='repel-breadth-',dir='/private/tmp') as temporary:
        path=Path(temporary)
        if language in ['c','cpp']:
            driver='#include <stdio.h>\n'+source+'\nint main(void) {\n'
            for i,value in enumerate(values):
                if family=='ceil_div': args=', '.join(map(str,value))
                elif family=='longest_run':
                    driver+='int values'+str(i)+'[]={'+','.join(map(str,value or [0]))+'};\n'; args='values'+str(i)+','+str(len(value))
                else:
                    raw=value.encode(); driver+='const char text'+str(i)+'[]="'+''.join('\\x%02x'%c for c in raw)+'";\n'; args='text'+str(i)+','+str(len(raw))
                driver+='printf("%d\\n", '+family+'('+args+'));\n'
            driver+='return 0; }\n'; filename='check.'+('c' if language=='c' else 'cpp'); (path/filename).write_text(driver)
            built=command(['clang' if language=='c' else 'clang++','-O0','-std=c11' if language=='c' else '-std=c++17',filename,'-o','check'],path)
            argv=[str(path/'check')]
        elif language in ['javascript','typescript','python','ruby','lua']:
            lines=[]
            for value in values:
                if language=='lua':
                    literal='{'+','.join(map(str,value))+'}' if isinstance(value,list) else '"'+''.join('\\%03d'%c for c in value.encode())+'"'
                elif language=='ruby': literal=json.dumps(value,ensure_ascii=False)
                else: literal=repr(value) if language=='python' else json.dumps(value,ensure_ascii=False)
                args=', '.join(map(str,value)) if family=='ceil_div' else literal
                call=family+'('+args+')'
                lines.append(('console.log('+call+');') if language in ['javascript','typescript'] else ('puts '+call) if language=='ruby' else 'print('+call+')')
            extension={'javascript':'js','typescript':'ts','python':'py','ruby':'rb','lua':'lua'}[language]
            (path/('check.'+extension)).write_text(source+'\n'+'\n'.join(lines)+'\n')
            built=command(['tsc','--target','ES2020','--strict','check.ts'],path) if language=='typescript' else {'ok':True}
            argv={'javascript':['node','check.js'],'typescript':['node','check.js'],'python':[str(Path(sys.executable).resolve()),'-I','check.py'],'ruby':['ruby','check.rb'],'lua':['lua','check.lua']}[language]
        elif language=='java':
            (path/'Generated.java').write_text(source)
            lines=[]
            for value in values:
                args=', '.join(map(str,value)) if family=='ceil_div' else 'new int[]{'+','.join(map(str,value))+'}' if family=='longest_run' else 'new String(new char[]{'+','.join('(char)'+str(ord(c)) for c in value)+'})'
                lines.append('System.out.println(Generated.'+family+'('+args+'));')
            (path/'Check.java').write_text('public class Check { public static void main(String[] args) {\n'+'\n'.join(lines)+'\n}}\n')
            built=command(['javac','Generated.java','Check.java'],path); argv=['java','-Xmx128m','-cp',str(path),'Check']
        elif language=='go':
            lines=[]
            for value in values:
                args=', '.join(map(str,value)) if family=='ceil_div' else '[]int{'+','.join(map(str,value))+'}' if family=='longest_run' else json.dumps(value,ensure_ascii=False)
                lines.append('fmt.Println('+names[family]+'('+args+'))')
            # Package-only adapter; the helper body remains byte-for-byte unchanged.
            source,n=re.subn(r'(?m)^package annotation\b','package main',source,count=1)
            if n!=1: return {'passed':False,'diagnostic':'Go package is not annotation','behavior_checked':False}
            (path/'candidate.go').write_text(source)
            (path/'main.go').write_text('package main\nimport "fmt"\nfunc main() {\n'+'\n'.join(lines)+'\n}\n')
            built=command(['go','build','-o','check','candidate.go','main.go'],path); argv=[str(path/'check')]
        elif language in ['rust','swift']:
            lines=[]
            for value in values:
                if family=='ceil_div': args=', '.join(map(str,value))
                elif family=='longest_run': args=('&' if language=='rust' else '')+'['+','.join(map(str,value))+']'
                else:
                    raw=','.join(map(str,value.encode()))
                    args='std::str::from_utf8(&['+raw+']).unwrap()' if language=='rust' else 'String(decoding: ['+raw+'] as [UInt8], as: UTF8.self)'
                call=family+'('+args+')'
                lines.append('println!("{}", '+call+');' if language=='rust' else 'print('+call+')')
            filename='check.rs' if language=='rust' else 'check.swift'
            body='\nfn main() {\n'+'\n'.join(lines)+'\n}\n' if language=='rust' else '\n'+'\n'.join(lines)+'\n'
            (path/filename).write_text(source+body)
            built=command(['rustc','--edition','2021',filename,'-o','check'] if language=='rust' else ['swiftc',filename,'-o','check'],path)
            argv=[str(path/'check')]
        else: raise ValueError('Unknown native language')
        if not built['ok']:
            return {'passed':False,'behavior_checked':False,'phase':'native_compile','diagnostic':built.get('diagnostic',''),'reason':built['reason']}
        run=command(argv,path,execute=True,timeout=15)
        if not run['ok']:
            return {'passed':False,'behavior_checked':False,'phase':'native_execution','reason':run['reason'],'diagnostic':run.get('diagnostic','')}
        try:
            # Lua may print integral numeric values with .0; reject nonintegral output.
            actual=[int(line) if re.fullmatch(r'-?\d+',line) else int(line[:-2]) if re.fullmatch(r'-?\d+\.0',line) else None for line in run['output'].splitlines()]
        except ValueError: actual=[]
        if len(actual)!=len(values):
            return {'passed':False,'behavior_checked':True,'diagnostic':'Answer count or representation differs','cases':len(values)}
        wrong=[i for i,(a,b) in enumerate(zip(actual,oracle['expected'])) if a!=b]
        return {'passed':not wrong,'behavior_checked':True,'cases':len(values),'public_cases':len(oracle['public']),
                'hidden_cases':len(oracle['private']),'checks_passed':len(values)-len(wrong),
                'failures':[{'index':i,'input':values[i],'expected':oracle['expected'][i],'actual':actual[i]} for i in wrong[:5]]}


def document(task, oracle, source):
    language=task['language']; expected=oracle.get('rows')
    if oracle['kind']=='binary':
        value=json.loads(source)
        return {'passed':value==oracle['expected'],'document_checked':True,'checks':1}
    if language in ['json','http','yaml','toml']:
        if language=='http':
            class Socket:
                def makefile(self,*_args,**_kwargs): return io.BytesIO(source.encode())
            response=http.client.HTTPResponse(Socket()); response.begin(); body=response.read()
            if response.status!=200 or body!=source.encode().partition(b'\r\n\r\n')[2] or response.getheader('Content-Length')!=str(len(body)):
                raise ValueError('HTTP status or byte framing differs')
            value=json.loads(body)
        elif language=='json': value=json.loads(source)
        elif language=='yaml':
            import yaml
            value=yaml.safe_load(source)
        else:
            try: import tomllib
            except ImportError: import tomli as tomllib
            value=tomllib.loads(source)
        # JSON serialization preserves type distinctions including bool vs integer.
        passed=json.dumps(value,sort_keys=True,ensure_ascii=False)==json.dumps({'schema_version':1,'records':expected},sort_keys=True,ensure_ascii=False)
    else:
        strings=[{key:str(value) for key,value in row.items()} for row in expected]
        if language=='csv':
            reader=csv.DictReader(io.StringIO(source,newline='')); actual=list(reader)
            passed=reader.fieldnames==list(strings[0]) and actual==strings
        elif language=='ini':
            parser=configparser.ConfigParser(interpolation=None); parser.optionxform=str; parser.read_string(source)
            passed=parser.sections()==['record'+str(i) for i in range(len(strings))] and [dict(parser.items(section,raw=True)) for section in parser.sections()]==strings
        elif language=='xml':
            tree=ET.fromstring(source)
            passed=(tree.tag=='dataset' and not tree.attrib and len(tree)==len(strings)
                    and all(row.tag=='record' and not row.attrib and [cell.tag for cell in row]==list(want)
                            and [cell.text or '' for cell in row]==list(want.values()) and all(not cell.attrib and not list(cell) for cell in row)
                            for row,want in zip(tree,strings)))
        elif language=='html':
            import html5lib
            tree=html5lib.parse(source,namespaceHTMLElements=False); tables=list(tree.iter('table')); titles=list(tree.iter('title'))
            rows=[[''.join(cell.itertext()).strip() for cell in row if cell.tag in ['td','th']] for table in tables for row in table.iter('tr')]
            passed=(len(tables)==1 and tables[0].get('id')=='records' and bool(titles) and bool(''.join(titles[0].itertext()).strip())
                    and rows==[list(strings[0])]+[list(row.values()) for row in strings])
        else: raise ValueError('Unknown document target')
    return {'passed':passed,'document_checked':True,'rows_checked':len(expected),'diagnostic':'' if passed else 'Exact schema, input preservation, calculation, ordering, or required markup differs.'}


def grade(task, oracle, source):
    try:
        return native(task,oracle,source) if oracle['kind']=='code' else document(task,oracle,source)
    except (ValueError,TypeError,KeyError,IndexError,ET.ParseError,configparser.Error,csv.Error,http.client.HTTPException) as exc:
        return {'passed':False,'diagnostic':str(exc)[:500],'behavior_checked':False}
