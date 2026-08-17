import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeUsageTests(unittest.TestCase):
    def test_readme_centers_the_simple_payload_lifecycle(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        documentation = " ".join(readme.split())
        expected = (
            "## Configuration and secret hygiene",
            "Checked-in configuration contains environment-variable references and placeholders only",
            "## Core repository commands",
            "repel add",
            "repel status",
            "repel remove",
            "repel guard",
            "python3 scripts/repel.py",
            "Standard `venv`",
            "conda create -n clanker-repellent",
            "No virtual environment",
            "python3 -m pip install --user -e .",
            "payload text files → language-appropriate comments",
            "automatically selects three bundled payload mixtures",
            "repel add --apply",
            "Current-directory mode is the default",
            "index at `./.anaphylaxis-index.json`",
            "`--git-repo` discovers the enclosing Git worktree",
            "repel remove --git-repo --apply",
            "repel add --file src/app.py --apply",
            "`--file` and `--count` are mutually exclusive",
            "do not need `--file` again",
            "repel add --instruction-files --apply",
            "--instruction-files AGENTS.md,CLAUDE.md",
            "Legacy sibling indexes",
            "`--strategy` defaults to `replicated`",
            "repository tool defaults to `head,tail`",
            "N = max(1, ceil(physical source lines / --inline-source-lines))",
            "Repeat `--payload`",
            "omitting it means every eligible file",
            "Publication automation is cleanup/block-only",
            "## Reviewed abliterated-model drafts",
            "### Direct no-op generation",
            "repel noop generate --list-languages",
            "repel noop generate --payload /private/payload.txt --language python --retries 3",
            "### OpenCode no-op generation",
            "repel noop generate --harness opencode",
            "--opencode-bin PATH",
            "## Optional evaluation harness",
        )
        for text in expected:
            with self.subTest(text=text):
                self.assertIn(text, documentation)

        self.assertNotIn("scripts/launch_repo_agents.py", readme)
        self.assertNotIn("anaphylaxis add", readme)
        self.assertLess(len(readme.splitlines()), 250)

    def test_only_three_top_level_guides_remain(self):
        guides = {
            path.name
            for path in ROOT.glob("*.md")
            if path.name in {"README.md", "EVALUATION.md", "RESEARCH.md"}
        }
        self.assertEqual(guides, {"README.md", "EVALUATION.md", "RESEARCH.md"})


if __name__ == "__main__":
    unittest.main()
