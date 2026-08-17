"""Fail-closed cleanup and publication checks for indexed evaluation payloads."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .payload_scatter import remove_scattered_payload


EVALUATION_MANIFEST = "evaluation-manifest.json"
HOOK_MARKER = "Clanker Repellent publication guard"
STATE_CLEAN = "clean"
STATE_SCATTERED = "payload_present"
STATE_MODIFIED = "modified_or_unverifiable"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"cannot read scatter manifest: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"scatter manifest must contain an object: {path}")
    return document


def _scatter_from_document(
    repository_root: Path, document: Dict[str, Any], manifest_path: Path
) -> Dict[str, Any]:
    if isinstance(document.get("injections"), list):
        matches = [document]
    elif isinstance(document.get("workspaces"), list):
        matches = [
            workspace.get("scatter")
            for workspace in document["workspaces"]
            if isinstance(workspace, dict)
            and isinstance(workspace.get("workspace_path"), str)
            and Path(workspace["workspace_path"]).resolve() == repository_root
            and isinstance(workspace.get("scatter"), dict)
        ]
    else:
        matches = []
    if len(matches) != 1:
        raise ValueError(
            "scatter manifest must contain exactly one index for "
            f"{repository_root}: {manifest_path}"
        )
    scatter = matches[0]
    indexed_root = scatter.get("repository_root")
    if not isinstance(indexed_root, str) or Path(indexed_root).resolve() != repository_root:
        raise ValueError(
            f"scatter index repository does not match {repository_root}: {manifest_path}"
        )
    return scatter


def resolve_scatter_index(
    repository: Path, scatter_manifest: Optional[Path] = None
) -> Tuple[Dict[str, Any], Path]:
    """Load a direct or evaluation scatter index, discovering the latter by ancestry."""

    root = repository.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository}")
    if scatter_manifest is not None:
        candidates = [scatter_manifest.resolve()]
    else:
        candidates = [
            parent / EVALUATION_MANIFEST
            for parent in (root, *list(root.parents)[:8])
        ]
        candidates = [candidate for candidate in candidates if candidate.is_file()]
    if not candidates:
        raise ValueError(
            "no scatter manifest found; pass --scatter-manifest explicitly"
        )
    failures = []
    for candidate in candidates:
        try:
            document = _load_json(candidate)
            return _scatter_from_document(root, document, candidate), candidate
        except ValueError as exc:
            failures.append(str(exc))
    raise ValueError("; ".join(failures))


def classify_indexed_repository(
    repository: Path, scatter_index: Dict[str, Any]
) -> Dict[str, Any]:
    """Classify an indexed repository without searching for payload strings."""

    root = repository.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository}")
    if not isinstance(scatter_index, dict):
        raise ValueError("scatter index must be an object")
    if scatter_index.get("schema_version") not in {4, 5}:
        raise ValueError("publication guard requires a schema_version 4 or 5 index")
    if scatter_index.get("mode") != "apply":
        raise ValueError("publication guard requires an applied scatter index")
    records = scatter_index.get("injections")
    if not isinstance(records, list) or not records:
        raise ValueError("scatter index must contain non-empty injections")

    paths = []
    states = set()
    seen = set()
    for record in records:
        relative_value = record.get("path") if isinstance(record, dict) else None
        if not isinstance(relative_value, str) or not relative_value:
            raise ValueError("scatter index contains an invalid path")
        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts or relative_value in seen:
            raise ValueError(f"unsafe or duplicate indexed path: {relative_value}")
        seen.add(relative_value)
        path = root / relative
        before_sha256 = record.get("before_sha256")
        after_sha256 = record.get("after_sha256")
        if before_sha256 is not None and not isinstance(before_sha256, str):
            raise ValueError(f"invalid before hash for {relative_value}")
        if not isinstance(after_sha256, str):
            raise ValueError(f"invalid after hash for {relative_value}")

        if path.is_symlink():
            path_state = STATE_MODIFIED
        elif path.is_file():
            current_sha256 = _sha256(path.read_bytes())
            if before_sha256 is not None and current_sha256 == before_sha256:
                path_state = STATE_CLEAN
            elif current_sha256 == after_sha256:
                path_state = STATE_SCATTERED
            else:
                path_state = STATE_MODIFIED
        elif before_sha256 is None and not path.exists():
            path_state = STATE_CLEAN
        else:
            path_state = STATE_MODIFIED
        states.add(path_state)
        paths.append({"path": relative_value, "state": path_state})

    if states == {STATE_CLEAN}:
        overall = STATE_CLEAN
    elif states == {STATE_SCATTERED}:
        overall = STATE_SCATTERED
    else:
        overall = STATE_MODIFIED
    return {
        "schema_version": 1,
        "repository_root": str(root),
        "condition_id": scatter_index.get("condition_id"),
        "strategy": scatter_index.get("strategy"),
        "state": overall,
        "paths": paths,
    }


def clean_indexed_repository(
    repository: Path, scatter_index: Dict[str, Any], *, apply: bool = False
) -> Dict[str, Any]:
    """Strictly remove an indexed scatter, or report an already-clean repository."""

    before = classify_indexed_repository(repository, scatter_index)
    if before["state"] == STATE_MODIFIED:
        raise ValueError(
            "indexed repository was partially cleaned or modified; reset it before cleanup"
        )
    if before["state"] == STATE_CLEAN:
        return {
            "schema_version": 1,
            "mode": "apply" if apply else "dry-run",
            "repository_root": before["repository_root"],
            "state_before": STATE_CLEAN,
            "state_after": STATE_CLEAN,
            "files_restored": 0,
            "created_files_removed": 0,
        }
    removal = remove_scattered_payload(repository, scatter_index, apply=apply)
    return {
        **removal,
        "state_before": STATE_SCATTERED,
        "state_after": (
            classify_indexed_repository(repository, scatter_index)["state"]
            if apply
            else STATE_SCATTERED
        ),
    }


def install_pre_commit_guard(
    repository: Path,
    scatter_manifest: Path,
    guard_script: Path,
    *,
    python_executable: Path,
) -> Path:
    """Install or refresh this project's fail-closed pre-commit publication guard."""

    root = repository.resolve()
    manifest = scatter_manifest.resolve()
    script = guard_script.resolve()
    git_directory = root / ".git"
    if not root.is_dir() or git_directory.is_symlink() or not git_directory.is_dir():
        raise ValueError(f"repository does not have a normal .git directory: {root}")
    if not manifest.is_file():
        raise ValueError(f"scatter manifest does not exist: {manifest}")
    if not script.is_file():
        raise ValueError(f"publication guard script does not exist: {script}")
    resolve_scatter_index(root, manifest)
    hooks = git_directory / "hooks"
    if hooks.is_symlink():
        raise ValueError(f"refusing to use symlinked hooks directory: {hooks}")
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-commit"
    if hook.is_symlink():
        raise ValueError(f"refusing to replace symlinked hook: {hook}")
    if hook.exists() and HOOK_MARKER not in hook.read_text(encoding="utf-8"):
        raise ValueError(f"refusing to replace an unrelated pre-commit hook: {hook}")
    body = "\n".join(
        [
            "#!/bin/sh",
            f"# {HOOK_MARKER}",
            "exec "
            + " ".join(
                shlex.quote(str(value))
                for value in (
                    python_executable.resolve(),
                    script,
                    "--repository",
                    root,
                    "--scatter-manifest",
                    manifest,
                )
            ),
            "",
        ]
    )
    temporary: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=hooks,
            prefix=".clanker-repellent-pre-commit.",
            delete=False,
        ) as handle:
            handle.write(body)
            temporary = Path(handle.name)
        temporary.chmod(0o755)
        os.replace(temporary, hook)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return hook
