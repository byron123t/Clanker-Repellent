"""Dataset loading and validation."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ..payload.payload_mixer import load_payload_mixture, validate_mixture_parts
from ..payload.payload_templates import load_and_render_template, resolve_config_file


REQUIRED_CASE_FIELDS = {"id", "task", "artifact", "expected_terms"}
REQUIRED_CONDITION_FIELDS = {"id", "family", "placement"}
VALID_PLACEMENTS = {"none", "prepend", "append"}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: each row must be an object")
            row["_source_line"] = line_number
            rows.append(row)
    return rows


def _check_unique(rows: Iterable[Dict[str, Any]], path: Path) -> None:
    seen = set()
    for row in rows:
        row_id = row["id"]
        if row_id in seen:
            raise ValueError(f"{path}: duplicate id {row_id!r}")
        seen.add(row_id)


def load_cases(path: Path) -> List[Dict[str, Any]]:
    rows = read_jsonl(path)
    for row in rows:
        missing = REQUIRED_CASE_FIELDS - row.keys()
        if missing:
            raise ValueError(f"{path}:{row['_source_line']}: missing {sorted(missing)}")
        if not isinstance(row["expected_terms"], list) or not row["expected_terms"]:
            raise ValueError(f"{path}:{row['_source_line']}: expected_terms must be non-empty")
        if not all(isinstance(term, str) and term for term in row["expected_terms"]):
            raise ValueError(f"{path}:{row['_source_line']}: expected_terms must be strings")
    _check_unique(rows, path)
    return rows


def validate_condition_references(
    path: Path, expected_template_fields: Iterable[str] = ()
) -> Dict[str, Any]:
    """Validate referenced paths and value names without reading referenced files."""

    rows = read_jsonl(path)
    config_root = path.parent.resolve()
    expected = set(expected_template_fields)
    referenced_files = set()
    template_conditions = 0
    mixture_conditions = 0
    for row in rows:
        line = row["_source_line"]
        source_fields = [
            field
            for field in (
                "payload",
                "payload_file",
                "payload_template",
                "payload_parts",
            )
            if field in row
        ]
        if len(source_fields) != 1:
            raise ValueError(
                f"{path}:{line}: specify exactly one of payload, payload_file, "
                "payload_template, or payload_parts"
            )
        source = source_fields[0]
        if source == "payload":
            continue
        if source == "payload_file":
            try:
                resolve_config_file(config_root, row["payload_file"], "payload_file")
            except ValueError as exc:
                raise ValueError(f"{path}:{line}: {exc}") from exc
            referenced_files.add(row["payload_file"])
            continue
        if source == "payload_parts":
            mixture_conditions += 1
            try:
                parts = validate_mixture_parts(config_root, row["payload_parts"])
            except ValueError as exc:
                raise ValueError(f"{path}:{line}: {exc}") from exc
            referenced_files.update(part["file"] for part in parts)
            part_separator = row.get("payload_part_separator", "\n\n")
            if not isinstance(part_separator, str) or "\x00" in part_separator:
                raise ValueError(
                    f"{path}:{line}: payload_part_separator must be a NUL-free string"
                )
            continue
        template_conditions += 1
        try:
            resolve_config_file(
                config_root, row["payload_template"], "payload_template"
            )
        except ValueError as exc:
            raise ValueError(f"{path}:{line}: {exc}") from exc
        referenced_files.add(row["payload_template"])
        values = row.get("payload_values")
        if not isinstance(values, dict):
            raise ValueError(f"{path}:{line}: payload_values must be an object")
        if expected and set(values) != expected:
            missing = expected - set(values)
            extra = set(values) - expected
            details = []
            if missing:
                details.append("missing " + ", ".join(sorted(missing)))
            if extra:
                details.append("unexpected " + ", ".join(sorted(extra)))
            raise ValueError(
                f"{path}:{line}: payload_values do not match expected fields: "
                + "; ".join(details)
            )
        for name, value in values.items():
            if not isinstance(name, str) or not name.isidentifier():
                raise ValueError(f"{path}:{line}: invalid payload value name")
            if isinstance(value, str):
                continue
            if not isinstance(value, dict) or set(value) != {"file"}:
                raise ValueError(
                    f"{path}:{line}: payload value {name!r} must be a string or "
                    "an object containing only 'file'"
                )
            try:
                resolve_config_file(
                    config_root, value["file"], f"payload value {name!r} file"
                )
            except ValueError as exc:
                raise ValueError(f"{path}:{line}: {exc}") from exc
            referenced_files.add(value["file"])
    return {
        "conditions": len(rows),
        "template_conditions": template_conditions,
        "mixture_conditions": mixture_conditions,
        "referenced_files": sorted(referenced_files),
    }


def load_conditions(path: Path) -> List[Dict[str, Any]]:
    rows = read_jsonl(path)
    for row in rows:
        missing = REQUIRED_CONDITION_FIELDS - row.keys()
        if missing:
            raise ValueError(f"{path}:{row['_source_line']}: missing {sorted(missing)}")
        if not isinstance(row["id"], str) or not row["id"].strip():
            raise ValueError(f"{path}:{row['_source_line']}: id must be a non-empty string")
        if not isinstance(row["family"], str) or not row["family"].strip():
            raise ValueError(f"{path}:{row['_source_line']}: family must be a non-empty string")
        source_fields = [
            field
            for field in (
                "payload",
                "payload_file",
                "payload_template",
                "payload_parts",
            )
            if field in row
        ]
        if len(source_fields) != 1:
            raise ValueError(
                f"{path}:{row['_source_line']}: specify exactly one of payload, "
                "payload_file, payload_template, or payload_parts"
            )
        source_field = source_fields[0]
        if source_field == "payload":
            if not isinstance(row["payload"], str):
                raise ValueError(f"{path}:{row['_source_line']}: payload must be a string")
            row["_payload_source"] = "inline"
            if "payload_values" in row:
                raise ValueError(
                    f"{path}:{row['_source_line']}: payload_values requires payload_template"
                )
        elif source_field == "payload_file":
            payload_file = row["payload_file"]
            config_root = path.parent.resolve()
            try:
                candidate = resolve_config_file(config_root, payload_file, "payload_file")
            except ValueError as exc:
                raise ValueError(f"{path}:{row['_source_line']}: {exc}") from exc
            row["payload"] = candidate.read_text(encoding="utf-8")
            row["_payload_source"] = payload_file
            if "payload_values" in row:
                raise ValueError(
                    f"{path}:{row['_source_line']}: payload_values requires payload_template"
                )
        elif source_field == "payload_template":
            config_root = path.parent.resolve()
            try:
                payload, metadata = load_and_render_template(
                    config_root,
                    row["payload_template"],
                    row.get("payload_values"),
                )
            except ValueError as exc:
                raise ValueError(f"{path}:{row['_source_line']}: {exc}") from exc
            row["payload"] = payload
            row["_payload_source"] = f"template:{row['payload_template']}"
            row["_payload_template_metadata"] = metadata
        else:
            config_root = path.parent.resolve()
            try:
                payload, metadata = load_payload_mixture(
                    config_root,
                    row["payload_parts"],
                    row.get("payload_part_separator", "\n\n"),
                )
            except ValueError as exc:
                raise ValueError(f"{path}:{row['_source_line']}: {exc}") from exc
            row["payload"] = payload
            row["_payload_source"] = "mixture:" + "+".join(
                part["file"] for part in row["payload_parts"]
            )
            row["_payload_mixture_metadata"] = metadata
            if "payload_values" in row:
                raise ValueError(
                    f"{path}:{row['_source_line']}: payload_values requires payload_template"
                )
        if "\x00" in row["payload"]:
            raise ValueError(f"{path}:{row['_source_line']}: payload cannot contain NUL bytes")
        for optional_string in ("carrier_label", "separator"):
            if optional_string in row and not isinstance(row[optional_string], str):
                raise ValueError(
                    f"{path}:{row['_source_line']}: {optional_string} must be a string"
                )
            if "\x00" in row.get(optional_string, ""):
                raise ValueError(
                    f"{path}:{row['_source_line']}: {optional_string} cannot contain NUL bytes"
                )
        if row["placement"] not in VALID_PLACEMENTS:
            raise ValueError(
                f"{path}:{row['_source_line']}: placement must be one of {sorted(VALID_PLACEMENTS)}"
            )
        if row["placement"] == "none" and row["payload"]:
            raise ValueError(f"{path}:{row['_source_line']}: none placement requires empty payload")
        if row["placement"] != "none" and not row["payload"]:
            raise ValueError(f"{path}:{row['_source_line']}: {row['placement']} requires a payload")
        if "operational" in row and not isinstance(row["operational"], bool):
            raise ValueError(f"{path}:{row['_source_line']}: operational must be boolean")
        if "tags" in row and (
            not isinstance(row["tags"], list)
            or not all(isinstance(tag, str) and tag for tag in row["tags"])
        ):
            raise ValueError(f"{path}:{row['_source_line']}: tags must be a list of strings")
    _check_unique(rows, path)
    if not any(row["id"] == "baseline" for row in rows):
        raise ValueError(f"{path}: a baseline condition is required")
    return rows


def condition_metadata(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in rows:
        payload = row["payload"]
        carrier_label = row.get("carrier_label", "[APPENDIX]\n") if row["placement"] != "none" else ""
        separator = row.get("separator", "\n\n") if row["placement"] != "none" else ""
        output.append(
            {
                "id": row["id"],
                "family": row["family"],
                "placement": row["placement"],
                "operational": bool(row.get("operational", False)),
                "tags": row.get("tags", []),
                "payload_source": row.get("_payload_source", "inline"),
                "payload_characters": len(payload),
                "payload_bytes_utf8": len(payload.encode("utf-8")),
                "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                "carrier_label_characters": len(carrier_label),
                "carrier_label_sha256": hashlib.sha256(carrier_label.encode("utf-8")).hexdigest(),
                "separator_characters": len(separator),
                "separator_sha256": hashlib.sha256(separator.encode("utf-8")).hexdigest(),
                "inserted_block_sha256": hashlib.sha256(
                    (carrier_label + payload).encode("utf-8")
                ).hexdigest(),
                **row.get("_payload_template_metadata", {}),
                **row.get("_payload_mixture_metadata", {}),
            }
        )
    return output
