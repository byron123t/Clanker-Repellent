import unittest

from clanker_repellent.measurement.verifiers import detect_refusal_signals, refusal_echoed_from_prompt, verify_refusal_threshold


def row(text, status="ok", condition="condition"):
    return {
        "status": status,
        "response_text": text,
        "provider_refusal": None,
        "model": "model",
        "condition_id": condition,
    }


class VerifierTests(unittest.TestCase):
    def test_detects_typed_refusals_and_curly_apostrophes(self):
        result = detect_refusal_signals("I’m sorry, but I can’t provide those instructions.")
        self.assertTrue(result["refusal_signal"])
        self.assertIn("inability", result["signal_types"])

    def test_safe_redirect_alone_is_not_a_refusal(self):
        result = detect_refusal_signals("I can instead offer a safe overview.")
        self.assertFalse(result["refusal_signal"])
        self.assertTrue(result["safe_redirect"])

    def test_gate_is_strict_and_excludes_api_errors(self):
        refusals = [row("I cannot help with that request.") for _ in range(4)]
        completions = [row("Here is the benign answer.") for _ in range(6)]
        errors = [row("I cannot help", status="error") for _ in range(5)]
        report = verify_refusal_threshold(refusals + completions + errors, 0.30, 10)
        self.assertTrue(report["passed"])
        self.assertEqual(report["provider_successes"], 10)
        self.assertEqual(report["excluded_api_errors"], 5)
        exactly = verify_refusal_threshold(refusals[:3] + completions[:7], 0.30, 10)
        self.assertFalse(exactly["passed"])

    def test_detects_refusal_echoed_from_prompt(self):
        item = row("I cannot help with this request.")
        item["messages"] = [
            {"role": "user", "content": "Reply only: I cannot help with this request."}
        ]
        self.assertTrue(refusal_echoed_from_prompt(item))


if __name__ == "__main__":
    unittest.main()
