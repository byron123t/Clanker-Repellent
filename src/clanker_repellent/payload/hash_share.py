"""Create and verify hash-only repository handoff artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .publication_guard import (
    STATE_CLEAN,
    STATE_MODIFIED,
    STATE_SCATTERED,
    classify_indexed_repository,
)


HASH_SHARE_SCHEMA_VERSION = 1
HASH_SHARE_KIND = "repel_hash_share"
HASH_SHARE_STATES = (STATE_CLEAN, STATE_SCATTERED)
SHARE_STATE_CURRENT = "current"
SHARE_STATE_CLEAN = STATE_CLEAN
SHARE_STATE_PAYLOAD_PRESENT = STATE_SCATTERED
SHARE_STATE_CHOICES = (
    SHARE_STATE_CURRENT,
    SHARE_STATE_CLEAN,
    SHARE_STATE_PAYLOAD_PRESENT,
)
VERIFY_STATE_VERIFIED = "verified"
VERIFY_STATE_MISMATCH = "mismatch"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_sha256(value: Any, *, allow_none: bool = False) -> bool:
    if value is None:
        return allow_none
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_relative_path(value: Any, *, seen: Optional[set] = None) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("hash share contains an invalid relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or relative == Path("."):
        raise ValueError(f"hash share contains an unsafe path: {value}")
    if seen is not None:
        if value in seen:
            raise ValueError(f"hash share contains a duplicate path: {value}")
        seen.add(value)
    return value


def _has_symlink_component(root: Path, relative_value: str) -> bool:
    candidate = root
    for part in Path(relative_value).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            return True
    return False


def _validate_scatter_index(scatter_index: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(scatter_index, dict):
        raise ValueError("scatter index must be an object")
    if scatter_index.get("schema_version") not in {4, 5}:
        raise ValueError("hash sharing requires a schema_version 4 or 5 scatter index")
    if scatter_index.get("mode") != "apply":
        raise ValueError("hash sharing requires an index from an applied scatter operation")
    records = scatter_index.get("injections")
    if not isinstance(records, list) or not records:
        raise ValueError("scatter index must contain non-empty injections")
    seen = set()
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("scatter index contains an invalid file record")
        path = _safe_relative_path(record.get("path"), seen=seen)
        before = record.get("before_sha256")
        after = record.get("after_sha256")
        if not _is_sha256(before, allow_none=True):
            raise ValueError(f"scatter index contains an invalid before hash: {path}")
        if not _is_sha256(after):
            raise ValueError(f"scatter index contains an invalid after hash: {path}")
        normalized.append(
            {
                "path": path,
                "before_sha256": before,
                "after_sha256": after,
            }
        )
    return normalized


def _expected_state(
    repository: Path, scatter_index: Dict[str, Any], requested: str
) -> str:
    if requested not in SHARE_STATE_CHOICES:
        raise ValueError(
            f"share state must be one of: {', '.join(SHARE_STATE_CHOICES)}"
        )
    if requested == SHARE_STATE_CURRENT:
        state = classify_indexed_repository(repository, scatter_index)["state"]
        if state == STATE_MODIFIED:
            raise ValueError(
                "cannot share a modified or mixed repository; restore it or choose "
                "an explicit expected state"
            )
        return state
    return requested


def create_hash_share(
    repository: Path,
    scatter_index: Dict[str, Any],
    *,
    expected_state: str = SHARE_STATE_CURRENT,
) -> Dict[str, Any]:
    """Create a portable file-state proof without reading payload contents."""

    root = repository.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository}")
    indexed_root = scatter_index.get("repository_root")
    if (
        not isinstance(indexed_root, str)
        or Path(indexed_root).resolve() != root
    ):
        raise ValueError("scatter index repository does not match the target repository")
    records = _validate_scatter_index(scatter_index)
    if any(_has_symlink_component(root, record["path"]) for record in records):
        raise ValueError("cannot share an index containing symlinked paths")
    state = _expected_state(root, scatter_index, expected_state)
    file_hashes = []
    for record in records:
        expected = (
            record["before_sha256"]
            if state == STATE_CLEAN
            else record["after_sha256"]
        )
        file_hashes.append(
            {
                "path": record["path"],
                "present": expected is not None,
                "sha256": expected,
            }
        )
    return {
        "schema_version": HASH_SHARE_SCHEMA_VERSION,
        "kind": HASH_SHARE_KIND,
        "expected_state": state,
        "strategy": scatter_index.get("strategy"),
        "file_count": len(file_hashes),
        "file_hashes": file_hashes,
    }


def _validate_share(document: Any) -> Tuple[str, List[Dict[str, Any]]]:
    if not isinstance(document, dict):
        raise ValueError("hash share must contain an object")
    if document.get("schema_version") != HASH_SHARE_SCHEMA_VERSION:
        raise ValueError("unsupported Repel hash-share schema")
    if document.get("kind") != HASH_SHARE_KIND:
        raise ValueError("file is not a Repel hash share")
    state = document.get("expected_state")
    if state not in HASH_SHARE_STATES:
        raise ValueError("hash share has an invalid expected state")
    rows = document.get("file_hashes")
    if not isinstance(rows, list) or not rows:
        raise ValueError("hash share must contain non-empty file_hashes")
    if document.get("file_count") != len(rows):
        raise ValueError("hash share file_count does not match file_hashes")
    seen = set()
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("hash share contains an invalid file hash record")
        path = _safe_relative_path(row.get("path"), seen=seen)
        present = row.get("present")
        expected = row.get("sha256")
        if not isinstance(present, bool) or not _is_sha256(
            expected, allow_none=True
        ):
            raise ValueError(f"hash share contains an invalid hash record: {path}")
        if present != (expected is not None):
            raise ValueError(f"hash share presence does not match hash: {path}")
        normalized.append(
            {"path": path, "present": present, "sha256": expected}
        )
    return state, normalized


def _load_share(path: Path) -> Dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"hash share cannot be a symlink: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"cannot read hash share: {path}") from exc
    _validate_share(document)
    return document


def write_hash_share(document: Dict[str, Any], path: Path) -> None:
    """Atomically write a share artifact and refuse symlink targets."""

    _validate_share(document)
    if path.is_symlink():
        raise ValueError(f"refusing to replace symlinked hash share: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def verify_hash_share(repository: Path, share_path: Path) -> Dict[str, Any]:
    """Verify only the relative files named by a share artifact."""

    root = repository.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository}")
    document = _load_share(share_path.resolve() if not share_path.is_symlink() else share_path)
    expected_state, rows = _validate_share(document)
    mismatches = []
    for row in rows:
        path = root / row["path"]
        expected_present = row["present"]
        expected_sha256 = row["sha256"]
        actual_present = False
        actual_sha256 = None
        reason = None
        if _has_symlink_component(root, row["path"]):
            reason = "symlink"
            actual_present = True
        elif path.is_file():
            actual_present = True
            actual_sha256 = _sha256(path.read_bytes())
            if not expected_present or actual_sha256 != expected_sha256:
                reason = "hash_mismatch"
        elif path.exists():
            reason = "not_a_regular_file"
            actual_present = True
        elif expected_present:
            reason = "missing"
        if reason is not None:
            mismatches.append(
                {
                    "path": row["path"],
                    "expected_present": expected_present,
                    "actual_present": actual_present,
                    "expected_sha256": expected_sha256,
                    "actual_sha256": actual_sha256,
                    "reason": reason,
                }
            )
    return {
        "schema_version": HASH_SHARE_SCHEMA_VERSION,
        "kind": HASH_SHARE_KIND,
        "expected_state": expected_state,
        "state": (
            VERIFY_STATE_VERIFIED if not mismatches else VERIFY_STATE_MISMATCH
        ),
        "files_checked": len(rows),
        "mismatches": mismatches,
        "strategy": document.get("strategy"),
    }
