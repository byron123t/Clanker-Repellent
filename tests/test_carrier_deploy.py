import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import clanker_repellent.payload.carrier_deploy as deploy


class NativeDeploymentTests(unittest.TestCase):
    def _run(self, root: Path, source: str, language: str = "python") -> Path:
        run = root / "run"
        candidate_dir = run / "candidate"
        candidate_dir.mkdir(parents=True)
        filename = "carrier.py" if language == "python" else "carrier.js"
        candidate = candidate_dir / filename
        candidate.write_text(source, encoding="utf-8")
        (run / "manifest.json").write_text(
            json.dumps(
                {
                    "kind": "repel_source_generation",
                    "candidates": [
                        {
                            "candidate_id": "python",
                            "language": language,
                            "status": "passed",
                            "accepted": True,
                            "candidate": {
                                "relative_path": f"candidate/{filename}",
                                "sha256": deploy._sha256_text(source),
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return run

    def test_python_alignment_preserves_multiline_literal_lines(self):
        source = 'if False:\n    class C:\n        """first\nsecond\n"""\n        pass\n'
        aligned = deploy.align_carrier(source, "python", "    ")
        self.assertIn('        """first\nsecond\n"""', aligned)
        compile("def f():\n" + aligned, "carrier.py", "exec", dont_inherit=True)

    def test_repeated_go_placement_avoids_duplicate_declarations(self):
        source = "package unit\n\nconst repelUnit = `payload`\n"
        repeated = deploy._disambiguate_carrier(source, "go", 1)
        self.assertIn("repelUnit_2", repeated)
        self.assertIn("`payload`", repeated)

    def test_apply_status_and_exact_remove(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root, "if False:\n    value = 'payload'\n")
            repository = root / "repo"
            repository.mkdir()
            target = repository / "main.py"
            original = "def f():\n    return 1\n"
            target.write_text(original, encoding="utf-8")
            result = deploy.deploy_carriers(
                run_dir=run, repository=repository, positions=["mid"], apply=True
            )
            self.assertEqual(result["files_changed"], 1)
            placement = result["files"][0]["placements"][0]
            self.assertIn("inserted_text", placement)
            self.assertGreater(placement["inserted_bytes"], 0)
            self.assertEqual(
                placement["inserted_sha256"],
                deploy._sha256_text(placement["inserted_text"]),
            )
            self.assertEqual(deploy.status_deployment(repository=repository)["status"], "clean")
            removed = deploy.remove_deployment(repository=repository, apply=True)
            self.assertEqual(removed["status"], "removed")
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_changed_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root, "if False:\n    value = 'payload'\n")
            repository = root / "repo"
            repository.mkdir()
            target = repository / "main.py"
            target.write_text("value = 1\n", encoding="utf-8")
            deploy.deploy_carriers(run_dir=run, repository=repository, positions=["tail"], apply=True)
            target.write_text("changed = True\n", encoding="utf-8")
            with self.assertRaisesRegex(deploy.DeploymentError, "refusing approximate removal"):
                deploy.remove_deployment(repository=repository, apply=True)

    def test_apply_fails_closed_when_host_integration_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root, "if False:\n    value = 'payload'\n")
            repository = root / "repo"
            repository.mkdir()
            target = repository / "main.py"
            original = "if True\n    broken = True\n"
            target.write_text(original, encoding="utf-8")

            with self.assertRaisesRegex(deploy.DeploymentError, "refusing partial deployment"):
                deploy.deploy_carriers(run_dir=run, repository=repository, positions=["tail"], apply=True)

            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertFalse((repository / deploy.INDEX_FILENAME).exists())

    def test_host_validation_has_a_strict_path_for_every_supported_language(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch("clanker_repellent.payload.carrier_deploy.shutil.which", return_value="/tool"), mock.patch(
            "clanker_repellent.payload.carrier_deploy.subprocess.run", return_value=completed
        ):
            for language, extensions in deploy.SOURCE_EXTENSIONS.items():
                suffix = extensions[0]
                path = Path("host" + suffix)
                with self.subTest(language=language):
                    report = deploy._validate_host_source(path, language, "pass\n")
                    self.assertEqual(report["status"], "passed")

    def test_candidate_file_is_rejected_with_generation_directory_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._run(root, "if False:\n    value = 'payload'\n")
            candidate = run / "candidate" / "carrier.py"

            with self.assertRaisesRegex(
                deploy.DeploymentError,
                r"--run-dir must point to the generation directory.*use "
                + str(run.resolve()),
            ):
                deploy.load_accepted_carriers(candidate)


if __name__ == "__main__":
    unittest.main()
