import unittest

from llmddos.metrics import aggregate


def row(condition_id, family, task_success, attack_success):
    return {
        "status": "ok",
        "model": "m",
        "prompt_mode": "naive",
        "case_id": "c",
        "repeat": 0,
        "condition_id": condition_id,
        "condition_family": family,
        "latency_ms": 1.0,
        "metrics": {
            "task_success": task_success,
            "attack_success": attack_success,
            "refusal": attack_success,
            "schema_valid": task_success,
        },
    }


class AggregateTests(unittest.TestCase):
    def test_conditional_attributable_block_requires_passing_controls(self):
        rows = [
            row("baseline", "clean", True, False),
            row("benign", "matched_control", True, False),
            row("marker", "sensitive_topic", False, True),
        ]
        marker = next(group for group in aggregate(rows) if group["condition_id"] == "marker")
        self.assertEqual(marker["paired_eligible_n"], 1)
        self.assertEqual(marker["conditional_attributable_block_rate"], 1.0)
        self.assertEqual(marker["paired_task_success_drop"], 1.0)


if __name__ == "__main__":
    unittest.main()

