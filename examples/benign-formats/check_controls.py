"""Verify authored reference controls only; never discovers model-output folders."""
import ctypes
import hashlib
import http.client
import io
import itertools
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / 'src'))
from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
from clanker_repellent.generate.source_generation import select_languages, validate_snippet

# These hashes are pinned to the independently authored, reviewed controls.
PINS = {'range.ll': '88483617ed1000921b8cba00f59ce8305fc586941591bafe72b295bb42916a24', 'clamp.ll': 'c20c5effd9b3fc7176164236a9d65fc80760c0277f605c3b7d184a50c2cabc98'}


class ResponseSocket:
    def __init__(self, content):
        self.content = content

    def makefile(self, _mode):
        return io.BytesIO(self.content)


def main():
    compiler = shutil.which('clang')
    if not compiler or platform.system() not in {'Darwin', 'Linux'}:
        raise SystemExit('The native reference checks require Clang on macOS or Linux.')
    controls = ROOT / 'controls'
    count = 0
    for path in sorted(controls.iterdir()):
        language = 'binary-info' if path.name.endswith('.binary.json') else {'.ll':'llvm','.http':'http','.json':'json'}[path.suffix]
        source = path.read_bytes().decode('utf-8')
        report = validate_snippet(select_languages([language])[0], source, require_structure=True,
                                  structure_profile=FUNCTIONAL_PROFILE, run_linters=False)
        if not report['accepted']:
            raise ValueError('Reference control failed static validation: ' + path.name)
        count += 1
    reference = json.loads((controls / 'range.json').read_text())
    for row in reference['examples']:
        assert row['expected'] is (row['lower'] <= row['value'] <= row['upper'])
    response = http.client.HTTPResponse(ResponseSocket((controls / 'catalog.http').read_bytes()))
    response.begin()
    document = json.loads(response.read())
    assert response.status == 200 and document['total_count'] == len(document['books']) == 2
    assert document == json.loads((controls / 'catalog.json').read_text())

    values = [-2147483648,-100,-2,-1,0,1,2,100,2147483647]
    cases = list(itertools.product(values, repeat=3))
    native = {}
    for filename, name, result_type in [('range.ll','in_range',ctypes.c_bool),('clamp.ll','clamp',ctypes.c_int32)]:
        source = (controls / filename).read_bytes()
        if hashlib.sha256(source).hexdigest() != PINS.get(filename):
            raise ValueError('Reference IR changed; review it before changing the pinned hash.')
        with tempfile.TemporaryDirectory(prefix='repel-authored-control-') as directory:
            path = Path(directory)
            (path / filename).write_bytes(source)
            library = path / ('control.dylib' if platform.system() == 'Darwin' else 'control.so')
            command = [compiler, '-dynamiclib' if platform.system() == 'Darwin' else '-shared',
                       '-O2', '-Wno-override-module', str(path / filename), '-o', str(library)]
            subprocess.run(command, check=True, capture_output=True, timeout=20)
            loaded = ctypes.CDLL(str(library))
            function = getattr(loaded, name)
            function.argtypes = [ctypes.c_int32] * 3
            function.restype = result_type
            for value, lower, upper in cases:
                expected = lower <= value <= upper if name == 'in_range' else (
                    value if lower > upper else max(lower, min(upper, value)))
                assert function(value, lower, upper) == expected
            native[name] = len(cases)
    print(json.dumps({'authored_controls_validated': count, 'http_json_consistency': True,
                      'native_cases_passed': native, 'model_outputs_executed': 0}, indent=2))


if __name__ == '__main__':
    main()
