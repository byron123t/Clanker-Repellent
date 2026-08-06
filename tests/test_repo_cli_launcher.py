import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llmddos.repo_cli_launcher import (
    _select_tasks,
    agent_command,
    build_parser,
    build_task_prompt,
    capture_tree_artifacts,
    isolated_task_environment,
    main,
    verify_git_isolation,
)


ROOT = Path(__file__).resolve().parents[1]


class RepositoryCliLauncherTests(unittest.TestCase):
    def test_task_id_is_optional_and_omission_selects_the_full_catalog(self):
        parser = build_parser(ROOT)
        arguments = parser.parse_args(["--condition-id", "condition"])

        self.assertIsNone(arguments.task_id)
        tasks = _select_tasks(
            ROOT / "data/benign_repositories.json",
            ROOT / "data/repository_tasks.json",
            None,
        )
        self.assertEqual(len(tasks), 40)
        self.assertEqual(len({task["id"] for task in tasks}), 40)

    def test_task_id_selects_one_task_and_rejects_unknown_ids(self):
        manifest = ROOT / "data/benign_repositories.json"
        catalog = ROOT / "data/repository_tasks.json"

        selected = _select_tasks(manifest, catalog, "stb_png_grayscale_cli")

        self.assertEqual([task["id"] for task in selected], ["stb_png_grayscale_cli"])
        with self.assertRaisesRegex(ValueError, "unknown task id"):
            _select_tasks(manifest, catalog, "missing_task")

    def test_omitted_task_id_runs_every_task_with_isolated_artifacts(self):
        selected = [
            {
                "id": "first_task",
                "repository_id": "sample",
                "task_type": "test",
                "task": "Implement the first task.",
                "safety": "benign_software_engineering",
            },
            {
                "id": "second_task",
                "repository_id": "sample",
                "task_type": "test",
                "task": "Implement the second task.",
                "safety": "benign_software_engineering",
            },
        ]

        def capture(_before, _workspace, result_directory):
            result_directory.mkdir(parents=True)
            return {"changed": False, "patch_bytes": 0, "untracked_files": 0}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = (
                root
                / "workspaces/without_instruction_files/baseline/sample"
            )
            workspace.mkdir(parents=True)
            (workspace / "app.py").write_text("before\n", encoding="utf-8")
            with (
                mock.patch(
                    "llmddos.repo_cli_launcher._select_tasks", return_value=selected
                ),
                mock.patch(
                    "llmddos.repo_cli_launcher.shutil.which", return_value="/bin/agent"
                ),
                mock.patch("llmddos.repo_cli_launcher._prepare") as prepare,
                mock.patch("llmddos.repo_cli_launcher.subprocess.run") as run,
                mock.patch(
                    "llmddos.repo_cli_launcher.verify_git_isolation",
                    return_value=os.environ.copy(),
                ),
                mock.patch(
                    "llmddos.repo_cli_launcher.capture_tree_artifacts",
                    side_effect=capture,
                ),
            ):
                run.return_value.returncode = 0
                status = main(
                    [
                        "--condition-id",
                        "condition",
                        "--agents",
                        "codex",
                        "--variants",
                        "baseline",
                        "--results-root",
                        str(root / "results"),
                        "--output-root",
                        str(root / "workspaces"),
                        "--run-id",
                        "all-tasks",
                        "--yes",
                    ]
                )

            record = json.loads(
                (root / "results/all-tasks/run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status, 0)
            self.assertEqual(record["task_selection"], "all")
            self.assertEqual(record["task_count"], 2)
            self.assertEqual(
                [item["task_id"] for item in record["runs"]],
                ["first_task", "second_task"],
            )
            self.assertEqual(prepare.call_count, 2)
            self.assertFalse(prepare.call_args_list[0].kwargs["reset"])
            self.assertTrue(prepare.call_args_list[1].kwargs["reset"])
            self.assertTrue(
                (root / "results/all-tasks/first_task/codex/baseline/result.json").is_file()
            )
            self.assertTrue(
                (root / "results/all-tasks/second_task/codex/baseline/result.json").is_file()
            )

    def test_agent_commands_are_interactive_and_do_not_override_models(self):
        prompt = build_task_prompt("Add a deterministic test.")

        codex = agent_command("codex", prompt)
        claude = agent_command("claude", prompt)

        self.assertEqual(codex[0], "codex")
        self.assertIn("workspace-write", codex)
        self.assertIn("never", codex)
        self.assertEqual(claude[0], "claude")
        self.assertIn("auto", claude)
        self.assertIn("project", claude)
        self.assertNotIn("--safe-mode", claude)
        self.assertNotIn("--model", codex)
        self.assertNotIn("--model", claude)
        self.assertEqual(codex[-1], claude[-1])
        self.assertNotIn("baseline", prompt)
        self.assertNotIn("payload", prompt)

    def test_capture_patch_compares_git_free_tree_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before"
            repository = root / "repository"
            before.mkdir()
            repository.mkdir()
            (before / "tracked.txt").write_text("before\n", encoding="utf-8")
            (repository / "tracked.txt").write_text("after\n", encoding="utf-8")
            (repository / "new.txt").write_text("new file\n", encoding="utf-8")

            result = capture_tree_artifacts(before, repository, root / "result")
            patch = (root / "result/changes.patch").read_text(encoding="utf-8")
            status = (root / "result/tree-status.txt").read_text(encoding="utf-8")

            self.assertTrue(result["changed"])
            self.assertEqual(result["untracked_files"], 1)
            self.assertFalse((repository / ".git").exists())
            self.assertIn("M tracked.txt", status)
            self.assertIn("A new.txt", status)
            self.assertIn("+after", patch)
            self.assertIn("+new file", patch)

    def test_task_environment_blocks_parent_git_log_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "tests@example.test"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Tests"], cwd=root, check=True
            )
            (root / "outer.txt").write_text("outer\n", encoding="utf-8")
            subprocess.run(["git", "add", "outer.txt"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "outer"], cwd=root, check=True
            )
            workspace = root / "tasks/sample"
            workspace.mkdir(parents=True)
            (workspace / "app.py").write_text("pass\n", encoding="utf-8")

            inherited = subprocess.run(
                ["git", "log", "-1", "--oneline"],
                cwd=workspace,
                check=False,
                stdout=subprocess.PIPE,
            )
            environment = verify_git_isolation(workspace)
            isolated = subprocess.run(
                ["git", "log", "-1", "--oneline"],
                cwd=workspace,
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(inherited.returncode, 0)
            self.assertNotEqual(isolated.returncode, 0)
            self.assertEqual(
                isolated_task_environment(workspace)["GIT_CEILING_DIRECTORIES"],
                str(workspace.resolve().parent),
            )
            self.assertFalse((workspace / ".git").exists())


if __name__ == "__main__":
    unittest.main()
