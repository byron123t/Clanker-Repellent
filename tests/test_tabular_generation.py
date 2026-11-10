import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from clanker_repellent.generate.source_generation import generate_source_run, select_languages, validate_snippet, validation_metadata
from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
from clanker_repellent.payload import catalog
from clanker_repellent.generate.contracts import check_contract


CONTROLS = {
    'yaml': 'title: "café"\nrecords:\n  - count: 2\n    enabled: false\n',
    'toml': 'title = "café"\n[record]\ncount = 2\nenabled = false\n',
    'xml': '<record><title>café &amp; tea</title><count>2</count></record>\n',
    'csv': 'title,count\n"café, tea",2\n"line\nnext",0\n',
    'ini': '[record]\ntitle=café\ncount=2\npercent=100%\n',
}


class TabularGenerationTests(unittest.TestCase):
    def validate(self, language, source):
        return validate_snippet(select_languages([language])[0], source, run_linters=False,
                                require_structure=True, structure_profile=FUNCTIONAL_PROFILE)

    def test_all_formats_generate_preserve_exact_bytes_and_catalog_round_trip(self):
        for language, source in CONTROLS.items():
            with self.subTest(language=language), tempfile.TemporaryDirectory() as folder:
                provider = Mock(spec=['complete'])
                provider.complete.return_value = {'response_text': '```'+language+'\n'+source+'```', 'finish_reason':'stop'}
                root = Path(folder)
                run = generate_source_run(provider=provider, model='test', payload='Benign reference records',
                    targets=select_languages([language]), output_dir=root/'generation', benign=True,
                    structure_profile=FUNCTIONAL_PROFILE, retries=0, run_linters=False)
                self.assertEqual(run['summary']['status'], 'passed', language)
                candidate = run['candidates'][0]['candidate']
                data = (root/'generation'/candidate['relative_path']).read_bytes()
                self.assertEqual(data, source.encode())
                self.assertEqual(hashlib.sha256(data).hexdigest(), candidate['sha256'])
                catalog.initialize(root/'catalog')
                catalog.import_run(root/'catalog', root/'generation', prefix='test', benign=True)
                self.assertEqual(catalog.read(root/'catalog', 'test-'+language)[1].encode(), data)

    def test_invalid_or_ambiguous_documents_fail_without_leaking_content(self):
        invalid = {
            'yaml': ['a: 1\na: 2\n', 'a: &value [1]\nb: *value', 'a: !!str 1\nb: 2',
                     'a: .nan\nb: 2', 'a: 2025-01-01\nb: 2', '1: value\nb: 2',
                     'a: 1\n---\nb: 2', 'a: '+ '['*40+'1'+']'*40+'\nb: 2', 'PRIVATE_INVALID'],
            'toml': ['a=1\na=2', 'a=nan\nb=2', 'a=2025-01-01\nb=2', 'PRIVATE_INVALID'],
            'xml': ['<!DOCTYPE r [<!ENTITY x "PRIVATE_INVALID">]><r><a>&x;</a><b>2</b></r>',
                    '<?reference PRIVATE_INVALID?><r><a>1</a><b>2</b></r>', '<r><a></r>', '<r/>', '<r>'*40+'</r>'*40,
                    '<root><wrapper><value>Only one populated field</value></wrapper></root>'],
            'csv': ['a,a\n1,2', 'a,b\n1', 'a,b\n"PRIVATE_INVALID', 'a,b\n,', 'a,b\nunquoted"quote,2'],
            'ini': ['[x]\na=1\na=2', '[DEFAULT]\na=1\n[x]\nb=2', '[x]\na', 'PRIVATE_INVALID'],
        }
        for language, cases in invalid.items():
            for source in cases:
                with self.subTest(language=language, source=source):
                    result = self.validate(language, source)
                    self.assertFalse(result['accepted'])
                    self.assertNotIn('PRIVATE_INVALID', json.dumps(validation_metadata(result)))

    def test_literal_default_text_is_not_ini_inheritance(self):
        self.assertTrue(self.validate('ini', '[section]\nlabel=[DEFAULT]\npercent=100%\n')['accepted'])
        self.assertFalse(self.validate('ini', '[DEFAULT]\n[section]\nx=1\ny=2\n')['accepted'])

    def test_new_document_contracts_check_arithmetic_and_drive_bounded_repair(self):
        controls={
            'yaml': ('quantity: 3\nunit_cents: 125\ntotal_cents: 375\n', ['/quantity','/unit_cents','/total_cents'], 3),
            'toml': ('quantity=3\nunit_cents=125\ntotal_cents=375\n', ['/quantity','/unit_cents','/total_cents'], 3),
            'ini': ('[invoice]\nquantity=3\nunit_cents=125\ntotal_cents=375\n', ['/invoice/quantity','/invoice/unit_cents','/invoice/total_cents'], '3'),
            'csv': ('quantity,unit_cents,total_cents\n3,125,375\n', ['/records/0/quantity','/records/0/unit_cents','/records/0/total_cents'], '3'),
            'xml': ('<invoice><quantity>3</quantity><unit_cents>125</unit_cents><total_cents>375</total_cents></invoice>\n', ['/children/0/text','/children/1/text','/children/2/text'], '3'),
        }
        for language,(source,paths,quantity) in controls.items():
            contract={'schema_version':1,'language':language,'document':{'shape':{'type':'object'},
                      'equals':[{'path':paths[0],'value':quantity}],
                      'equations':[{'left':paths[2],'expression':{'op':'mul','args':[{'path':paths[0]},{'path':paths[1]}]}}]}}
            with self.subTest(language=language), tempfile.TemporaryDirectory() as folder:
                bad=source.replace('375','376')
                self.assertTrue(check_contract(source,contract)['passed'])
                self.assertFalse(check_contract(bad,contract)['passed'])
                if language in {'ini','csv','xml'}:
                    self.assertFalse(check_contract(source.replace('375','0375'),contract)['passed'])
                provider=Mock(spec=['complete'])
                provider.complete.side_effect=[{'response_text':'```'+language+'\n'+s+'```','finish_reason':'stop'} for s in [bad,source]]
                run=generate_source_run(provider=provider,model='test',payload='Compute the invoice total',
                    targets=select_languages([language]),output_dir=Path(folder)/'generation',benign=True,
                    structure_profile=FUNCTIONAL_PROFILE,contract=contract,retries=1,run_linters=False)
                self.assertEqual(run['summary']['status'],'passed')
                self.assertEqual(len(run['candidates'][0]['attempts']),2)
                self.assertIn('contract_representation',provider.complete.call_args_list[0].kwargs['messages'][1]['content'])

    def test_xml_contracts_reject_external_declarations_before_constructing_tree(self):
        contract={'schema_version':1,'language':'xml','document':{'shape':{'type':'object'}}}
        self.assertFalse(check_contract('<!DOCTYPE r SYSTEM "file:///nonexistent"><r><a>1</a><b>2</b></r>',contract)['passed'])
        self.assertFalse(check_contract('<r><missing:a>1</missing:a><b>2</b></r>',contract)['passed'])


if __name__ == '__main__':
    unittest.main()
