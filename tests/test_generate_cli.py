import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest import mock

from clanker_repellent.cli import generate_cli as cli
from clanker_repellent.cli.generate_cli import build_parser, main


class GenerateCliTests(unittest.TestCase):
    def test_task_contract_requires_benign_and_matching_format_before_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'contract.json'
            path.write_text(json.dumps({'schema_version':1,'language':'python','function':{'name':'increment','parameters':['value']},
                                       'examples':[{'inputs':[1],'expected':2}]}))
            for arguments,message in [([], '--contract requires --benign'),(['--benign','--format','json'],'matching language/format')]:
                with self.subTest(arguments=arguments),redirect_stdout(io.StringIO()) as output,mock.patch.object(cli,'load_endpoint_config') as load:
                    status=main(['/unused','--contract',str(path),*arguments])
                    self.assertEqual(status,2); self.assertIn(message,output.getvalue()); load.assert_not_called()

    def test_task_contract_infers_format_and_records_requested_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); contract=root/'contract.json'; prompt=root/'request.txt'; prompt.write_text('Benign increment helper')
            contract.write_text(json.dumps({'schema_version':1,'language':'python','function':{'name':'increment','parameters':['value']},
                                           'examples':[{'inputs':[1],'expected':2}]}))
            provider=mock.Mock(spec=['wait_for_model','complete']); provider.wait_for_model.return_value='fixture-model'
            provider.complete.return_value={'response_text':'```python\ndef increment(value):\n    return value+1\n```','resolved_model':'fixture-model','finish_reason':'stop'}
            with redirect_stdout(io.StringIO()),mock.patch.object(cli,'load_endpoint_config',return_value={}),mock.patch.object(cli,'RoutedOpenAICompatibleProvider',return_value=provider):
                status=main([str(prompt),'--benign','--contract',str(contract),'--seed','42','--skip-linters','--output-dir',str(root/'run')])
            self.assertEqual(status,0)
            manifest=json.loads((root/'run/manifest.json').read_text())
            self.assertEqual(manifest['settings']['seed'],42); self.assertEqual(manifest['settings']['mode'],'benign')
            self.assertEqual(manifest['candidates'][0]['language'],'python')
            self.assertTrue(any(check['name']=='task_contract' and check['status']=='passed' for check in manifest['candidates'][0]['validation']['checks']))

    def test_help_uses_server_model_discovery(self):
        help_text = build_parser().format_help()

        self.assertIn("discovered from the server", help_text)
        self.assertIn("--harness {direct,opencode}", help_text)
        self.assertIn("--benign", help_text)
        self.assertNotIn("--model", help_text)
        self.assertIsNone(build_parser().parse_args([]).config)

    def test_opencode_harness_options_parse_without_a_model(self):
        defaults = build_parser().parse_args(["--harness", "opencode"])
        args = build_parser().parse_args(
            ["--harness", "opencode", "--opencode-timeout", "45"]
        )

        self.assertEqual(defaults.opencode_timeout, 900.0)
        self.assertEqual(args.harness, "opencode")
        self.assertEqual(args.opencode_timeout, 45.0)
        self.assertFalse(hasattr(args, "model"))

    def test_benign_mode_parses_as_a_generation_control(self):
        args = build_parser().parse_args(["--benign"])

        self.assertTrue(args.benign)

    def test_content_logging_is_opt_in(self):
        self.assertFalse(build_parser().parse_args([]).show_content)
        self.assertTrue(build_parser().parse_args(["--show-content"]).show_content)

    def test_no_thinking_requires_a_harness_that_forwards_it(self):
        output = io.StringIO()
        with redirect_stdout(output), mock.patch.object(cli, "load_endpoint_config", return_value={}):
            status = main(["--payload", "/unused", "--harness", "opencode", "--no-thinking"])
        self.assertEqual(status, 2)
        self.assertIn("--no-thinking requires --harness direct", output.getvalue())

    def test_lists_languages_without_loading_endpoint_configuration(self):
        output = io.StringIO()

        with redirect_stdout(output):
            status = main(["--list-languages"])

        self.assertEqual(status, 0)
        languages = output.getvalue().splitlines()
        self.assertEqual(len(languages), 23)
        self.assertIn("json\tgenerated.json", languages)
        self.assertIn("http\tgenerated.http", languages)
        self.assertIn("binary-info\tgenerated.binary.json", languages)
        self.assertIn("llvm\tgenerated.ll", languages)
        self.assertIn("lua\tgenerated.lua", languages)
        self.assertIn("sql\tgenerated.sql", languages)
        self.assertIn("html\tgenerated.html", languages)
        self.assertIn("python\tgenerated.py", languages)

    def test_lists_toolchains_without_a_payload(self):
        output = io.StringIO()

        with redirect_stdout(output):
            status = main(["--list-toolchains", "--language", "python"])

        self.assertEqual(status, 0)
        self.assertIn("python_ast\tparser\trequired", output.getvalue())

    def test_payload_is_required_for_generation(self):
        output = io.StringIO()

        with redirect_stdout(output):
            status = main([])

        self.assertEqual(status, 2)
        self.assertIn("input file or folder", output.getvalue())


class FolderGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "benign"
        self.inputs.mkdir()
        self.output = self.root / "output"
        self.provider = mock.Mock(spec=["wait_for_model", "complete"])
        self.provider.wait_for_model.return_value = "fixture-model"
        self.provider.complete.return_value = {
            "response_text": "```python\ndef increment(value):\n    return value + 1\n```",
            "finish_reason": "stop", "resolved_model": "fixture-model",
        }

    def invoke(self, *arguments, config=None):
        capture = io.StringIO()
        with mock.patch.object(cli, "load_endpoint_config", return_value=config or {}), mock.patch.object(
            cli, "RoutedOpenAICompatibleProvider", return_value=self.provider
        ), redirect_stdout(capture):
            status = main([str(self.inputs), "--benign", "--language", "python", "--skip-linters",
                           "--output-dir", str(self.output), *arguments])
        return status, capture.getvalue()

    def test_directory_recurses_handles_spaces_and_keeps_same_named_inputs_separate(self):
        (self.inputs / "note.txt").write_text("First private input")
        nested = self.inputs / "nested folder"
        nested.mkdir()
        (nested / "note.txt").write_text("Second private input")
        (self.inputs / "upper.TXT").write_text("Third private input")
        (self.inputs / "skip.md").write_text("Not an input")
        status, printed = self.invoke()
        self.assertEqual(status, 0)
        self.assertEqual(self.provider.complete.call_count, 3)
        self.assertTrue((self.output / "note.txt" / "manifest.json").is_file())
        self.assertTrue((self.output / "nested folder" / "note.txt" / "manifest.json").is_file())
        self.assertNotIn("private input", printed)
        self.assertNotIn("ordinary documentation", printed)

    def test_directory_skips_symlink_files_and_directories(self):
        (self.inputs / "note.txt").write_text("Ordinary input")
        external = self.root / "external"
        external.mkdir()
        (external / "other.txt").write_text("External input")
        (self.inputs / "link.txt").symlink_to(external / "other.txt")
        (self.inputs / "linked folder").symlink_to(external, target_is_directory=True)
        status, _ = self.invoke()
        self.assertEqual(status, 0)
        self.assertEqual(self.provider.complete.call_count, 1)

    def test_empty_directory_does_not_contact_endpoint(self):
        status, printed = self.invoke()
        self.assertEqual(status, 2)
        self.assertIn("no .txt files", printed)
        self.provider.wait_for_model.assert_not_called()

    def test_output_inside_input_is_rejected_before_generation(self):
        status, printed = self.invoke("--output-dir", str(self.inputs / "generated"))
        self.assertEqual(status, 2)
        self.assertIn("outside the input directory", printed)
        self.provider.wait_for_model.assert_not_called()

    def test_invalid_input_does_not_prevent_other_inputs_from_running(self):
        (self.inputs / "a.txt").write_bytes(b"\xff")
        (self.inputs / "b.txt").write_text("Ordinary input")
        status, printed = self.invoke()
        self.assertEqual(status, 1)
        self.assertEqual(self.provider.complete.call_count, 1)
        self.assertIn('"failed_inputs": 1', printed)
        self.assertTrue((self.output / "b.txt" / "manifest.json").is_file())

    def test_reusing_output_directory_preserves_completed_inputs(self):
        (self.inputs / "note.txt").write_text("Ordinary input")
        self.assertEqual(self.invoke()[0], 0)
        source = self.output / "note.txt" / "python" / "generated.py"
        original_mtime = source.stat().st_mtime_ns
        status, printed = self.invoke()
        self.assertEqual(status, 0)
        self.assertIn('"already_complete_inputs": 1', printed)
        self.assertEqual(self.provider.complete.call_count, 1)
        self.assertEqual(source.stat().st_mtime_ns, original_mtime)

    def test_folder_catalog_ids_are_distinct_for_same_named_inputs(self):
        (self.inputs / "note.txt").write_text("Ordinary input")
        nested = self.inputs / "nested"
        nested.mkdir()
        (nested / "note.txt").write_text("Another ordinary input")
        with mock.patch("clanker_repellent.payload.catalog.import_run") as register:
            status, _ = self.invoke("--catalog", str(self.root / "catalog"), "--register-prefix", "sample")
        self.assertEqual(status, 0)
        self.assertEqual(register.call_count, 2)
        self.assertEqual(len({call.kwargs["prefix"] for call in register.call_args_list}), 2)

    def test_one_tunnel_is_kept_open_for_the_entire_folder(self):
        (self.inputs / "a.txt").write_text("Ordinary input")
        (self.inputs / "b.txt").write_text("Another ordinary input")
        state = {"depth": 0, "starts": 0}

        @contextmanager
        def tunnel(config, batch_ssh):
            if not state["depth"]:
                state["starts"] += 1
            state["depth"] += 1
            try:
                yield {"status": "reused"}
            finally:
                state["depth"] -= 1

        with mock.patch.object(cli, "_tunnel_context", side_effect=tunnel):
            status, _ = self.invoke()
        self.assertEqual(status, 0)
        self.assertEqual(state, {"depth": 0, "starts": 1})

    def test_positional_file_uses_local_configuration_defaults_and_explicit_overrides(self):
        source = self.root / "note.txt"
        source.write_text("Ordinary input")
        local = self.root / ".repel-generate.json"
        local.write_text("{}")
        config = {"generation": {"languages": ["python"], "no_thinking": True,
                                  "batch_ssh": True, "max_tokens": 123}}
        for flags, thinking in [([], False), (["--thinking", "--max-tokens", "321"], True)]:
            with self.subTest(flags=flags), mock.patch.object(cli, "LOCAL_CONFIG", local), mock.patch.object(
                cli, "load_endpoint_config", return_value=config
            ) as load, mock.patch.object(cli, "RoutedOpenAICompatibleProvider", return_value=self.provider), redirect_stdout(io.StringIO()):
                output = self.root / ("thinking" if thinking else "no-thinking")
                status = main([str(source), "--benign", "--skip-linters", "--output-dir", str(output), *flags])
            self.assertEqual(status, 0)
            load.assert_called_once_with(local)
            request = self.provider.complete.call_args.kwargs
            self.assertEqual(request["max_tokens"], 321 if thinking else 123)
            self.assertEqual(request["extra_body"].get("reasoning_effort"), None if thinking else "none")

    def test_explicit_config_wins_over_local_config(self):
        source = self.root / "note.txt"
        source.write_text("Ordinary input")
        explicit = self.root / "explicit.json"
        with mock.patch.object(cli, "load_endpoint_config", return_value={}) as load, mock.patch.object(
            cli, "RoutedOpenAICompatibleProvider", return_value=self.provider
        ), redirect_stdout(io.StringIO()):
            status = main([str(source), "--benign", "--config", str(explicit), "--language", "python",
                           "--skip-linters", "--output-dir", str(self.output)])
        self.assertEqual(status, 0)
        load.assert_called_once_with(explicit)

    def test_endpoint_override_is_forwarded_and_saved_preferences_still_apply(self):
        source=self.root/'note.txt'
        source.write_text('Ordinary input')
        config={'generation':{'languages':['python'],'max_tokens':345}}
        with mock.patch.object(cli,'load_endpoint_config',return_value=config) as load, mock.patch.object(
            cli,'RoutedOpenAICompatibleProvider',return_value=self.provider
        ),redirect_stdout(io.StringIO()):
            status=main([str(source),'--benign','--endpoint','http://127.0.0.1:18473/v1',
                         '--skip-linters','--output-dir',str(self.output)])
        self.assertEqual(status,0)
        self.assertEqual(load.call_args.kwargs,{'endpoint_override':'http://127.0.0.1:18473/v1'})
        self.assertEqual(self.provider.complete.call_args.kwargs['max_tokens'],345)

    def test_input_forms_are_mutually_exclusive(self):
        status, printed = self.invoke("--payload", str(self.root / "another.txt"))
        self.assertEqual(status, 2)
        self.assertIn("choose INPUT", printed)
        self.provider.complete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
