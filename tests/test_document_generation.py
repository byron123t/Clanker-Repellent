import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from clanker_repellent.generate.document_formats import document_metrics, normalize_http, strict_json
from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
from clanker_repellent.generate.source_generation import build_generation_messages, generate_source_run, select_languages, validate_snippet, validation_metadata
from clanker_repellent.payload.carrier_deploy import load_accepted_carriers
from clanker_repellent.payload import catalog


BINARY = {"schema_version": 1, "format": "ELF", "architecture": "x86_64",
          "sections": [{"name": ".text", "kind": "code"}, {"name": ".rodata", "kind": "data"}],
          "symbols": [{"name": "in_range", "kind": "function", "section": ".text"},
                      {"name": "description", "kind": "object", "section": ".rodata"}],
          "strings": ["Inclusive integer range helper"]}
LLVM = 'define i1 @in_range(i32 %value, i32 %lower, i32 %upper) {\nentry:\n  %lo = icmp sge i32 %value, %lower\n  %hi = icmp sle i32 %value, %upper\n  %result = and i1 %lo, %hi\n  ret i1 %result\n}\n'
HTTP = 'HTTP/1.1 200 OK\nContent-Type: application/json\n\n{"name":"café", "count":2}\n'


class DocumentGenerationTests(unittest.TestCase):
    def validate(self, language, source, **kwargs):
        return validate_snippet(select_languages([language])[0], source, run_linters=False,
                                require_structure=True, structure_profile=FUNCTIONAL_PROFILE, **kwargs)

    def test_json_requires_populated_object_without_duplicate_keys_or_nonfinite_numbers(self):
        self.assertTrue(self.validate('json', '{"enabled":false,"count":0}')['accepted'])
        for source in ['[]', '"plain prose"', '{}', '{"a":null,"b":[]}', '{"a":1,"a":2}',
                       '{"a":1,"b":{"c":1,"c":2}}', '{"a":NaN,"b":1}', '{"a":1e400,"b":1}',
                       '{"a":"\\ud800","b":1}', '{"a":1,"b":2} trailing']:
            with self.subTest(source=source):
                self.assertFalse(self.validate('json', source)['accepted'])

    def test_json_diagnostics_do_not_expose_values(self):
        report=self.validate('json', '{"PRIVATE_VALUE":INVALID_TOKEN}')
        self.assertNotIn('PRIVATE_VALUE', json.dumps(validation_metadata(report)))
        self.assertNotIn('INVALID_TOKEN', report['checks'][0]['_stderr'])

    def test_http_framing_counts_utf8_bytes_and_preserves_json_escapes(self):
        source = HTTP.replace('"count":2', '"path":"C:\\\\notes\\nnext"')
        framed = normalize_http(source)
        self.assertTrue(self.validate('http', framed)['accepted'])
        header, body = framed.split('\r\n\r\n')
        self.assertIn('Content-Length: ' + str(len(body.encode('utf-8'))), header)
        self.assertEqual(strict_json(body)['path'], 'C:\\notes\nnext')
        self.assertEqual(normalize_http(framed), framed)
        self.assertFalse(self.validate('http', framed.replace('Content-Length: ', 'Content-Length: 9'))['accepted'])
        multiline = HTTP.replace('{"name":"café", "count":2}', '{\r\n"name":"café",\r\n"count":2\r\n}')
        self.assertIn('{\r\n"name"', normalize_http(multiline))

    def test_http_rejects_ambiguous_messages_encodings_and_credentials(self):
        for source in [HTTP.replace('200 OK','204 No Content'), HTTP + 'HTTP/1.1 200 OK\n\n{}',
                       HTTP.replace('Content-Type:', ' Content-Type:'),
                       HTTP.replace('\n\n', '\nContent-Length: 3\ncontent-length: 4\n\n'),
                       HTTP.replace('\n\n', '\nTransfer-Encoding: chunked\n\n'),
                       HTTP.replace('\n\n', '\nSet-Cookie: session=example\n\n')]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                normalize_http(source)

    def test_binary_metadata_covers_native_and_vm_formats(self):
        for family, arch in [('ELF','x86_64'),('PE','aarch64'),('Mach-O','x86_64'),('JVM','jvm'),('CLR','cil'),('Wasm','wasm32')]:
            value=dict(BINARY, format=family, architecture=arch)
            with self.subTest(format=family):
                self.assertTrue(self.validate('binary-info', json.dumps(value))['accepted'])

    def test_binary_rejects_inconsistent_architectures_references_duplicates_and_raw_data(self):
        variants=[]
        value=copy.deepcopy(BINARY); value['architecture']='jvm'; variants.append(value)
        value=copy.deepcopy(BINARY); value['symbols'][0]['section']='absent'; variants.append(value)
        value=copy.deepcopy(BINARY); value['symbols'][0]['section']='.rodata'; variants.append(value)
        value=copy.deepcopy(BINARY); value['sections'][1]['name']='.text'; variants.append(value)
        value=copy.deepcopy(BINARY); value['symbols'][1]['name']='in_range'; variants.append(value)
        value=copy.deepcopy(BINARY); value['machine_code']='0000'; variants.append(value)
        for value in variants:
            self.assertFalse(self.validate('binary-info', json.dumps(value))['accepted'])

    def test_document_prompts_do_not_request_functions(self):
        for language in ['json','http','binary-info']:
            prompt=build_generation_messages(select_languages([language])[0], 'Ordinary documentation', benign=True,
                                             structure_profile=FUNCTIONAL_PROFILE)[0]['content']
            self.assertNotIn('named function or method', prompt)
            self.assertIn('document fixture', prompt)

    def test_generation_formats_http_and_keeps_metadata_only(self):
        for language,source in [('http',HTTP),('json','{"request":"example","path":"C:\\\\notes"}'),('binary-info',json.dumps(BINARY)),('llvm',LLVM)]:
            if language=='llvm' and not shutil.which('clang'):
                continue
            with self.subTest(language=language), tempfile.TemporaryDirectory() as directory:
                provider=mock.Mock(spec=['complete'])
                provider.complete.return_value={'response_text':'```'+language+'\n'+source+'\n```','finish_reason':'stop'}
                output=Path(directory)/'run'
                run=generate_source_run(provider=provider, model='fixture', payload='Ordinary documentation',
                                        targets=select_languages([language]), output_dir=output, benign=True,
                                        structure_profile=FUNCTIONAL_PROFILE, retries=0)
                self.assertEqual(run['summary']['status'],'passed')
                record=run['candidates'][0]
                content=(output/record['candidate']['relative_path']).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(),record['candidate']['sha256'])
                self.assertNotIn('café',json.dumps(run))
                loaded=load_accepted_carriers(output)
                self.assertEqual(loaded[0].source.encode('utf-8'),content)
                store=Path(directory)/'catalog'
                catalog.initialize(store)
                catalog.import_run(store,output,prefix='control',benign=True)
                _metadata, restored=catalog.read(store,'control-'+language)
                self.assertEqual(restored.encode('utf-8'),content)
                if language=='http':
                    self.assertIn(b'\r\n\r\n',content)
                    self.assertTrue(record['attempts'][0]['formatting']['changed'])

    @unittest.skipUnless(shutil.which('clang'),'Clang required')
    def test_llvm_is_compiled_and_checks_input_dependence(self):
        self.assertTrue(self.validate('llvm',LLVM)['accepted'])
        self.assertFalse(self.validate('llvm',LLVM.replace('ret i1 %result','ret i1 false'))['accepted'])
        self.assertFalse(self.validate('llvm',LLVM.replace('and i1 %lo, %hi','and i32 %lo, %hi'))['accepted'])
        self.assertFalse(self.validate('llvm',LLVM.replace('and i1 %lo, %hi','and i1 %lo, %never_defined'))['accepted'])
        self.assertFalse(self.validate('llvm',LLVM.replace('icmp sge','call i1 @other'))['accepted'])
        self.assertFalse(self.validate('llvm',LLVM.replace('@in_range','@main'))['accepted'])

    def test_llvm_missing_compiler_does_not_pass_by_default(self):
        with mock.patch('clanker_repellent.generate.source_generation.shutil.which',return_value=None):
            self.assertFalse(self.validate('llvm',LLVM)['accepted'])

    def test_truncation_is_counted_without_persisting_partial_content_and_retry_can_recover(self):
        provider=mock.Mock(spec=['complete'])
        provider.complete.side_effect=[{'response_text':'PRIVATE_TRUNCATED_CONTENT','finish_reason':'length'},
                                       {'response_text':'```json\n{"count":2,"enabled":true}\n```','finish_reason':'stop'}]
        with tempfile.TemporaryDirectory() as directory:
            run=generate_source_run(provider=provider,model='fixture',payload='Ordinary example',
                                    targets=select_languages(['json']),output_dir=Path(directory)/'run',
                                    benign=True,retries=1,structure_profile=FUNCTIONAL_PROFILE)
            self.assertEqual(run['summary']['status'],'passed')
            self.assertEqual(run['attempt_status_counts'],{'token_limit':1,'passed':1})
            self.assertNotIn('PRIVATE_TRUNCATED_CONTENT',json.dumps(run))

    def test_switching_models_requires_a_fresh_output_directory(self):
        provider=mock.Mock(spec=['complete'])
        provider.complete.return_value={'response_text':'incomplete','finish_reason':'length'}
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'run'
            arguments=dict(provider=provider,payload='Ordinary example',targets=select_languages(['json']),
                           output_dir=output,benign=True,retries=0)
            generate_source_run(model='first',**arguments)
            before=(output/'manifest.json').read_bytes()
            provider.reset_mock()
            with self.assertRaisesRegex(ValueError,'different model'):
                generate_source_run(model='second',**arguments)
            provider.complete.assert_not_called()
            self.assertEqual((output/'manifest.json').read_bytes(),before)


if __name__=='__main__':
    unittest.main()
