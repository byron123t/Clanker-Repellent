"""Paired, inference-free pipeline audit of the frozen authored controls.

Each engine runs in its own process. Native grades are recomputed, not inferred
from syntax acceptance. This auxiliary audit never revises model-study records.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
if (Path(__file__).resolve().parent.parent / 'runner').is_dir():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'runner'))
from experiment import digest, save, verify


def engine_digest(root):
    files = {str(p.relative_to(root)): digest(p) for p in root.rglob('*.py')
             if '__pycache__' not in p.parts}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def stable(value):
    if isinstance(value, dict):
        return {key: stable(child) for key, child in value.items() if key != 'diagnostic'}
    if isinstance(value, list):
        return [stable(child) for child in value]
    return value


def worker(root, engine, output):
    verify(root)
    sys.path.insert(0, str(engine))
    sys.path.insert(0, str(root / 'runner'))
    from clanker_repellent.generate.source_generation import generate_source_run, select_languages
    from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
    from grade import grade
    tasks = json.loads((root / 'tasks.json').read_text())['tasks']
    corpus = json.loads((root / 'oracles.json').read_text())
    if corpus.get('benign') is not True:
        raise ValueError('Only authored benign controls are supported')
    output.mkdir(parents=True, exist_ok=False)
    outcomes = []
    for task in tasks:
        oracle = corpus['oracles'][task['id']]
        source = oracle['control']

        class AuthoredProvider:
            def complete(self, **_kwargs):
                return {'response_text': '```' + task['language'] + '\n' + source + '```',
                        'finish_reason': 'stop', 'resolved_model': 'authored-control'}

        directory = output / task['id']
        run = generate_source_run(provider=AuthoredProvider(), model='authored-control',
            payload=task['prompt'], targets=select_languages([task['language']]),
            output_dir=directory, benign=True, structure_profile=FUNCTIONAL_PROFILE,
            retries=0, run_linters=False, validator_timeout_seconds=90)
        if run['settings']['mode'] != 'benign':
            raise ValueError('Expected benign generation provenance')
        candidate = run['candidates'][0]
        result = None
        unchanged = False
        source_hash = None
        if candidate['accepted']:
            path = directory / candidate['candidate']['relative_path']
            path.resolve().relative_to(directory.resolve())
            if path.is_symlink() or digest(path) != candidate['candidate']['sha256']:
                raise ValueError('Control source checksum differs')
            content = path.read_bytes().decode()
            source_hash = digest(path)
            unchanged = content == source
            result = grade(task, oracle, content)
        outcomes.append({'task': task['id'], 'language': task['language'],
            'accepted': candidate['accepted'], 'status': candidate['status'],
            'source_unchanged': unchanged, 'source_sha256': source_hash,
            'control_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'strict_pass': bool(candidate['accepted'] and result and result['passed']),
            'grade': stable(result)})
    save(output / 'report.json', {'benign': True, 'inference_requests': 0,
        'engine_sha256': engine_digest(engine), 'outcomes': outcomes})


def audit(root, updated_engine, output, expected=None):
    protocol = verify(root)
    if output.exists():
        raise ValueError('Choose a new controls-audit directory')
    output.mkdir(parents=True)
    arms = {}
    for name, engine in [('before', root / 'engine'), ('updated', updated_engine)]:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), str(root),
            str(engine), str(output / name), '--worker'], check=True)
        arms[name] = json.loads((output / name / 'report.json').read_text())
        if [row['task'] for row in arms[name]['outcomes']] != protocol['task_ids']:
            raise ValueError('Control grid differs from the frozen protocol')
    report = {'benign': True, 'kind': 'paired_full_pipeline_control_audit',
        'protocol_sha256': digest(root / 'protocol.json'), 'inference_requests': 0,
        'units': len(protocol['task_ids']), 'arms': arms,
        'summary': {name: {'accepted': sum(row['accepted'] for row in arm['outcomes']),
            'verified': sum(row['strict_pass'] for row in arm['outcomes']),
            'source_unchanged': sum(row['source_unchanged'] for row in arm['outcomes']),
            'native_checks': sum((row['grade'] or {}).get('cases', 0) for row in arm['outcomes'])}
            for name, arm in arms.items()},
        'method': 'Same 63 authored sources, original and updated pipelines; every accepted source independently regraded. No inference, retries, or model-study outcome changes.'}
    if expected:
        original = json.loads(expected.read_text())
        if stable(report) != stable(original):
            raise ValueError('Paired control audit did not reproduce exactly')
    save(output / 'report.json', report)
    print(json.dumps({'kind': report['kind'], 'units': report['units'],
        'summary': report['summary'], 'matched_reference': bool(expected)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('updated_engine', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.root.resolve(), args.updated_engine.resolve(), args.output.resolve())
    else:
        audit(args.root.resolve(), args.updated_engine.resolve(), args.output.resolve(), args.compare)
