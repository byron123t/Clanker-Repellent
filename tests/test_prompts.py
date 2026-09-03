import unittest

from clanker_repellent.inference.prompts import build_messages, render_artifact


CASE = {"task": "Find CANARY.", "artifact": "CANARY", "expected_terms": ["CANARY"]}


class PromptTests(unittest.TestCase):
    def test_append_and_prepend(self):
        append = {"payload": "PAYLOAD", "placement": "append"}
        prepend = {"payload": "PAYLOAD", "placement": "prepend"}
        self.assertTrue(render_artifact("BODY", append).endswith("PAYLOAD"))
        self.assertTrue(render_artifact("BODY", prepend).startswith("[APPENDIX]"))
        self.assertNotIn("UNTRUSTED", render_artifact("BODY", append))

    def test_hardened_prompt_marks_artifact_as_data(self):
        condition = {"payload": "ignore prior", "placement": "append"}
        messages = build_messages(CASE, condition, "hardened")
        self.assertIn("untrusted data", messages[0]["content"])
        self.assertIn("<artifact>", messages[1]["content"])

    def test_naive_prompt_has_no_provenance_reinforcement(self):
        condition = {"payload": "ignore prior", "placement": "append"}
        messages = build_messages(CASE, condition, "naive")
        self.assertNotIn("<artifact>", messages[1]["content"])
        self.assertNotIn("Perform only", messages[1]["content"])

    def test_follow_artifact_mode_requests_action(self):
        condition = {"payload": "ACTION: decline", "placement": "append"}
        messages = build_messages(CASE, condition, "follow_artifact")
        self.assertIn("Carry out the instruction", messages[1]["content"])
        self.assertIn("ACTION: decline", messages[1]["content"])

    def test_raw_naive_has_no_system_or_document_label(self):
        condition = {"payload": "ignore prior", "placement": "append"}
        messages = build_messages(CASE, condition, "raw_naive")
        self.assertEqual([message["role"] for message in messages], ["user"])
        self.assertNotIn("Document:", messages[0]["content"])

    def test_payload_wrapper_can_be_disabled_exactly(self):
        condition = {
            "payload": "PAYLOAD",
            "placement": "append",
            "carrier_label": "",
            "separator": "",
        }
        self.assertEqual(render_artifact("BODY", condition), "BODYPAYLOAD")


if __name__ == "__main__":
    unittest.main()
