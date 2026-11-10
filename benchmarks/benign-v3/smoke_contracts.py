"""Small live smoke check of the five new public invoice contracts.

This is an auxiliary example check, not a controlled model comparison. Accepted
results receive an exact independent parse/value comparison after generation.
"""
import argparse
import configparser
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from experiment import digest, save

REPO = Path(__file__).resolve().parents[2]
FORMATS = ['yaml', 'toml', 'xml', 'csv', 'ini']


def independent(language, source):
    rows = [{'sku': 'A', 'quantity': 3, 'unit_cents': 125, 'total_cents': 375},
            {'sku': 'B', 'quantity': 2, 'unit_cents': 240, 'total_cents': 480}]
    strings = [{key: str(value) for key, value in row.items()} for row in rows]
    if language in ['yaml', 'toml']:
        if language == 'yaml':
            import yaml
            actual = yaml.safe_load(source)
        else:
            try: import tomllib
            except ImportError: import tomli as tomllib
            actual = tomllib.loads(source)
        return json.dumps(actual, sort_keys=True) == json.dumps({'schema_version': 1, 'records': rows}, sort_keys=True)
    if language == 'csv':
        reader = csv.DictReader(io.StringIO(source, newline=''))
        actual = list(reader)
        return reader.fieldnames == list(strings[0]) and actual == strings
    if language == 'ini':
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read_string(source)
        return parser.sections() == ['record0', 'record1'] and [dict(parser.items(section)) for section in parser.sections()] == strings
    tree = ET.fromstring(source)
    return (tree.tag == 'invoice' and not tree.attrib and len(tree) == 2
            and all(row.tag == 'record' and not row.attrib and [cell.tag for cell in row] == list(want)
                and [cell.text or '' for cell in row] == list(want.values())
                and all(not cell.attrib and not list(cell) for cell in row)
                for row, want in zip(tree, strings)))


def run(output, endpoint):
    if output.exists(): raise ValueError('Use a fresh smoke-check directory')
    sys.path.insert(0, str(REPO / 'src'))
    from clanker_repellent.generate.contracts import load_contract
    from clanker_repellent.generate.source_generation import generate_source_run, select_languages
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    from clanker_repellent.inference.provider import OpenAICompatibleProvider
    output.mkdir(parents=True)
    inputs = output / 'inputs'
    inputs.mkdir()
    for name in ['invoice.txt'] + ['invoice.' + language + '.contract.json' for language in FORMATS]:
        shutil.copyfile(REPO / 'examples/benign-contracts' / name, inputs / name)
    client = OpenAICompatibleProvider('local', endpoint, timeout=900)
    models = client.list_models()
    if len(models) != 1: raise ValueError('Expected one unambiguous local model')
    model = models[0]
    outcomes = []
    for language in FORMATS:
        directory = output / language
        class Provider:
            number = 0
            def complete(self, **kwargs):
                self.number += 1
                started = time.monotonic()
                response = client.complete(**kwargs)
                if response.get('resolved_model') != model: raise ValueError('Model identity changed')
                save(directory / 'traces' / ('%02d.json' % self.number), {'benign': True,
                    'request': kwargs, 'request_sha256': hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest(),
                    'response': response, 'seconds': time.monotonic() - started})
                return response
        manifest = generate_source_run(provider=Provider(), model=model, payload=(inputs / 'invoice.txt').read_text(),
            targets=select_languages([language]), output_dir=directory / 'generation',
            benign=True, contract=load_contract(inputs / ('invoice.' + language + '.contract.json')),
            structure_profile=FUNCTIONAL_PROFILE, retries=1, max_tokens=8192, temperature=.2, top_p=.8,
            no_thinking=True, seed=20261110, run_linters=False, validator_timeout_seconds=90)
        if manifest['settings']['mode'] != 'benign': raise ValueError('Only benign runs may be inspected')
        candidate = manifest['candidates'][0]
        source_hash = None
        passed = False
        if candidate['accepted']:
            path = directory / 'generation' / candidate['candidate']['relative_path']
            if digest(path) != candidate['candidate']['sha256']: raise ValueError('Source checksum differs')
            source_hash = digest(path)
            passed = independent(language, path.read_text())
        row = {'format': language, 'accepted': candidate['accepted'], 'independent_pass': passed,
            'attempts': len(candidate['attempts']), 'status': candidate['status'], 'source_sha256': source_hash}
        outcomes.append(row)
        save(output / 'report.json', {'benign': True, 'kind': 'auxiliary_live_contract_smoke', 'model': model,
            'planned': 5, 'completed': len(outcomes), 'outcomes': outcomes,
            'scope': 'One small invoice example per format, public task contracts and exact independent parsing. No causal improvement or general model comparison.'})
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--endpoint', required=True)
    args = parser.parse_args()
    run(args.output.resolve(), args.endpoint)
