"""Runner integration with an explicitly synthetic local inference fixture.

These are software tests, never published as GLM/DeepSeek experimental results.
"""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

REPO=Path(__file__).resolve().parents[1]
CORRECT='def clamp(value, lower, upper):\n    if lower > upper: return value\n    return max(lower,min(value,upper))\n'
WRONG='def clamp(value, lower, upper):\n    return max(lower,min(value,upper))\n'


class ExperimentIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.requests=[]; self.mode='repair'; self.model_id='synthetic-fixture'
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def respond(self,value,status=200):
                data=json.dumps(value).encode(); self.send_response(status); self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_GET(self): self.respond({'object':'list','data':[{'id':owner.model_id,'object':'model'}]})
            def do_POST(self):
                owner.requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                if owner.mode=='transport': return self.respond({'error':{'message':'synthetic outage','type':'server_error'}},503)
                code=WRONG if owner.mode=='wrong' or len(owner.requests)==1 else CORRECT
                self.respond({'id':'fixture','object':'chat.completion','created':0,'model':owner.model_id,
                    'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'```python\n'+code+'```'}}],
                    'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.addCleanup(self.stop)
        for arm in ['baseline','contract']:
            shutil.copytree(REPO/'src',self.root/'engines'/arm,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        (self.root/'runner').mkdir()
        for name in ['experiment.py','grade.py']: shutil.copyfile(REPO/'benchmarks/benign-v2'/name,self.root/'runner'/name)
        contract={'schema_version':1,'language':'python','function':{'name':'clamp','parameters':['value','lower','upper']},
                  'examples':[{'inputs':[5,10,0],'expected':5},{'inputs':[-2,0,10],'expected':0},{'inputs':[15,0,10],'expected':10}]}
        task={'id':'fixture-clamp','language':'python','level':1,'family':'clamp','split':'development','prompt':'Benign clamp helper. Return value if bounds reverse.','contract':contract}
        self.save('tasks.json',{'benign':True,'tasks':[task]})
        self.save('oracles.json',{'benign':True,'oracles':{'fixture-clamp':{'kind':'numeric','cases':[{'inputs':[991,0,20],'expected':20}],'control':CORRECT}}})
        files={str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        self.save('protocol.json',{'schema_version':1,'kind':'benign_evaluation','benign':True,'stage':'development','repeats':1,
            'task_ids':['fixture-clamp'],'arms':['baseline','contract'],'models':{'fixture':{'id':'synthetic-fixture','endpoint':f'http://127.0.0.1:{self.server.server_port}/v1'}},
            'files':files,'settings':{'request_timeout_seconds':3,'max_tokens':512,'temperature':.2,'top_p':.8,'retries':2,
                                     'no_thinking':True,'linters':False,'validator_timeout_seconds':20}})
        self.job=self.root/'runs/fixture/contract/fixture-clamp/0'

    def stop(self): self.server.shutdown(); self.server.server_close(); self.thread.join()
    def save(self,name,value): (self.root/name).write_text(json.dumps(value))
    def worker(self):
        return subprocess.run([sys.executable,str(self.root/'runner/experiment.py'),'worker',str(self.root),
            '--model','fixture','--arm','contract','--task','fixture-clamp','--trial','0'],capture_output=True,text=True,timeout=30)

    def test_semantic_retry_trace_resume_and_independent_score(self):
        result=self.worker(); self.assertEqual(result.returncode,0,result.stderr)
        record=json.loads((self.job/'record.json').read_text())
        self.assertTrue(record['benign']); self.assertTrue(record['accepted']); self.assertEqual(record['attempts'],2)
        self.assertIn('Public example 1 failed',self.requests[1]['messages'][1]['content'])
        self.assertFalse(any('991' in message['content'] for request in self.requests for message in request['messages']))
        self.assertEqual(self.requests[1]['seed'],(self.requests[0]['seed']+1)%2**32)
        before=(self.job/'record.json').read_bytes(); self.assertEqual(self.worker().returncode,0)
        self.assertEqual(len(self.requests),2); self.assertEqual((self.job/'record.json').read_bytes(),before)
        score=subprocess.run([sys.executable,str(REPO/'benchmarks/benign-v2/experiment.py'),'score',str(self.root)],capture_output=True,text=True,timeout=30)
        self.assertEqual(score.returncode,0,score.stderr)
        scored=json.loads((self.root/'scores.json').read_text())['records'][0]
        self.assertTrue(scored['strict_pass']); self.assertEqual(scored['grade']['hidden_passed'],1)

    def test_completed_failure_is_preserved_and_transport_is_missing_not_failure(self):
        self.mode='wrong'; result=self.worker(); self.assertEqual(result.returncode,0,result.stderr)
        record=json.loads((self.job/'record.json').read_text()); self.assertFalse(record['accepted']); self.assertEqual(record['attempts'],3)
        self.assertEqual(self.worker().returncode,0); self.assertEqual(len(self.requests),3)
        shutil.rmtree(self.root/'runs'); self.requests.clear(); self.mode='transport'
        result=self.worker(); self.assertEqual(result.returncode,75,result.stderr)
        self.assertFalse((self.job/'record.json').exists())
        manifest=json.loads((self.job/'generation/manifest.json').read_text())
        self.assertEqual(manifest['summary']['pending'],1); self.assertEqual(manifest['candidates'],[])
        self.assertTrue((self.job/'interruption.json').is_file())

    def test_changed_frozen_task_is_rejected_before_contacting_provider(self):
        (self.root/'tasks.json').write_text('{}')
        result=self.worker(); self.assertNotEqual(result.returncode,0); self.assertIn('Frozen study artifact changed',result.stderr)
        self.assertEqual(self.requests,[])


if __name__=='__main__': unittest.main()
