import tempfile
import unittest
from pathlib import Path

from clanker_repellent.datasets.dataset import (
    condition_metadata,
    load_cases,
    load_conditions,
    validate_condition_references,
)


ROOT = Path(__file__).resolve().parents[1]


class DatasetTests(unittest.TestCase):
    def test_repository_data_is_valid(self):
        self.assertEqual(len(load_cases(ROOT / "data/cases.jsonl")), 12)
        self.assertEqual(len(load_conditions(ROOT / "data/conditions.jsonl")), 8)

    def test_baseline_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conditions.jsonl"
            path.write_text(
                '{"id":"x","family":"control","payload":"","placement":"none"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "baseline"):
                load_conditions(path)

    def test_payload_can_be_loaded_from_relative_utf8_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload.txt").write_text("line one\nλ line two\n", encoding="utf-8")
            path = root / "conditions.jsonl"
            path.write_text(
                '{"id":"baseline","family":"clean","payload":"","placement":"none"}\n'
                '{"id":"file","family":"custom","payload_file":"payload.txt","placement":"append"}\n',
                encoding="utf-8",
            )
            rows = load_conditions(path)
            self.assertEqual(rows[1]["payload"], "line one\nλ line two\n")
            metadata = condition_metadata(rows)[1]
            self.assertEqual(metadata["payload_source"], "payload.txt")
            self.assertEqual(len(metadata["payload_sha256"]), 64)

    def test_exactly_one_payload_source_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conditions.jsonl"
            path.write_text(
                '{"id":"baseline","family":"clean","payload":"","placement":"none"}\n'
                '{"id":"bad","family":"custom","payload":"x","payload_file":"x.txt","placement":"append"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "exactly one"):
                load_conditions(path)

    def test_payload_file_cannot_escape_config_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "conditions.jsonl"
            path.write_text(
                '{"id":"baseline","family":"clean","payload":"","placement":"none"}\n'
                '{"id":"bad","family":"custom","payload_file":"../outside.txt","placement":"append"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cannot leave"):
                load_conditions(path)

    def test_structured_payload_template_loads_inline_and_file_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "template.txt").write_text(
                "PHASE I: {category}\n{raw1}\nPHASE II: {topic}\n{raw2}\n",
                encoding="utf-8",
            )
            (root / "fragment.txt").write_text("fragment body\n", encoding="utf-8")
            path = root / "conditions.jsonl"
            path.write_text(
                '{"id":"baseline","family":"clean","payload":"","placement":"none"}\n'
                '{"id":"structured","family":"custom","payload_template":"template.txt",'
                '"payload_values":{"category":"ALPHA","raw1":{"file":"fragment.txt"},'
                '"topic":"BETA","raw2":"tail"},"placement":"append"}\n',
                encoding="utf-8",
            )

            row = load_conditions(path)[1]
            metadata = condition_metadata([row])[0]

            self.assertEqual(
                row["payload"],
                "PHASE I: ALPHA\nfragment body\n\nPHASE II: BETA\ntail\n",
            )
            self.assertEqual(metadata["payload_source"], "template:template.txt")
            self.assertEqual(
                metadata["template_fields"], ["category", "raw1", "topic", "raw2"]
            )
            self.assertEqual(metadata["value_sources"]["raw1"], "fragment.txt")
            self.assertNotIn("fragment body", str(metadata))

    def test_structured_payload_requires_exact_template_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "template.txt").write_text("{one} {two}", encoding="utf-8")
            path = root / "conditions.jsonl"
            path.write_text(
                '{"id":"baseline","family":"clean","payload":"","placement":"none"}\n'
                '{"id":"bad","family":"custom","payload_template":"template.txt",'
                '"payload_values":{"one":"value","extra":"value"},"placement":"append"}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "missing two; unexpected extra"):
                load_conditions(path)

    def test_reference_validation_does_not_read_referenced_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "template.txt").write_bytes(b"\xff\xfe")
            (root / "fragment.txt").write_bytes(b"\xff\xfe")
            path = root / "conditions.jsonl"
            path.write_text(
                '{"id":"baseline","family":"clean","payload":"","placement":"none"}\n'
                '{"id":"structured","family":"custom","payload_template":"template.txt",'
                '"payload_values":{"category":"A","topic":"B",'
                '"raw1":{"file":"fragment.txt"},"raw2":""},"placement":"append"}\n',
                encoding="utf-8",
            )

            summary = validate_condition_references(
                path, ("category", "topic", "raw1", "raw2")
            )

            self.assertEqual(summary["conditions"], 2)
            self.assertEqual(summary["template_conditions"], 1)
            self.assertEqual(
                summary["referenced_files"], ["fragment.txt", "template.txt"]
            )
            with self.assertRaisesRegex(ValueError, "utf-8"):
                load_conditions(path)


if __name__ == "__main__":
    unittest.main()
