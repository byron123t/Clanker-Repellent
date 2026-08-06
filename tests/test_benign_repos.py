import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from llmddos.benign_repos import (
    clone_repositories,
    create_injected_workspace,
    load_repository_manifest,
    strip_corpus_git_metadata,
)


class BenignRepositoryTests(unittest.TestCase):
    def _local_repository_manifest(self, root):
        source = root / "source"
        source.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=source, check=True)
        subprocess.run(
            ["git", "config", "user.email", "tests@example.test"],
            cwd=source,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Tests"], cwd=source, check=True
        )
        (source / "app.py").write_text("print('benign')\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.py"], cwd=source, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=source, check=True)
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        manifest_path = root / "repos.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "repositories": [
                        {
                            "id": "sample",
                            "url": source.as_uri(),
                            "revision": revision,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        repositories = load_repository_manifest(manifest_path, allow_file_urls=True)
        return repositories, revision

    def test_manifest_requires_https_and_full_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repos.json"
            path.write_text(
                json.dumps(
                    {
                        "repositories": [
                            {
                                "id": "sample",
                                "url": "http://example.test/repo.git",
                                "revision": "main",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "url must use"):
                load_repository_manifest(path)

    def test_manifest_rejects_credentials_in_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repos.json"
            path.write_text(
                json.dumps(
                    {
                        "repositories": [
                            {
                                "id": "sample",
                                "url": "https://token@example.test/repo.git",
                                "revision": "a" * 40,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "no credentials"):
                load_repository_manifest(path)

    def test_clones_an_exact_pinned_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repositories, revision = self._local_repository_manifest(root)

            records = clone_repositories(repositories, root / "output")

            self.assertEqual(records[0]["resolved_revision"], revision)
            self.assertTrue(records[0]["git_metadata_removed"])
            self.assertFalse((root / "output/sample/.git").exists())
            self.assertEqual(
                (root / "output/sample/app.py").read_text(encoding="utf-8"),
                "print('benign')\n",
            )
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                clone_repositories(repositories, root / "output")

    def test_disposable_workspace_resets_only_from_verified_clean_clone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repositories, revision = self._local_repository_manifest(root)
            clean_root = root / "clean"
            clone_repositories(repositories, clean_root)
            output_root = root / "injected"

            record = create_injected_workspace(
                repositories[0], clean_root, output_root, "replicated"
            )
            workspace = Path(record["workspace_path"])
            (workspace / "temporary.txt").write_text("remove me", encoding="utf-8")

            reset_record = create_injected_workspace(
                repositories[0], clean_root, output_root, "replicated", reset=True
            )
            reset_workspace = Path(reset_record["workspace_path"])

            self.assertFalse((reset_workspace / "temporary.txt").exists())
            self.assertFalse((reset_workspace / ".git").exists())
            self.assertEqual(
                (reset_workspace / "app.py").read_text(encoding="utf-8"),
                "print('benign')\n",
            )
            self.assertEqual(
                (clean_root / "sample/app.py").read_text(encoding="utf-8"),
                "print('benign')\n",
            )
            self.assertFalse((clean_root / "sample/.git").exists())

            baseline = create_injected_workspace(
                repositories[0], clean_root, output_root, "baseline"
            )
            self.assertFalse((Path(baseline["workspace_path"]) / ".git").exists())

    def test_modified_clean_tree_cannot_seed_a_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repositories, _ = self._local_repository_manifest(root)
            clean_root = root / "clean"
            clone_repositories(repositories, clean_root)
            (clean_root / "sample/app.py").write_text("changed\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "local changes"):
                create_injected_workspace(
                    repositories[0], clean_root, root / "injected", "replicated"
                )

    def test_reset_refuses_unrecognized_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repositories, _ = self._local_repository_manifest(root)
            clean_root = root / "clean"
            clone_repositories(repositories, clean_root)
            destination = root / "injected" / "replicated" / "sample"
            destination.mkdir(parents=True)
            (destination / "keep.txt").write_text("user data", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unrecognized workspace"):
                create_injected_workspace(
                    repositories[0],
                    clean_root,
                    root / "injected",
                    "replicated",
                    reset=True,
                )
            self.assertTrue((destination / "keep.txt").is_file())

    def test_migrates_existing_git_clones_and_externalizes_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repositories, _ = self._local_repository_manifest(root)
            corpus_root = root / "corpus"
            clean_root = corpus_root / "clean"
            clean_root.mkdir(parents=True)
            subprocess.run(
                ["git", "clone", "-q", repositories[0]["url"], "sample"],
                cwd=clean_root,
                check=True,
            )
            injected = corpus_root / "injected/replicated"
            injected.mkdir(parents=True)
            subprocess.run(
                ["git", "clone", "-q", str(clean_root / "sample"), "sample"],
                cwd=injected,
                check=True,
            )

            summary = strip_corpus_git_metadata(
                repositories, clean_root, corpus_root
            )

            self.assertEqual(summary["git_entries_removed"], 2)
            self.assertEqual(summary["clean_repositories_registered"], 1)
            self.assertEqual(summary["workspace_markers_written"], 1)
            self.assertFalse(any(corpus_root.rglob(".git")))
            clone_manifest = json.loads(
                (clean_root / "clone-manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                clone_manifest["repositories"][0]["git_metadata_removed"]
            )
            reset = create_injected_workspace(
                repositories[0],
                clean_root,
                corpus_root / "injected",
                "replicated",
                reset=True,
            )
            self.assertFalse((Path(reset["workspace_path"]) / ".git").exists())


if __name__ == "__main__":
    unittest.main()
