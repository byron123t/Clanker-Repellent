"""Strict, provenance-preserving rendering for structured payload templates."""

from __future__ import annotations

import hashlib
import string
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple


class PayloadTemplateError(ValueError):
    """Raised when a structured payload template is ambiguous or unsafe to load."""


def resolve_config_file(config_root: Path, reference: str, label: str) -> Path:
    """Resolve a relative config file without allowing directory traversal."""

    if not isinstance(reference, str) or not reference.strip():
        raise PayloadTemplateError(f"{label} must be a non-empty relative path")
    if Path(reference).is_absolute():
        raise PayloadTemplateError(f"{label} must be relative")
    candidate = (config_root / reference).resolve()
    try:
        candidate.relative_to(config_root.resolve())
    except ValueError as exc:
        raise PayloadTemplateError(f"{label} cannot leave {config_root}") from exc
    if not candidate.is_file():
        raise PayloadTemplateError(f"{label} not found: {reference}")
    return candidate


def template_fields(template: str) -> Tuple[str, ...]:
    """Return ordered simple field names and reject advanced format expressions."""

    fields = []
    try:
        parsed = string.Formatter().parse(template)
        for _, field_name, format_spec, conversion in parsed:
            if field_name is None:
                continue
            if not field_name.isidentifier():
                raise PayloadTemplateError(
                    f"template field {field_name!r} must be a simple identifier"
                )
            if format_spec or conversion:
                raise PayloadTemplateError(
                    f"template field {field_name!r} cannot use conversion or formatting"
                )
            if field_name not in fields:
                fields.append(field_name)
    except ValueError as exc:
        raise PayloadTemplateError(f"invalid payload template: {exc}") from exc
    if not fields:
        raise PayloadTemplateError("payload template must contain at least one field")
    return tuple(fields)


def _load_values(
    config_root: Path, values: Mapping[str, Any]
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    rendered_values: Dict[str, str] = {}
    sources: Dict[str, str] = {}
    hashes: Dict[str, str] = {}
    for name, value in values.items():
        if not isinstance(name, str) or not name.isidentifier():
            raise PayloadTemplateError("payload value names must be simple identifiers")
        if isinstance(value, str):
            text = value
            source = "inline"
        elif isinstance(value, dict) and set(value) == {"file"}:
            reference = value["file"]
            path = resolve_config_file(
                config_root, reference, f"payload value {name!r} file"
            )
            text = path.read_text(encoding="utf-8")
            source = reference
        else:
            raise PayloadTemplateError(
                f"payload value {name!r} must be a string or an object containing only 'file'"
            )
        if "\x00" in text:
            raise PayloadTemplateError(f"payload value {name!r} cannot contain NUL bytes")
        rendered_values[name] = text
        sources[name] = source
        hashes[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return rendered_values, sources, hashes


def load_and_render_template(
    config_root: Path, template_reference: str, values: Mapping[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    """Load a UTF-8 template and render it with an exact, closed set of values."""

    if not isinstance(values, dict):
        raise PayloadTemplateError("payload_values must be an object")
    template_path = resolve_config_file(
        config_root, template_reference, "payload_template"
    )
    template = template_path.read_text(encoding="utf-8")
    if "\x00" in template:
        raise PayloadTemplateError("payload_template cannot contain NUL bytes")
    required = template_fields(template)
    rendered_values, sources, hashes = _load_values(config_root, values)
    missing = set(required) - set(rendered_values)
    extra = set(rendered_values) - set(required)
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if extra:
            details.append("unexpected " + ", ".join(sorted(extra)))
        raise PayloadTemplateError(
            "payload_values do not match template: " + "; ".join(details)
        )
    payload = template.format_map(rendered_values)
    return payload, {
        "template_source": template_reference,
        "template_sha256": hashlib.sha256(template.encode("utf-8")).hexdigest(),
        "template_fields": list(required),
        "value_sources": sources,
        "value_sha256": hashes,
    }
