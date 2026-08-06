import json
import tempfile
import unittest
from pathlib import Path

from llmddos.events import EventLogger, compact_usage, redact_text
from llmddos.runner import run_trials


class FakeProvider:
    def complete(self, **kwargs):
        return {
            "response_text": '{"answer":"CODE","summary":"ok"}',
            "provider_refusal": None,
            "finish_reason": "stop",
            "latency_ms": 2.0,
            "usage": {"prompt_tokens": 8, "completion_tokens": 4},
            "provider_request_id": "provider-id",
        }


class EventTests(unittest.TestCase):
    def test_redacts_key_and_bearer_shapes(self):
        redacted = redact_text("sk-" + "abcdefghijklmnop" + " Bearer " + "abc.def.ghi")
        self.assertNotIn("abcdefghijklmnop", redacted)
        self.assertNotIn("abc.def.ghi", redacted)

    def test_run_emits_metadata_only_events(self):
        case = {
            "id": "case",
            "task": "Find the code",
            "artifact": "CODE",
            "expected_terms": ["CODE"],
        }
        condition = {
            "id": "baseline",
            "family": "clean",
            "payload": "",
            "placement": "none",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run.jsonl"
            events = Path(directory) / "events.jsonl"
            run_trials(
                FakeProvider(),
                output,
                ["model"],
                [case],
                [condition],
                ["naive"],
                event_log_path=events,
            )
            rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                [row["event"] for row in rows],
                ["run_started", "trial_started", "provider_succeeded", "trial_scored", "run_finished"],
            )
            event_text = events.read_text(encoding="utf-8")
            self.assertNotIn("response_text", event_text)
            self.assertNotIn("messages", event_text)

    def test_event_fields_are_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            EventLogger(path, "run").emit("test", accidental="sk-" + "abcdefghijklmnop")
            self.assertNotIn("abcdefghijklmnop", path.read_text(encoding="utf-8"))

    def test_usage_is_compact(self):
        usage = compact_usage(
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "latency_checkpoint": {"large": "detail"},
                "completion_tokens_details": {"reasoning_tokens": 2},
                "prompt_tokens_details": {"cached_tokens": 3},
            }
        )
        self.assertEqual(usage["reasoning_tokens"], 2)
        self.assertNotIn("latency_checkpoint", usage)


if __name__ == "__main__":
    unittest.main()
