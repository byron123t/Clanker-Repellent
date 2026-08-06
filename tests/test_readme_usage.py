import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeUsageTests(unittest.TestCase):
    def test_readme_centers_the_simple_payload_lifecycle(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        documentation = " ".join(readme.split())
        expected = (
            "## The four commands",
            "guardrail-anaphylaxis add",
            "guardrail-anaphylaxis status",
            "guardrail-anaphylaxis remove",
            "guardrail-anaphylaxis guard",
            "python3 scripts/guardrail.py",
            "payload text files → language-appropriate comments",
            "Repeat `--payload`",
            "omitting it means every eligible file",
            "Publication automation is cleanup/block-only",
            "## Reviewed abliterated-model drafts",
            "## Optional evaluation harness",
        )
        for text in expected:
            with self.subTest(text=text):
                self.assertIn(text, documentation)

        self.assertNotIn("scripts/launch_repo_agents.py", readme)
        self.assertLess(len(readme.splitlines()), 200)

    def test_only_three_top_level_guides_remain(self):
        guides = {path.name for path in ROOT.glob("*.md")}
        self.assertEqual(guides, {"README.md", "EVALUATION.md", "RESEARCH.md"})


if __name__ == "__main__":
    unittest.main()
