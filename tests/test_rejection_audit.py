"""Integrity gates for post hoc diagnostics, using only authored benign fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('rejection_audit',Path(__file__).resolve().parents[1]/'benchmarks/benign-v2/audit_rejections.py')
audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class RejectionAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.directory=self.root/'runs/fixture/baseline/helper/0'
        (self.directory/'generation').mkdir(parents=True)
        (self.directory/'traces').mkdir()
        self.source='def increment(value):\n    """Read an integer input."""\n    return value + 1\n'
        response='```python\n'+self.source+'```'
        self.manifest={'settings':{'mode':'benign'},'model':'authored-fixture',
            'candidates':[{'language':'python','accepted':False,'status':'failed','attempts':[
                {'status':'benign_policy_failed','response':{'sha256':hashlib.sha256(response.encode()).hexdigest(),'bytes':len(response.encode())}}]}]}
        self.manifest_path=self.directory/'generation/manifest.json'
        audit.save(self.manifest_path,self.manifest)
        self.record={'benign':True,'model':'fixture','arm':'baseline','task':'helper','trial':0,'language':'python',
            'accepted':False,'status':'failed','attempts':1,'generation_manifest_sha256':audit.sha(self.manifest_path)}
        audit.save(self.directory/'record.json',self.record)
        self.protocol={'benign':True,'files':{},'models':{'fixture':{'id':'authored-fixture'}},
            'arms':['baseline'],'task_ids':['helper'],'repeats':1}
        audit.save(self.root/'protocol.json',self.protocol)
        request={'synthetic':True}
        self.trace={'benign':True,'mode':'benign','request':request,
            'request_sha256':hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest(),
            'response':{'response_text':response}}
        self.trace_path=self.directory/'traces/01.json'; audit.save(self.trace_path,self.trace)

    def test_complete_benign_grid_and_exact_response_can_be_selected(self):
        protocol,records=audit.selected_records(self.root,['fixture'])
        self.assertEqual(len(records),1)
        before=self.trace_path.read_bytes()
        source,path=audit.response_source(*records[0])
        self.assertEqual(source,self.source); self.assertEqual(path,self.trace_path)
        self.assertEqual(self.trace_path.read_bytes(),before)

    def test_incomplete_grid_or_nonbenign_manifest_is_rejected(self):
        self.protocol['repeats']=2; audit.save(self.root/'protocol.json',self.protocol)
        with self.assertRaisesRegex(ValueError,'Complete model grid'): audit.selected_records(self.root,['fixture'])
        self.protocol['repeats']=1; audit.save(self.root/'protocol.json',self.protocol)
        self.manifest['settings']['mode']='standard'; audit.save(self.manifest_path,self.manifest)
        self.record['generation_manifest_sha256']=audit.sha(self.manifest_path); audit.save(self.directory/'record.json',self.record)
        with self.assertRaisesRegex(ValueError,'provenance'): audit.selected_records(self.root,['fixture'])

    def test_tampered_response_or_untrusted_mode_is_not_extracted(self):
        self.trace['response']['response_text']+=' changed'; audit.save(self.trace_path,self.trace)
        with self.assertRaisesRegex(ValueError,'Response checksum'): audit.response_source(self.directory,self.record,self.manifest)
        self.trace['mode']='standard'; audit.save(self.trace_path,self.trace)
        with self.assertRaisesRegex(ValueError,'Nonbenign response'): audit.response_source(self.directory,self.record,self.manifest)

    def test_reproduction_requires_exact_cases_and_groups(self):
        result={'benign':True,'post_hoc':True,'source_protocol_sha256':'synthetic','groups':[{'verified':1}],
                'cases':[{'benign':True,'verified':True}]}
        path=self.root/'original.json'; audit.save(path,result)
        audit.verify_against(result,path,self.root)
        proof=audit.read(self.root/'reproduction-check.json')
        self.assertEqual(proof['report_sha256'],audit.sha(path)); self.assertEqual(proof['cases'],1)
        result['cases'][0]['verified']=False
        with self.assertRaisesRegex(ValueError,'outcomes differ'): audit.verify_against(result,path,self.root)


if __name__=='__main__': unittest.main()
