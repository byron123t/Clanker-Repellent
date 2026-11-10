import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

BENCHMARK=Path(__file__).resolve().parents[1]/'benchmarks/benign-v3'


def module(name):
    spec=importlib.util.spec_from_file_location('breadth_'+name,BENCHMARK/(name+'.py'))
    value=importlib.util.module_from_spec(spec)
    if name=='publish':
        old=sys.modules.get('experiment'); sys.modules['experiment']=module('experiment')
        try: spec.loader.exec_module(value)
        finally:
            if old is None: sys.modules.pop('experiment',None)
            else: sys.modules['experiment']=old
    else: spec.loader.exec_module(value)
    return value


class BreadthEvaluationTests(unittest.TestCase):
    def test_reproduction_verifies_inventory_before_extracting(self):
        reproduce=module('reproduce')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); archive=root/'evidence.zip'; content=b'authored reference data\n'
            with zipfile.ZipFile(archive,'w') as bundle:
                bundle.writestr('reference.txt',content)
                bundle.writestr('ARTIFACTS.json',json.dumps({'benign':True,'files':{'reference.txt':hashlib.sha256(content).hexdigest()}}))
            sha=hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(reproduce.extract(archive,root/'valid',sha),1)
            self.assertEqual((root/'valid/reference.txt').read_bytes(),content)
            with self.assertRaises(ValueError): reproduce.extract(archive,root/'wrong-hash','0'*64)
            self.assertFalse((root/'wrong-hash').exists())
            with zipfile.ZipFile(archive,'w') as bundle:
                bundle.writestr('reference.txt',content)
                bundle.writestr('ARTIFACTS.json',json.dumps({'benign':True,'files':{'reference.txt':'0'*64}}))
            with self.assertRaises(ValueError): reproduce.extract(archive,root/'bad-member',hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertFalse((root/'bad-member').exists())

    def test_reproduction_rejects_paths_outside_the_new_directory(self):
        reproduce=module('reproduce')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); archive=root/'evidence.zip'
            with zipfile.ZipFile(archive,'w') as bundle:
                bundle.writestr('../outside.txt','authored')
                bundle.writestr('ARTIFACTS.json',json.dumps({'benign':True,'files':{'../outside.txt':hashlib.sha256(b'authored').hexdigest()}}))
            with self.assertRaises(ValueError): reproduce.extract(archive,root/'new',hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertFalse((root/'new').exists()); self.assertFalse((root/'outside.txt').exists())
    def test_document_oracles_reject_valid_but_wrong_calculations(self):
        suite=module('build_suite'); grader=module('grade')
        tasks,oracles=suite.build()
        for task in tasks['tasks']:
            oracle=oracles['oracles'][task['id']]
            if oracle['kind']!='document': continue
            with self.subTest(task=task['id']):
                self.assertTrue(grader.grade(task,oracle,oracle['control'])['passed'])
                rows=copy.deepcopy(oracle['rows']); key=list(rows[0])[-1]; rows[0][key]+=1
                self.assertFalse(grader.grade(task,oracle,suite.document_control(task['language'],rows))['passed'])

    def test_native_task_boundaries_are_explicit(self):
        suite=module('build_suite')
        for value,expected in [('',-1),('+',-1),(' +00065535\r\n',65535),('65536',-1),('12\0',-1),('\u0661',-1),('1\v',-1)]:
            self.assertEqual(suite.expected('parse_decimal',value),expected)
        self.assertEqual(suite.expected('longest_run',[1,2,2,3,4]),3)
        self.assertEqual(suite.expected('ceil_div',[0,3]),0)

    def test_publication_rejects_manifest_record_disagreement(self):
        publisher=module('publish')
        record={'accepted':True,'status':'passed','candidate':{'sha256':'a'*64},'language':'csv','attempts':1,
                'attempt_outcomes':['passed'],'strict_pass':True,'grade':{'passed':True},
                'family':'invoice','level':2,'track':'documents','arm':'current','trial':0}
        task={'language':'csv','family':'invoice','level':2,'track':'documents','prompt':'Authored invoice task'}
        candidate={k:record[k] for k in ['accepted','status','candidate','language']}; candidate['attempts']=[{'status':'passed'}]
        manifest={'settings':{'mode':'benign'},'model':'test','candidates':[candidate],
                  'payload':{'sha256':hashlib.sha256(task['prompt'].encode()).hexdigest(),'bytes':len(task['prompt'])}}
        publisher.validate_record(record,manifest,task,{'id':'test'})
        for key,value in [('accepted',False),('candidate',{'sha256':'b'*64}),('attempts',2),('strict_pass',False),('language','xml'),('level',1),('family','other'),('arm','baseline'),('trial',1)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                changed=dict(record); changed[key]=value
                publisher.validate_record(changed,manifest,task,{'id':'test'})
        manifest['payload']['bytes']+=1
        with self.assertRaises(ValueError): publisher.validate_record(record,manifest,task,{'id':'test'})
        manifest['payload']['bytes']-=1
        manifest['settings']['mode']='default'
        with self.assertRaises(ValueError): publisher.validate_record(record,manifest,task,{'id':'test'})


if __name__=='__main__': unittest.main()
