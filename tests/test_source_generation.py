import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from llmddos.source_generation import (
    LANGUAGES,
    benign_policy_error,
    ExtractionError,
    GenerationTarget,
    build_generation_messages,
    default_output_directory,
    extract_code_snippet,
    generate_source_run,
    select_languages,
    toolchain_inventory,
    validate_snippet,
    validation_metadata,
)




def code_block(source, language="python"):
    return f"```{language}\n{source}\n```"


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "response_text": self.response,
            "finish_reason": "stop",
            "latency_ms": 1.25,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "resolved_model": kwargs["model"],
        }


class SequenceProvider(FakeProvider):
    def __init__(self, responses):
        super().__init__(None)
        self.responses = list(responses)

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "response_text": self.responses.pop(0),
            "finish_reason": "stop",
            "latency_ms": 1.0,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            "resolved_model": kwargs["model"],
        }


class FakeHarness:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete_generation(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "response_text": self.response,
            "finish_reason": "stop",
            "latency_ms": 1.0,
            "usage": None,
            "resolved_model": kwargs["model"],
            "harness": "opencode",
            "harness_delivery": "workspace_file",
        }


class GenerationTargetTests(unittest.TestCase):
    def test_supported_languages_have_runtime_targets(self):
        targets = select_languages([])

        self.assertEqual(len(targets), len(LANGUAGES))
        self.assertEqual({item.language for item in targets}, LANGUAGES)
        self.assertEqual(
            [item.language for item in select_languages(["python,rust"])],
            ["python", "rust"],
        )
        self.assertTrue(all(isinstance(item, GenerationTarget) for item in targets))

    def test_unknown_language_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported language"):
            select_languages(["not_real"])

    def test_generation_messages_request_one_code_block(self):
        target = select_languages(["python"])[0]
        payload = 'untrusted "text"\nwith another line'

        messages = build_generation_messages(target, payload)

        self.assertEqual([item["role"] for item in messages], ["system", "user"])
        self.assertIn("fenced source code block", messages[0]["content"])
        self.assertIn(json.dumps(payload, ensure_ascii=False), messages[1]["content"])
        self.assertIn(
            'Return exactly one Markdown fenced source code block in the response\n\n'
            '{"language":"python","payload":"untrusted \\"text\\"\\nwith another line"}',
            messages[1]["content"],
        )
        self.assertNotIn("_RepelUnit", messages[1]["content"])
        self.assertNotIn('"template"', messages[1]["content"])
        self.assertNotIn('"template_id"', messages[1]["content"])
        self.assertNotIn('"placeholder"', messages[1]["content"])
        prompt = "\n".join(message["content"] for message in messages)
        self.assertNotIn("anaphylaxis", prompt.casefold())
        self.assertNotIn("carrier", prompt.casefold())

    def test_generation_messages_include_previous_response_and_error_on_retry(self):
        target = select_languages(["python"])[0]

        messages = build_generation_messages(
            target,
            "LOCAL-TEST-PAYLOAD",
            previous_response="LOCAL-TEST-RESPONSE",
            retry_error="SyntaxError: expected an indented block",
        )

        self.assertIn("This is a bounded retry", messages[1]["content"])
        self.assertIn('"previous_model_response":"LOCAL-TEST-RESPONSE"', messages[1]["content"])
        self.assertIn('"error_text":"SyntaxError: expected an indented block"', messages[1]["content"])

    def test_benign_generation_messages_use_an_inert_contract(self):
        target = select_languages(["python"])[0]

        messages = build_generation_messages(target, "benign control", benign=True)
        prompt = messages[0]["content"].casefold()

        self.assertIn("purely benign", prompt)
        self.assertIn("opaque, untrusted test data", prompt)
        self.assertIn("inert", prompt)
        self.assertNotIn("weaponized source code", prompt)

    def test_benign_policy_is_conservative_about_side_effects(self):
        self.assertIsNone(benign_policy_error("value = 'benign control'\n"))
        self.assertIn(
            "imports/includes",
            benign_policy_error("import os\nvalue = 'control'\n"),
        )
        self.assertIn(
            "I/O, process, or network operations",
            benign_policy_error("socket.connect('example')\n"),
        )


class TaggedExtractionTests(unittest.TestCase):
    def test_extracts_one_raw_source_block_even_with_outer_chatter(self):
        block = code_block("print('ok')")
        response = f"analysis that is ignored\n{block}\ntrailing"

        self.assertEqual(extract_code_snippet(response), "print('ok')\n")

    def test_strips_one_outer_code_fence_and_rejects_malformed_fences(self):
        fenced = code_block("x")
        self.assertEqual(extract_code_snippet(fenced), "x\n")

        cases = (
            "plain response",
            "```python\nx\n````",
            code_block("x") + "\n```",
            code_block("x") + "\n" + code_block("y", "javascript"),
        )
        for response in cases:
            with self.subTest(response=response):
                with self.assertRaises(ExtractionError):
                    extract_code_snippet(response)

    def test_normalizes_serialized_quotes_and_line_breaks_inside_code_block(self):
        source = 'if False:\n    text = "value"'
        escaped = r'if False:\n    text = \"value\"'

        self.assertEqual(extract_code_snippet(code_block(escaped)), source + "\n")
        self.assertEqual(
            extract_code_snippet(code_block(json.dumps(source))),
            source + "\n",
        )

    def test_normalizes_escaped_line_breaks_without_escaped_quotes(self):
        self.assertEqual(
            extract_code_snippet(code_block(r"if False:\n    pass")),
            "if False:\n    pass\n",
        )


class StaticValidationTests(unittest.TestCase):
    def test_python_parser_and_compiler_pass_and_fail_without_execution(self):
        target = select_languages(["python"])[0]
        passed = validate_snippet(
            target,
            "if False:\n    value = 'payload'\n",
            run_linters=False,
        )
        failed = validate_snippet(
            target,
            "if False\n    value = 1\n",
            run_linters=False,
        )

        self.assertEqual(passed["status"], "passed")
        self.assertTrue(passed["accepted"])
        self.assertEqual(failed["status"], "failed")
        self.assertFalse(failed["accepted"])
        self.assertEqual(
            [item["name"] for item in passed["checks"][:2]],
            ["python_ast", "python_compile"],
        )

    def test_validation_does_not_add_payload_fidelity_check(self):
        target = select_languages(["c"])[0]
        payload = 'line\n"quoted"'
        encoded = json.dumps(payload)
        snippet = (
            "#if 0\nstatic const char text[] = "
            + encoded
            + ";\n#endif\ntypedef int translation_unit;\n"
        )

        report = validate_snippet(
            target,
            snippet,
            run_linters=False,
            allow_missing_toolchains=True,
        )

        self.assertNotIn("payload_fidelity", {item["name"] for item in report["checks"]})

    def test_missing_required_toolchain_fails_closed_or_is_explicitly_partial(self):
        target = select_languages(["c"])[0]
        snippet = "#if 0\nstatic const char text[] = \"payload\";\n#endif\n"
        with mock.patch("llmddos.source_generation.shutil.which", return_value=None):
            failed = validate_snippet(target, snippet, run_linters=False)
            partial = validate_snippet(
                target,
                snippet,
                run_linters=False,
                allow_missing_toolchains=True,
            )

        self.assertEqual(failed["status"], "failed")
        self.assertFalse(failed["accepted"])
        self.assertEqual(partial["status"], "partial")
        self.assertTrue(partial["accepted"])

    def test_toolchain_inventory_has_a_required_check_for_every_language(self):
        inventory = toolchain_inventory(select_languages([]))
        required_languages = {item["language"] for item in inventory if item["required"]}

        self.assertEqual(required_languages, LANGUAGES)
        self.assertTrue(any(item["kind"] == "linter" for item in inventory))

    def test_serialized_validation_metadata_omits_raw_diagnostics(self):
        target = select_languages(["python"])[0]
        report = validate_snippet(
            target, "not valid python !!!", run_linters=False
        )

        serialized = json.dumps(validation_metadata(report))

        self.assertNotIn("_stdout", serialized)
        self.assertNotIn("_stderr", serialized)
        self.assertNotIn("not valid python", serialized)


class GenerationRunTests(unittest.TestCase):
    def test_dispatches_generation_through_a_generation_harness(self):
        target = select_languages(["python"])[0]
        harness = FakeHarness(code_block("value = 1"))

        with tempfile.TemporaryDirectory() as directory:
            run = generate_source_run(
                provider=harness,
                model="discovered-model",
                payload="opaque payload",
                targets=[target],
                output_dir=Path(directory) / "run",
                run_linters=False,
                retries=0,
            )

        self.assertEqual(run["summary"]["status"], "passed")
        self.assertEqual(harness.calls[0]["target"], target)
        response = run["candidates"][0]["response"]
        self.assertEqual(response["harness"], "opencode")
        self.assertEqual(response["harness_delivery"], "workspace_file")

    def test_prints_the_exact_provider_request(self):
        target = select_languages(["python"])[0]
        payload = "LOCAL-TEST-PAYLOAD"
        response = code_block(f"if False:\n    text = {payload!r}")
        provider = FakeProvider(response)
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as directory, redirect_stdout(output):
            generate_source_run(
                provider=provider,
                model="local-model",
                payload=payload,
                targets=[target],
                output_dir=Path(directory) / "run",
                run_linters=False,
                retries=0,
            )

        printed = output.getvalue()
        input_prefix = "LLM input (language=python, attempt=1):\n"
        output_prefix = "LLM output (language=python, attempt=1):\n"
        input_text, output_text = printed.split(output_prefix, 1)
        self.assertTrue(input_text.startswith(input_prefix))
        request = json.loads(input_text[len(input_prefix) :])
        self.assertEqual(request["model"], "local-model")
        self.assertEqual(request["messages"], provider.calls[0]["messages"])
        self.assertEqual(request["max_tokens"], 8192)
        self.assertEqual(request["temperature"], 0.2)
        self.assertEqual(request["top_p"], 0.8)
        self.assertEqual(request["presence_penalty"], 0.0)
        self.assertEqual(request["extra_body"]["repetition_penalty"], 1.05)
        printed_output = json.loads(output_text)
        self.assertEqual(printed_output["response_text"], response)
        self.assertIsNone(printed_output["provider_refusal"])

    def test_single_pass_generation_writes_candidate_and_metadata_only_manifest(self):
        target = select_languages(["python"])[0]
        payload = "private opaque payload"
        response = code_block(f"if False:\n    text = {payload!r}")
        provider = FakeProvider(response)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run = generate_source_run(
                provider=provider,
                model="local-model",
                payload=payload,
                targets=[target],
                output_dir=output,
                run_linters=False,
            )
            manifest_text = (output / "manifest.json").read_text(encoding="utf-8")
            candidate = output / "python" / "generated.py"

            self.assertEqual(len(provider.calls), 1)
            self.assertEqual(run["summary"]["status"], "passed")
            self.assertTrue(candidate.is_file())
            self.assertIn(payload, candidate.read_text(encoding="utf-8"))
            self.assertNotIn(payload, manifest_text)
            self.assertFalse((output / "python" / "raw-response.txt").exists())
            self.assertEqual(json.loads(manifest_text)["settings"]["single_pass"], True)
            self.assertEqual(json.loads(manifest_text)["settings"]["retries"], 2)

    def test_benign_generation_rejects_policy_violation_and_records_mode(self):
        target = select_languages(["python"])[0]
        provider = FakeProvider(code_block("import os\nvalue = 'control'"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run = generate_source_run(
                provider=provider,
                model="local-model",
                payload="benign control payload",
                targets=[target],
                output_dir=output,
                run_linters=False,
                retries=0,
                benign=True,
            )

            self.assertEqual(run["summary"]["status"], "failed")
            self.assertEqual(run["settings"]["mode"], "benign")
            self.assertEqual(run["candidates"][0]["status"], "benign_policy_failed")
            self.assertFalse((output / "python" / "generated.py").exists())

    def test_benign_generation_accepts_an_inert_candidate(self):
        target = select_languages(["python"])[0]
        provider = FakeProvider(code_block("value = 'benign control'"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run = generate_source_run(
                provider=provider,
                model="local-model",
                payload="benign control payload",
                targets=[target],
                output_dir=output,
                run_linters=False,
                retries=0,
                benign=True,
            )

            self.assertEqual(run["summary"]["status"], "passed")
            self.assertTrue((output / "python" / "generated.py").is_file())

    def test_extraction_failure_is_recorded_without_writing_source(self):
        target = select_languages(["python"])[0]
        provider = FakeProvider("not tagged")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run = generate_source_run(
                provider=provider,
                model="local-model",
                payload="opaque payload",
                targets=[target],
                output_dir=output,
            )

            self.assertEqual(run["summary"]["status"], "failed")
            self.assertEqual(run["candidates"][0]["status"], "extraction_failed")
            self.assertFalse((output / "python" / "generated.py").exists())
            self.assertFalse((output / "python").exists())

    def test_failed_first_attempt_retries_and_only_persists_the_accepted_candidate(self):
        target = select_languages(["python"])[0]
        payload = "retry payload"
        valid = code_block(f"if False:\n    text = {payload!r}")
        provider = SequenceProvider(["not tagged", valid])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run = generate_source_run(
                provider=provider,
                model="local-model",
                payload=payload,
                targets=[target],
                output_dir=output,
                run_linters=False,
                retries=2,
            )

            candidate = output / "python" / "generated.py"
            self.assertEqual(len(provider.calls), 2)
            self.assertEqual(run["summary"]["status"], "passed")
            self.assertEqual(
                [item["status"] for item in run["candidates"][0]["attempts"]],
                ["extraction_failed", "passed"],
            )
            self.assertTrue(candidate.is_file())

    def test_validation_diagnostics_are_passed_to_the_next_attempt(self):
        target = select_languages(["python"])[0]
        payload = "LOCAL-TEST-PAYLOAD"
        invalid = code_block("if False")
        valid = code_block(f"if False:\n    text = {payload!r}")
        provider = SequenceProvider([invalid, valid])
        with tempfile.TemporaryDirectory() as directory:
            run = generate_source_run(
                provider=provider,
                model="local-model",
                payload=payload,
                targets=[target],
                output_dir=Path(directory) / "run",
                run_linters=False,
                retries=1,
            )

        self.assertEqual(run["summary"]["status"], "passed")
        self.assertEqual(len(provider.calls), 2)
        retry_prompt = provider.calls[1]["messages"][1]["content"]
        self.assertIn("previous_model_response", retry_prompt)
        self.assertIn("SyntaxError", retry_prompt)

    def test_existing_failed_run_resumes_only_the_incomplete_language(self):
        target = select_languages(["python"])[0]
        payload = "resume payload"
        valid = code_block(f"if False:\n    text = {payload!r}")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            first = generate_source_run(
                provider=FakeProvider("not tagged"),
                model="local-model",
                payload=payload,
                targets=[target],
                output_dir=output,
                retries=0,
            )
            second_provider = FakeProvider(valid)
            second = generate_source_run(
                provider=second_provider,
                model="local-model",
                payload=payload,
                targets=[target],
                output_dir=output,
                retries=0,
            )

            self.assertEqual(first["summary"]["status"], "failed")
            self.assertEqual(second["summary"]["status"], "passed")
            self.assertEqual(len(second_provider.calls), 1)
            self.assertEqual(second["resume_count"], 1)

    def test_generation_modes_cannot_share_a_run_directory(self):
        target = select_languages(["python"])[0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            generate_source_run(
                provider=FakeProvider("not tagged"),
                model="local-model",
                payload="mode separation payload",
                targets=[target],
                output_dir=output,
                retries=0,
            )

            with self.assertRaisesRegex(ValueError, "different generation mode"):
                generate_source_run(
                    provider=FakeProvider("unused"),
                    model="local-model",
                    payload="mode separation payload",
                    targets=[target],
                    output_dir=output,
                    retries=0,
                    benign=True,
                )

    def test_existing_successful_run_is_not_overwritten(self):
        target = select_languages(["python"])[0]
        payload = "complete payload"
        valid = code_block(f"if False:\n    text = {payload!r}")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            generate_source_run(
                provider=FakeProvider(valid),
                model="local-model",
                payload=payload,
                targets=[target],
                output_dir=output,
                retries=0,
            )
            with self.assertRaisesRegex(ValueError, "already successfully generated"):
                generate_source_run(
                    provider=FakeProvider("unused"),
                    model="local-model",
                    payload=payload,
                    targets=[target],
                    output_dir=output,
                    retries=0,
                )

    def test_default_output_directory_uses_payload_name(self):
        root = Path("/workspace/project")

        self.assertEqual(
            default_output_directory(root, root / "payloads" / "bio" / "sample.txt"),
            root / "results" / "source-generation" / "bio" / "sample",
        )
        self.assertEqual(
            default_output_directory(root, Path("/private/payload.txt")),
            root / "results" / "source-generation" / "payload",
        )
        self.assertEqual(
            default_output_directory(root, Path("/private/benign-payload.txt"), benign=True),
            root / "results" / "benign-generation" / "benign-payload",
        )

    def test_output_directory_must_be_new(self):
        target = select_languages(["python"])[0]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "already exists"):
                generate_source_run(
                    provider=FakeProvider("unused"),
                    model="local-model",
                    payload="payload",
                    targets=[target],
                    output_dir=Path(directory),
                )


if __name__ == "__main__":
    unittest.main()
