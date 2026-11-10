"""Keep post hoc diagnostics distinct from the frozen primary observations."""
import hashlib
import json
from pathlib import Path
import shutil
from experiment import digest
from audit_controls import engine_digest


def retention_evidence(root, workspace):
    from integration import tracked
    report = json.loads((workspace / 'report.json').read_text())
    if report.get('benign') is not True or report['completed'] != report['planned'] or report['planned'] != 3:
        raise ValueError('Only the completed benign retention check may be collected')
    target = root / 'supplement/retention'
    target.mkdir(parents=True, exist_ok=False)
    if digest(workspace / 'note.txt') != report['note_sha256']:
        raise ValueError('Authored retention note changed')
    shutil.copyfile(workspace / 'note.txt', target / 'note.txt')
    shutil.copyfile(workspace / 'report.json', target / 'report.json')
    shutil.copyfile(workspace / 'linkage-diagnostic.json', target / 'linkage-diagnostic.json')
    for row in report['outcomes']:
        identity = row['repository']
        if tracked(workspace / 'repos' / identity) != row['inventory']:
            raise ValueError('Restored tracked sources differ')
        if digest(workspace / 'repos' / identity / '.repel-evaluation/program') != row['artifact_before_sha256']:
            raise ValueError('Restored artifact differs from its original bytes')
        destination = target / identity
        destination.mkdir()
        shutil.copyfile(workspace / identity / 'deployment.json', destination / 'deployment.json')
        baseline = next(item for item in report['baseline_builds'] if item['id'] == identity)
        for step in baseline['steps'] + row['build_steps']:
            path = workspace / 'builds' / identity / step['log']
            if path.name != step['log'] or path.is_symlink() or digest(path) != step['log_sha256']:
                raise ValueError('Retention build log differs')
            shutil.copyfile(path, destination / step['log'])


def build_logs(root, workspace):
    report = json.loads((workspace / 'builds/report.json').read_text())
    if report.get('benign') is not True:
        raise ValueError('Only the benign pinned builds may be archived')
    for repository in report['repositories']:
        for step in repository['steps']:
            if Path(step['log']).name != step['log']:
                raise ValueError('Build log name must be a basename')
            source = workspace / 'builds' / repository['id'] / step['log']
            if source.is_symlink() or digest(source) != step['log_sha256']:
                raise ValueError('Build log differs from the baseline evidence')
            target = root / 'integration/logs' / repository['id'] / step['log']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def diagnostics(root, protocol):
    directory = root / 'supplement'
    controls = json.loads((directory / 'control-audit/report.json').read_text())
    extraction = json.loads((directory / 'extraction-audit/report.json').read_text())
    for report in [controls, extraction]:
        if (report.get('benign') is not True or report['protocol_sha256'] != digest(root / 'protocol.json')
                or report.get('inference_requests') != 0):
            raise ValueError('Auxiliary evidence belongs to another protocol or run mode')
    if controls['units'] != len(protocol['task_ids']):
        raise ValueError('Authored control audit is incomplete')
    oracles = json.loads((root / 'oracles.json').read_text())['oracles']
    for arm, engine in [('before', root / 'engine'), ('updated', directory / 'updated-engine')]:
        rows = controls['arms'][arm]['outcomes']
        if ([row['task'] for row in rows] != protocol['task_ids']
                or controls['arms'][arm]['engine_sha256'] != engine_digest(engine)):
            raise ValueError('Control audit source grid or engine differs')
        for row in rows:
            if row['control_sha256'] != hashlib.sha256(oracles[row['task']]['control'].encode()).hexdigest():
                raise ValueError('Control audit changed an authored input')
            if arm == 'updated' and not (row['accepted'] and row['source_unchanged'] and row['strict_pass']):
                raise ValueError('The updated pipeline has a failing authored control')
        expected = {'accepted': sum(row['accepted'] for row in rows),
            'verified': sum(row['strict_pass'] for row in rows),
            'source_unchanged': sum(row['source_unchanged'] for row in rows),
            'native_checks': sum((row['grade'] or {}).get('cases', 0) for row in rows)}
        if controls['summary'][arm] != expected:
            raise ValueError('Authored control summary disagrees with its observations')
    if (extraction['complete_grid'] is not True or extraction['screened_completed'] != protocol['planned']
            or extraction['planned_candidates'] != protocol['planned']
            or extraction['screened_completed'] != sum(extraction[key] for key in [
                'excluded_token_limit', 'excluded_unextractable', 'unchanged_extraction', 'changed_first_responses'])
            or extraction['changed_first_responses'] != len(extraction['cases'])):
        raise ValueError('Extraction audit does not account for the complete grid')
    seen = set()
    for case in extraction['cases']:
        key = (case['model'], case['task'])
        if key in seen or key[0] not in protocol['models'] or key[1] not in protocol['task_ids']:
            raise ValueError('Extraction audit has a duplicate or unregistered case')
        seen.add(key)
        for outcome in case['arms'].values():
            path = directory / 'extraction-audit' / outcome['source']
            path.resolve().relative_to((directory / 'extraction-audit').resolve())
            if path.is_symlink() or digest(path) != outcome['source_sha256']:
                raise ValueError('Extraction audit source differs')
    for arm in ['before', 'preserve_escapes']:
        expected = {key: sum(case['arms'][arm][field] for case in extraction['cases'])
            for key, field in [('accepted', 'accepted'), ('verified', 'strict_pass')]}
        if extraction[arm] != expected:
            raise ValueError('Extraction summary disagrees with its observations')
    return {'controls': {'units': controls['units'], 'summary': controls['summary'],
                'engines': {key: value['engine_sha256'] for key, value in controls['arms'].items()},
                'report_sha256': digest(directory / 'control-audit/report.json')},
            'extraction': extraction,
            'extraction_report_sha256': digest(directory / 'extraction-audit/report.json')}


def enrich(report, root, protocol):
    evidence = diagnostics(root, protocol)
    report['diagnostics'] = evidence
    controls = evidence['controls']
    audit = evidence['extraction']
    report['findings'] += [
        f"Post hoc authored controls: {controls['summary']['before']['verified']}/{controls['units']} verified through the original pipeline; {controls['summary']['updated']['verified']}/{controls['units']} through the updated pipeline, with exact source preservation.",
        f"Separate extraction audit: {audit['changed_first_responses']} changed complete first responses; {audit['before']['verified']} verified before versus {audit['preserve_escapes']['verified']} with escapes preserved. No inference or revised retry trajectory."]
    report['methodology'] += [
        {'title': 'Source preservation correction · post hoc',
         'body': 'The frozen primary engine could turn literal source escape sequences into control characters. Its completed outcomes remain unchanged. The updated CLI preserves literal source by default. A paired audit screens all first responses, excludes token-limit or unextractable responses, and revalidates only responses whose extracted source differs. Frozen validators and graders are identical across the two arms. Both accepted and failing audited sources are archived.'},
        {'title': 'Full-pipeline authored controls · post hoc',
         'body': f"All {controls['units']} identical authored controls were also passed through original and updated generation pipelines using a fixed local response provider, with zero inference requests. Every accepted source was independently regraded; the updated pipeline passed {controls['summary']['updated']['native_checks']:,} native behavior assertions and all document/metadata checks. This supplements the original pre-freeze direct-validator controls, which had not exercised extraction."}]
    report['limitations'] += [
        'Primary outcomes describe the frozen CLI, including its escape-handling defect. They are not estimates of the updated CLI or of model quality independent of extraction.',
        'The extraction audit is a post hoc mechanism check on changed complete first responses. It does not estimate full generation success after different retry feedback. Authored controls do not estimate naturally occurring model errors.']
    directory = root / 'supplement/retention'
    if (directory / 'report.json').exists():
        retention = json.loads((directory / 'report.json').read_text())
        linkage = json.loads((directory / 'linkage-diagnostic.json').read_text())
        if retention.get('benign') is not True or linkage.get('benign') is not True or retention['completed'] != 3:
            raise ValueError('Invalid auxiliary retention evidence')
        if digest(directory / 'note.txt') != retention['note_sha256']:
            raise ValueError('Auxiliary retention note differs')
        retention['linkage_diagnostic'] = linkage
        report['retention'] = retention
        recovered = sum(row['retention_verified'] for row in retention['outcomes'])
        restored = sum(row['tracked_sources_restored'] and row['artifact_restored_exactly'] for row in retention['outcomes'])
        report['findings'].append(f"Separate authored placement check: {recovered}/3 stripped executables retained the note; {restored}/3 source trees and snapshotted executables restored exactly. zlib's note was recovered from its linked shared library in a separate diagnostic.")
        report['methodology'].append({'title': 'Placement and restoration · auxiliary authored check',
            'body': 'A known benign note was placed in six explicit source files across separate pinned cJSON, zlib and curl clones, with real records in the central journal. Release rebuilds and declared upstream tests passed. One executable per project was symbol-stripped, checked for note recovery, smoke-tested, and restored exactly with every tracked source file. cJSON and curl retained the note in their executable; minigzip links a shared zlib library, where a separate local-symbol-stripping check recovered it. The executable-only failure is retained. This is an authored lifecycle check, separate from model generation and from the clean primary/audit reproduction.'})
        report['limitations'].append('The auxiliary placement check uses one authored note and six explicitly chosen source files. It does not measure whole-repository coverage or preservation in a decompiler’s reconstructed source. Executable-only verification can miss notes located in shipped shared libraries.')


def markdown(report):
    evidence = report['diagnostics']
    controls = evidence['controls']
    audit = evidence['extraction']
    text = '\n\n## Post hoc source-preservation audits\n\n'
    text += '| Authored pipeline | Accepted | Verified | Source preserved |\n| --- | ---: | ---: | ---: |\n'
    for arm, row in controls['summary'].items():
        text += f"| {arm} | {row['accepted']}/{controls['units']} | {row['verified']}/{controls['units']} | {row['source_unchanged']}/{controls['units']} |\n"
    text += (f"\nExtraction audit: {audit['screened_completed']} first responses screened; "
        f"{audit['excluded_token_limit']} excluded for token limits, {audit['excluded_unextractable']} unextractable, "
        f"{audit['unchanged_extraction']} unchanged, and {audit['changed_first_responses']} changed. "
        'Only the changed complete responses enter the following paired table.\n\n')
    text += '| Model | Task | Before: accepted / verified | Preserved: accepted / verified |\n| --- | --- | --- | --- |\n'
    for case in audit['cases']:
        a, b = case['arms']['before'], case['arms']['preserve_escapes']
        text += f"| {case['model']} | {case['task']} | {a['accepted']} / {a['strict_pass']} | {b['accepted']} / {b['strict_pass']} |\n"
    text += '\nNo model requests or completed primary outcomes were changed. Sources and reproduction scripts are in the archive.\n'
    if report.get('retention'):
        text += '\n## Auxiliary placement and exact restoration\n\n| Project | Source files | Stripped executable note | Tracked source restored | Executable bytes restored |\n| --- | ---: | --- | --- | --- |\n'
        for row in report['retention']['outcomes']:
            text += f"| {row['repository']} | {len(row['selected_files'])} | {row['retention_verified']} | {row['tracked_sources_restored']} | {row['artifact_restored_exactly']} |\n"
        text += '\nThe missing zlib executable note was recovered from its separately stripped linked library. Both observations are retained; library stripping removes local symbols (`strip -x`). The journal contains three restored deployments.\n'
    return text
