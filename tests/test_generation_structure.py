import unittest

from clanker_repellent.generate.structure import LANGUAGE_HINTS, STRUCTURE_PROFILE, structure_metrics
from clanker_repellent.generate.source_generation import select_languages, validate_snippet, validation_metadata


EXAMPLES = {
    "lua": 'local annotation = {text = "example", revision = 1}\n',
    "sql": "SELECT 'example' AS text, 1 AS revision;\n",
    "html": '<section id="annotation"><h2>Example</h2><p>Ordinary documentation.</p></section>',
    "python": 'ANNOTATION = {"text": "note", "revision": 1}\n',
    "bash": 'annotation_texts=("first" "second")\nannotation_revisions=(1 2)\n',
    "c": 'typedef struct Annotation { const char *text; int revision; } Annotation;\nconst Annotation annotation = {"note", 1};\n',
    "cpp": 'struct Annotation { const char *text; int revision; };\ninline constexpr Annotation annotation = {"note", 1};\n',
    "go": 'package annotation\n\ntype Annotation struct {\n\tText     string\n\tRevision int\n}\n\nvar Example = Annotation{\n\tText:     "note",\n\tRevision: 1,\n}\n',
    "java": 'public final class Generated {\npublic static final String TEXT = "note";\npublic static final int REVISION = 1;\n}\n',
    "javascript": 'const annotation = {text: "note", revision: 1};\n',
    "typescript": 'interface Annotation { text: string; revision: number; }\nconst annotation: Annotation = {text: "note", revision: 1};\n',
    "ruby": 'ANNOTATION = {text: "note", revision: 1}\n',
    "rust": 'pub struct Annotation {\n    pub text: &\'static str,\n    pub revision: u32,\n}\n\npub const ANNOTATION: Annotation = Annotation {\n    text: "note",\n    revision: 1,\n};\n',
    "swift": 'struct Annotation {\n    let text: String = "note"\n    let revision: Int = 1\n}\n',
}


class StructureTests(unittest.TestCase):
    def passes(self, language, source):
        try:
            metrics = structure_metrics(language, source)
        except (ValueError, SyntaxError):
            return False
        return metrics["fields"] >= 2 and metrics["initialized_fields"] >= 2

    def test_every_supported_language_has_a_populated_example(self):
        self.assertEqual(set(EXAMPLES), set(LANGUAGE_HINTS))
        for language, source in EXAMPLES.items():
            with self.subTest(language=language):
                self.assertTrue(self.passes(language, source))

    def test_comments_do_not_count_as_structure(self):
        for language, source in EXAMPLES.items():
            prefix = "# " if language in {"bash", "python", "ruby"} else "// "
            commented = "\n".join(prefix + line for line in source.splitlines())
            if language == "html":
                commented = "<!--" + source + "-->"
            if language in {"lua", "sql"}:
                commented = "\n".join("-- " + line for line in source.splitlines())
            with self.subTest(language=language):
                self.assertFalse(self.passes(language, commented))

    def test_empty_wrappers_and_scalar_assignments_fail(self):
        samples = {
            "python": ['note = "example"', 'class Note:\n    pass', '"a long natural language explanation"'],
            "bash": ['note="example"', 'a=("one")\nb=("two")'],
            "c": ['typedef int Annotation;', 'struct Note { int revision; };'],
            "cpp": ['struct Note {};', 'constexpr int revision = 1;'],
            "go": ['package annotation', 'package annotation\nvar text = "example"'],
            "java": ['public class Generated {}', 'class Generated { static final String TEXT = "example"; }'],
            "javascript": ['const note = "example";', 'const note = {};', 'class Note {}'],
            "typescript": ['interface Note { text: string; revision: number; }', 'const note = {text: "example"};'],
            "ruby": ['NOTE = "example"', 'NOTE = {}', 'class Note\nend'],
            "rust": ['pub struct Note {}', 'pub const TEXT: &str = "example";'],
            "swift": ['struct Note {}', 'let note = "example"'],
        }
        for language, sources in samples.items():
            for source in sources:
                with self.subTest(language=language, source=source):
                    self.assertFalse(self.passes(language, source))

    def test_code_shaped_strings_and_heredocs_do_not_count(self):
        samples = {
            "python": 'NOTE = """class Model:\n    text = "example"\n    revision = 1\n"""',
            "javascript": 'const note = `const fake = {text: "example", revision: 1};`;',
            "typescript": 'const note = "struct Fake { int a; int b; }";',
            "ruby": 'NOTE = <<~TEXT\nFAKE = {text: "example", revision: 1}\nTEXT\n',
            "rust": 'pub const NOTE: &str = r#"pub struct Fake {pub a: i32, pub b: i32} const V: Fake = Fake {a: 1, b: 2};"#;',
            "bash": 'a="(one two)"\nb="(three four)"',
            "c": 'const char *note = "struct Fake { int a; int b; }; struct Fake f = {1,2};";',
            "cpp": 'const char *note = R"(struct Fake { int a; int b; }; Fake f = {1,2};)";',
            "java": 'class Generated {static final String TEXT = "class Fake {int a = 1; int b = 2;}";}',
            "swift": 'let note = "struct Fake { let a = 1; let b = 2 }"',
        }
        for language, source in samples.items():
            with self.subTest(language=language):
                self.assertFalse(self.passes(language, source))

    def test_duplicate_fields_and_disabled_declarations_fail(self):
        for language, source in [
            ("python", 'note = {"text": "one", "text": "two"}'),
            ("javascript", 'const note = {text: "one", "text": "two"};'),
            ("python", 'if False:\n    NOTE = {"text": "note", "revision": 1}'),
            ("c", '#if 0\n' + EXAMPLES["c"] + '\n#endif\ntypedef int Stub;'),
            ("rust", '#![cfg(any())]\n' + EXAMPLES["rust"]),
        ]:
            with self.subTest(language=language):
                self.assertFalse(self.passes(language, source))

    def test_python_records_and_populated_class(self):
        self.assertTrue(self.passes("python", 'NOTES = [{"text": "example", "revision": 1}]'))
        self.assertTrue(self.passes("python", 'class Note:\n    text = "example"\n    revision = 1'))
        self.assertFalse(self.passes("python", 'note = {"text": get_text(), "revision": get_revision()}'))

    def test_maps_support_quoted_keys_and_arrays_of_records(self):
        for language, source in [
            ("javascript", 'const notes = [{"text": "example", "revision": 1}];'),
            ("ruby", 'NOTE = {"text" => "example", "revision" => 1}'),
            ("swift", 'let note = ["text": "example", "revision": "1"]'),
        ]:
            with self.subTest(language=language):
                self.assertTrue(self.passes(language, source))

    def test_cpp_direct_list_initialization_is_substantive(self):
        self.assertTrue(self.passes("cpp", 'struct Note { const char *text; int revision; };\ninline constexpr Note note{"example", 1};'))
        self.assertFalse(self.passes("cpp", 'struct Note { const char *text; int revision; };'))

    def test_structure_is_required_even_when_optional_linters_are_skipped(self):
        report = validate_snippet(select_languages(["python"])[0], '# documentation only\n',
                                  run_linters=False, require_structure=True, allow_missing_toolchains=True)
        self.assertFalse(report["accepted"])
        check = next(item for item in report["checks"] if item["name"] == "source_structure")
        self.assertEqual(check["status"], "failed")
        self.assertTrue(check["required"])

    def test_structure_metrics_contain_no_source_values(self):
        import json
        report = validate_snippet(select_languages(["python"])[0],
                                  'PRIVATE_NAME = {"private_key": "PRIVATE_VALUE", "revision": 1}',
                                  run_linters=False, require_structure=True)
        self.assertTrue(report["accepted"])
        metadata = json.dumps(validation_metadata(report))
        self.assertIn(STRUCTURE_PROFILE, metadata)
        self.assertNotIn("PRIVATE", metadata)
        self.assertNotIn("private_key", metadata)

    def test_missing_structure_dependency_is_not_partial_acceptance(self):
        from unittest import mock
        with mock.patch("clanker_repellent.generate.structure._lex", side_effect=ImportError), mock.patch(
            "clanker_repellent.generate.source_generation.shutil.which", return_value=None
        ):
            report = validate_snippet(select_languages(["javascript"])[0], EXAMPLES["javascript"],
                                      run_linters=False, require_structure=True, allow_missing_toolchains=True)
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["accepted"])


if __name__ == "__main__":
    unittest.main()
