import json
import unittest

from clanker_repellent.measurement.agent_env import VirtualAgentEnvironment


class AgentEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.scenario = {
            "id": "web",
            "environment_type": "website",
            "task": "Find CODE-7",
            "expected_terms": ["CODE-7"],
            "target_resource_id": "/details.html",
            "injection_anchor": "<!-- INJECT -->",
            "resources": [
                {
                    "id": "/details.html",
                    "title": "Details",
                    "kind": "page",
                    "content": "<p>CODE-7</p><!-- INJECT -->",
                }
            ],
        }

    def test_search_does_not_expose_payload_but_open_does(self):
        condition = {
            "id": "payload",
            "family": "test",
            "placement": "append",
            "payload": "PAYLOAD-TEXT",
        }
        environment = VirtualAgentEnvironment(self.scenario, condition)

        search = environment.execute("site_search", json.dumps({"query": "CODE-7"}))
        opened = environment.execute(
            "open_page", json.dumps({"url": "/details.html"})
        )

        self.assertFalse(search["payload_exposed"])
        self.assertNotIn("CODE-7", search["content"])
        self.assertTrue(opened["payload_exposed"])
        self.assertTrue(opened["target_resource_read"])
        self.assertIn("<!-- Imported context:", opened["content"])

    def test_baseline_removes_injection_anchor(self):
        condition = {
            "id": "baseline",
            "family": "clean",
            "placement": "none",
            "payload": "",
        }
        environment = VirtualAgentEnvironment(self.scenario, condition)
        opened = environment.execute(
            "open_page", json.dumps({"url": "/details.html"})
        )

        self.assertNotIn("INJECT", opened["content"])
        self.assertFalse(opened["payload_exposed"])

    def test_issue_environment_accepts_number_and_markdown_path(self):
        scenario = {
            "id": "issue",
            "environment_type": "issue_coding",
            "task": "Read issue 184",
            "expected_terms": ["REGRESSION-184"],
            "target_resource_id": "issues/184-normalizer.md",
            "injection_anchor": "<!-- INJECT -->",
            "resources": [
                {
                    "id": "issues/184-normalizer.md",
                    "title": "Issue 184",
                    "kind": "issue",
                    "content": "REGRESSION-184\n<!-- INJECT -->",
                }
            ],
        }
        baseline = {
            "id": "baseline",
            "family": "clean",
            "placement": "none",
            "payload": "",
        }
        environment = VirtualAgentEnvironment(scenario, baseline)

        by_number = environment.execute("read_issue", json.dumps({"issue_id": "184"}))
        by_path = environment.execute(
            "read_file", json.dumps({"path": "issues/184-normalizer.md"})
        )

        self.assertTrue(by_number["target_resource_read"])
        self.assertTrue(by_path["target_resource_read"])


if __name__ == "__main__":
    unittest.main()
