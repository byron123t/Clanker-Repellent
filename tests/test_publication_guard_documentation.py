import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicationGuardDocumentationTests(unittest.TestCase):
    def test_cleanup_publication_and_branding_contract_is_documented(self):
        publication = " ".join(
            (ROOT / "README.md").read_text(encoding="utf-8").split()
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        expected = (
            "repel remove",
            "repel guard",
            "scripts/install_publication_guard.py",
            "without searching for their strings",
            "partially changed workspace fails closed",
            "commit, CI, static-site, frontmatter",
            "does not automatically inject payloads during a commit",
            "There is no automatic generate-and-publish loop",
        )
        for text in expected:
            with self.subTest(text=text):
                self.assertIn(text, publication)
        self.assertIn("# Clanker Repellent", readme)
        self.assertIn("Guardrail Anaphylaxis paper/research project", readme)
        self.assertIn('name = "clanker-repellent"', project)
        self.assertIn('repel = "clanker_repellent.cli.repo_tool:main"', project)
        self.assertNotIn('anaphylaxis = "clanker_repellent.cli.repo_tool:main"', project)

    def test_inference_docs_do_not_claim_automatic_payload_generation(self):
        documentation = " ".join(
            (ROOT / "RESEARCH.md").read_text(encoding="utf-8").split()
        )
        self.assertIn("not automatic payload generators", documentation)
        self.assertIn(
            "does not optimize, mutate, or publish evasive variants automatically",
            documentation,
        )
        self.assertIn("repository addition is a separate explicit", documentation)


if __name__ == "__main__":
    unittest.main()
