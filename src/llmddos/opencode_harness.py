"""Isolated OpenCode harness for source generation and validation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List


PROVIDER_ID = "repel-local"
AGENT_ID = "noop-generator"
DEFAULT_OPENCODE_TIMEOUT_SECONDS = 900.0


def build_opencode_config(
    *, model: str, base_url: str, max_tokens: int
) -> Dict[str, Any]:
    """Build a runtime-only OpenCode configuration for one discovered model."""

    qualified_model = f"{PROVIDER_ID}/{model}"
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": qualified_model,
        "small_model": qualified_model,
        "share": "disabled",
        "autoupdate": False,
        "formatter": True,
        "lsp": True,
        "provider": {
            PROVIDER_ID: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Clanker Repellent local endpoint",
                "options": {"baseURL": base_url, "apiKey": "unused"},
                "models": {
                    model: {
                        "name": model,
                        "limit": {
                            "context": max(32768, max_tokens * 2),
                            "output": max_tokens,
                        },
                    }
                },
            }
        },
        "default_agent": AGENT_ID,
        "agent": {
            AGENT_ID: {
                "description": "Create one statically validated no-op source candidate",
                "mode": "primary",
                "model": qualified_model,
                "prompt": (
                    "Work only in the provided isolated directory. Create exactly the requested "
                    "source file using a file-editing tool. Use the formatter, LSP diagnostics, "
                    "and shell-based parser, compiler, or linter commands when they are available "
                    "to make the candidate valid. Fix reported problems before replying and remove "
                    "any validation artifacts. Do not use network access, subagents, or external "
                    "paths. Put source code only in the requested file, with no Markdown fences, "
                    "and do not leave any other file in the workspace."
                ),
                "permission": {
                    "*": "deny",
                    "bash": "allow",
                    "edit": "allow",
                    "glob": "allow",
                    "grep": "allow",
                    "lsp": "allow",
                    "read": "allow",
                },
            }
        },
    }


def extract_opencode_text(stdout: str) -> str:
    """Extract assistant text from OpenCode's newline-delimited JSON event stream."""

    parts: List[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "".join(parts).strip()


class OpenCodeNoopHarness:
    """Run one OpenCode agent attempt in a disposable, tool-restricted workspace."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        binary: str = "opencode",
        timeout_seconds: float = DEFAULT_OPENCODE_TIMEOUT_SECONDS,
    ) -> None:
        resolved = shutil.which(binary)
        if resolved is None:
            raise RuntimeError(
                f"OpenCode executable not found: {binary!r}; install it or use --opencode-bin"
            )
        if timeout_seconds <= 0:
            raise ValueError("OpenCode timeout must be positive")
        self.binary = resolved
        self.model = model
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def complete_noop(
        self,
        *,
        target: Any,
        messages: List[Dict[str, str]],
        max_tokens: int,
        **_: Any,
    ) -> Dict[str, Any]:
        """Run OpenCode and normalize its candidate into the direct-provider response shape."""

        runtime_config = build_opencode_config(
            model=self.model,
            base_url=self.base_url,
            max_tokens=max_tokens,
        )
        request = (
            f"Create exactly {target.output_filename} for the {target.language} language. "
            "Follow the system and user requirements below. Use the file-editing tool, then "
            "reply with a short completion notice.\n\n"
            + json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        )
        with tempfile.TemporaryDirectory(prefix="anaphylaxis-opencode-") as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir(mode=0o700)
            environment = dict(os.environ)
            environment.pop("OPENCODE_DISABLE_LSP_DOWNLOAD", None)
            environment.update(
                {
                    "XDG_CACHE_HOME": str(root / "cache"),
                    "XDG_CONFIG_HOME": str(root / "config"),
                    "XDG_DATA_HOME": str(root / "data"),
                    "XDG_STATE_HOME": str(root / "state"),
                    "OPENCODE_CONFIG_CONTENT": json.dumps(
                        runtime_config, ensure_ascii=False, separators=(",", ":")
                    ),
                    "OPENCODE_AUTO_SHARE": "false",
                    "OPENCODE_DISABLE_AUTOUPDATE": "true",
                    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
                    "OPENCODE_EXPERIMENTAL_LSP_TOOL": "true",
                    "OPENCODE_DISABLE_MODELS_FETCH": "true",
                    "OPENCODE_DISABLE_PRUNE": "true",
                    "OPENCODE_DISABLE_CLAUDE_CODE": "true",
                    "NO_COLOR": "1",
                }
            )
            command = [
                self.binary,
                "--pure",
                "run",
                "--format",
                "json",
                "--agent",
                AGENT_ID,
                "--dir",
                str(workspace),
            ]
            try:
                completed = subprocess.run(
                    command,
                    input=request,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    env=environment,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"OpenCode exceeded its {self.timeout_seconds:g}s timeout"
                ) from exc
            if completed.returncode != 0:
                detail = completed.stderr.strip().replace("\n", " ")[:500]
                raise RuntimeError(
                    f"OpenCode exited with status {completed.returncode}"
                    + (f": {detail}" if detail else "")
                )

            candidate = workspace / target.output_filename
            files = sorted(
                path.relative_to(workspace).as_posix()
                for path in workspace.rglob("*")
                if path.is_file() or path.is_symlink()
            )
            if candidate.is_symlink():
                raise RuntimeError("OpenCode created a symlink instead of a candidate file")
            if candidate.is_file():
                if files != [target.output_filename]:
                    raise RuntimeError(
                        "OpenCode created unexpected workspace files: " + ", ".join(files)
                    )
                source = candidate.read_text(encoding="utf-8")
                response_text = f"```{target.language}\n{source.rstrip()}\n```"
                delivery = "workspace_file"
            else:
                response_text = extract_opencode_text(completed.stdout)
                if not response_text:
                    raise RuntimeError(
                        f"OpenCode did not create {target.output_filename} or return text"
                    )
                delivery = "assistant_text"

            return {
                "response_text": response_text,
                "provider_refusal": None,
                "finish_reason": "stop",
                "latency_ms": None,
                "usage": None,
                "provider_request_id": None,
                "resolved_model": self.model,
                "harness": "opencode",
                "harness_delivery": delivery,
            }
