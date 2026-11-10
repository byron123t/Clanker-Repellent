"""Auxiliary benign placement/build/strip/exact-restoration check in pinned clones."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
if (Path(__file__).resolve().parent.parent / 'runner').is_dir():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'runner'))
from experiment import digest, save
from integration import build, logged, tracked

REPO = Path(__file__).resolve().parents[2]
TARGETS = {'cjson': ['cJSON.c'], 'zlib': ['adler32.c', 'deflate.c', 'inflate.c'],
           'curl': ['lib/easy.c', 'src/tool_main.c']}
ARTIFACTS = {'cjson': 'tests/parse_examples', 'zlib': 'minigzip', 'curl': 'src/curl'}


def diagnose_linkage(workspace):
    """Inspect the shipped shared library separately; retain the executable failure."""
    archived_engine = Path(__file__).resolve().parent.parent / 'supplement/updated-engine'
    sys.path.insert(0, str(archived_engine if archived_engine.is_dir() else REPO / 'src'))
    from clanker_repellent.payload.retained_deploy import recover_hashes
    root = workspace / 'repos/zlib'
    executable = workspace / 'builds/zlib/minigzip'
    library = workspace / 'builds/zlib/libz.1.3.1.dylib'
    target = workspace / 'zlib/stripped-libz.dylib'
    dependencies = subprocess.check_output(['otool', '-L', str(executable)], text=True)
    shutil.copy2(library, target)
    subprocess.run(['strip', '-x', str(target)], check=True, capture_output=True)
    evidence = json.loads((workspace / 'report.json').read_text())
    if evidence.get('benign') is not True or digest(workspace / 'note.txt') != evidence['note_sha256']:
        raise ValueError('Only the known benign deployment note may be checked')
    found = recover_hashes(target.read_bytes(), web_text=False)
    verification = {'expected_sha256': evidence['note_sha256'], 'found_sha256': sorted(found),
        'status': 'verified' if evidence['note_sha256'] in found else 'missing'}
    save(workspace / 'linkage-diagnostic.json', {'benign': True, 'kind': 'post_hoc_zlib_linkage_diagnostic',
        'executable_dependencies': dependencies, 'library': library.name, 'strip_command': ['strip', '-x', library.name],
        'stripped_library_sha256': digest(target), 'retention_verified': verification['status'] == 'verified',
        'verification': verification, 'scope': 'Separate local-symbol stripping and note recovery check in the linked zlib library. The original executable-only missing-note result is unchanged.'})


def run(workspace, baseline, cmake, store):
    if workspace.exists(): raise ValueError('Use a fresh auxiliary retention workspace')
    workspace.mkdir(parents=True)
    archived_engine = Path(__file__).resolve().parent.parent / 'supplement/updated-engine'
    sys.path.insert(0, str(archived_engine if archived_engine.is_dir() else REPO / 'src'))
    from clanker_repellent.payload.retained_deploy import deploy_retained, verify_artifacts
    from clanker_repellent.payload.carrier_deploy import remove_deployment, INDEX_FILENAME
    from clanker_repellent.payload.deployment_store import seal
    spec_path = Path(__file__).parent / 'repositories.json'
    if not spec_path.exists(): spec_path = Path(__file__).parent.parent / 'repositories.json'
    specification = json.loads(spec_path.read_text())
    for repository in specification['repositories']:
        target = workspace / 'repos' / repository['id']
        subprocess.run(['git', '-c', 'advice.detachedHead=false', 'clone', '--quiet', '--no-hardlinks', str(baseline / 'repos' / repository['id']), str(target)], check=True)
    builds = build(workspace, cmake)
    if not all(row['passed'] for row in builds): raise ValueError('Auxiliary baseline builds failed')
    note = workspace / 'note.txt'
    note.write_text('Benign integration reference: preserve this project note and its UTF-8 text.\nQuotes " and \\; café; examples remain ordinary data.\n')
    outcomes = []
    for baseline_row in builds:
        identity = baseline_row['id']
        root = workspace / 'repos' / identity
        built = workspace / 'builds' / identity
        inventory = tracked(root)
        artifact = root / '.repel-evaluation' / 'program'
        artifact.parent.mkdir()
        shutil.copy2(built / ARTIFACTS[identity], artifact)
        before = digest(artifact)
        deployment = deploy_retained(repository=root, payloads=[note],
            target_files=[Path(name) for name in TARGETS[identity]], benign=True, apply=True,
            store_path=store, snapshots=[artifact])
        if deployment.get('benign') is not True: raise ValueError('Only benign deployment is inspected')
        save(workspace / identity / 'deployment.json', deployment)
        if identity == 'zlib':
            for name in TARGETS[identity]:
                shutil.copyfile(root / name, workspace / 'build-sources/zlib' / name)
        steps = [logged([str(cmake), '--build', str(built), '--parallel', '2'], workspace, built / 'retained-build.log')]
        if identity == 'curl':
            steps.append(logged([str(cmake), '--build', str(built), '--parallel', '2', '--target'] + baseline_row['unit_targets'], workspace, built / 'retained-unit-build.log'))
            for name in baseline_row['unit_targets']:
                steps.append(logged([str(built / 'tests/unit' / name), 'http://127.0.0.1/'], built, built / ('retained-' + name + '.log')))
        else:
            steps.append(logged([str(cmake.parent / 'ctest'), '--test-dir', str(built), '--output-on-failure'], workspace, built / 'retained-tests.log'))
        if not all(step['returncode'] == 0 for step in steps): raise ValueError('Retained build or declared tests failed')
        shutil.copy2(built / ARTIFACTS[identity], artifact)
        subprocess.run(['strip', str(artifact)], check=True, capture_output=True)
        seal(root, root / INDEX_FILENAME)
        verification = verify_artifacts(repository=root, artifacts=[artifact])
        if identity == 'zlib':
            original = b'benign compression reference\n' * 10
            packed = subprocess.run([str(artifact)], input=original, capture_output=True, check=True).stdout
            restored = subprocess.run([str(artifact), '-d'], input=packed, capture_output=True, check=True).stdout
            behavior = restored == original
        else:
            command = [str(artifact)] + (['--version'] if identity == 'curl' else [])
            behavior = subprocess.run(command, cwd=built / 'tests' if identity == 'cjson' else built, capture_output=True).returncode == 0
        after = digest(artifact)
        removal = remove_deployment(repository=root, apply=True)
        restored_tree = tracked(root) == inventory
        restored_artifact = digest(artifact) == before
        row = {'repository': identity, 'revision': baseline_row['revision'], 'inventory': inventory,
            'benign': True, 'selected_files': TARGETS[identity], 'coverage_scope': 'explicit file list',
            'coverage': deployment['coverage'], 'deployment_index': deployment['index'], 'build_steps': steps,
            'artifact': ARTIFACTS[identity], 'artifact_before_sha256': before, 'artifact_after_sha256': after,
            'retention_verified': verification['status'] == 'verified', 'strip_command': ['strip', 'program'],
            'post_strip_behavior_passed': behavior, 'tracked_sources_restored': restored_tree,
            'artifact_restored_exactly': restored_artifact, 'removal_status': removal['status']}
        row['passed'] = all([row['retention_verified'], behavior, restored_tree, restored_artifact])
        outcomes.append(row)
        save(workspace / 'report.json', {'benign': True, 'kind': 'post_hoc_pinned_retention_check',
            'inference_requests': 0, 'note_sha256': digest(note), 'planned': 3, 'completed': len(outcomes),
            'outcomes': outcomes, 'baseline_builds': builds,
            'scope': 'One authored note in six explicit source files across three pinned C projects. Release build, symbol stripping, selected behavior checks, exact restoration of tracked sources and one snapshotted executable per project. No decompilation or full-repository coverage claim.'})
        print(json.dumps({key: row[key] for key in ['repository', 'passed', 'retention_verified', 'tracked_sources_restored', 'artifact_restored_exactly']}), flush=True)
    diagnose_linkage(workspace)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('workspace', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--cmake', required=True, type=Path)
    parser.add_argument('--store', required=True, type=Path)
    parser.add_argument('--diagnose-only', action='store_true')
    args = parser.parse_args()
    if args.diagnose_only:
        diagnose_linkage(args.workspace.resolve())
    else:
        run(args.workspace.resolve(), args.baseline.resolve(), args.cmake.absolute(), args.store.resolve())
