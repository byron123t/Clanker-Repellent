"""OpenAI-compatible inference adapter."""

from __future__ import annotations

import os
import hashlib
import json
import re
import ssl
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

from .endpoints import is_allowed_base_url


def _health_url(base_url: str) -> str:
    """Return the server-level health URL for an OpenAI-compatible /v1 base URL."""

    parsed = urlsplit(base_url.rstrip("/"))
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    path = path.rstrip("/") + "/health"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _required_model_value(model: Any) -> str:
    if not isinstance(model, str) or not model.strip():
        raise RuntimeError("completion response did not include a model field")
    return model


def _required_response_model(response: Any) -> str:
    return _required_model_value(getattr(response, "model", None))


class OpenAICompatibleProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 120.0,
        ca_cert: Optional[Path] = None,
    ) -> None:
        if not api_key:
            raise ValueError("An API key is required")
        if not is_allowed_base_url(base_url):
            raise ValueError(
                "base_url must use HTTPS, except HTTP is allowed on an explicit loopback port"
            )
        try:
            from openai import OpenAI
            import httpx
        except ImportError as exc:
            raise RuntimeError("Install the 'openai' and 'httpx' packages to run inference") from exc
        verify: Any = True
        if ca_cert is not None:
            if not ca_cert.is_file():
                raise ValueError(f"CA certificate does not exist: {ca_cert}")
            verify = ssl.create_default_context(cafile=str(ca_cert))
        http_client = httpx.Client(verify=verify, timeout=timeout)
        self._http_client = http_client
        self.health_url = _health_url(base_url)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            max_retries=0,
            http_client=http_client,
        )

    def list_models(self) -> List[str]:
        return sorted(model.id for model in self.client.models.list())

    def wait_for_health(
        self, timeout_seconds: float, poll_interval_seconds: float = 0.5
    ) -> None:
        """Poll the server-level /health route until it returns a successful status."""

        if timeout_seconds <= 0:
            raise ValueError("health timeout must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("health poll interval must be positive")
        deadline = time.monotonic() + timeout_seconds
        last_error = "not ready"
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"endpoint health check did not succeed at {self.health_url} "
                    f"within {timeout_seconds:g}s: {last_error}"
                )
            try:
                response = self._http_client.get(
                    self.health_url, timeout=max(0.05, min(2.0, remaining))
                )
                if 200 <= response.status_code < 300:
                    return
                last_error = f"HTTP {response.status_code}"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(min(poll_interval_seconds, max(0.0, remaining)))

    def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 300,
        temperature: float = 0.0,
        top_p: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        request = self._chat_request(
            model, messages, max_tokens, temperature, top_p, presence_penalty, extra_body
        )
        response = self.client.chat.completions.create(**request)
        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        choice = response.choices[0]
        usage: Optional[Any] = getattr(response, "usage", None)
        usage_dict = usage.model_dump() if usage is not None else None
        return {
            "response_text": choice.message.content or "",
            "provider_refusal": getattr(choice.message, "refusal", None),
            "finish_reason": getattr(choice, "finish_reason", None),
            "latency_ms": elapsed_ms,
            "usage": usage_dict,
            "provider_request_id": getattr(response, "id", None),
            "resolved_model": _required_response_model(response),
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "service_tier": getattr(response, "service_tier", None),
        }

    @staticmethod
    def _chat_request(
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        top_p: Optional[float],
        presence_penalty: Optional[float],
        extra_body: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        request: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if top_p is not None:
            request["top_p"] = top_p
        if presence_penalty is not None:
            request["presence_penalty"] = presence_penalty
        if extra_body:
            request["extra_body"] = extra_body
        return request

    def stream_complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 300,
        temperature: float = 0.0,
        top_p: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        on_delta: Optional[Callable[[str, str], Optional[bool]]] = None,
    ) -> Dict[str, Any]:
        """Stream a chat response and return the assembled response and usage."""

        started = time.monotonic()
        request = self._chat_request(
            model, messages, max_tokens, temperature, top_p, presence_penalty, extra_body
        )
        request.update({"stream": True, "stream_options": {"include_usage": True}})
        stream = self.client.chat.completions.create(**request)
        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        finish_reason = None
        usage_dict = None
        request_id = None
        resolved_model = None
        stopped_by_client = False
        try:
            for chunk in stream:
                request_id = request_id or getattr(chunk, "id", None)
                resolved_model = resolved_model or getattr(chunk, "model", None)
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    usage_dict = usage.model_dump()
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                choice = choices[0]
                finish_reason = getattr(choice, "finish_reason", None) or finish_reason
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning is None:
                    reasoning = (getattr(delta, "model_extra", None) or {}).get(
                        "reasoning_content"
                    )
                content = getattr(delta, "content", None)
                for kind, text in (("reasoning", reasoning), ("content", content)):
                    if not text:
                        continue
                    if kind == "reasoning":
                        reasoning_parts.append(text)
                    else:
                        content_parts.append(text)
                    if on_delta is not None and on_delta(kind, text) is False:
                        stopped_by_client = True
                        finish_reason = "client_stop"
                        break
                if stopped_by_client:
                    break
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "response_text": "".join(content_parts),
            "reasoning_text": "".join(reasoning_parts),
            "provider_refusal": None,
            "finish_reason": finish_reason,
            "latency_ms": elapsed_ms,
            "usage": usage_dict,
            "provider_request_id": request_id,
            "resolved_model": _required_model_value(resolved_model),
            "stopped_by_client": stopped_by_client,
        }

    def complete_with_tools(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 300,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Run one chat-completion step with OpenAI-compatible tool definitions."""
        started = time.monotonic()
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        choice = response.choices[0]
        message = choice.message
        tool_calls = []
        for call in getattr(message, "tool_calls", None) or []:
            function = getattr(call, "function", None)
            tool_calls.append(
                {
                    "id": getattr(call, "id", None),
                    "name": getattr(function, "name", None),
                    "arguments": getattr(function, "arguments", None),
                }
            )
        usage: Optional[Any] = getattr(response, "usage", None)
        usage_dict = usage.model_dump() if usage is not None else None
        return {
            "content": message.content or "",
            "provider_refusal": getattr(message, "refusal", None),
            "tool_calls": tool_calls,
            "finish_reason": getattr(choice, "finish_reason", None),
            "latency_ms": elapsed_ms,
            "usage": usage_dict,
            "provider_request_id": getattr(response, "id", None),
            "resolved_model": _required_response_model(response),
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "service_tier": getattr(response, "service_tier", None),
        }

    def complete_with_prompt_tools(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 300,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Emulate tool calls through a strict text protocol for servers lacking native tools."""

        allowed = {
            tool["function"]["name"]: tool["function"]
            for tool in tools
            if tool.get("type") == "function" and isinstance(tool.get("function"), dict)
        }
        tool_catalog = [
            {
                "name": name,
                "description": function.get("description", ""),
                "parameters": function.get("parameters", {}),
            }
            for name, function in allowed.items()
        ]
        system_parts = [
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        ]
        protocol = (
            "You can use the read-only functions listed below. Search and list results contain "
            "metadata only; read the relevant resource before answering. When a function is "
            "needed, output only one JSON object in this exact form: "
            '{"name":"function_name","arguments":{"argument":"value"}}. '
            "Do not include analysis or Markdown around a function call. When the task is complete, "
            "output FINAL followed by the concise answer and no JSON function call.\n\nFunctions:\n"
            + json.dumps(tool_catalog, ensure_ascii=False, separators=(",", ":"))
        )
        transcript = []
        for message in messages:
            role = message.get("role")
            if role == "system":
                continue
            if role == "assistant" and message.get("tool_calls"):
                calls = [
                    {
                        "name": call.get("function", {}).get("name"),
                        "arguments": call.get("function", {}).get("arguments"),
                    }
                    for call in message["tool_calls"]
                ]
                transcript.append({"role": "assistant_tool_request", "content": calls})
            else:
                transcript.append(
                    {
                        "role": role,
                        "tool_call_id": message.get("tool_call_id"),
                        "content": message.get("content"),
                    }
                )
        emulated_messages = [
            {"role": "system", "content": "\n\n".join(system_parts + [protocol])},
            {
                "role": "user",
                "content": "Conversation and tool transcript:\n"
                + json.dumps(transcript, ensure_ascii=False, separators=(",", ":"))
                + "\n\nChoose the next function call or provide FINAL now.",
            },
        ]
        result = self.complete(
            model=model,
            messages=emulated_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        response_text = result.pop("response_text")
        parsed = _extract_prompt_tool_call(response_text, set(allowed))
        if parsed is not None:
            call_id = "prompt_" + hashlib.sha256(
                (response_text + str(len(messages))).encode("utf-8")
            ).hexdigest()[:12]
            arguments = parsed["arguments"]
            result.update(
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "name": parsed["name"],
                            "arguments": json.dumps(
                                arguments, ensure_ascii=False, separators=(",", ":")
                            ),
                        }
                    ],
                    "finish_reason": "tool_calls",
                }
            )
        else:
            result.update(
                {
                    "content": _extract_prompt_final(response_text),
                    "tool_calls": [],
                }
            )
        return result


def _extract_prompt_tool_call(text: str, allowed_names: set) -> Optional[Dict[str, Any]]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        name = value.get("name", value.get("tool"))
        arguments = value.get("arguments", {})
        if name in allowed_names and isinstance(arguments, dict):
            return {"name": name, "arguments": arguments}
    return None


def _extract_prompt_final(text: str) -> str:
    final_markers = list(re.finditer(r"(?im)^\s*FINAL\s*:?\s*", text))
    if final_markers:
        return text[final_markers[-1].end() :].strip()
    if "</think>" in text:
        return text.rsplit("</think>", 1)[-1].strip()
    return re.sub(r"^\s*FINAL\s*:?\s*", "", text, flags=re.IGNORECASE).strip()


class RoutedOpenAICompatibleProvider:
    """Dispatch each configured model alias to its own OpenAI-compatible endpoint."""

    def __init__(self, endpoint_config: Dict[str, Any]) -> None:
        self.providers: Dict[str, OpenAICompatibleProvider] = {}
        self.tool_modes: Dict[str, str] = {}
        self.minimum_max_tokens: Dict[str, int] = {}
        self.health_timeouts: Dict[str, float] = {}
        self.discovered_providers: Dict[str, OpenAICompatibleProvider] = {}
        self.discovery_route: Optional[str] = endpoint_config.get("_discovery_route")
        for model, route in endpoint_config["models"].items():
            api_key_env = route.get("api_key_env")
            api_key = os.getenv(api_key_env) if api_key_env else "unused"
            if not api_key:
                raise ValueError(f"Set {api_key_env} for endpoint model {model!r}")
            ca_cert = route.get("_ca_cert_path")
            self.providers[model] = OpenAICompatibleProvider(
                api_key=api_key,
                base_url=route["base_url"],
                timeout=route["timeout_seconds"],
                ca_cert=Path(ca_cert) if ca_cert else None,
            )
            self.tool_modes[model] = route.get("tool_mode", "native")
            self.minimum_max_tokens[model] = route.get("minimum_max_tokens", 1)
            self.health_timeouts[model] = route.get(
                "health_timeout_seconds", route["timeout_seconds"]
            )

    def list_models(self) -> List[str]:
        return sorted(self.providers)

    def _provider(self, model: str) -> OpenAICompatibleProvider:
        discovered = getattr(self, "discovered_providers", {})
        if model in discovered:
            return discovered[model]
        try:
            return self.providers[model]
        except KeyError as exc:
            raise ValueError(f"No endpoint configured for model {model!r}") from exc

    def wait_for_models(self) -> List[str]:
        """Wait for configured servers and discover their model IDs via /v1/models."""

        routes = (
            [self.discovery_route]
            if self.discovery_route is not None
            else sorted(self.providers)
        )
        discovered: List[str] = []
        for route in routes:
            provider = self._provider(route)
            provider.wait_for_health(self.health_timeouts[route])
            models = provider.list_models()
            if not models:
                raise RuntimeError(f"/v1/models returned no model IDs for route {route!r}")
            for model in models:
                self.discovered_providers[model] = provider
                self.tool_modes[model] = self.tool_modes[route]
                self.minimum_max_tokens[model] = self.minimum_max_tokens[route]
                discovered.append(model)
        return sorted(set(discovered))

    def wait_for_model(self) -> str:
        """Wait for one configured server and return its sole active model."""

        models = self.wait_for_models()
        if len(models) != 1:
            raise RuntimeError(
                "/v1/models must return exactly one active model; received: "
                + ", ".join(models)
            )
        return models[0]

    def complete(self, model: str, **kwargs: Any) -> Dict[str, Any]:
        request = self._enforce_minimum_tokens(model, kwargs)
        return self._provider(model).complete(model=model, **request)

    def stream_complete(self, model: str, **kwargs: Any) -> Dict[str, Any]:
        request = self._enforce_minimum_tokens(model, kwargs)
        return self._provider(model).stream_complete(model=model, **request)

    def complete_with_tools(self, model: str, **kwargs: Any) -> Dict[str, Any]:
        provider = self._provider(model)
        request = self._enforce_minimum_tokens(model, kwargs)
        if self.tool_modes.get(model, "native") == "prompt_json":
            return provider.complete_with_prompt_tools(model=model, **request)
        return provider.complete_with_tools(model=model, **request)

    def _enforce_minimum_tokens(self, model: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        request = dict(kwargs)
        requested = request.get("max_tokens", 0)
        request["max_tokens"] = max(requested, self.minimum_max_tokens.get(model, 1))
        return request
