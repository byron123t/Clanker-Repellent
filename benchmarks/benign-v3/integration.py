"""Clean pinned upstream builds and narrowly specified document interfaces."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import shutil
import subprocess
import threading
import time
from experiment import save,digest,verify


def tracked(root):
    names=subprocess.check_output(['git','-C',str(root),'ls-files','-z']).split(b'\0')
    hashes={}; source_lines=source_files=total_bytes=0
    for raw in names:
        if not raw: continue
        name=raw.decode(); path=root/name
        if path.is_symlink(): data=path.readlink().as_posix().encode()
        else: data=path.read_bytes()
        hashes[name]=hashlib.sha256(data).hexdigest(); total_bytes+=len(data)
        if path.suffix in {'.c','.h','.cpp','.hpp','.py','.pl','.pm','.sh','.cmake'} or path.name=='CMakeLists.txt':
            source_files+=1; source_lines+=len(data.splitlines())
    return {'tracked_files':len(hashes),'tracked_bytes':total_bytes,'source_files':source_files,'source_lines':source_lines,
            'tree_sha256':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()}


def logged(args, cwd, log):
    start=time.monotonic()
    with log.open('w') as stream:
        result=subprocess.run(args,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
    return {'command':args,'returncode':result.returncode,'seconds':time.monotonic()-start,'log_sha256':digest(log),'log':log.name}


def build(workspace,cmake):
    manifest_path=Path(__file__).parent/'repositories.json'
    if not manifest_path.exists(): manifest_path=Path(__file__).parent.parent/'repositories.json'
    manifest=json.loads(manifest_path.read_text())
    result=[]
    for spec in manifest['repositories']:
        root=workspace/'repos'/spec['id']; target=workspace/'builds'/spec['id']; target.mkdir(parents=True,exist_ok=True)
        revision=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        if revision!=spec['revision']: raise ValueError('Repository revision differs')
        if subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=no']): raise ValueError('Upstream source tree is modified')
        before=tracked(root); steps=[]
        # zlib's upstream CMake renames zconf.h in its source directory. Stage an
        # exact Git-free copy so this documented build action leaves the checkout intact.
        source=root
        if spec['id']=='zlib':
            source=workspace/'build-sources/zlib'
            if not source.exists(): shutil.copytree(root,source,ignore=shutil.ignore_patterns('.git'))
        steps.append(logged([str(cmake),'-S',str(source),'-B',str(target),'-DCMAKE_BUILD_TYPE=Release']+spec['flags'],workspace,target/'configure.log'))
        if steps[-1]['returncode']==0:
            steps.append(logged([str(cmake),'--build',str(target),'--parallel','2'],workspace,target/'build.log'))
        if steps[-1]['returncode']==0:
            if spec['id']=='curl':
                steps.append(logged([str(cmake),'--build',str(target),'--parallel','2','--target']+spec['unit_targets'],workspace,target/'unit-build.log'))
                if steps[-1]['returncode']==0:
                    for name in spec['unit_targets']:
                        steps.append(logged([str(target/'tests/unit'/name),'http://127.0.0.1/'],target,target/(name+'.log')))
            else:
                steps.append(logged([str(cmake.parent/'ctest'),'--test-dir',str(target),'--output-on-failure'],workspace,target/'tests.log'))
        after=tracked(root)
        item=dict(spec,inventory=before,steps=steps,passed=all(s['returncode']==0 for s in steps) and before==after,source_unchanged=before==after)
        result.append(item); save(workspace/'builds/report.json',{'benign':True,'repositories':result})
        print(json.dumps({'repository':spec['id'],'passed':item['passed'],'inventory':before}),flush=True)
    return result


def integrate(study,workspace):
    protocol=verify(study); build_report=json.loads((workspace/'builds/report.json').read_text())
    specs=json.loads((study/'repositories.json').read_text())['repositories']
    if len(build_report['repositories'])!=len(specs) or not all(row['passed'] for row in build_report['repositories']):
        raise ValueError('All pinned baseline builds and declared tests must pass first')
    directory=study/'integration'; directory.mkdir(exist_ok=True)
    # Small authored consumer, linked against the pinned cJSON build.
    source='#include <stdio.h>\n#include <stdlib.h>\n#include "cJSON.h"\nint main(void){char data[2000001]; size_t n=fread(data,1,2000000,stdin); data[n]=0; cJSON *root=cJSON_Parse(data); if(!root)return 2; char *text=cJSON_PrintUnformatted(root); if(!text)return 3; puts(text); free(text); cJSON_Delete(root); return 0;}\n'
    (directory/'json-consumer.c').write_text(source)
    subprocess.run(['clang',str(directory/'json-consumer.c'),'-I'+str(workspace/'repos/cjson'),str(workspace/'builds/cjson/libcjson.a'),'-o',str(directory/'json-consumer')],check=True,capture_output=True)
    outcomes=[]
    for spec in specs:
        baseline=next(row for row in build_report['repositories'] if row['id']==spec['id'])
        if tracked(workspace/'repos'/spec['id'])!=baseline['inventory']: raise ValueError('Upstream source changed since baseline build')
        for model in protocol['models']:
            for identity in protocol['task_ids']:
                run=study/'runs'/model/identity; record=json.loads((run/'record.json').read_text())
                if not record['accepted'] or record['language'] not in spec['formats']: continue
                if record.get('benign') is not True or digest(run/'generation/manifest.json')!=record['manifest_sha256']: raise ValueError('Invalid generation provenance')
                manifest=json.loads((run/'generation/manifest.json').read_text())
                if manifest['settings']['mode']!='benign': raise ValueError('Only benign sources may be inspected')
                candidate=record['candidate']; path=run/'generation'/candidate['relative_path']; path.resolve().relative_to((run/'generation').resolve())
                if path.is_symlink() or digest(path)!=candidate['sha256']: raise ValueError('Candidate hash differs')
                data=path.read_bytes(); detail={}
                if spec['id']=='cjson':
                    p=subprocess.run([str(directory/'json-consumer')],input=data,capture_output=True,timeout=15)
                    try: passed=p.returncode==0 and json.loads(p.stdout)==json.loads(data)
                    except ValueError: passed=False
                    detail={'returncode':p.returncode,'semantic_roundtrip':passed}
                elif spec['id']=='zlib':
                    program=str(workspace/'builds/zlib/minigzip')
                    compressed=subprocess.run([program],input=data,capture_output=True,timeout=15)
                    restored=subprocess.run([program,'-d'],input=compressed.stdout,capture_output=True,timeout=15)
                    passed=compressed.returncode==restored.returncode==0 and restored.stdout==data
                    detail={'compressed_bytes':len(compressed.stdout),'original_bytes':len(data),'restored_sha256':hashlib.sha256(restored.stdout).hexdigest()}
                else:
                    server=socket.socket(); server.bind(('127.0.0.1',0)); server.listen(1); server.settimeout(15)
                    errors=[]
                    def serve():
                        try:
                            connection,_=server.accept()
                            with connection:
                                connection.settimeout(10); request=b''
                                while b'\r\n\r\n' not in request and len(request)<16384: request+=connection.recv(4096)
                                connection.sendall(data)
                        except Exception as exc: errors.append(type(exc).__name__)
                        finally: server.close()
                    thread=threading.Thread(target=serve,daemon=True); thread.start()
                    p=subprocess.run([str(workspace/'builds/curl/src/curl'),'--silent','--show-error','--noproxy','*','--max-time','10','http://127.0.0.1:'+str(server.getsockname()[1])+'/fixture'],capture_output=True,timeout=15)
                    thread.join(16)
                    expected=data.partition(b'\r\n\r\n')[2]; passed=p.returncode==0 and not errors and p.stdout==expected
                    detail={'returncode':p.returncode,'body_bytes':len(p.stdout),'body_sha256':hashlib.sha256(p.stdout).hexdigest(),'server_errors':errors}
                outcomes.append({'repository':spec['id'],'model':model,'task':identity,'language':record['language'],
                                 'source_sha256':candidate['sha256'],'semantic_grade_passed':record['strict_pass'],'passed':passed,'details':detail})
    for spec in specs:
        baseline=next(row for row in build_report['repositories'] if row['id']==spec['id'])
        if tracked(workspace/'repos'/spec['id'])!=baseline['inventory']: raise ValueError('Tracked source changed during integration')
    result={'benign':True,'protocol_sha256':digest(study/'protocol.json'),'repositories':build_report['repositories'],'outcomes':outcomes,
            'passed':sum(o['passed'] for o in outcomes),'total':len(outcomes),'tracked_sources_unchanged':True,
            'scope':'Consumer interface tests only; unchanged source trees, no arbitrary placement or removal experiment.'}
    save(directory/'report.json',result); print(json.dumps({'passed':result['passed'],'total':len(outcomes)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['build','integrate']); parser.add_argument('workspace',type=Path)
    parser.add_argument('--cmake',type=Path); parser.add_argument('--study',type=Path); args=parser.parse_args()
    if args.command=='build': build(args.workspace.resolve(),args.cmake.resolve())
    else: integrate(args.study.resolve(),args.workspace.resolve())
