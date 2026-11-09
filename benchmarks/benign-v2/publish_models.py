"""Export measured model studies and a checksum-pinned offline grading archive."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile


def read(path): return json.loads(path.read_text())
def digest(data): return hashlib.sha256(data).hexdigest()


def publish(root,destination):
    protocol=read(root/'protocol.json'); scores=read(root/'scores.json')
    if protocol.get('benign') is not True or scores.get('benign') is not True: raise ValueError('Only benign model studies')
    for name,expected in protocol['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts: raise ValueError('Unsafe frozen path')
        path=root/relative; path.resolve().relative_to(root.resolve())
        if path.is_symlink() or digest(path.read_bytes())!=expected: raise ValueError('Frozen artifact changed: '+name)
    spec=importlib.util.spec_from_file_location('frozen_model_analysis',root/'runner/analyze.py')
    analysis=importlib.util.module_from_spec(spec); spec.loader.exec_module(analysis)
    analysis.publish(root,destination)
    report=read(destination/'report.json')
    if report['state']!='complete': return
    members=set(protocol['files'])|{'protocol.json','scores.json','status.json'}
    for row in scores['records']:
        if row.get('benign') is not True: raise ValueError('Nonbenign observation')
        directory=Path(row['directory'])
        if directory.is_absolute() or '..' in directory.parts: raise ValueError('Unsafe observation path')
        manifest_path=root/directory/'generation/manifest.json'
        if digest(manifest_path.read_bytes())!=row['generation_manifest_sha256']: raise ValueError('Manifest changed')
        manifest=read(manifest_path)
        if manifest.get('settings',{}).get('mode')!='benign': raise ValueError('Nonbenign manifest')
        members.update(str(directory/name) for name in ['record.json','generation/manifest.json'])
        if row.get('candidate'):
            members.add(str(directory/'generation'/row['candidate']['relative_path']))
        for path in (root/directory/'traces').glob('*.json'):
            trace=read(path)
            if trace.get('benign') is not True or trace.get('mode')!='benign': raise ValueError('Nonbenign trace')
            if digest(json.dumps(trace['request'],sort_keys=True).encode())!=trace['request_sha256']:
                raise ValueError('Trace request checksum differs')
            number=int(path.stem)
            attempts=manifest['candidates'][0]['attempts']
            if not 1<=number<=len(attempts): raise ValueError('Trace does not match a completed attempt')
            response=trace['response']['response_text'].encode()
            metadata=attempts[number-1]['response']
            if digest(response)!=metadata['sha256'] or len(response)!=metadata['bytes']:
                raise ValueError('Trace response differs from its manifest')
            members.add(str(path.relative_to(root)))
    contents={}
    for name in sorted(members):
        relative=Path(name); path=root/relative
        if relative.is_absolute() or '..' in relative.parts or path.is_symlink(): raise ValueError('Unsafe archive member')
        path.resolve().relative_to(root.resolve()); contents[name]=path.read_bytes()
    here=Path(__file__).parent
    for name in ['reproduce_models.py','publish_models.py','plot_models.py','requirements.txt']:
        contents.setdefault('runner/'+name,(here/name).read_bytes())
    contents['README-REPRODUCE.md']=(
        '# Recorded benign model study\n\nRun `python runner/reproduce_models.py .` with the project dependencies on macOS with Clang.\n'
        'This verifies archive checksums and regrades saved outputs in a temporary copy. It makes no inference requests.\n'
        'The original acceptance manifests are preserved; independent native/document and filter-only outcomes are recomputed.\n'
        'Requested sampling seeds do not establish that new model generations would be identical.\n').encode()
    artifact={'schema_version':1,'benign':True,'files':{name:digest(data) for name,data in contents.items()}}
    with zipfile.ZipFile(destination/'reproduction.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in contents.items():
            item=zipfile.ZipInfo(name,date_time=(2026,11,9,0,0,0)); item.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(item,data)
        archive.writestr('artifact-manifest.json',json.dumps(artifact,indent=2)+'\n')
    report['provenance']['reproduction_sha256']=digest((destination/'reproduction.zip').read_bytes())
    report['methodology'].append({'title':'Offline reproduction archive','body':'Download includes both frozen engines, public tasks, private grading fixtures, raw explicitly benign request/response traces, manifests, exact accepted sources, and checksums. The offline driver regrades in a temporary copy without inference or altering original evidence. The original acceptance decision is preserved; native/data and filter-only outcomes are recomputed.'})
    (destination/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (destination/'REPORT.md').write_text(analysis.markdown(report))
    print(json.dumps({'archive_sha256':report['provenance']['reproduction_sha256'],'archive_bytes':(destination/'reproduction.zip').stat().st_size}))


if __name__=='__main__': publish(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
