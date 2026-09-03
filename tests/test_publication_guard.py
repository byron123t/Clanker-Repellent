import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from clanker_repellent.payload.payload_scatter import scatter_payload
from clanker_repellent.payload.publication_guard import (
    HOOK_MARKER,
    STATE_CLEAN,
    STATE_MODIFIED,
    STATE_SCATTERED,
    classify_indexed_repository,
    clean_indexed_repository,
    install_pre_commit_guard,
    resolve_scatter_index,
)


class PublicationGuardTests(unittest.TestCase):
    def _scattered(self, root: Path):
        (root / "app.py").write_text("value = 1\n", encoding="utf-8")
        return scatter_payload(
            root,
            "indexed payload",
            condition_id="indexed",
            count=1,
            seed=7,
            instruction_files=["agents"],
            apply=True,
        )

    def test_auto_discovers_evaluation_manifest_and_exact_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = Path(directory) / "with_instruction_files"
            repository = layout / "replicated" / "sample"
            repository.mkdir(parents=True)
            scatter = self._scattered(repository)
            manifest = layout / "evaluation-manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "workspaces": [
                            {
                                "workspace_path": str(repository),
                                "scatter": scatter,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            loaded, source = resolve_scatter_index(repository)

            self.assertEqual(loaded, scatter)
            self.assertEqual(source, manifest.resolve())

    def test_classifies_previews_cleans_and_accepts_already_clean_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b"value = 1\n"
            scatter = self._scattered(root)

            present = classify_indexed_repository(root, scatter)
            preview = clean_indexed_repository(root, scatter)

            self.assertEqual(present["state"], STATE_SCATTERED)
            self.assertEqual(preview["state_before"], STATE_SCATTERED)
            self.assertEqual(preview["state_after"], STATE_SCATTERED)
            self.assertIn(b"indexed payload", (root / "app.py").read_bytes())

            cleaned = clean_indexed_repository(root, scatter, apply=True)

            self.assertEqual(cleaned["state_after"], STATE_CLEAN)
            self.assertEqual((root / "app.py").read_bytes(), original)
            self.assertFalse((root / "AGENTS.md").exists())
            self.assertEqual(
                classify_indexed_repository(root, scatter)["state"], STATE_CLEAN
            )
            no_op = clean_indexed_repository(root, scatter, apply=True)
            self.assertEqual(no_op["files_restored"], 0)
            self.assertEqual(no_op["state_after"], STATE_CLEAN)

    def test_modified_repository_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scatter = self._scattered(root)
            source = root / "app.py"
            source.write_bytes(source.read_bytes() + b"# edit\n")

            self.assertEqual(
                classify_indexed_repository(root, scatter)["state"], STATE_MODIFIED
            )
            with self.assertRaisesRegex(ValueError, "partially cleaned or modified"):
                clean_indexed_repository(root, scatter, apply=True)

    def test_direct_manifest_requires_matching_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            other = root / "other"
            repository.mkdir()
            other.mkdir()
            scatter = self._scattered(repository)
            manifest = root / "scatter.json"
            manifest.write_text(json.dumps(scatter), encoding="utf-8")

            loaded, source = resolve_scatter_index(repository, manifest)
            self.assertEqual(loaded, scatter)
            self.assertEqual(source, manifest.resolve())
            with self.assertRaisesRegex(ValueError, "does not match"):
                resolve_scatter_index(other, manifest)

    def test_manifest_discovery_and_index_validation_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "no scatter manifest"):
                resolve_scatter_index(root)
            with self.assertRaisesRegex(ValueError, "schema_version"):
                classify_indexed_repository(root, {"schema_version": 3})
            with self.assertRaisesRegex(ValueError, "not a directory"):
                resolve_scatter_index(root / "missing")

    def test_installs_refreshes_and_protects_pre_commit_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git/hooks").mkdir(parents=True)
            scatter = self._scattered(root)
            manifest = root / "scatter.json"
            manifest.write_text(json.dumps(scatter), encoding="utf-8")
            guard = root / "guard_publication.py"
            guard.write_text("print('guard')\n", encoding="utf-8")

            hook = install_pre_commit_guard(
                root,
                manifest,
                guard,
                python_executable=Path("/usr/bin/python3"),
            )
            refreshed = install_pre_commit_guard(
                root,
                manifest,
                guard,
                python_executable=Path("/usr/bin/python3"),
            )

            self.assertEqual(hook, refreshed)
            self.assertIn(HOOK_MARKER, hook.read_text(encoding="utf-8"))
            self.assertTrue(hook.stat().st_mode & 0o100)

            hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unrelated"):
                install_pre_commit_guard(
                    root,
                    manifest,
                    guard,
                    python_executable=Path("/usr/bin/python3"),
                )

    def test_command_line_cleaner_and_guard_work_without_pythonpath(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.md").write_text(
                "---\ntitle: Example\n---\n\nPublic page.\n", encoding="utf-8"
            )
            scatter = scatter_payload(
                root,
                "indexed payload",
                condition_id="indexed",
                count=1,
                seed=8,
                apply=True,
            )
            manifest = root.parent / f"{root.name}-scatter.json"
            manifest.write_text(json.dumps(scatter), encoding="utf-8")
            guard_command = [
                sys.executable,
                str(project / "scripts/guard_publication.py"),
                "--repository",
                str(root),
                "--scatter-manifest",
                str(manifest),
            ]

            blocked = subprocess.run(
                guard_command, capture_output=True, text=True, check=False
            )
            cleaned = subprocess.run(
                [
                    sys.executable,
                    str(project / "scripts/clean_indexed_payloads.py"),
                    "--repository",
                    str(root),
                    "--scatter-manifest",
                    str(manifest),
                    "--apply",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            allowed = subprocess.run(
                guard_command, capture_output=True, text=True, check=False
            )

            self.assertEqual(blocked.returncode, 3, blocked.stderr)
            self.assertIn("publication blocked", blocked.stdout)
            self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
            self.assertIn('"state_after": "clean"', cleaned.stdout)
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertIn("publication guard: clean", allowed.stdout)


if __name__ == "__main__":
    unittest.main()
