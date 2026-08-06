import json
import tempfile
import unittest
from pathlib import Path

from llmddos.dataset import load_conditions
from llmddos.payload_scatter import MARKER, scatter_payload


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "payloads/mixed_conditions.generated.jsonl"


class ActualPayloadManifestTests(unittest.TestCase):
    def test_generated_rows_enforce_cross_topic_order_with_shadow_files(self):
        rows = [
            json.loads(line)
            for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        ]
        mixtures = [row for row in rows if row["family"] == "mixed_actual"]
        self.assertEqual(len(mixtures), 24)
        for row in mixtures:
            parts = row["payload_parts"]
            self.assertEqual(
                [part["role"] for part in parts],
                ["bio_header", "topic_header", "raw_text"],
            )
            self.assertEqual(parts[0]["topic"], "bio")
            self.assertNotEqual(parts[1]["topic"], "bio")
            self.assertNotIn(parts[2]["topic"], {"bio", parts[1]["topic"]})

        referenced = {
            part["file"] for row in mixtures for part in row["payload_parts"]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for reference in referenced:
                (root / reference).write_text(
                    f"SHADOW CONTENT FOR {reference}", encoding="utf-8"
                )
            shadow_manifest = root / MANIFEST.name
            shadow_manifest.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
            )

            conditions = load_conditions(shadow_manifest)
            actual = [row for row in conditions if row["family"] == "mixed_actual"]

            self.assertEqual(len(actual), 24)
            for source, rendered in zip(mixtures, actual):
                expected_parts = [
                    f"SHADOW CONTENT FOR {part['file']}"
                    for part in source["payload_parts"]
                ]
                self.assertEqual(rendered["payload"], "\n\n".join(expected_parts))
            repository = root / "repository"
            repository.mkdir()
            (repository / "app.py").write_text("print('ok')\n", encoding="utf-8")
            scatter_payload(
                repository,
                actual[0]["payload"],
                condition_id=actual[0]["id"],
                count=1,
                seed=7,
                apply=True,
            )
            scattered = (repository / "app.py").read_text(encoding="utf-8")
            self.assertIn("# SHADOW CONTENT FOR", scattered)
            self.assertNotIn(MARKER, scattered)


if __name__ == "__main__":
    unittest.main()
