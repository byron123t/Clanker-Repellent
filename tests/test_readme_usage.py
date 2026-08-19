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
            "## Architecture and lifecycle",
            "Generation, insertion, verification, and removal are separate operations",
            "repel generate --> statically validated source candidate",
            "repel deploy --> native carrier insertion",
            "repel add --> syntax-aware comment insertion",
            "repel remove --apply",
            "## Core repository commands",
            "repel add",
            "repel status",
            "repel remove",
            "repel guard",
            "python3 scripts/repel.py",
            "Recommended for using the installed CLI",
            "python3 -m pipx install .",
            "python3 -m pipx reinstall .",
            "python3 -m pipx uninstall clanker-repellent",
            "python -m pip install -e '.[dev]'",
            "python3 -m pip install --user .",
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
            "## Share hashes before enabling collaborators' agents",
            "repel share --state clean --output .repel-hashes.json",
            "repel verify --repo . --hashes .repel-hashes.json",
            "Only a `state` of `verified` enables the agent workflow",
            "## Git, GitHub, Claude, and Codex hooks",
            "actions/checkout@v4",
            "project's `.claude/settings.json`",
            "trusted project-local `.codex/hooks.json`",
            "## Reviewed abliterated-model drafts",
            "### Direct generation",
            "repel generate --list-languages",
            "repel generate --payload /private/payload.txt --language python --retries 3",
            "repel generate --benign --payload /private/benign-payload.txt",
            "results/benign-generation/",
            "### OpenCode generation",
            "repel generate --harness opencode",
            "--opencode-bin PATH",
            "## Optional evaluation harness",
        )
        for text in expected:
            with self.subTest(text=text):
                self.assertIn(text, documentation)

        self.assertNotIn("scripts/launch_repo_agents.py", readme)
        self.assertNotIn("anaphylaxis add", readme)
        self.assertLess(len(readme.splitlines()), 420)

    def test_only_three_top_level_guides_remain(self):
        guides = {
            path.name
            for path in ROOT.glob("*.md")
            if path.name in {"README.md", "EVALUATION.md", "RESEARCH.md"}
        }
        self.assertEqual(guides, {"README.md", "EVALUATION.md", "RESEARCH.md"})

    def test_package_exposes_only_the_repel_console_command(self):
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('repel = "llmddos.repo_tool:main"', project)
        self.assertNotIn("guardrail-eval =", project)
        self.assertNotIn("llmddos =", project)


if __name__ == "__main__":
    unittest.main()
