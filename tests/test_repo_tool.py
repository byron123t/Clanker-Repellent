import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from llmddos.repo_tool import default_index_path, legacy_index_path, main


class RepositoryToolTests(unittest.TestCase):
    def test_unified_noop_help_uses_server_model_discovery(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                main(["noop", "generate", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("discovered from the server", output.getvalue())
        self.assertNotIn("--model", output.getvalue())

    def test_noop_generation_is_exposed_through_anaphylaxis(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            result = main(["noop", "generate", "--list-languages"])

        self.assertEqual(result, 0)
        self.assertIn("python\tgenerated.py", output.getvalue())

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
            self.assertEqual(document["target_mode"], "current_directory")
            self.assertEqual(source.read_text(encoding="utf-8"), "pass\n")
            self.assertFalse(default_index_path(repository).exists())
            self.assertEqual(default_index_path(repository).parent, repository.resolve())

    def test_git_repo_mode_discovers_root_and_keeps_index_in_git_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "owned"
            repository.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(repository)],
                check=True,
                capture_output=True,
            )
            nested = repository / "nested"
            nested.mkdir()
            source = repository / "app.py"
            source.write_text("pass\n", encoding="utf-8")
            payload = root / "payload.txt"
            payload.write_text("payload\n", encoding="utf-8")
            previous = Path.cwd()
            try:
                os.chdir(nested)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    added = main(
                        [
                            "add",
                            "--git-repo",
                            "--file",
                            "app.py",
                            "--payload",
                            str(payload),
                            "--apply",
                        ]
                    )
                add_result = json.loads(output.getvalue())
                with contextlib.redirect_stdout(io.StringIO()):
                    removed = main(["remove", "--git-repo", "--apply"])
            finally:
                os.chdir(previous)

            git_index = repository / ".git" / "anaphylaxis-index.json"
            self.assertEqual(added, 0)
            self.assertEqual(removed, 0)
            self.assertEqual(add_result["repository_root"], str(repository.resolve()))
            self.assertEqual(add_result["target_mode"], "git_repository")
            self.assertEqual(add_result["target_file"], "app.py")
            self.assertEqual(add_result["index"], str(git_index.resolve()))
            self.assertTrue(git_index.is_file())
            self.assertFalse(default_index_path(repository).exists())
            self.assertEqual(source.read_text(encoding="utf-8"), "pass\n")

    def test_legacy_sibling_index_cleans_and_migrates_on_readd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "sample"
            repository.mkdir()
            source = repository / "app.py"
            source.write_text("pass\n", encoding="utf-8")
            payload = root / "payload.txt"
            payload.write_text("payload\n", encoding="utf-8")
            legacy = legacy_index_path(repository)

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "add",
                            "--repo",
                            str(repository),
                            "--payload",
                            str(payload),
                            "--index",
                            str(legacy),
                            "--apply",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(["remove", "--repo", str(repository), "--apply"]), 0
                )
            self.assertTrue(legacy.is_file())
            self.assertFalse(default_index_path(repository).exists())

            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(
                    main(
                        [
                            "add",
                            "--repo",
                            str(repository),
                            "--payload",
                            str(payload),
                            "--apply",
                        ]
                    ),
                    0,
                )
            self.assertTrue(json.loads(output.getvalue())["legacy_index_migrated"])
            self.assertFalse(legacy.exists())
            self.assertTrue(default_index_path(repository).is_file())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(["remove", "--repo", str(repository), "--apply"]), 0
                )

    def test_fragmented_binary_defaults_to_head_tail_and_scales_inline_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "sample"
            repository.mkdir()
            (repository / "short.py").write_text(
                "".join(f"short_{index} = {index}\n" for index in range(10)),
                encoding="utf-8",
            )
            (repository / "long.py").write_text(
                "".join(f"long_{index} = {index}\n" for index in range(100)),
                encoding="utf-8",
            )
            payload = root / "payload.txt"
            payload.write_text(
                "".join(f"payload line {index}\n" for index in range(8)),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--payload",
                        str(payload),
                        "--strategy",
                        "fragmented",
                        "--apply",
                    ]
                )

            manifest = json.loads(
                default_index_path(repository).read_text(encoding="utf-8")
            )
            records = {record["path"]: record for record in manifest["injections"]}
            self.assertEqual(result, 0)
            self.assertEqual(manifest["file_positions"], ["head", "tail"])
            self.assertEqual(records["short.py"]["full_replica_placements"], 2)
            self.assertEqual(records["long.py"]["full_replica_placements"], 2)
            self.assertEqual(records["short.py"]["inline_chunk_count"], 1)
            self.assertEqual(records["long.py"]["inline_chunk_count"], 3)
            for record in records.values():
                positions = {placement["position"] for placement in record["placements"]}
                self.assertTrue({"head", "tail"}.issubset(positions))

    def test_file_flag_targets_one_exact_file_and_removes_it_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "sample"
            repository.mkdir()
            selected = repository / "selected.py"
            selected.write_text("selected = True\n", encoding="utf-8")
            untouched = repository / "untouched.py"
            untouched.write_text("untouched = True\n", encoding="utf-8")
            payload = root / "payload.txt"
            payload.write_text("payload\n", encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()) as output:
                added = main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--file",
                        "selected.py",
                        "--payload",
                        str(payload),
                        "--apply",
                    ]
                )
            result = json.loads(output.getvalue())

            self.assertEqual(added, 0)
            self.assertEqual(result["target_file"], "selected.py")
            self.assertIn("payload", selected.read_text(encoding="utf-8"))
            self.assertEqual(
                untouched.read_text(encoding="utf-8"), "untouched = True\n"
            )
            manifest = json.loads(
                default_index_path(repository).read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["requested_paths"], ["selected.py"])
            self.assertEqual(manifest["source_files_selected"], 1)

            with contextlib.redirect_stdout(io.StringIO()):
                removed = main(["remove", "--repo", str(repository), "--apply"])
            self.assertEqual(removed, 0)
            self.assertEqual(selected.read_text(encoding="utf-8"), "selected = True\n")

    def test_file_flag_rejects_outside_symlink_and_count_combination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "sample"
            repository.mkdir()
            (repository / "app.py").write_text("pass\n", encoding="utf-8")
            outside = root / "outside.py"
            outside.write_text("pass\n", encoding="utf-8")
            (repository / "linked.py").symlink_to(outside)

            for value in (outside, Path("linked.py")):
                with self.subTest(value=value), self.assertRaises(
                    SystemExit
                ), contextlib.redirect_stderr(io.StringIO()):
                    main(
                        [
                            "add",
                            "--repo",
                            str(repository),
                            "--file",
                            str(value),
                        ]
                    )

            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--file",
                        "app.py",
                        "--count",
                        "1",
                    ]
                )

    def test_instruction_files_flag_without_value_adds_and_removes_all_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "sample"
            repository.mkdir()
            (repository / "app.py").write_text("pass\n", encoding="utf-8")
            payload = root / "payload.txt"
            payload.write_text("payload\n", encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                added = main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--payload",
                        str(payload),
                        "--instruction-files",
                        "--apply",
                    ]
                )
            self.assertEqual(added, 0)
            for filename in ("CLAUDE.md", "AGENTS.md", "MEMORY.md"):
                self.assertIn(
                    "payload", (repository / filename).read_text(encoding="utf-8")
                )

            with contextlib.redirect_stdout(io.StringIO()):
                removed = main(["remove", "--repo", str(repository), "--apply"])
            self.assertEqual(removed, 0)
            for filename in ("CLAUDE.md", "AGENTS.md", "MEMORY.md"):
                self.assertFalse((repository / filename).exists())

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

            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                main(
                    [
                        "add",
                        "--repo",
                        str(repository),
                        "--payload",
                        str(payload),
                        "--apply",
                    ]
                )

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

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "add",
                            "--repo",
                            str(repository),
                            "--payload",
                            str(payload),
                            "--apply",
                        ]
                    ),
                    0,
                )
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["status", "--repo", str(repository)]), 0)
            self.assertEqual(json.loads(output.getvalue())["state"], "payload_present")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(["remove", "--repo", str(repository), "--apply"]), 0
                )

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
