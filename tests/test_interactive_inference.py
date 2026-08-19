import argparse
import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "interactive_inference.py"
SPEC = importlib.util.spec_from_file_location("interactive_inference", SCRIPT)
interactive = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(interactive)


class FakeProvider:
    def __init__(self):
        self.requests = []

    def complete(self, **request):
        self.requests.append(request)
        return {
            "response_text": "hello from model",
            "resolved_model": request["model"],
            "finish_reason": "stop",
            "usage": {"completion_tokens": 3},
            "latency_ms": 4.2,
        }

    def stream_complete(self, **request):
        self.requests.append(request)
        request["on_delta"]("content", "hello from model")
        return {
            "response_text": "hello from model",
            "reasoning_text": "",
            "resolved_model": request["model"],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            "latency_ms": 4.2,
        }


def make_args(**overrides):
    values = {
        "max_tokens": 8192,
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.05,
        "context_window": 32768,
        "compact_at": 0.70,
        "keep_turns": 4,
        "no_auto_compact": False,
        "thinking": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class InteractiveInferenceTests(unittest.TestCase):
    def test_model_is_discovered_instead_of_accepted_as_an_argument(self):
        args = interactive.build_parser().parse_args([])

        self.assertFalse(hasattr(args, "model"))
        self.assertNotIn("--model", interactive.build_parser().format_help())
        self.assertEqual(args.temperature, 0.7)
        self.assertEqual(args.top_p, 0.95)

    def test_default_config_has_one_server_discovered_route(self):
        base_url = "http://127.0.0.1:19002/v1"
        config = interactive.load_endpoint_config(
            interactive.DEFAULT_CONFIG,
            environ={
                "GUARDRAIL_SSH_TARGET": "user@example.test",
                "GUARDRAIL_REMOTE_HOST": "127.0.0.1",
                "REPEL_LOCAL_PORT": "19002",
                "REPEL_REMOTE_PORT": "19002",
                "REPEL_BASE_URL": base_url,
            },
        )
        route = config["models"]["server"]

        self.assertEqual(route["base_url"], base_url)
        self.assertEqual(config["_discovery_route"], "server")
        self.assertEqual(len(config["models"]), 1)
        self.assertEqual(len(config["ssh"]["forwards"]), 1)
        self.assertEqual(route["minimum_max_tokens"], 8192)
        self.assertEqual(route["tool_mode"], "prompt_json")

    def test_prompt_loop_sends_history_and_prints_response(self):
        provider = FakeProvider()
        histories = {"qwen": []}
        args = make_args()

        with patch("builtins.input", side_effect=["hello", "/quit"]):
            output = io.StringIO()
            with redirect_stdout(output):
                status = interactive._prompt_loop(
                    provider, ["qwen"], ["qwen"], histories, "", args
                )

        self.assertEqual(status, 0)
        self.assertEqual(provider.requests[0]["max_tokens"], 8192)
        self.assertEqual(
            provider.requests[0]["messages"], [{"role": "user", "content": "hello"}]
        )
        self.assertEqual(histories["qwen"][-1]["content"], "hello from model")
        self.assertIn("hello from model", output.getvalue())

    def test_native_editor_returns_multiline_paste_as_one_message(self):
        session = unittest.mock.MagicMock()
        session.prompt.return_value = "first line\n    indented line\nlast line"

        message = interactive.read_message(session)

        self.assertEqual(message, "first line\n    indented line\nlast line")
        session.prompt.assert_called_once_with("\nyou> ")

    def test_multiline_text_starting_with_slash_is_not_a_command(self):
        provider = FakeProvider()
        histories = {"qwen": []}
        session = unittest.mock.MagicMock()
        session.prompt.side_effect = ["/tmp/example\nsecond line", "/quit"]

        status = interactive._prompt_loop(
            provider,
            ["qwen"],
            ["qwen"],
            histories,
            "",
            make_args(),
            session,
        )

        self.assertEqual(status, 0)
        self.assertEqual(
            provider.requests[0]["messages"][0]["content"],
            "/tmp/example\nsecond line",
        )

    def test_repetition_guard_detects_word_and_phrase_loops(self):
        self.assertTrue(interactive.has_repetition_loop("implant " * 24))
        self.assertTrue(interactive.has_repetition_loop("alpha beta gamma " * 8))
        self.assertFalse(
            interactive.has_repetition_loop(
                "This is a normal response with varied words and no repeating tail."
            )
        )

    def test_glm_does_not_receive_qwen_chat_template_arguments(self):
        body = interactive.vllm_extra_body(
            "glm-4.7-flash-abliterated", make_args()
        )

        self.assertEqual(body, {"repetition_penalty": 1.05})

    def test_qwen_3_6_receives_qwen_sampling_and_thinking_arguments(self):
        body = interactive.vllm_extra_body(
            "qwen3.6-35b-a3b-claude-4.7-opus-abliterated", make_args()
        )

        self.assertEqual(body["top_k"], 20)
        self.assertEqual(body["min_p"], 0.0)
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": True})

    def test_compaction_keeps_recent_turn_and_summary(self):
        provider = FakeProvider()
        history = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user", "content": "second question"},
            {"role": "assistant", "content": "second answer"},
        ]

        compacted, changed = interactive.compact_history(
            provider, "qwen", history, make_args(), keep_turns=1
        )

        self.assertTrue(changed)
        self.assertEqual(compacted[0]["role"], "system")
        self.assertIn("hello from model", compacted[0]["content"])
        self.assertEqual(compacted[-2:], history[-2:])

    def test_repeated_compaction_rolls_summary_into_one_system_message(self):
        provider = FakeProvider()
        args = make_args()
        history = [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "answer one"},
            {"role": "user", "content": "two"},
            {"role": "assistant", "content": "answer two"},
        ]
        first, _ = interactive.compact_history(
            provider, "qwen", history, args, keep_turns=1
        )
        extended = first + [
            {"role": "user", "content": "three"},
            {"role": "assistant", "content": "answer three"},
        ]

        second, changed = interactive.compact_history(
            provider, "qwen", extended, args, keep_turns=1
        )

        self.assertTrue(changed)
        self.assertEqual(sum(item["role"] == "system" for item in second), 1)
        self.assertTrue(second[0]["content"].startswith("Be concise."))
        self.assertEqual(second[0]["content"].count(interactive.SUMMARY_HEADER), 1)


if __name__ == "__main__":
    unittest.main()
