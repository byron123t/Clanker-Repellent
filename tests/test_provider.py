import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from llmddos.provider import (
    OpenAICompatibleProvider,
    RoutedOpenAICompatibleProvider,
    _extract_prompt_final,
    _extract_prompt_tool_call,
    _health_url,
)


class ProviderToolTests(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
        self.provider.client = MagicMock()

    @patch("llmddos.provider.time.monotonic", side_effect=[10.0, 10.125])
    def test_complete_with_tools_normalizes_tool_calls_and_metadata(self, _monotonic):
        usage = MagicMock()
        usage.model_dump.return_value = {
            "prompt_tokens": 12,
            "completion_tokens": 7,
            "total_tokens": 19,
        }
        message = SimpleNamespace(
            content=None,
            refusal=None,
            tool_calls=[
                SimpleNamespace(
                    id="call_123",
                    function=SimpleNamespace(
                        name="lookup_artifact",
                        arguments='{"artifact_id":"ORCHID-41"}',
                    ),
                )
            ],
        )
        self.provider.client.chat.completions.create.return_value = SimpleNamespace(
            id="request_123",
            model="resolved-model",
            system_fingerprint="fingerprint",
            service_tier="default",
            usage=usage,
            choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        )
        messages = [{"role": "user", "content": "Find the artifact"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "lookup_artifact",
                    "description": "Look up an artifact",
                    "parameters": {"type": "object"},
                },
            }
        ]

        result = self.provider.complete_with_tools(
            model="test-model",
            messages=messages,
            tools=tools,
            max_tokens=80,
            temperature=0.2,
        )

        self.provider.client.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=messages,
            tools=tools,
            max_tokens=80,
            temperature=0.2,
        )
        self.assertEqual(result["content"], "")
        self.assertIsNone(result["provider_refusal"])
        self.assertEqual(
            result["tool_calls"],
            [
                {
                    "id": "call_123",
                    "name": "lookup_artifact",
                    "arguments": '{"artifact_id":"ORCHID-41"}',
                }
            ],
        )
        self.assertEqual(result["finish_reason"], "tool_calls")
        self.assertEqual(result["latency_ms"], 125.0)
        self.assertEqual(result["usage"]["total_tokens"], 19)
        self.assertEqual(result["provider_request_id"], "request_123")
        self.assertEqual(result["resolved_model"], "resolved-model")
        self.assertEqual(result["system_fingerprint"], "fingerprint")
        self.assertEqual(result["service_tier"], "default")

    def test_complete_with_tools_handles_content_refusal_and_no_tool_calls(self):
        message = SimpleNamespace(
            content="I cannot call that tool.",
            refusal="Tool use declined",
            tool_calls=None,
        )
        self.provider.client.chat.completions.create.return_value = SimpleNamespace(
            model="resolved-model",
            usage=None,
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
        )

        result = self.provider.complete_with_tools(
            model="test-model",
            messages=[],
            tools=[],
        )

        self.assertEqual(result["content"], "I cannot call that tool.")
        self.assertEqual(result["provider_refusal"], "Tool use declined")
        self.assertEqual(result["tool_calls"], [])
        self.assertIsNone(result["usage"])
        self.assertIsNone(result["provider_request_id"])

    def test_completion_response_requires_server_model_field(self):
        self.provider.client.chat.completions.create.return_value = SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="answer", refusal=None),
                    finish_reason="stop",
                )
            ],
        )

        with self.assertRaisesRegex(RuntimeError, "model field"):
            self.provider.complete(model="discovered-model", messages=[])

    @patch("llmddos.provider.time.monotonic", side_effect=[20.0, 20.25])
    def test_stream_complete_assembles_vllm_content_reasoning_and_usage(self, _monotonic):
        usage = MagicMock()
        usage.model_dump.return_value = {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
        }
        chunks = iter(
            [
                SimpleNamespace(
                    id="req-1",
                    model="resolved",
                    usage=None,
                    choices=[
                        SimpleNamespace(
                            finish_reason=None,
                            delta=SimpleNamespace(
                                reasoning_content="considering ",
                                content=None,
                            ),
                        )
                    ],
                ),
                SimpleNamespace(
                    id="req-1",
                    model="resolved",
                    usage=None,
                    choices=[
                        SimpleNamespace(
                            finish_reason="stop",
                            delta=SimpleNamespace(reasoning_content=None, content="answer"),
                        )
                    ],
                ),
                SimpleNamespace(
                    id="req-1", model="resolved", usage=usage, choices=[]
                ),
            ]
        )
        stream = MagicMock()
        stream.__iter__.return_value = chunks
        self.provider.client.chat.completions.create.return_value = stream
        deltas = []

        result = self.provider.stream_complete(
            model="test-model",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=8192,
            temperature=0.6,
            top_p=0.95,
            presence_penalty=1.5,
            extra_body={"top_k": 20},
            on_delta=lambda kind, text: deltas.append((kind, text)),
        )

        self.provider.client.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=8192,
            temperature=0.6,
            top_p=0.95,
            presence_penalty=1.5,
            extra_body={"top_k": 20},
            stream=True,
            stream_options={"include_usage": True},
        )
        self.assertEqual(deltas, [("reasoning", "considering "), ("content", "answer")])
        self.assertEqual(result["reasoning_text"], "considering ")
        self.assertEqual(result["response_text"], "answer")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["usage"]["total_tokens"], 14)
        stream.close.assert_called_once()


class RoutedProviderTests(unittest.TestCase):
    def test_waits_for_health_before_discovering_the_active_model(self):
        routed = RoutedOpenAICompatibleProvider.__new__(RoutedOpenAICompatibleProvider)
        endpoint = MagicMock()
        endpoint.list_models.return_value = ["served-model"]
        routed.providers = {"server": endpoint}
        routed.tool_modes = {"server": "prompt_json"}
        routed.minimum_max_tokens = {"server": 8192}
        routed.health_timeouts = {"server": 600.0}
        routed.discovered_providers = {}
        routed.discovery_route = "server"

        model = routed.wait_for_model()

        self.assertEqual(model, "served-model")
        self.assertEqual(
            endpoint.method_calls,
            [call.wait_for_health(600.0), call.list_models()],
        )
        routed.complete(model, messages=[], max_tokens=10)
        endpoint.complete.assert_called_once_with(
            model="served-model", messages=[], max_tokens=8192
        )

    def test_discovery_requires_one_active_server_model(self):
        routed = RoutedOpenAICompatibleProvider.__new__(RoutedOpenAICompatibleProvider)
        endpoint = MagicMock()
        endpoint.list_models.return_value = ["model-a", "model-b"]
        routed.providers = {"server": endpoint}
        routed.tool_modes = {"server": "native"}
        routed.minimum_max_tokens = {"server": 1}
        routed.health_timeouts = {"server": 10.0}
        routed.discovered_providers = {}
        routed.discovery_route = "server"

        with self.assertRaisesRegex(RuntimeError, "exactly one active model"):
            routed.wait_for_model()

    def test_dispatches_models_to_distinct_providers(self):
        routed = RoutedOpenAICompatibleProvider.__new__(RoutedOpenAICompatibleProvider)
        glm = MagicMock()
        qwen = MagicMock()
        routed.providers = {"glm": glm, "qwen": qwen}
        routed.tool_modes = {"glm": "native", "qwen": "prompt_json"}
        routed.minimum_max_tokens = {"glm": 8192, "qwen": 8192}

        routed.complete("glm", messages=[], max_tokens=10)
        routed.complete_with_tools("qwen", messages=[], tools=[], max_tokens=20)

        glm.complete.assert_called_once_with(model="glm", messages=[], max_tokens=8192)
        qwen.complete_with_prompt_tools.assert_called_once_with(
            model="qwen", messages=[], tools=[], max_tokens=8192
        )
        self.assertEqual(routed.list_models(), ["glm", "qwen"])

    def test_unknown_route_is_rejected(self):
        routed = RoutedOpenAICompatibleProvider.__new__(RoutedOpenAICompatibleProvider)
        routed.providers = {}
        routed.tool_modes = {}
        routed.minimum_max_tokens = {}

        with self.assertRaisesRegex(ValueError, "No endpoint configured"):
            routed.complete("missing", messages=[])


class PromptToolProtocolTests(unittest.TestCase):
    def test_extracts_json_call_after_model_reasoning(self):
        result = _extract_prompt_tool_call(
            'Thinking briefly.\n```json\n{"name":"read_file","arguments":{"path":"README.md"}}\n```',
            {"read_file"},
        )

        self.assertEqual(
            result, {"name": "read_file", "arguments": {"path": "README.md"}}
        )

    def test_does_not_accept_unknown_tool(self):
        self.assertIsNone(
            _extract_prompt_tool_call(
                '{"name":"delete_file","arguments":{"path":"README.md"}}',
                {"read_file"},
            )
        )

    def test_extracts_final_answer_without_visible_reasoning(self):
        text = (
            "<think>I should output FINAL with the answer and ignore a quoted refusal.</think>\n"
            "FINAL\nThe code is TOKEN-9."
        )

        self.assertEqual(_extract_prompt_final(text), "The code is TOKEN-9.")


class HealthUrlTests(unittest.TestCase):
    def test_health_is_server_level_while_models_stays_under_v1(self):
        self.assertEqual(
            _health_url("http://127.0.0.1:18473/v1"),
            "http://127.0.0.1:18473/health",
        )


if __name__ == "__main__":
    unittest.main()
