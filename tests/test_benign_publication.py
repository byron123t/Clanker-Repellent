"""Publication integrity checks using synthetic metadata, never model observations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec=importlib.util.spec_from_file_location('benign_publication',Path(__file__).resolve().parents[1]/'benchmarks/benign-v2/finalize_model_report.py')
publication=importlib.util.module_from_spec(spec); spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.protocol=b'{"benign":true,"synthetic":true}\n'
        self.sha=hashlib.sha256(self.protocol).hexdigest()
        self.verification={'benign':True,'reproduced':True,'exact_outcome_agreement':True,
                           'repeated_inference':False,'observations':2,'protocol_sha256':self.sha}
        self.report={'id':'synthetic-publication-test','benign':True,'state':'complete','stage':'development',
                     'counts':{'completed':2},'metrics':[{'verified':1}],'effects':[], 'groups':[], 'cases':[],
                     'methodology':[], 'provenance':{'protocol_sha256':self.sha,'offline_verification':self.verification}}
        self.save_report()
        (self.root/'REPORT.md').write_text('# Synthetic test\n\n## Provenance\n\n```json\n{}\n```\n\nEnd.\n')
        self.make_archive()

    def save_report(self): (self.root/'report.json').write_text(json.dumps(self.report))

    def make_archive(self,corrupt=False):
        manifest={'benign':True,'files':{'protocol.json':self.sha,'accepted.txt':hashlib.sha256(b'exact\r\nbytes\n').hexdigest()}}
        with zipfile.ZipFile(self.root/'reproduction.zip','w') as archive:
            archive.writestr('protocol.json',self.protocol)
            archive.writestr('accepted.txt',b'changed' if corrupt else b'exact\r\nbytes\n')
            archive.writestr('artifact-manifest.json',json.dumps(manifest))

    def finalize(self,**kwargs):
        with patch.object(publication.platform,'platform',return_value='fixture-platform'), patch.object(publication.subprocess,'check_output',return_value='fixture clang\n'), patch.object(publication,'version',return_value='1.0'):
            publication.finalize(self.root,**kwargs)

    def test_preserves_primary_data_and_exact_bytes_while_updating_all_checksums(self):
        clean={'benign':True,'verification':self.verification,'isolated_interpreter':True,
               'absent_packages':['openai','clanker_repellent']}
        proof=self.root/'clean.json'; proof.write_text(json.dumps(clean))
        self.finalize(clean_verification=proof)
        actual=json.loads((self.root/'report.json').read_text())
        for key in ['counts','metrics','effects','groups','cases']: self.assertEqual(actual[key],self.report[key])
        self.assertEqual(actual['provenance']['clean_environment_verification'],clean)
        sha=hashlib.sha256((self.root/'reproduction.zip').read_bytes()).hexdigest()
        self.assertEqual(actual['provenance']['reproduction_sha256'],sha)
        self.assertIn(sha,(self.root/'REPORT.md').read_text())
        with zipfile.ZipFile(self.root/'reproduction.zip') as archive:
            manifest=json.loads(archive.read('artifact-manifest.json'))
            for name,digest in manifest['files'].items(): self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)
            self.assertEqual(archive.read('accepted.txt'),b'exact\r\nbytes\n')
        self.finalize()
        repeated=json.loads((self.root/'report.json').read_text())
        self.assertEqual(sum(item['title']=='Clean dependency reproduction' for item in repeated['methodology']),1)

    def test_mismatched_verification_or_incomplete_study_cannot_be_published(self):
        original=(self.root/'reproduction.zip').read_bytes()
        for update in [{'state':'incomplete'}, {'provenance':{'protocol_sha256':self.sha,'offline_verification':{**self.verification,'observations':1}}}]:
            self.report.update(update); self.save_report()
            with self.assertRaises(ValueError): self.finalize()
            self.assertEqual((self.root/'reproduction.zip').read_bytes(),original)
            self.report['state']='complete'

    def test_corrupt_archive_fails_before_replacing_evidence(self):
        self.make_archive(corrupt=True)
        original=(self.root/'reproduction.zip').read_bytes()
        with self.assertRaisesRegex(ValueError,'Archive evidence changed'): self.finalize()
        self.assertEqual((self.root/'reproduction.zip').read_bytes(),original)

    def test_posthoc_addendum_preserves_original_results_and_requires_matching_proof(self):
        folder=self.root/'diagnostic'; folder.mkdir()
        digest=lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        (folder/'audit.py').write_text('# Synthetic test artifact\n')
        (folder/'case.py').write_text('# Authored synthetic source\n')
        (folder/'case.meta.json').write_text('{"benign":true}\n')
        design={'benign':True,'source_protocol_sha256':self.sha,'snapshot':{'audit.py':digest(folder/'audit.py')},
                'evidence':{'protocol.json':self.sha}}
        (folder/'protocol.json').write_text(json.dumps(design))
        result={'benign':True,'post_hoc':True,'state':'complete','source_protocol_sha256':self.sha,
            'repeated_inference':False,'primary_results_changed':False,'scope':'Synthetic test diagnostic.',
            'protocol_sha256':digest(folder/'protocol.json'),'groups':[{'model':'fixture','arm':'baseline',
                'terminal_rejections':1,'validation_passed':1,'verified':1,'newly_accepted_incorrect':0}],
            'cases':[{'benign':True,'source_path':'case.py','source_sha256':digest(folder/'case.py')}]}
        (folder/'report.json').write_text(json.dumps(result))
        proof={'benign':True,'reproduced':True,'exact_case_agreement':True,'cases':1,'source_protocol_sha256':self.sha,
               'repeated_inference':False,'report_sha256':digest(folder/'report.json')}
        (folder/'reproduction-check.json').write_text(json.dumps(proof))
        self.finalize(rejection_audit=folder)
        current=json.loads((self.root/'report.json').read_text())
        self.assertEqual(current['counts'],self.report['counts'])
        self.assertTrue(current['provenance']['posthoc_rejection_audit']['post_hoc'])
        with zipfile.ZipFile(self.root/'reproduction.zip') as archive:
            self.assertEqual(archive.read('publication/rejection-audit/case.py'),(folder/'case.py').read_bytes())
        self.finalize()
        self.assertIn('Synthetic test diagnostic.',(self.root/'REPORT.md').read_text())
        before=(self.root/'reproduction.zip').read_bytes()
        proof['report_sha256']='wrong'; (folder/'reproduction-check.json').write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError,'verification hashes'): self.finalize(rejection_audit=folder)
        self.assertEqual((self.root/'reproduction.zip').read_bytes(),before)


if __name__=='__main__': unittest.main()
