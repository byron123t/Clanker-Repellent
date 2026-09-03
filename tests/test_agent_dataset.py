import json
import tempfile
import unittest
from pathlib import Path

from clanker_repellent.datasets.agent_dataset import load_agent_scenarios


class AgentDatasetTests(unittest.TestCase):
    def test_loads_confined_environment_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "env"
            environment.mkdir()
            (environment / "note.md").write_text(
                "# Note\nCODE-7\n<!-- INJECT -->", encoding="utf-8"
            )
            row = {
                "id": "scenario",
                "environment_type": "repository",
                "environment_root": "env",
                "task": "Find the code",
                "expected_terms": ["CODE-7"],
                "inject_target_resource": "note.md",
                "injection_anchor": "<!-- INJECT -->",
            }
            config = root / "scenarios.jsonl"
            config.write_text(json.dumps(row) + "\n", encoding="utf-8")

            scenarios = load_agent_scenarios(config)

            self.assertEqual(scenarios[0]["target_resource_id"], "note.md")
            self.assertEqual(scenarios[0]["resources"][0]["content"].splitlines()[0], "# Note")

    def test_environment_root_cannot_escape_config_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {
                "id": "scenario",
                "environment_type": "repository",
                "environment_root": "../outside",
                "task": "Find the code",
                "expected_terms": ["CODE-7"],
                "inject_target_resource": "note.md",
                "injection_anchor": "<!-- INJECT -->",
            }
            config = root / "scenarios.jsonl"
            config.write_text(json.dumps(row) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "cannot leave"):
                load_agent_scenarios(config)


if __name__ == "__main__":
    unittest.main()
