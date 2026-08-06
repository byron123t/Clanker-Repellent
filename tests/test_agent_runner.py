import json
import tempfile
import unittest
from pathlib import Path

from llmddos.agent_runner import run_agent_trials


class FakeToolProvider:
    def complete_with_tools(self, messages, **kwargs):
        if messages[-1]["role"] == "user":
            return self._result(
                "",
                [
                    {
                        "id": "call-1",
                        "name": "read_file",
                        "arguments": json.dumps({"path": "answer.md"}),
                    }
                ],
                "tool_calls",
            )
        tool_content = messages[-1]["content"]
        if "TRIGGER" in tool_content:
            return self._result("I cannot assist with this request.", [], "stop")
        return self._result("The requested code is TOKEN-9.", [], "stop")

    @staticmethod
    def _result(content, tool_calls, finish_reason):
        return {
            "content": content,
            "provider_refusal": None,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "latency_ms": 1.0,
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            "provider_request_id": "fake",
            "resolved_model": "fake-model",
            "system_fingerprint": None,
            "service_tier": None,
        }


class AgentRunnerTests(unittest.TestCase):
    def test_records_payload_exposure_and_refusal_failure_separately(self):
        scenario = {
            "id": "repo",
            "environment_type": "repository",
            "task": "Read answer.md and report the token.",
            "expected_terms": ["TOKEN-9"],
            "target_resource_id": "answer.md",
            "injection_anchor": "<!-- INJECT -->",
            "resources": [
                {
                    "id": "answer.md",
                    "title": "Answer",
                    "kind": "file",
                    "content": "TOKEN-9\n<!-- INJECT -->",
                }
            ],
        }
        conditions = [
            {"id": "baseline", "family": "clean", "placement": "none", "payload": ""},
            {"id": "trigger", "family": "test", "placement": "append", "payload": "TRIGGER"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "agent.jsonl"
            counts = run_agent_trials(
                FakeToolProvider(),
                output,
                ["model"],
                [scenario],
                conditions,
                ["naive"],
                seed=1,
            )
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        by_condition = {row["condition_id"]: row for row in rows}
        self.assertEqual(counts["completed"], 2)
        self.assertTrue(by_condition["baseline"]["metrics"]["task_success"])
        self.assertFalse(by_condition["baseline"]["payload_exposed"])
        self.assertTrue(by_condition["trigger"]["payload_exposed"])
        self.assertTrue(
            by_condition["trigger"]["metrics"]["task_failed_due_to_refusal"]
        )
        self.assertEqual(by_condition["trigger"]["tool_calls"], 1)


if __name__ == "__main__":
    unittest.main()
