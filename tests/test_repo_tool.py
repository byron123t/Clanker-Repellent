import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from llmddos.repo_tool import default_index_path, main


class RepositoryToolTests(unittest.TestCase):
    def test_zero_argument_add_uses_cwd_bundled_pool_and_replicated_default(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "sample"
            repository.mkdir()
            source = repository / "app.py"
            source.write_text("pass\n", encoding="utf-8")
            previous = Path.cwd()
            try:
                os.chdir(repository)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    result = main(["add"])
            finally:
                os.chdir(previous)

            document = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(document["repository_root"], str(repository.resolve()))
            self.assertEqual(document["strategy"], "replicated")
            self.assertEqual(document["mode"], "dry-run")
            self.assertEqual(document["payload_selection"], "bundled_conditions")
            self.assertEqual(len(document["payload_pool"]), 3)
            self.assertEqual(source.read_text(encoding="utf-8"), "pass\n")
            self.assertFalse(default_index_path(repository).exists())

    def test_add_status_remove_and_guard_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "sample"
            repository.mkdir()
            source = repository / "app.py"
            source.write_text("value = 1\n", encoding="utf-8")
            payload = root / "payload.txt"
            payload.write_text("first line\nsecond line\n", encoding="utf-8")
            index = default_index_path(repository)

            with contextlib.redirect_stdout(io.StringIO()) as output:
                added = main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--payload",
                        str(payload),
                        "--positions",
                        "head,tail",
                        "--instruction-files",
                        "agents",
                        "--apply",
                    ]
                )
            add_result = json.loads(output.getvalue())

            self.assertEqual(added, 0)
            self.assertTrue(index.is_file())
            self.assertEqual(add_result["index"], str(index))
            self.assertEqual(add_result["payload_selection"], "explicit_files")
            self.assertIn("# first line", source.read_text(encoding="utf-8"))
            self.assertTrue((repository / "AGENTS.md").is_file())

            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = main(["status", "--repo", str(repository)])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())["state"], "payload_present")

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["guard", "--repo", str(repository)]), 3)

            with contextlib.redirect_stdout(io.StringIO()) as output:
                preview = main(["remove", "--repo", str(repository)])
            self.assertEqual(preview, 0)
            self.assertEqual(json.loads(output.getvalue())["state_after"], "payload_present")

            with contextlib.redirect_stdout(io.StringIO()) as output:
                removed = main(
                    ["remove", "--repo", str(repository), "--apply"]
                )
            self.assertEqual(removed, 0)
            self.assertEqual(json.loads(output.getvalue())["state_after"], "clean")
            self.assertEqual(source.read_text(encoding="utf-8"), "value = 1\n")
            self.assertFalse((repository / "AGENTS.md").exists())

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["guard", "--repo", str(repository)]), 0)

    def test_dry_run_does_not_write_repo_or_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "sample"
            repository.mkdir()
            source = repository / "app.py"
            source.write_text("pass\n", encoding="utf-8")
            payload = root / "payload.txt"
            payload.write_text("payload\n", encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--payload",
                        str(payload),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue())["mode"], "dry-run")
            self.assertEqual(source.read_text(encoding="utf-8"), "pass\n")
            self.assertFalse(default_index_path(repository).exists())

    def test_rejects_payload_inside_target_and_existing_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "sample"
            repository.mkdir()
            (repository / "app.py").write_text("pass\n", encoding="utf-8")
            inside = repository / "payload.txt"
            inside.write_text("payload\n", encoding="utf-8")

            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--payload",
                        str(inside),
                    ]
                )

            outside = root / "outside.txt"
            outside.write_text("payload\n", encoding="utf-8")
            default_index_path(repository).write_text("{}\n", encoding="utf-8")
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--payload",
                        str(outside),
                    ]
                )

    def test_rejects_invalid_automatic_payload_count(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "sample"
            repository.mkdir()
            (repository / "app.py").write_text("pass\n", encoding="utf-8")
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--payload-count",
                        "0",
                    ]
                )

if __name__ == "__main__":
    unittest.main()
