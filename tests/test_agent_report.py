import json
import tempfile
import unittest
from pathlib import Path

from clanker_repellent.measurement.agent_report import (
    aggregate_agent_records,
    make_agent_report,
    write_agent_report,
)


def record(
    scenario_id,
    variant,
    task_success,
    refusal=False,
    payload_exposed=False,
    model="m",
    prompt_mode="naive",
    status="ok",
    repeat=0,
):
    return {
        "status": status,
        "model": model,
        "prompt_mode": prompt_mode,
        "scenario_id": scenario_id,
        "variant": variant,
        "repeat": repeat,
        "payload_exposed": payload_exposed,
        "payload_delivered": payload_exposed,
        "metrics": {
            "task_success": task_success,
            "refusal": refusal,
            "task_failed_due_to_refusal": refusal and not task_success,
        },
    }


class AgentReportTests(unittest.TestCase):
    def test_reports_exposure_conditioning_and_paired_attribution(self):
        rows = [
            record("blocked", "clean", True),
            record("blocked", "injected", False, refusal=True, payload_exposed=True),
            record("completed", "clean", True),
            record("completed", "injected", True, refusal=True, payload_exposed=False),
            record("bad-clean", "clean", False),
            record("bad-clean", "injected", False, refusal=True, payload_exposed=True),
        ]

        group = aggregate_agent_records(rows)[0]

        self.assertEqual(group["paired_n"], 3)
        self.assertEqual(group["clean_task_success_rate"], 2 / 3)
        self.assertEqual(group["injected_task_success_rate"], 1 / 3)
        self.assertEqual(group["refusal_caused_failure_rate"], 2 / 3)
        self.assertEqual(group["payload_exposure_rate"], 2 / 3)
        self.assertEqual(group["conditional_failure_rate_among_exposed"], 1.0)
        self.assertEqual(group["attributable_eligible_n"], 2)
        self.assertEqual(group["attributable_refusal_failures"], 1)
        self.assertEqual(group["attributable_refusal_failure_rate"], 0.5)

    def test_does_not_pair_across_model_or_prompt_mode(self):
        rows = [
            record("same", "clean", True, model="a", prompt_mode="naive"),
            record(
                "same",
                "injected",
                False,
                refusal=True,
                payload_exposed=True,
                model="b",
                prompt_mode="naive",
            ),
            record("same", "clean", True, model="a", prompt_mode="hardened"),
        ]

        groups = aggregate_agent_records(rows)

        self.assertEqual(sum(group["paired_n"] for group in groups), 0)
        self.assertTrue(all(group["attributable_refusal_failure_rate"] is None for group in groups))

    def test_no_exposures_has_undefined_conditional_rate(self):
        rows = [
            record("one", "clean", True),
            record("one", "injected", True, payload_exposed=False),
        ]

        group = aggregate_agent_records(rows)[0]

        self.assertEqual(group["payload_exposure_rate"], 0.0)
        self.assertIsNone(group["conditional_failure_rate_among_exposed"])
        self.assertIsNone(group["conditional_failure_among_exposed_ci95"])

    def test_error_records_are_excluded_from_report(self):
        rows = [
            record("one", "clean", True),
            record("one", "injected", False, refusal=True, payload_exposed=True),
            record("error", "injected", False, status="error"),
        ]

        report = make_agent_report(rows)

        self.assertEqual(report["records"], 3)
        self.assertEqual(report["usable_records"], 2)
        self.assertEqual(report["excluded_records"], 1)
        self.assertEqual(report["complete_pairs"], 1)

    def test_primary_runner_schema_and_repeats_are_supported(self):
        rows = [
            {
                "status": "ok",
                "model": "m",
                "prompt_mode": "naive",
                "scenario_id": "one",
                "repeat": 0,
                "condition_id": "baseline",
                "condition_family": "clean",
                "payload_exposed": False,
                "payload_delivered": False,
                "metrics": {
                    "task_success": True,
                    "refusal": False,
                    "task_failed_due_to_refusal": False,
                },
            },
            {
                "status": "ok",
                "model": "m",
                "prompt_mode": "naive",
                "scenario_id": "one",
                "repeat": 0,
                "condition_id": "injection",
                "condition_family": "injected",
                "payload_exposed": True,
                "payload_delivered": True,
                "metrics": {
                    "task_success": False,
                    "refusal": True,
                    "task_failed_due_to_refusal": True,
                },
            },
            record("one", "clean", True, repeat=1),
            record("one", "injected", True, repeat=1),
        ]

        group = aggregate_agent_records(rows)[0]

        self.assertEqual(group["paired_n"], 2)
        self.assertEqual(group["payload_deliveries"], 1)
        self.assertEqual(group["payload_exposures"], 1)
        self.assertEqual(group["attributable_refusal_failure_rate"], 0.5)

    def test_duplicate_pair_member_is_rejected(self):
        rows = [
            record("one", "clean", True),
            record("one", "clean", True),
        ]

        with self.assertRaisesRegex(ValueError, "duplicate agent record"):
            aggregate_agent_records(rows)

    def test_multiple_payload_conditions_are_reported_separately(self):
        clean = record("one", "clean", True)
        first = record("one", "injected", False, refusal=True, payload_exposed=True)
        first.pop("variant")
        first["condition_id"] = "payload_a"
        second = record("one", "injected", True, payload_exposed=True)
        second.pop("variant")
        second["condition_id"] = "payload_b"

        groups = aggregate_agent_records([clean, first, second])

        self.assertEqual([group["condition_id"] for group in groups], ["payload_a", "payload_b"])
        self.assertEqual(groups[0]["attributable_refusal_failure_rate"], 1.0)
        self.assertEqual(groups[1]["attributable_refusal_failure_rate"], 0.0)

    def test_explicit_rerun_supersedes_same_trial_cell(self):
        failed = record("one", "injected", False, payload_exposed=False)
        corrected = record("one", "injected", True, payload_exposed=True)
        clean = record("one", "clean", True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            first.write_text(
                "\n".join(json.dumps(item) for item in (clean, failed)) + "\n",
                encoding="utf-8",
            )
            second.write_text(json.dumps(corrected) + "\n", encoding="utf-8")

            report = write_agent_report(
                [first, second],
                root / "report.json",
                root / "report.md",
                supersede_duplicates=True,
            )

        self.assertEqual(report["records"], 2)
        self.assertEqual(report["groups"][0]["injected_task_success_rate"], 1.0)
        self.assertEqual(report["groups"][0]["payload_exposure_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
