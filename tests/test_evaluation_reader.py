import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from clanker_repellent.dashboard.app import DashboardApp
from clanker_repellent.dashboard.evaluations import EvaluationReader


class EvaluationReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.directory=self.root/'example'; self.directory.mkdir()
        self.source=b'def double(value): return value*2\n'; self.identity=hashlib.sha256(b'case').hexdigest()
        self.report={'schema_version':1,'benign':True,'id':'example','title':'Example','stage':'development','state':'complete',
            'updated_at':'2026-11-09','design':{'formats':['python'],'models':['test'],'arms':['contract']},'counts':{},'provenance':{},
            'metrics':[],'effects':[],'groups':[],'methodology':[],'limitations':[],'references':[],
            'cases':[{'id':self.identity,'task':'double','language':'python','model':'test','arm':'contract','source_sha256':hashlib.sha256(self.source).hexdigest()}]}
        self.save(); (self.directory/'candidates').mkdir()
        self.candidate=self.directory/'candidates'/(self.identity+'.txt'); self.candidate.write_bytes(self.source)
        self.reader=EvaluationReader(self.root)

    def save(self): (self.directory/'report.json').write_text(json.dumps(self.report))

    def test_catalog_metadata_does_not_read_sources(self):
        self.candidate.unlink()
        self.assertEqual(len(self.reader.catalog()['studies']),1)
        self.assertEqual(len(self.reader.study('example')['cases']),1)
        with self.assertRaises(ValueError): self.reader.preview('example',self.identity)

    def test_explicit_source_preview_checks_hash_and_truncation(self):
        self.assertEqual(self.reader.preview('example',self.identity)['text'],self.source.decode())
        self.candidate.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'checksum'): self.reader.preview('example',self.identity)
        data=b'x'*65537; self.candidate.write_bytes(data)
        self.report['cases'][0]['source_sha256']=hashlib.sha256(data).hexdigest(); self.save()
        preview=self.reader.preview('example',self.identity)
        self.assertTrue(preview['truncated']); self.assertEqual(len(preview['text']),65536)

    def test_nonbenign_unknown_schema_duplicates_and_bad_shapes_are_excluded(self):
        original=json.loads(json.dumps(self.report))
        for patch in [{'benign':False},{'schema_version':True},{'schema_version':2},{'metrics':{}},
                      {'cases':self.report['cases']*2},{'design':{}}]:
            with self.subTest(patch=patch):
                self.report={**original,**patch}; self.save()
                self.assertEqual(self.reader.catalog()['studies'],[]); self.assertEqual(self.reader.catalog()['errors'],1)

    def test_symlinks_traversal_and_nonallowlisted_downloads_are_rejected(self):
        for identity in ['../example','EXAMPLE','example/../example']:
            with self.assertRaises(LookupError): self.reader.study(identity)
        self.candidate.unlink(); self.candidate.symlink_to(self.directory/'report.json')
        with self.assertRaises(ValueError): self.reader.preview('example',self.identity)
        for name in ['../report.json','candidates/'+self.identity+'.txt','missing']:
            with self.assertRaises(LookupError): self.reader.download('example',name)
        self.assertEqual(self.reader.download('example','report.json')[1],'report.json')

    def test_routes_require_authentication_and_do_not_serve_raw_directories(self):
        with patch('clanker_repellent.dashboard.app.JournalReader'):
            app=DashboardApp(self.root/'journal','token',experiments=self.root)
        def request(path,auth=True):
            captured={}
            env={'PATH_INFO':path,'QUERY_STRING':'','REQUEST_METHOD':'GET','wsgi.input':io.BytesIO()}
            if auth: env['HTTP_AUTHORIZATION']='Bearer token'
            body=b''.join(app(env,lambda status,headers:captured.update(status=status,headers=dict(headers))))
            return captured,body
        path='/api/evaluations/example/candidates/'+self.identity
        for route in ['/api/evaluations','/api/evaluations/example',path]:
            self.assertTrue(request(route,False)[0]['status'].startswith('401'))
            self.assertTrue(request(route)[0]['status'].startswith('200'))
        self.assertTrue(request('/evaluation/example/report.json')[0]['status'].startswith('404'))
        self.assertTrue(request('/research.js')[0]['status'].startswith('200'))
        self.assertEqual(request(path)[0]['headers']['Cache-Control'],'no-store')

    def test_recorded_artifact_hashes_are_checked_before_download(self):
        data=b'original protocol'; (self.directory/'protocol.json').write_bytes(data)
        self.report['provenance']['protocol_sha256']=hashlib.sha256(data).hexdigest(); self.save()
        self.assertEqual(self.reader.download('example','protocol.json')[0],data)
        (self.directory/'protocol.json').write_bytes(b'changed protocol')
        with self.assertRaisesRegex(ValueError,'checksum'): self.reader.download('example','protocol.json')


if __name__=='__main__': unittest.main()
