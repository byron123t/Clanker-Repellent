import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from llmddos.opencode_harness import (
    AGENT_ID,
    OpenCodeNoopHarness,
    build_opencode_config,
    extract_opencode_text,
)


class OpenCodeHarnessTests(unittest.TestCase):
    def target(self):
        return SimpleNamespace(language="python", output_filename="generated.py")

    def harness(self):
        with patch("llmddos.opencode_harness.shutil.which", return_value="/bin/opencode"):
            return OpenCodeNoopHarness(
                model="served/model",
                base_url="http://127.0.0.1:18473/v1",
                timeout_seconds=12,
            )

    def test_runtime_config_uses_discovered_model_and_enables_code_tools(self):
        config = build_opencode_config(
            model="served/model",
            base_url="http://127.0.0.1:18473/v1",
            max_tokens=8192,
        )

        self.assertEqual(config["model"], "anaphylaxis-local/served/model")
        self.assertEqual(
            config["provider"]["anaphylaxis-local"]["options"]["baseURL"],
            "http://127.0.0.1:18473/v1",
        )
        self.assertIn(
            "served/model", config["provider"]["anaphylaxis-local"]["models"]
        )
        self.assertEqual(config["agent"][AGENT_ID]["permission"]["*"], "deny")
        self.assertEqual(config["agent"][AGENT_ID]["permission"]["edit"], "allow")
        self.assertEqual(config["agent"][AGENT_ID]["permission"]["bash"], "allow")
        self.assertEqual(config["agent"][AGENT_ID]["permission"]["lsp"], "allow")
        self.assertIs(config["formatter"], True)
        self.assertIs(config["lsp"], True)
        self.assertEqual(config["share"], "disabled")

    def test_runs_without_a_model_argument_and_reads_the_workspace_candidate(self):
        observed = {}

        def fake_run(command, **kwargs):
            workspace = Path(command[command.index("--dir") + 1])
            (workspace / "generated.py").write_text("value = 1\n", encoding="utf-8")
            observed.update({"command": command, **kwargs})
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"type":"text","part":{"text":"done"}}\n',
                stderr="",
            )

        with patch("llmddos.opencode_harness.subprocess.run", side_effect=fake_run):
            result = self.harness().complete_noop(
                target=self.target(),
                messages=[{"role": "user", "content": "make a candidate"}],
                max_tokens=8192,
            )

        self.assertNotIn("--model", observed["command"])
        self.assertEqual(observed["input"].count("make a candidate"), 1)
        config = json.loads(observed["env"]["OPENCODE_CONFIG_CONTENT"])
        self.assertEqual(config["model"], "anaphylaxis-local/served/model")
        self.assertEqual(result["response_text"], "```python\nvalue = 1\n```")
        self.assertEqual(result["resolved_model"], "served/model")
        self.assertEqual(result["harness_delivery"], "workspace_file")
        self.assertIn("XDG_STATE_HOME", observed["env"])
        self.assertNotIn("OPENCODE_DISABLE_LSP_DOWNLOAD", observed["env"])
        self.assertEqual(observed["env"]["OPENCODE_EXPERIMENTAL_LSP_TOOL"], "true")

    def test_falls_back_to_assistant_text_when_no_file_was_created(self):
        stdout = (
            '{"type":"step_start","part":{}}\n'
            '{"type":"text","part":{"text":"```python\\nvalue = 2\\n```"}}\n'
        )
        completed = subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")

        with patch("llmddos.opencode_harness.subprocess.run", return_value=completed):
            result = self.harness().complete_noop(
                target=self.target(),
                messages=[{"role": "user", "content": "make a candidate"}],
                max_tokens=8192,
            )

        self.assertEqual(result["response_text"], "```python\nvalue = 2\n```")
        self.assertEqual(result["harness_delivery"], "assistant_text")

    def test_rejects_extra_workspace_files(self):
        def fake_run(command, **_kwargs):
            workspace = Path(command[command.index("--dir") + 1])
            (workspace / "generated.py").write_text("value = 1\n", encoding="utf-8")
            (workspace / "extra.txt").write_text("unexpected\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with patch("llmddos.opencode_harness.subprocess.run", side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, "unexpected workspace files"):
                self.harness().complete_noop(
                    target=self.target(),
                    messages=[{"role": "user", "content": "make a candidate"}],
                    max_tokens=8192,
                )

    def test_extracts_only_text_events(self):
        stdout = (
            '{"type":"tool_use","part":{"text":"ignored"}}\n'
            '{"type":"text","part":{"text":"first"}}\n'
            "not-json\n"
            '{"type":"text","part":{"text":" second"}}\n'
        )

        self.assertEqual(extract_opencode_text(stdout), "first second")


if __name__ == "__main__":
    unittest.main()
