"""Validated model routing and SSH-tunnel endpoint configuration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse

from .dotenv import merged_environment


_SSH_TARGET = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._:-]+$")
_REMOTE_HOST = re.compile(r"^[A-Za-z0-9._:-]+$")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def is_allowed_base_url(value: str) -> bool:
    """Allow HTTPS generally and HTTP only through a local loopback socket."""

    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    if parsed.username or parsed.password or not parsed.hostname:
        return False
    if parsed.scheme == "https":
        return True
    return (
        parsed.scheme == "http"
        and parsed.hostname.casefold() in _LOOPBACK_HOSTS
        and port is not None
    )


def _port(value: Any, location: str) -> int:
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
        raise ValueError(f"{location} must be an integer from 1 to 65535")
    return value


def _default_dotenv(path: Path) -> Optional[Path]:
    for parent in (path.parent.resolve(), *list(path.parent.resolve().parents)[:4]):
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


def _expand_environment(value: Any, environment: Mapping[str, str], location: str) -> Any:
    if isinstance(value, dict):
        return {
            key: _expand_environment(item, environment, f"{location}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _expand_environment(item, environment, f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in environment or not environment[name]:
            raise ValueError(f"{location}: required environment variable {name} is not set")
        return environment[name]

    rendered = _ENV_REFERENCE.sub(replace, value)
    if "${" in rendered:
        raise ValueError(f"{location}: invalid environment reference")
    return rendered


def load_endpoint_config(
    path: Path,
    *,
    environ: Optional[Mapping[str, str]] = None,
    dotenv_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Load a credential-free endpoint map and validate its tunnel definition."""

    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError(f"{path}: configuration must be an object")
    selected_dotenv = dotenv_path if dotenv_path is not None else _default_dotenv(path)
    environment = merged_environment(
        dotenv_path=selected_dotenv,
        environ=environ,
    )
    config = _expand_environment(config, environment, str(path))
    models = config.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError(f"{path}: models must be a non-empty object")

    tunnel_ports = set()
    ssh = config.get("ssh")
    if ssh is not None:
        if not isinstance(ssh, dict):
            raise ValueError(f"{path}: ssh must be an object")
        target = ssh.get("target")
        if not isinstance(target, str) or not _SSH_TARGET.fullmatch(target):
            raise ValueError(f"{path}: ssh.target must look like user@host")
        forwards = ssh.get("forwards")
        if not isinstance(forwards, list) or not forwards:
            raise ValueError(f"{path}: ssh.forwards must be a non-empty list")
        normalized_forwards = []
        for index, forward in enumerate(forwards):
            location = f"{path}: ssh.forwards[{index}]"
            if not isinstance(forward, dict):
                raise ValueError(f"{location} must be an object")
            local_port = _port(forward.get("local_port"), f"{location}.local_port")
            remote_port = _port(forward.get("remote_port"), f"{location}.remote_port")
            remote_host = forward.get("remote_host", "127.0.0.1")
            if not isinstance(remote_host, str) or not _REMOTE_HOST.fullmatch(remote_host):
                raise ValueError(f"{location}.remote_host is invalid")
            if local_port in tunnel_ports:
                raise ValueError(f"{path}: duplicate SSH local port {local_port}")
            tunnel_ports.add(local_port)
            normalized_forwards.append(
                {
                    "local_port": local_port,
                    "remote_host": remote_host,
                    "remote_port": remote_port,
                }
            )
        ssh["forwards"] = normalized_forwards
        timeout = ssh.get("startup_timeout_seconds", 15.0)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError(f"{path}: ssh.startup_timeout_seconds must be positive")
        ssh["startup_timeout_seconds"] = float(timeout)

    for model, route in models.items():
        if not isinstance(model, str) or not model:
            raise ValueError(f"{path}: model names must be non-empty strings")
        if not isinstance(route, dict):
            raise ValueError(f"{path}: route for {model!r} must be an object")
        base_url = route.get("base_url")
        if not isinstance(base_url, str) or not is_allowed_base_url(base_url):
            raise ValueError(
                f"{path}: {model!r} base_url must use HTTPS, or HTTP on loopback with a port"
            )
        parsed = urlparse(base_url)
        if parsed.scheme == "http" and parsed.hostname.casefold() in _LOOPBACK_HOSTS:
            if ssh is None or parsed.port not in tunnel_ports:
                raise ValueError(
                    f"{path}: loopback port {parsed.port} for {model!r} is not SSH-forwarded"
                )
        api_key_env = route.get("api_key_env")
        if api_key_env is not None and (
            not isinstance(api_key_env, str) or not api_key_env.strip()
        ):
            raise ValueError(f"{path}: {model!r} api_key_env must be a non-empty string")
        if "api_key" in route:
            raise ValueError(f"{path}: credentials cannot be stored in endpoint configuration")
        timeout = route.get("timeout_seconds", 120.0)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError(f"{path}: {model!r} timeout_seconds must be positive")
        route["timeout_seconds"] = float(timeout)
        minimum_max_tokens = route.get("minimum_max_tokens", 1)
        if (
            not isinstance(minimum_max_tokens, int)
            or isinstance(minimum_max_tokens, bool)
            or minimum_max_tokens < 1
        ):
            raise ValueError(f"{path}: {model!r} minimum_max_tokens must be a positive integer")
        route["minimum_max_tokens"] = minimum_max_tokens
        tool_mode = route.get("tool_mode", "native")
        if tool_mode not in {"native", "prompt_json"}:
            raise ValueError(
                f"{path}: {model!r} tool_mode must be 'native' or 'prompt_json'"
            )
        route["tool_mode"] = tool_mode
        ca_cert = route.get("ca_cert")
        if ca_cert is not None:
            if not isinstance(ca_cert, str) or Path(ca_cert).is_absolute():
                raise ValueError(f"{path}: {model!r} ca_cert must be a relative path")
            candidate = (path.parent.resolve() / ca_cert).resolve()
            try:
                candidate.relative_to(path.parent.resolve())
            except ValueError as exc:
                raise ValueError(f"{path}: {model!r} ca_cert cannot leave the config directory") from exc
            if not candidate.is_file():
                raise ValueError(f"{path}: {model!r} ca_cert not found: {ca_cert}")
            route["_ca_cert_path"] = str(candidate)

    config["_source"] = str(path.resolve())
    config["_dotenv_source"] = (
        str(selected_dotenv.resolve()) if selected_dotenv is not None else None
    )
    return config
