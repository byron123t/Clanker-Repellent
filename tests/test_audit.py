import csv
import json
import tempfile
import unittest
from pathlib import Path

from llmddos.audit import evaluate_audit, export_blinded_sample


class AuditTests(unittest.TestCase):
    def test_blinded_export_and_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results.jsonl"
            audit = root / "audit.csv"
            row = {
                "status": "ok",
                "trial_id": "trial",
                "model": "secret-model",
                "condition_id": "secret-condition",
                "messages": [{"role": "user", "content": "Task: Find the code.\n\nDocument: X"}],
                "expected_terms": ["X"],
                "response_text": '{"answer":"X","summary":"ok"}',
                "metrics": {"outcome": "task_completed"},
            }
            results.write_text(json.dumps(row) + "\n", encoding="utf-8")
            self.assertEqual(export_blinded_sample([results], audit), 1)
            text = audit.read_text(encoding="utf-8")
            self.assertNotIn("secret-model", text)
            self.assertNotIn("secret-condition", text)
            rows = list(csv.DictReader(text.splitlines()))
            rows[0]["human_outcome"] = "task_completed"
            with audit.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            evaluation = evaluate_audit([results], audit)
            self.assertEqual(evaluation["evaluated"], 1)
            self.assertEqual(evaluation["accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()

