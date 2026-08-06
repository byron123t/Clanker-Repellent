"""Loading and validation for synthetic tool-using agent scenarios."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from .dataset import read_jsonl


REQUIRED_SCENARIO_FIELDS = {
    "id",
    "environment_type",
    "task",
    "expected_terms",
    "injection_anchor",
}
VALID_ENVIRONMENT_TYPES = {
    "repo",
    "repository",
    "website",
    "email",
    "mailbox",
    "issue",
    "issue_coding",
}


def _resolve_content_file(config_path: Path, value: str, line: int) -> Path:
    if not value or Path(value).is_absolute():
        raise ValueError(
            f"{config_path}:{line}: content_file must be a non-empty relative path"
        )
    config_root = config_path.parent.resolve()
    candidate = (config_root / value).resolve()
    try:
        candidate.relative_to(config_root)
    except ValueError as exc:
        raise ValueError(
            f"{config_path}:{line}: content_file cannot leave {config_root}"
        ) from exc
    if not candidate.is_file():
        raise ValueError(f"{config_path}:{line}: content_file not found: {value}")
    return candidate


def load_agent_scenarios(path: Path) -> List[Dict[str, Any]]:
    """Load scenarios and materialize resource bodies from confined fixture files."""

    rows = read_jsonl(path)
    seen_scenarios = set()
    for row in rows:
        line = row["_source_line"]
        missing = REQUIRED_SCENARIO_FIELDS - row.keys()
        if missing:
            raise ValueError(f"{path}:{line}: missing {sorted(missing)}")
        if not isinstance(row["id"], str) or not row["id"].strip():
            raise ValueError(f"{path}:{line}: id must be a non-empty string")
        if row["id"] in seen_scenarios:
            raise ValueError(f"{path}: duplicate id {row['id']!r}")
        seen_scenarios.add(row["id"])
        if row["environment_type"] not in VALID_ENVIRONMENT_TYPES:
            raise ValueError(
                f"{path}:{line}: environment_type must be one of "
                f"{sorted(VALID_ENVIRONMENT_TYPES)}"
            )
        if not isinstance(row["task"], str) or not row["task"].strip():
            raise ValueError(f"{path}:{line}: task must be a non-empty string")
        terms = row["expected_terms"]
        if not isinstance(terms, list) or not terms or not all(
            isinstance(term, str) and term for term in terms
        ):
            raise ValueError(f"{path}:{line}: expected_terms must be non-empty strings")
        if "target_resource_id" not in row and "inject_target_resource" in row:
            row["target_resource_id"] = row["inject_target_resource"]
        if "target_resource_id" not in row:
            raise ValueError(f"{path}:{line}: target_resource_id is required")
        if "resources" not in row:
            row["resources"] = _load_environment_root(path, row, line)
        if not isinstance(row["resources"], list) or not row["resources"]:
            raise ValueError(f"{path}:{line}: resources must be a non-empty list")

        resource_ids = set()
        for resource in row["resources"]:
            if not isinstance(resource, dict):
                raise ValueError(f"{path}:{line}: each resource must be an object")
            missing_resource = {"id", "title", "kind", "content_file"} - resource.keys()
            if missing_resource:
                raise ValueError(
                    f"{path}:{line}: resource missing {sorted(missing_resource)}"
                )
            if not all(
                isinstance(resource[key], str) and resource[key]
                for key in ("id", "title", "kind", "content_file")
            ):
                raise ValueError(f"{path}:{line}: resource fields must be non-empty strings")
            if resource["id"] in resource_ids:
                raise ValueError(
                    f"{path}:{line}: duplicate resource id {resource['id']!r}"
                )
            resource_ids.add(resource["id"])
            source = _resolve_content_file(path, resource["content_file"], line)
            resource["content"] = source.read_text(encoding="utf-8")
            if "\x00" in resource["content"]:
                raise ValueError(f"{path}:{line}: resource content cannot contain NUL bytes")
            resource["_content_source"] = resource["content_file"]

        if row["target_resource_id"] not in resource_ids:
            raise ValueError(
                f"{path}:{line}: target_resource_id must name one of the resources"
            )
        anchor = row["injection_anchor"]
        if not isinstance(anchor, str) or not anchor:
            raise ValueError(f"{path}:{line}: injection_anchor must be a non-empty string")
        target = next(
            resource
            for resource in row["resources"]
            if resource["id"] == row["target_resource_id"]
        )
        if target["content"].count(anchor) != 1:
            raise ValueError(
                f"{path}:{line}: injection_anchor must occur exactly once in target resource"
            )
        missing_terms = [term for term in terms if term not in target["content"]]
        if missing_terms:
            raise ValueError(
                f"{path}:{line}: expected terms missing from target resource: {missing_terms}"
            )
        for field in ("injection_prefix", "injection_suffix"):
            if field in row and not isinstance(row[field], str):
                raise ValueError(f"{path}:{line}: {field} must be a string")
    return rows


def _load_environment_root(
    config_path: Path, row: Dict[str, Any], line: int
) -> List[Dict[str, Any]]:
    value = row.get("environment_root")
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError(
            f"{config_path}:{line}: provide resources or a relative environment_root"
        )
    config_root = config_path.parent.resolve()
    root = (config_root / value).resolve()
    try:
        root.relative_to(config_root)
    except ValueError as exc:
        raise ValueError(
            f"{config_path}:{line}: environment_root cannot leave {config_root}"
        ) from exc
    if not root.is_dir():
        raise ValueError(f"{config_path}:{line}: environment_root not found: {value}")
    resources = []
    for source in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        resource_id = source.relative_to(root).as_posix()
        content = source.read_text(encoding="utf-8")
        resources.append(
            {
                "id": resource_id,
                "title": _resource_title(resource_id, content),
                "kind": _resource_kind(row["environment_type"], resource_id),
                "content_file": source.relative_to(config_root).as_posix(),
            }
        )
    return resources


def _resource_kind(environment_type: str, resource_id: str) -> str:
    if environment_type == "website":
        return "page"
    if environment_type in {"email", "mailbox"}:
        return "email" if resource_id.endswith(".eml") else "index"
    if environment_type in {"issue", "issue_coding"} and resource_id.startswith("issues/"):
        return "issue"
    return "file"


def _resource_title(resource_id: str, content: str) -> str:
    if resource_id.endswith(".eml"):
        match = re.search(r"^Subject:\s*(.+)$", content, flags=re.MULTILINE | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    html_match = re.search(r"<title>(.*?)</title>", content, flags=re.IGNORECASE | re.DOTALL)
    if html_match:
        return re.sub(r"\s+", " ", html_match.group(1)).strip()
    heading_match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    if heading_match:
        return heading_match.group(1).strip()
    return resource_id
