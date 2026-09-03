"""Validation for benign software-engineering tasks over pinned repositories."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


TASK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
TASK_TYPES = {
    "audit",
    "benchmark",
    "bugfix",
    "fuzz",
    "implementation",
    "integration",
    "profiling",
    "test",
}
TASK_FIELDS = {"id", "repository_id", "task_type", "task", "safety"}
SAFETY = "benign_software_engineering"


def load_repository_tasks(
    path: Path, repository_ids: Iterable[str]
) -> List[Dict[str, Any]]:
    """Load a task catalog and require exact references to the repository corpus."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"schema_version", "tasks"}:
        raise ValueError(f"{path}: expected exactly schema_version and tasks")
    if document["schema_version"] != "1.0":
        raise ValueError(f"{path}: unsupported schema_version")
    tasks = document["tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(f"{path}: tasks must be a non-empty array")

    known_repositories = set(repository_ids)
    if not known_repositories:
        raise ValueError("repository ids must be non-empty")
    seen_tasks = set()
    validated = []
    for index, task in enumerate(tasks):
        label = f"{path}:tasks[{index}]"
        if not isinstance(task, dict) or set(task) != TASK_FIELDS:
            raise ValueError(f"{label}: fields must be exactly {sorted(TASK_FIELDS)}")
        task_id = task["id"]
        if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
            raise ValueError(f"{label}: invalid task id")
        if task_id in seen_tasks:
            raise ValueError(f"{label}: duplicate task id {task_id!r}")
        seen_tasks.add(task_id)
        repository_id = task["repository_id"]
        if repository_id not in known_repositories:
            raise ValueError(f"{label}: unknown repository id {repository_id!r}")
        if task["task_type"] not in TASK_TYPES:
            raise ValueError(
                f"{label}: task_type must be one of {sorted(TASK_TYPES)}"
            )
        if not isinstance(task["task"], str) or not task["task"].strip():
            raise ValueError(f"{label}: task must be a non-empty string")
        if task["safety"] != SAFETY:
            raise ValueError(f"{label}: safety must be {SAFETY!r}")
        validated.append(dict(task))

    return validated
