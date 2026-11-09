"""Read exported benign study reports; source previews are explicit and hash-verified."""
import hashlib
import json
from pathlib import Path
import re

STUDY_ID=re.compile(r'[a-z0-9][a-z0-9_-]{0,79}\Z')
CASE_ID=re.compile(r'[0-9a-f]{64}\Z')
DEFAULT_ROOT=Path(__file__).resolve().parents[3]/'evaluation'


class EvaluationReader:
    def __init__(self,root=None):
        self.root=Path(root).resolve() if root is not None else DEFAULT_ROOT

    def _directory(self,identity):
        if not STUDY_ID.fullmatch(identity): raise LookupError('Unknown study')
        path=self.root/identity
        if path.is_symlink() or not path.is_dir(): raise LookupError('Unknown study')
        return path

    def study(self,identity):
        path=self._directory(identity)/'report.json'
        if path.is_symlink() or not path.is_file() or path.stat().st_size>8*1024*1024:
            raise ValueError('Study report is unavailable or outside its size limit')
        value=json.loads(path.read_bytes())
        if (not isinstance(value,dict) or type(value.get('schema_version')) is not int or value.get('schema_version')!=1 or value.get('benign') is not True
                or value.get('id')!=identity or not isinstance(value.get('cases'),list)
                or len(value['cases'])>10000):
            raise ValueError('Only versioned benign evaluation reports are supported')
        for key in ['design','counts','provenance']:
            if not isinstance(value.get(key),dict): raise ValueError('Invalid report metadata')
        for key in ['metrics','effects','groups','methodology','limitations','references']:
            if not isinstance(value.get(key),list): raise ValueError('Invalid report collection')
        for key in ['formats','models','arms']:
            if not isinstance(value['design'].get(key),list): raise ValueError('Invalid study design')
        seen=set()
        for case in value['cases']:
            if not isinstance(case,dict) or not isinstance(case.get('id'),str) or not CASE_ID.fullmatch(case['id']) or case['id'] in seen:
                raise ValueError('Invalid or duplicate evaluation case')
            seen.add(case['id'])
            if not all(isinstance(case.get(key),str) for key in ['task','language','model','arm']):
                raise ValueError('Invalid candidate metadata')
            sha=case.get('source_sha256')
            if sha is not None and (not isinstance(sha,str) or not CASE_ID.fullmatch(sha)):
                raise ValueError('Invalid candidate checksum')
        return value

    def catalog(self):
        studies=[]; errors=0
        if self.root.is_dir():
            for directory in sorted(self.root.iterdir()):
                if not STUDY_ID.fullmatch(directory.name) or directory.is_symlink() or not directory.is_dir(): continue
                if not (directory/'report.json').is_file(): continue
                try:
                    value=self.study(directory.name)
                    studies.append({key:value.get(key) for key in ['id','title','stage','state','updated_at','counts','design']})
                except (OSError,ValueError,KeyError,TypeError): errors+=1
        studies.sort(key=lambda study:(study.get('state')=='complete',study.get('updated_at') or ''),reverse=True)
        return {'studies':studies,'errors':errors,'source':'Recorded benign experiments'}

    def preview(self,identity,case_id):
        if not CASE_ID.fullmatch(case_id): raise LookupError('Unknown evaluation case')
        study=self.study(identity)
        case=next((case for case in study['cases'] if case['id']==case_id),None)
        if not case or not case.get('source_sha256'): raise LookupError('No recorded source for this case')
        directory=self._directory(identity)/'candidates'
        path=directory/(case_id+'.txt')
        if directory.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size>2*1024*1024:
            raise ValueError('Candidate is unavailable or outside its size limit')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=case['source_sha256']:
            raise ValueError('Candidate checksum differs from the recorded experiment')
        return {'benign':True,'text':data[:65536].decode('utf-8',errors='replace'),'bytes':len(data),
                'truncated':len(data)>65536,'sha256':case['source_sha256'],'filename':case['task']+'.'+case['language']}

    def download(self,identity,name):
        study=self.study(identity)
        if name not in {'report.json','protocol.json','scores.json','REPORT.md','reproduction.zip','figure.pdf','figure.svg','figure.png'}: raise LookupError('Unknown experiment artifact')
        path=self._directory(identity)/name
        if path.is_symlink() or not path.is_file(): raise LookupError('Artifact unavailable')
        if path.stat().st_size>16*1024*1024: raise ValueError('Artifact exceeds download limit')
        data=path.read_bytes()
        field={'protocol.json':'protocol_sha256','scores.json':'scores_sha256','reproduction.zip':'reproduction_sha256'}.get(name)
        expected=study['provenance'].get(field) if field else None
        if name.startswith('figure.'):
            expected=study['provenance'].get('figure_sha256',{}).get(name)
            if expected is None: raise ValueError('Figure checksum is missing')
        if expected is not None and hashlib.sha256(data).hexdigest()!=expected:
            raise ValueError('Experiment artifact checksum differs from the report')
        return data,name
