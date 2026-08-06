"""Manifest-driven cloning for a pinned corpus of benign public repositories."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from .payload_scatter import STRATEGIES


REPOSITORY_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
CLEAN_METADATA_DIRECTORY = ".llmddos-clean-metadata"
WORKSPACE_METADATA_DIRECTORY = ".llmddos-workspace-metadata"
BASELINE_VARIANT = "baseline"
WORKSPACE_VARIANTS = (BASELINE_VARIANT, *STRATEGIES)


def load_repository_manifest(
    path: Path, *, allow_file_urls: bool = False
) -> List[Dict[str, str]]:
    """Load and validate a repository corpus manifest."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"repositories"}:
        raise ValueError(f"{path}: expected one 'repositories' array")
    repositories = document["repositories"]
    if not isinstance(repositories, list) or not repositories:
        raise ValueError(f"{path}: repositories must be a non-empty array")
    seen = set()
    validated = []
    for index, item in enumerate(repositories):
        label = f"{path}:repositories[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{label}: repository must be an object")
        unknown = set(item) - {"id", "url", "revision"}
        missing = {"id", "url", "revision"} - set(item)
        if missing or unknown:
            raise ValueError(
                f"{label}: fields must be exactly id, url, revision"
            )
        repo_id = item["id"]
        url = item["url"]
        revision = item["revision"]
        if not isinstance(repo_id, str) or not REPOSITORY_ID.fullmatch(repo_id):
            raise ValueError(f"{label}: invalid repository id")
        if repo_id in seen:
            raise ValueError(f"{label}: duplicate repository id {repo_id!r}")
        seen.add(repo_id)
        if not isinstance(url, str):
            raise ValueError(f"{label}: url must be a string")
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme.casefold()
        allowed_schemes = {"https"}
        if allow_file_urls:
            allowed_schemes.add("file")
        if scheme not in allowed_schemes:
            raise ValueError(
                f"{label}: url must use one of {sorted(allowed_schemes)}"
            )
        if scheme == "https" and (
            not parsed_url.hostname
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError(
                f"{label}: HTTPS url must contain a host and no credentials, query, or fragment"
            )
        if not isinstance(revision, str) or not COMMIT_SHA.fullmatch(revision):
            raise ValueError(f"{label}: revision must be a full lowercase commit SHA")
        validated.append({"id": repo_id, "url": url, "revision": revision})
    return validated


def _git_environment() -> Dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _run_git(arguments: List[str], *, cwd: Optional[Path] = None) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            env=_git_environment(),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is required to prepare benign repositories") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "git command failed"
        raise RuntimeError(detail) from exc
    return completed.stdout.strip()


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path, label: str) -> Dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing {label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"invalid {label}: {path}")
    return value


def _git_entries(root: Path) -> List[Path]:
    return sorted(
        (
            path
            for path in root.rglob(".git")
            if path.is_symlink() or path.is_dir() or path.is_file()
        ),
        key=lambda path: path.as_posix(),
    )


def _require_no_git_metadata(root: Path) -> None:
    entries = _git_entries(root)
    if entries:
        relative = ", ".join(path.relative_to(root).as_posix() for path in entries)
        raise ValueError(f"task repository contains forbidden Git metadata: {relative}")


def repository_tree_sha256(root: Path) -> str:
    """Hash a repository worktree without following symlinks."""

    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        status = path.lstat()
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0")
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        elif path.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0")
            digest.update(str(stat.S_IMODE(status.st_mode)).encode("ascii") + b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        else:
            raise ValueError(f"unsupported filesystem entry in task repository: {path}")
    return digest.hexdigest()


def _clean_metadata_path(clean_root: Path, repository_id: str) -> Path:
    return clean_root / CLEAN_METADATA_DIRECTORY / f"{repository_id}.json"


def _workspace_metadata_path(
    output_root: Path, strategy: str, repository_id: str
) -> Path:
    return output_root / WORKSPACE_METADATA_DIRECTORY / strategy / f"{repository_id}.json"


def _clean_metadata(
    repository: Dict[str, str], tree_sha256: str
) -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "repository_id": repository["id"],
        "revision": repository["revision"],
        "tree_sha256": tree_sha256,
        "git_metadata_removed": True,
    }


def clone_repository(repository: Dict[str, str], output_root: Path) -> Dict[str, Any]:
    """Clone a pinned revision, verify it, then publish a Git-free worktree."""

    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / repository["id"]
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite existing repository directory: {destination}"
        )
    staging = Path(tempfile.mkdtemp(prefix=f".{repository['id']}.", dir=output_root))
    try:
        _run_git(
            [
                "clone",
                "--no-checkout",
                "--filter=blob:none",
                "--no-tags",
                repository["url"],
                str(staging),
            ]
        )
        _run_git(
            [
                "-c",
                "filter.lfs.smudge=",
                "-c",
                "filter.lfs.required=false",
                "checkout",
                "--detach",
                repository["revision"],
            ],
            cwd=staging,
        )
        resolved = _run_git(["rev-parse", "HEAD"], cwd=staging)
        if resolved != repository["revision"]:
            raise RuntimeError(
                f"resolved commit {resolved} does not match {repository['revision']}"
            )
        git_directory = staging / ".git"
        if git_directory.is_symlink() or not git_directory.is_dir():
            raise RuntimeError(f"clone did not create expected Git metadata: {git_directory}")
        shutil.rmtree(git_directory)
        _require_no_git_metadata(staging)
        tree_sha256 = repository_tree_sha256(staging)
        staging.rename(destination)
        try:
            _write_json(
                _clean_metadata_path(output_root, repository["id"]),
                _clean_metadata(repository, tree_sha256),
            )
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "id": repository["id"],
        "url": repository["url"],
        "requested_revision": repository["revision"],
        "resolved_revision": resolved,
        "path": str(destination),
        "tree_sha256": tree_sha256,
        "git_metadata_removed": True,
    }


def clone_repositories(
    repositories: Iterable[Dict[str, str]],
    output_root: Path,
    repository_ids: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Clone a selected set of repositories and return provenance records."""

    rows = list(repositories)
    if repository_ids is not None:
        requested = set(repository_ids)
        known = {row["id"] for row in rows}
        missing = requested - known
        if missing:
            raise ValueError("unknown repository ids: " + ", ".join(sorted(missing)))
        rows = [row for row in rows if row["id"] in requested]
    existing = [
        str(output_root / row["id"])
        for row in rows
        if (output_root / row["id"]).exists()
    ]
    if existing:
        raise FileExistsError(
            "refusing to overwrite existing repository directories: "
            + ", ".join(existing)
        )
    return [clone_repository(row, output_root) for row in rows]


def write_clone_manifest(records: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"repositories": records}, indent=2) + "\n", encoding="utf-8"
    )


def verify_clean_repository(repository: Dict[str, str], clean_root: Path) -> Path:
    """Require an exact, Git-free clean tree matching external provenance."""

    source = (clean_root / repository["id"]).resolve()
    if not source.is_dir():
        raise ValueError(f"clean repository is missing or invalid: {source}")
    _require_no_git_metadata(source)
    metadata = _read_json(
        _clean_metadata_path(clean_root, repository["id"]),
        "clean repository metadata",
    )
    expected_identity = {
        "schema_version": 2,
        "repository_id": repository["id"],
        "revision": repository["revision"],
        "git_metadata_removed": True,
    }
    for key, expected in expected_identity.items():
        if metadata.get(key) != expected:
            raise ValueError(
                f"clean repository metadata mismatch for {repository['id']!r}: {key}"
            )
    actual_tree_sha256 = repository_tree_sha256(source)
    if metadata.get("tree_sha256") != actual_tree_sha256:
        raise ValueError(f"clean repository {repository['id']!r} has local changes")
    return source


def _read_workspace_marker(
    output_root: Path, strategy: str, repository_id: str
) -> Dict[str, Any]:
    marker = _workspace_metadata_path(output_root, strategy, repository_id)
    try:
        return _read_json(marker, "evaluation workspace marker")
    except ValueError as exc:
        raise ValueError(
            f"refusing to reset unrecognized workspace without external marker: "
            f"{output_root / strategy / repository_id}"
        ) from exc


def create_injected_workspace(
    repository: Dict[str, str],
    clean_root: Path,
    output_root: Path,
    strategy: str,
    *,
    reset: bool = False,
) -> Dict[str, str]:
    """Copy one disposable Git-free workspace from a verified clean tree."""

    if strategy not in WORKSPACE_VARIANTS:
        raise ValueError(
            "strategy must be one of: " + ", ".join(WORKSPACE_VARIANTS)
        )
    source = verify_clean_repository(repository, clean_root)
    clean_metadata = _read_json(
        _clean_metadata_path(clean_root, repository["id"]),
        "clean repository metadata",
    )
    root = output_root.resolve()
    destination = (root / strategy / repository["id"]).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"workspace escapes output root: {destination}") from exc

    expected_marker = {
        "schema_version": 2,
        "repository_id": repository["id"],
        "revision": repository["revision"],
        "strategy": strategy,
        "clean_tree_sha256": clean_metadata["tree_sha256"],
        "git_metadata_removed": True,
    }
    marker_path = _workspace_metadata_path(root, strategy, repository["id"])
    if destination.exists() or destination.is_symlink():
        if not reset:
            raise FileExistsError(f"workspace already exists: {destination}")
        if destination.is_symlink() or not destination.is_dir():
            raise ValueError(f"refusing to reset non-directory workspace: {destination}")
        marker = _read_workspace_marker(root, strategy, repository["id"])
        if marker != expected_marker:
            raise ValueError(f"workspace marker does not match requested reset: {destination}")
        shutil.rmtree(destination)
        marker_path.unlink()
    elif marker_path.exists():
        if not reset:
            raise ValueError(f"orphaned evaluation workspace marker: {marker_path}")
        marker = _read_workspace_marker(root, strategy, repository["id"])
        if marker != expected_marker:
            raise ValueError(f"workspace marker does not match requested reset: {marker_path}")
        marker_path.unlink()

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{repository['id']}.", dir=destination.parent)
    )
    staging = staging_root / repository["id"]
    try:
        shutil.copytree(source, staging, symlinks=True)
        _require_no_git_metadata(staging)
        staging.rename(destination)
        _write_json(marker_path, expected_marker)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        marker_path.unlink(missing_ok=True)
        raise
    shutil.rmtree(staging_root, ignore_errors=True)
    return {
        "repository_id": repository["id"],
        "revision": repository["revision"],
        "strategy": strategy,
        "clean_path": str(source),
        "workspace_path": str(destination),
    }


def strip_corpus_git_metadata(
    repositories: Iterable[Dict[str, str]], clean_root: Path, corpus_root: Path
) -> Dict[str, int]:
    """Migrate an existing corpus to external provenance and Git-free task trees."""

    rows = list(repositories)
    by_id = {row["id"]: row for row in rows}
    clean_root = clean_root.resolve()
    corpus_root = corpus_root.resolve()
    if not clean_root.is_dir() or not corpus_root.is_dir():
        raise ValueError("clean_root and corpus_root must both exist")

    clean_sources = []
    for repository in rows:
        source = clean_root / repository["id"]
        git_directory = source / ".git"
        if git_directory.is_dir() and not git_directory.is_symlink():
            resolved = _run_git(["rev-parse", "HEAD"], cwd=source)
            dirty = _run_git(
                ["status", "--porcelain", "--untracked-files=all"], cwd=source
            )
            if resolved != repository["revision"]:
                raise ValueError(
                    f"clean repository {repository['id']!r} is at {resolved}, "
                    f"expected {repository['revision']}"
                )
            if dirty:
                raise ValueError(
                    f"clean repository {repository['id']!r} has local changes"
                )
        elif _clean_metadata_path(clean_root, repository["id"]).is_file():
            verify_clean_repository(repository, clean_root)
        else:
            raise ValueError(f"clean repository is missing or invalid: {source}")
        clean_sources.append((repository, source))

    git_entries = _git_entries(corpus_root)
    for entry in git_entries:
        if entry.is_symlink():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    clean_records = []
    for repository, source in clean_sources:
        _require_no_git_metadata(source)
        tree_sha256 = repository_tree_sha256(source)
        _write_json(
            _clean_metadata_path(clean_root, repository["id"]),
            _clean_metadata(repository, tree_sha256),
        )
        clean_records.append(
            {
                "id": repository["id"],
                "url": repository["url"],
                "requested_revision": repository["revision"],
                "resolved_revision": repository["revision"],
                "path": str(source),
                "tree_sha256": tree_sha256,
                "git_metadata_removed": True,
            }
        )
    write_clone_manifest(clean_records, clean_root / "clone-manifest.json")

    workspace_markers = 0
    injected_root = corpus_root / "injected"
    if injected_root.is_dir():
        for destination in sorted(injected_root.rglob("*")):
            if not destination.is_dir() or destination.name not in by_id:
                continue
            strategy = destination.parent.name
            if strategy not in WORKSPACE_VARIANTS:
                continue
            relative = destination.relative_to(injected_root)
            if len(relative.parts) not in {2, 3}:
                continue
            workspace_root = destination.parents[1]
            repository = by_id[destination.name]
            clean_metadata = _read_json(
                _clean_metadata_path(clean_root, repository["id"]),
                "clean repository metadata",
            )
            _write_json(
                _workspace_metadata_path(workspace_root, strategy, repository["id"]),
                {
                    "schema_version": 2,
                    "repository_id": repository["id"],
                    "revision": repository["revision"],
                    "strategy": strategy,
                    "clean_tree_sha256": clean_metadata["tree_sha256"],
                    "git_metadata_removed": True,
                },
            )
            workspace_markers += 1
    return {
        "git_entries_removed": len(git_entries),
        "clean_repositories_registered": len(clean_sources),
        "workspace_markers_written": workspace_markers,
    }
