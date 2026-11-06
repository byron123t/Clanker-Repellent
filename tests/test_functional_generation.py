import json
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE, FUNCTIONAL_HINTS, functional_metrics
from clanker_repellent.generate.source_generation import benign_policy_error, build_generation_messages, generate_source_run, select_languages, validate_snippet, validation_metadata


EXAMPLES = {
    "llvm": 'define i32 @increment(i32 %value) {\nentry:\n  %result = add i32 %value, 1\n  ret i32 %result\n}\n',
    "lua": 'function in_range(value, lower, upper)\n    return lower <= value and value <= upper\nend\n',
    "sql": 'SELECT CASE WHEN :lower <= :value AND :value <= :upper THEN 1 ELSE 0 END AS in_range;\n',
    "python": 'def in_range(value, lower, upper):\n    return lower <= value <= upper\n',
    "c": 'int in_range(int value, int lower, int upper) { return lower <= value && value <= upper; }\n',
    "cpp": 'inline bool in_range(int value, int lower, int upper) { return lower <= value && value <= upper; }\n',
    "go": 'package annotation\n\nfunc InRange(value int, lower int, upper int) bool {\n\treturn lower <= value && value <= upper\n}\n',
    "java": 'public final class Generated { public static boolean inRange(int value, int lower, int upper) { return lower <= value && value <= upper; } }\n',
    "javascript": 'function inRange(value, lower, upper) { return lower <= value && value <= upper; }\n',
    "typescript": 'function inRange(value: number, lower: number, upper: number): boolean { return lower <= value && value <= upper; }\n',
    "rust": 'pub fn in_range(value: i32, lower: i32, upper: i32) -> bool {\n    return lower <= value && value <= upper;\n}\n',
    "swift": 'func inRange(_ value: Int, _ lower: Int, _ upper: Int) -> Bool {\n    return lower <= value && value <= upper\n}\n',
    "ruby": 'def in_range(value, lower, upper)\n  return lower <= value && value <= upper\nend\n',
    "bash": 'in_range() {\n  local value=$1 lower=$2 upper=$3\n  if (( value >= lower && value <= upper )); then\n    return 0\n  fi\n  return 1\n}\n',
}


class FunctionalGenerationTests(unittest.TestCase):
    def test_runtime_policy_ignores_comment_prose_but_checks_code(self):
        self.assertIsNone(benign_policy_error('# Returns an exit status.\n' + EXAMPLES['bash'], language='bash'))
        self.assertIsNotNone(benign_policy_error('in_range() { exit 1; }', language='bash'))
        self.assertIsNotNone(benign_policy_error('#include <stdio.h>\n', language='c'))
        self.assertIsNone(benign_policy_error('<p>Returns an exit status.</p>', language='html'))

    def test_all_function_languages_have_an_input_dependent_example(self):
        self.assertEqual(set(EXAMPLES), set(FUNCTIONAL_HINTS))
        for language, source in EXAMPLES.items():
            with self.subTest(language=language):
                metrics = functional_metrics(language, source)
                self.assertGreater(metrics.get("qualifying_functions", metrics.get("qualifying_queries", 0)), 0)

    def test_data_only_and_constant_or_identity_functions_fail(self):
        examples = [
            ("python", 'DATA = {"first": 1, "second": 2}'),
            ("python", 'def example(value):\n    return value'),
            ("python", 'def example(value):\n    unused = value + 1\n    return 0'),
            ("python", 'def example(value):\n    return "value + 1"'),
            ("python", 'def example(value):\n    if value < 0:\n        return 1\n    return 1'),
            ("javascript", 'const data = {first: 1, second: 2};'),
            ("javascript", 'function example(value) { return value; }'),
            ("cpp", 'int example(int value) { return 0; }'),
            ("ruby", 'def example(value)\nreturn value\nend'),
        ]
        for language, source in examples:
            with self.subTest(language=language, source=source):
                self.assertEqual(functional_metrics(language, source)["qualifying_functions"], 0)

    def test_comments_and_string_contents_cannot_supply_function_bodies(self):
        for language, source in EXAMPLES.items():
            prefix = "# " if language in {"python", "ruby", "bash"} else "// "
            commented = "\n".join(prefix + line for line in source.splitlines())
            if language in {"lua", "sql"}:
                commented = "\n".join("-- " + line for line in source.splitlines())
            if language == "llvm":
                commented = "\n".join("; " + line for line in source.splitlines())
            with self.subTest(language=language):
                if language == "sql":
                    with self.assertRaises(ValueError):
                        functional_metrics(language, commented)
                else:
                    self.assertEqual(functional_metrics(language, commented)["qualifying_functions"], 0)
        self.assertEqual(functional_metrics("javascript", 'const text = `function example(value) {return value + 1;}`;')["qualifying_functions"], 0)

    def test_python_computed_locals_and_conditional_results(self):
        for source in ['def example(value):\n    result = value + 1\n    return result',
                       'def example(value):\n    if value < 0:\n        return False\n    return True']:
            self.assertEqual(functional_metrics("python", source)["qualifying_functions"], 1)

    def test_rust_computed_tail_expression(self):
        source = EXAMPLES['rust'].replace('return ', '').replace('upper;', 'upper')
        self.assertEqual(functional_metrics('rust', source)['qualifying_functions'], 1)

    @unittest.skipUnless(shutil.which('gofmt') and shutil.which('go'), 'Go tools required')
    def test_go_formatting_does_not_require_another_model_attempt(self):
        provider = mock.Mock(spec=['complete'])
        provider.complete.return_value = {'response_text': '```go\npackage annotation\nfunc InRange(value int, lower int, upper int) bool {return lower<=value && value<=upper}\n```'}
        with tempfile.TemporaryDirectory() as directory:
            run = generate_source_run(provider=provider, model='fixture', payload='Ordinary helper',
                                      targets=select_languages(['go']), output_dir=Path(directory) / 'run',
                                      benign=True, run_linters=False, retries=0, structure_profile=FUNCTIONAL_PROFILE)
        self.assertEqual(run['summary']['status'], 'passed')
        self.assertEqual(provider.complete.call_count, 1)
        self.assertTrue(run['candidates'][0]['attempts'][0]['formatting']['changed'])

    def test_functional_prompt_and_metadata(self):
        target = select_languages(["python"])[0]
        prompt = build_generation_messages(target, "Ordinary helper", benign=True, structure_profile=FUNCTIONAL_PROFILE)[0]["content"]
        self.assertIn("side-effect-free computation", prompt)
        self.assertNotIn("inert declarations", prompt)
        report = validate_snippet(target, EXAMPLES["python"], require_structure=True,
                                  structure_profile=FUNCTIONAL_PROFILE, run_linters=False)
        self.assertTrue(report["accepted"])
        serialized = json.dumps(validation_metadata(report))
        self.assertIn(FUNCTIONAL_PROFILE, serialized)
        self.assertNotIn("in_range", serialized)

    def test_data_candidate_retries_to_a_function_and_profile_cannot_silently_change(self):
        provider = mock.Mock(spec=["complete"])
        provider.complete.side_effect = [{"response_text": '```python\nDATA = {"first": 1, "second": 2}\n```'},
                                         {"response_text": '```python\n' + EXAMPLES["python"] + '```'}]
        with tempfile.TemporaryDirectory() as directory:
            arguments = dict(provider=provider, model="fixture", payload="Ordinary helper",
                             targets=select_languages(["python"]), output_dir=Path(directory) / "run",
                             benign=True, run_linters=False, retries=1)
            run = generate_source_run(**arguments, structure_profile=FUNCTIONAL_PROFILE)
            self.assertEqual(run["summary"]["status"], "passed")
            self.assertEqual(len(run["candidates"][0]["attempts"]), 2)
            self.assertEqual(run["settings"]["structure_profile"], FUNCTIONAL_PROFILE)
            with self.assertRaisesRegex(ValueError, "structural requirements changed"):
                generate_source_run(**arguments)


if __name__ == "__main__":
    unittest.main()
