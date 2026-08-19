import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    "GitHub token": re.compile(
        r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"
    ),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "credential URL": re.compile(r"https?://[^/@\s]+:[^/@\s]+@"),
}


class SecretHygieneTests(unittest.TestCase):
    def test_local_secret_files_and_key_formats_are_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for pattern in (
            ".env",
            ".env.*",
            "*.pem",
            "*.key",
            "*.p12",
            "*.pfx",
            ".netrc",
            "credentials*.json",
            "secrets*.json",
        ):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, ignore)
        self.assertIn("!.env.example", ignore)
        self.assertIn("results/", ignore)
        self.assertFalse(any(line.startswith("!results/") for line in ignore))

    def test_publishable_project_files_have_no_credential_shaped_values(self):
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        paths = [
            ROOT / relative.decode("utf-8")
            for relative in listing
            if relative
            and not {"payloads", "results"}.intersection(
                Path(relative.decode("utf-8")).parts
            )
        ]

        findings = []
        for path in paths:
            if (
                not path.is_file()
                or "benign_repos" in path.parts
                or path.name == ".env"
            ):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(content):
                    findings.append(f"{label}: {path.relative_to(ROOT)}")
        self.assertEqual(findings, [])

    def test_checked_in_endpoint_templates_have_no_literal_endpoint_or_key(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        config = (ROOT / "configs" / "abliterated-local.json").read_text(encoding="utf-8")
        remote_config = (ROOT / "configs" / "abliterated-remote.json").read_text(encoding="utf-8")

        self.assertNotRegex(example, r"https?://")
        self.assertNotRegex(example, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        self.assertNotRegex(config, r"https?://")
        self.assertNotRegex(config, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        self.assertNotRegex(remote_config, r"https?://")
        self.assertNotRegex(remote_config, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        self.assertNotIn('"api_key"', config)
        self.assertNotIn('"api_key"', remote_config)


if __name__ == "__main__":
    unittest.main()
