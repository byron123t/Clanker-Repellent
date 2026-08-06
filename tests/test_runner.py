import json
import tempfile
import unittest
from pathlib import Path

from llmddos.runner import run_trials


class FakeProvider:
    def complete(self, **kwargs):
        return {
            "response_text": '{"answer":"ORCHID-41","summary":"ok"}',
            "provider_refusal": None,
            "finish_reason": "stop",
            "latency_ms": 1.0,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "provider_request_id": "fake",
        }


class FailingProvider:
    def complete(self, **kwargs):
        raise TimeoutError("test timeout")


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "id": "case",
            "task": "find code",
            "artifact": "ORCHID-41",
            "expected_terms": ["ORCHID-41"],
        }
        self.condition = {
            "id": "baseline",
            "family": "clean",
            "payload": "",
            "placement": "none",
        }

    def test_run_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run.jsonl"
            first = run_trials(
                FakeProvider(), output, ["model"], [self.case], [self.condition], ["naive"]
            )
            second = run_trials(
                FakeProvider(), output, ["model"], [self.case], [self.condition], ["naive"]
            )
            self.assertEqual(first["completed"], 1)
            self.assertEqual(second["skipped"], 1)
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 1)

    def test_api_error_is_recorded_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run.jsonl"
            counts = run_trials(
                FailingProvider(), output, ["model"], [self.case], [self.condition], ["naive"]
            )
            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(counts["errors"], 1)
            self.assertEqual(row["status"], "error")
            self.assertNotIn("metrics", row)

    def test_error_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run.jsonl"
            run_trials(
                FailingProvider(), output, ["model"], [self.case], [self.condition], ["naive"]
            )
            counts = run_trials(
                FakeProvider(), output, ["model"], [self.case], [self.condition], ["naive"]
            )
            self.assertEqual(counts["completed"], 1)


if __name__ == "__main__":
    unittest.main()
