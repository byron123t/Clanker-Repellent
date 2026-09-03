import json
import tempfile
import unittest
from pathlib import Path

from clanker_repellent.payload.payload_mixer import (
    build_mix_condition_rows,
    validate_mixture_parts,
    write_mix_conditions,
)


class PayloadMixerTests(unittest.TestCase):
    def _sources(self, root: Path) -> None:
        names = (
            "bio_header1.txt",
            "bio_header2.txt",
            "c4_header.txt",
            "chem_header.txt",
            "nuke_header.txt",
            "raw_c41.txt",
            "raw_acid1.txt",
            "raw_meth1.txt",
            "raw_nuke2.txt",
            "raw_bio2.txt",
        )
        for name in names:
            (root / name).write_bytes(b"\xff\xfe")

    def test_generation_is_seeded_and_never_reads_payload_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._sources(root)

            first = build_mix_condition_rows(root, count=8, seed=42)
            second = build_mix_condition_rows(root, count=8, seed=42)

            self.assertEqual(first, second)
            self.assertEqual(len(first), 9)
            for row in first[1:]:
                parts = row["payload_parts"]
                self.assertEqual(parts[0]["topic"], "bio")
                self.assertNotEqual(parts[1]["topic"], "bio")
                self.assertNotIn(parts[2]["topic"], {"bio", parts[1]["topic"]})
            output = root / "generated.jsonl"
            write_mix_conditions(first, output)
            written = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(written, first)
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                write_mix_conditions(first, output)
            write_mix_conditions(second, output, replace=True)
            replaced = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(replaced, second)

    def test_validator_rejects_same_topic_header_and_raw_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._sources(root)
            parts = [
                {"file": "bio_header1.txt", "role": "bio_header", "topic": "bio"},
                {"file": "c4_header.txt", "role": "topic_header", "topic": "c4"},
                {"file": "raw_c41.txt", "role": "raw_text", "topic": "c4"},
            ]
            with self.assertRaisesRegex(ValueError, "raw-text topic must differ"):
                validate_mixture_parts(root, parts)


if __name__ == "__main__":
    unittest.main()
