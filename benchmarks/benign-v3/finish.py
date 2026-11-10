"""Complete the declared integration, publication and clean offline reproduction.

This helper never starts or retries inference. It may wait for the separate
registered model runner; an interrupted runner requires explicit investigation.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from evidence import build_logs
from experiment import digest, save, verify

HERE = Path(__file__).resolve().parent


def execute(arguments):
    print(json.dumps({'step': [str(value) for value in arguments]}), flush=True)
    subprocess.run([str(value) for value in arguments], check=True)


def examples(output, report):
    text = ('# Benign breadth examples\n\n'
        'Every linked file is an unchanged, checksum-verified accepted artifact from an explicitly benign run. '
        '“Verified” means it passed the frozen task checks; it is not an all-input correctness or code-quality guarantee. '
        '“Review issue” means generic CLI acceptance succeeded but the independent task grade failed.\n\n'
        'The primary study used the original frozen extraction behavior. Corrected extraction examples are separate '
        'in `supplement/extraction-audit/sources/` inside the reproduction archive.\n\n'
        '| Format | Model | Task | Independent result | Source SHA-256 |\n| --- | --- | --- | --- | --- |\n')
    for case in sorted(report['cases'], key=lambda row: (row['language'], row['task'], row['model'])):
        if not case['source_sha256']:
            continue
        path = output / 'candidates' / (case['id'] + '.txt')
        if digest(path) != case['source_sha256']:
            raise ValueError('Example differs from its recorded source')
        result = 'Verified' if case['strict_pass'] else 'Review issue'
        text += f"| {case['language']} | {case['model']} | [{case['task']}](candidates/{path.name}) | {result} | `{case['source_sha256']}` |\n"
    (output / 'EXAMPLES.md').write_text(text)


def finish(root, output, clean_python, wait):
    protocol = verify(root)
    while True:
        status = json.loads((root / 'status.json').read_text())
        if status['state'] == 'complete' and status['completed'] == protocol['planned']:
            break
        if not wait or status.get('interruptions') or status['state'] == 'interrupted':
            raise ValueError('Model grid is incomplete or interrupted; no outcomes were retried')
        time.sleep(30)
    workspace = root.parent
    execute([sys.executable, root / 'runner/integration.py', 'integrate', workspace, '--study', root])
    build_logs(root, workspace)
    execute([sys.executable, root / 'runner/experiment.py', 'regrade', root])
    audit = root / 'supplement/extraction-audit'
    if not (audit / 'report.json').exists():
        execute([sys.executable, HERE / 'audit_extraction.py', root, audit])
    packages = subprocess.check_output([str(clean_python), '-m', 'pip', 'freeze'], text=True)
    version = subprocess.check_output([str(clean_python), '-c', 'import sys; print(sys.version)'], text=True).strip()
    save(root / 'supplement/clean-environment.json', {'benign': True, 'python': version,
        'packages': packages.splitlines(), 'scope': 'Separate Python environment on the same host and native toolchains.'})
    execute([sys.executable, HERE / 'publish.py', root, output])
    report = json.loads((output / 'report.json').read_text())
    archive_hash = report['provenance']['reproduction_sha256']
    # Reproduction destinations are disposable and always new; no old proof is trusted.
    identity = archive_hash[:12] + '-' + str(time.time_ns())
    clean_root = workspace / ('reproduced-' + identity)
    execute([clean_python, HERE / 'reproduce.py', output / 'reproduction.zip', clean_root,
        '--sha256', archive_hash, '--python', clean_python])
    clean_audit = workspace / ('extraction-reproduced-' + identity)
    execute([clean_python, clean_root / 'publication/audit_extraction.py', clean_root, clean_audit,
        '--compare', clean_root / 'supplement/extraction-audit/report.json'])
    clean_controls = workspace / ('controls-reproduced-' + identity)
    execute([clean_python, clean_root / 'publication/audit_controls.py', clean_root,
        clean_root / 'supplement/updated-engine', clean_controls,
        '--compare', clean_root / 'supplement/control-audit/report.json'])
    proof = json.loads((clean_root / 'reproduction-check.json').read_text())
    if proof['passed'] is not True or proof['protocol_sha256'] != digest(root / 'protocol.json'):
        raise ValueError('Clean reproduction failed')
    verification = {'benign': True, 'passed': True, 'archive_sha256': archive_hash,
        'protocol_sha256': proof['protocol_sha256'], 'accepted_candidates': proof['accepted_candidates'],
        'primary_grade_proof_sha256': digest(clean_root / 'reproduction-check.json'),
        'extraction_audit_matched': True, 'control_audit_matched': True,
        'inference_requests': 0, 'python': version, 'packages': packages.splitlines(),
        'scope': 'Fresh checksum-verified archive extraction, separate Python environment, same host and native toolchains.',
        'created_at': datetime.now(timezone.utc).isoformat()}
    save(output / 'reproduction-verification.json', verification)
    report['provenance']['clean_reproduction'] = verification
    report['methodology'].append({'title': 'Clean archive reproduction',
        'body': f"The published archive was extracted into a fresh directory only after its inventory and every member hash passed. All {proof['accepted_candidates']} accepted primary grades, the paired source-extraction audit, and the 126 authored pipeline evaluations reproduced exactly in a separate Python environment, using the same host/native toolchains and zero inference requests. This is local reproducibility, not replication by an independent team."})
    report['updated_at'] = datetime.now(timezone.utc).isoformat()
    save(output / 'report.json', report)
    with (output / 'REPORT.md').open('a') as stream:
        stream.write('\n\n## Clean archive reproduction\n\n' + report['methodology'][-1]['body']
            + '\n\nPublished archive SHA-256: `' + archive_hash + '`\n')
    examples(output, report)
    execute([sys.executable, HERE / 'plot.py', output])
    print(json.dumps({'state': 'published-and-reproduced', 'directory': str(output),
        'counts': report['counts'], 'archive_sha256': archive_hash}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--clean-python', required=True, type=Path)
    parser.add_argument('--wait', action='store_true')
    args = parser.parse_args()
    finish(args.root.resolve(), args.output.resolve(), args.clean_python.absolute(), args.wait)
