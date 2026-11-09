"""Attach reproduction environment and reporting clarifications; preserve primary results."""
from datetime import datetime,timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import zipfile


def finalize(directory):
    report=json.loads((directory/'report.json').read_text())
    if report.get('benign') is not True or report['state']!='complete' or report['stage'] not in {'development','heldout'}:
        raise ValueError('Only complete benign model studies')
    verification=report['provenance'].get('offline_verification',{})
    if (verification.get('benign') is not True or not verification.get('reproduced')
            or verification.get('observations')!=report['counts']['completed']
            or verification.get('protocol_sha256')!=report['provenance']['protocol_sha256']):
        raise ValueError('Verify the exported outcomes before finalizing the report')
    primary=json.dumps({k:report[k] for k in ['counts','metrics','effects','groups','cases']},sort_keys=True)
    environment={'benign':True,'recorded_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Local offline grading/verification host; remote inference hardware and model weights are not independently verified.',
        'python':platform.python_version(),'platform':platform.platform(),'sqlite':sqlite3.sqlite_version,
        'clang':subprocess.check_output(['clang','--version'],text=True).splitlines()[0],
        'python_packages':{name:version(name) for name in ['html5lib','Pygments','six','webencodings']}}
    requirements=''.join(name+'=='+value+'\n' for name,value in environment['python_packages'].items())
    artifact={'title':'Artifact being graded','body':'The outcome is the accepted CLI artifact after ordinary source extraction and formatting. Fenced source is extracted; HTTP headers are normalized to CRLF and Content-Length is computed from the final UTF-8 body. Exported snippets preserve those accepted bytes. Raw provider responses remain separate in the archive. HTTP framing success is therefore a pipeline result, not proof that the model calculated byte lengths itself.'}
    runtime={'title':'Grading environment','body':'Offline outcomes were reproduced on '+environment['platform']+', Python '+environment['python']+', SQLite '+environment['sqlite']+', '+environment['clang']+'. Python parsing dependencies: '+', '.join(name+' '+value for name,value in environment['python_packages'].items())+'. The archive includes exact regrading dependency pins. The frozen native LLVM grader uses macOS linking; other platforms have not been validated. Remote serving hardware and weights are not independently verified.'}
    titles={artifact['title'],runtime['title']}
    report['methodology']=[item for item in report['methodology'] if item['title'] not in titles]+[artifact,runtime]
    with zipfile.ZipFile(directory/'reproduction.zip') as archive:
        manifest=json.loads(archive.read('artifact-manifest.json'))
        if manifest.get('benign') is not True: raise ValueError('Nonbenign archive')
        contents={name:archive.read(name) for name in manifest['files']}
        for name,data in contents.items():
            if hashlib.sha256(data).hexdigest()!=manifest['files'][name]: raise ValueError('Archive evidence changed: '+name)
    if hashlib.sha256(contents['protocol.json']).hexdigest()!=report['provenance']['protocol_sha256']:
        raise ValueError('Archive and report protocol differ')
    contents['publication/environment.json']=(json.dumps(environment,indent=2)+'\n').encode()
    contents['publication/offline-verification.json']=(json.dumps(verification,indent=2)+'\n').encode()
    contents['publication/finalize_model_report.py']=Path(__file__).read_bytes()
    contents['requirements-regrade.txt']=requirements.encode()
    contents['REGRADING_ENVIRONMENT.md']=(
        '# Offline regrading\n\nInstall `requirements-regrade.txt` in a Python environment, then run:\n\n'
        '```sh\npython runner/reproduce_models.py .\n```\n\n'
        'Use macOS with Clang for the frozen native LLVM linker settings. No inference endpoint or API key is used.\n'
        'The optional plotting dependency is in `runner/requirements.txt`.\n\n'+runtime['body']+'\n\n'+artifact['body']+'\n').encode()
    manifest={'schema_version':1,'benign':True,'files':{name:hashlib.sha256(data).hexdigest() for name,data in contents.items()}}
    temporary=directory/'reproduction.zip.tmp'
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in contents.items():
            item=zipfile.ZipInfo(name,date_time=(2026,11,9,0,0,0)); item.compress_type=zipfile.ZIP_DEFLATED; archive.writestr(item,data)
        archive.writestr('artifact-manifest.json',json.dumps(manifest,indent=2)+'\n')
    temporary.replace(directory/'reproduction.zip')
    report['provenance']['reproduction_sha256']=hashlib.sha256((directory/'reproduction.zip').read_bytes()).hexdigest()
    report['provenance']['grading_environment']=environment
    report['updated_at']=datetime.now(timezone.utc).isoformat()
    if primary!=json.dumps({k:report[k] for k in ['counts','metrics','effects','groups','cases']},sort_keys=True):
        raise ValueError('Primary results changed')
    temporary=directory/'report.json.tmp';temporary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');temporary.replace(directory/'report.json')
    heading='\n## Regrading environment and artifact definition\n'
    document=(directory/'REPORT.md').read_text().split(heading)[0].split('\n## Artifact being graded\n')[0]
    (directory/'REPORT.md').write_text(document+heading+'\n'+runtime['body']+'\n\n'+artifact['body']+'\n')
    print(json.dumps({'finalized':report['id'],'observations':report['counts']['completed'],'primary_results_unchanged':True,
                      'reproduction_sha256':report['provenance']['reproduction_sha256']}))


if __name__=='__main__': finalize(Path(sys.argv[1]).resolve())
