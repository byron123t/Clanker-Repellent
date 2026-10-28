import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import reset_claude_session as reset


class ClaudeSessionResetTests(unittest.TestCase):
    def setUp(self):
        environment = mock.patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        which = mock.patch.object(reset.shutil, "which", return_value="/tools/claude")
        which.start()
        self.addCleanup(which.stop)
        run = mock.patch.object(
            reset.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0),
        )
        self.run_command = run.start()
        self.addCleanup(run.stop)

    def test_preview_targets_only_the_fixed_checkout(self):
        for arguments in ([], ["--dry-run"]):
            with self.subTest(arguments=arguments):
                self.assertEqual(reset.main(arguments), 0)
                self.run_command.assert_called_with(
                    [
                        "/tools/claude",
                        "purge",
                        "/Users/bjaytang/Desktop/github/telegram/sandbox/clanker-repellent",
                        "--dry-run",
                    ],
                    cwd=reset.REPOSITORY,
                    check=False,
                )

    def test_apply_keeps_the_same_target_from_another_working_directory(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertEqual(reset.main(["--apply"]), 0)
            finally:
                os.chdir(previous)
        self.run_command.assert_called_once_with(
            ["/tools/claude", "purge", str(reset.REPOSITORY), "--yes"],
            cwd=reset.REPOSITORY,
            check=False,
        )

    def test_rejects_target_overrides_all_projects_and_ambiguous_flags(self):
        for arguments in (
            ["/another/repository"],
            ["--all"],
            ["--repo", "/another/repository"],
            ["--app"],
            ["--apply", "--dry-run"],
        ):
            with self.subTest(arguments=arguments):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        reset.main(arguments)
                self.assertEqual(raised.exception.code, 2)
        self.run_command.assert_not_called()

    def test_refuses_to_run_if_copied_to_another_checkout(self):
        with mock.patch.object(reset, "__file__", "/tmp/other/scripts/reset_claude_session.py"):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    reset.main(["--apply"])
        self.assertEqual(raised.exception.code, 2)
        self.run_command.assert_not_called()

    def test_refuses_alternate_profiles_and_shared_project_names(self):
        for name in ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_PROJECT_DIR_NAME"):
            with self.subTest(name=name):
                with mock.patch.dict(os.environ, {name: "another-profile"}):
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as raised:
                            reset.main(["--apply"])
                self.assertEqual(raised.exception.code, 2)
        self.run_command.assert_not_called()

    def test_missing_claude_does_not_attempt_deletion(self):
        with mock.patch.object(reset.shutil, "which", return_value=None):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    reset.main(["--apply"])
        self.assertEqual(raised.exception.code, 2)
        self.run_command.assert_not_called()

    def test_preserves_claude_exit_status(self):
        self.run_command.return_value = subprocess.CompletedProcess([], 1)
        self.assertEqual(reset.main([]), 1)

    def test_reports_launch_failure(self):
        self.run_command.side_effect = OSError("cannot launch")
        with contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(reset.main([]), 2)
        self.assertIn("Cannot run Claude project reset", output.getvalue())


if __name__ == "__main__":
    unittest.main()
