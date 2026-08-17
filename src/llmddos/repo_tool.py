"""Small payload add/status/remove/guard CLI for authorized repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .dataset import load_conditions
from .payload_scatter import (
    DEFAULT_HUB_CHUNK_LINES,
    DEFAULT_INLINE_SOURCE_LINES,
    INSTRUCTION_FILES,
    POSITION_HEAD,
    POSITION_TAIL,
    STRATEGIES,
    normalize_file_positions,
    normalize_instruction_files,
    scatter_payload,
)
from .publication_guard import (
    STATE_CLEAN,
    classify_indexed_repository,
    clean_indexed_repository,
    resolve_scatter_index,
)
from . import noop_cli, noop_deploy_cli


DEFAULT_REPO_TOOL_POSITIONS = (POSITION_HEAD, POSITION_TAIL)
CURRENT_INDEX_FILENAME = ".anaphylaxis-index.json"
GIT_INDEX_FILENAME = "anaphylaxis-index.json"


def _csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def default_index_path(repository: Path) -> Path:
    return repository.resolve() / CURRENT_INDEX_FILENAME


def legacy_index_path(repository: Path) -> Path:
    root = repository.resolve()
    return root.parent / f".{root.name}.guardrail-index.json"


def _git_repository(start: Path) -> Tuple[Path, Path]:
    """Resolve the enclosing Git worktree and its private metadata directory."""

    if not start.is_dir():
        raise ValueError(f"target directory is not a directory: {start}")
    values = []
    for argument in ("--show-toplevel", "--absolute-git-dir"):
        try:
            result = subprocess.run(
                ["git", "-C", str(start), "rev-parse", argument],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise ValueError("git executable is unavailable") from exc
        if result.returncode != 0 or not result.stdout.strip():
            raise ValueError(f"no enclosing Git repository found from: {start}")
        values.append(Path(result.stdout.strip()).resolve())
    return values[0], values[1]


def _target_context(start: Path, git_repo: bool) -> Tuple[Path, Path, str]:
    start = start.resolve()
    if git_repo:
        repository, git_directory = _git_repository(start)
        return repository, git_directory / GIT_INDEX_FILENAME, "git_repository"
    if not start.is_dir():
        raise ValueError(f"target directory is not a directory: {start}")
    return start, default_index_path(start), "current_directory"


def _operation_index(
    repository: Path,
    preferred: Path,
    explicit: Optional[Path],
    *,
    adding: bool,
) -> Tuple[Path, Optional[Path]]:
    """Choose the current index and identify a clean legacy index to migrate."""

    if explicit is not None:
        return explicit.resolve(), None
    legacy = legacy_index_path(repository)
    if preferred.exists() and legacy.exists() and preferred != legacy:
        raise ValueError(
            "both current and legacy indexes exist; remove the stale index or "
            "select one explicitly with --index"
        )
    if preferred.exists() or not legacy.exists():
        return preferred, None
    return (preferred, legacy) if adding else (legacy, None)


def _add_target_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="target/start directory (default: current directory)",
    )
    parser.add_argument(
        "--git-repo",
        action="store_true",
        help="target the enclosing Git root and keep its index under Git metadata",
    )


def _allow_clean_index_replacement(repository: Path, index_path: Path) -> None:
    """Allow reuse only for a direct index whose repository is already clean."""

    try:
        document = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"cannot read existing index: {index_path}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("injections"), list):
        raise ValueError(
            f"refusing to replace a non-direct or aggregate index: {index_path}"
        )
    scatter, _ = resolve_scatter_index(repository, index_path)
    state = classify_indexed_repository(repository, scatter)["state"]
    if state != STATE_CLEAN:
        raise ValueError(
            f"existing index is not clean (state={state}): {index_path}; "
            "remove the payload or resolve repository changes first"
        )


def _write_index_atomically(manifest: Dict, path: Path) -> None:
    """Atomically create or replace a direct scatter index."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _payload_pool(repository: Path, paths: Sequence[Path]) -> List[Dict[str, str]]:
    root = repository.resolve()
    payloads = []
    seen = set()
    for path_value in paths:
        path = path_value.resolve()
        if not path.is_file():
            raise ValueError(f"payload file does not exist: {path}")
        try:
            path.relative_to(root)
        except ValueError:
            pass
        else:
            raise ValueError("payload files must be stored outside the target repository")
        text = path.read_text(encoding="utf-8")
        if not text or "\x00" in text:
            raise ValueError(f"payload file must contain non-empty NUL-free text: {path}")
        payload_id = path.stem
        if not payload_id or payload_id in seen:
            raise ValueError(f"payload filenames must have unique non-empty stems: {path}")
        seen.add(payload_id)
        payloads.append({"id": payload_id, "payload": text})
    return payloads


def _target_file(repository: Path, value: Path) -> str:
    """Resolve one requested file within the selected target root."""

    root = repository.resolve()
    candidate = value if value.is_absolute() else root / value
    if candidate.is_symlink():
        raise ValueError(f"target file cannot be a symlink: {candidate}")
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"target file must be inside {root}: {value}") from exc
    if not resolved.is_file() or relative == Path("."):
        raise ValueError(f"target file does not exist: {resolved}")
    return relative.as_posix()


def _automatic_payload_pool(seed: int, payload_count: int) -> List[Dict[str, str]]:
    """Select and render a deterministic pool from the bundled generated conditions."""

    if payload_count < 1:
        raise ValueError("--payload-count must be at least 1")
    project_root = Path(__file__).resolve().parents[2]
    conditions_path = project_root / "payloads/mixed_conditions.generated.jsonl"
    template_path = project_root / "payloads/header.txt"
    if not conditions_path.is_file() or not template_path.is_file():
        raise ValueError(
            "bundled payload pool is unavailable; use an editable source install "
            "or pass --payload"
        )
    conditions = load_conditions(conditions_path)
    candidates = [
        row
        for row in conditions
        if row.get("placement") != "none" and bool(row.get("payload"))
    ]
    if payload_count > len(candidates):
        raise ValueError(
            f"--payload-count requests {payload_count}, but only "
            f"{len(candidates)} bundled payloads are available"
        )
    ranked = sorted(
        candidates,
        key=lambda row: hashlib.sha256(
            f"{seed}\x00{row['id']}".encode("utf-8")
        ).hexdigest(),
    )
    # Reuse the evaluation renderer so every selected mixture receives header.txt.
    from .cli import _build_scatter_payload_pool

    return _build_scatter_payload_pool(
        conditions,
        ranked[0]["id"],
        payload_count,
        seed,
        conditions_path,
        template_path,
    )


def _summary(manifest: Dict) -> Dict:
    return {
        "mode": manifest["mode"],
        "repository_root": manifest["repository_root"],
        "strategy": manifest["strategy"],
        "payload_pool": manifest["payload_pool"],
        "source_files_selected": manifest["source_files_selected"],
        "files_changed": manifest["files_changed"],
        "placements_written": manifest["placements_written"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repel",
        description="Add, inspect, and exactly remove indexed comment payloads.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="comment-deliver payload files")
    _add_target_arguments(add)
    add.add_argument(
        "--payload",
        type=Path,
        action="append",
        default=[],
        help="override the automatic pool with a UTF-8 file; repeat for a pool",
    )
    add.add_argument(
        "--payload-count",
        type=int,
        default=3,
        help="number of automatically selected bundled payloads (default: 3)",
    )
    add.add_argument("--index", type=Path)
    add.add_argument(
        "--strategy",
        choices=STRATEGIES,
        default=STRATEGIES[0],
        help="comment-delivery strategy (default: replicated)",
    )
    add.add_argument(
        "--positions",
        type=_csv,
        default=list(DEFAULT_REPO_TOOL_POSITIONS),
        help="full-payload positions (default: head,tail)",
    )
    selection = add.add_mutually_exclusive_group()
    selection.add_argument("--count", type=int)
    selection.add_argument(
        "--file",
        type=Path,
        help="target exactly one eligible file, relative to the selected root",
    )
    add.add_argument("--seed", type=int, default=20260805)
    add.add_argument(
        "--instruction-files",
        nargs="?",
        const=list(INSTRUCTION_FILES),
        type=_csv,
        metavar="FILES",
        help=(
            "also target CLAUDE.md, AGENTS.md, and MEMORY.md; optionally pass "
            "a comma-separated subset"
        ),
    )
    add.add_argument(
        "--inline-source-lines", type=int, default=DEFAULT_INLINE_SOURCE_LINES
    )
    add.add_argument("--hub-chunk-lines", type=int, default=DEFAULT_HUB_CHUNK_LINES)
    add.add_argument(
        "--apply", action="store_true", help="write files; default is a dry run"
    )

    for command, help_text in (
        ("status", "show indexed repository state"),
        ("remove", "restore indexed files exactly"),
        ("guard", "exit nonzero unless indexed paths are clean"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        _add_target_arguments(subparser)
        subparser.add_argument("--index", type=Path)
        if command == "remove":
            subparser.add_argument(
                "--apply", action="store_true", help="write files; default is a preview"
            )
    noop = subparsers.add_parser(
        "noop", help="generate and deploy validated native no-op source"
    )
    noop.add_argument(
        "operation",
        choices=("generate", "deploy"),
        help="generate source or manage native source deployment",
    )
    noop.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "noop":
        if args.operation == "generate":
            return noop_cli.main(args.arguments)
        return noop_deploy_cli.main(args.arguments)
    try:
        repository, preferred_index, target_mode = _target_context(
            args.repo, args.git_repo
        )
        index_path, legacy_migration = _operation_index(
            repository,
            preferred_index,
            args.index,
            adding=args.command == "add",
        )
        if args.command == "add":
            if legacy_migration is not None:
                _allow_clean_index_replacement(repository, legacy_migration)
            elif index_path.exists():
                _allow_clean_index_replacement(repository, index_path)
            automatic = not args.payload
            payloads = (
                _automatic_payload_pool(args.seed, args.payload_count)
                if automatic
                else _payload_pool(repository, args.payload)
            )
            target_file = (
                _target_file(repository, args.file) if args.file is not None else None
            )
            manifest = scatter_payload(
                repository,
                payloads[0]["payload"],
                condition_id=payloads[0]["id"],
                count=args.count,
                target_paths=[target_file] if target_file is not None else None,
                seed=args.seed,
                apply=args.apply,
                strategy=args.strategy,
                file_positions=normalize_file_positions(args.positions),
                instruction_files=normalize_instruction_files(
                    args.instruction_files
                ),
                payload_pool=payloads,
                inline_source_lines=args.inline_source_lines,
                hub_chunk_lines=args.hub_chunk_lines,
            )
            manifest["payload_sources"] = [
                {
                    "id": item["id"],
                    "sha256": hashlib.sha256(
                        item["payload"].encode("utf-8")
                    ).hexdigest(),
                }
                for item in payloads
            ]
            if args.apply:
                _write_index_atomically(manifest, index_path)
                if legacy_migration is not None:
                    legacy_migration.unlink()
            output = _summary(manifest)
            output["index"] = str(index_path)
            output["target_mode"] = target_mode
            if target_file is not None:
                output["target_file"] = target_file
            if legacy_migration is not None:
                output["legacy_index_migrated"] = bool(args.apply)
            output["payload_selection"] = (
                "bundled_conditions" if automatic else "explicit_files"
            )
            print(json.dumps(output, indent=2))
            return 0

        scatter, source = resolve_scatter_index(repository, index_path)
        if args.command == "status":
            output = classify_indexed_repository(repository, scatter)
        elif args.command == "remove":
            output = clean_indexed_repository(
                repository, scatter, apply=args.apply
            )
        else:
            output = classify_indexed_repository(repository, scatter)
            if output["state"] != STATE_CLEAN:
                print(
                    f"blocked: state={output['state']} repo={repository} index={source}"
                )
                return 3
        output["index"] = str(source)
        output["target_mode"] = target_mode
        print(json.dumps(output, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    return 2
