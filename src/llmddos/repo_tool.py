"""Small payload add/status/remove/guard CLI for authorized repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .dataset import load_conditions
from .payload_scatter import (
    DEFAULT_FILE_POSITIONS,
    DEFAULT_HUB_CHUNK_LINES,
    DEFAULT_INLINE_SOURCE_LINES,
    INSTRUCTION_FILES,
    STRATEGIES,
    normalize_file_positions,
    normalize_instruction_files,
    scatter_payload,
    write_scatter_manifest,
)
from .publication_guard import (
    STATE_CLEAN,
    classify_indexed_repository,
    clean_indexed_repository,
    resolve_scatter_index,
)


def _csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def default_index_path(repository: Path) -> Path:
    root = repository.resolve()
    return root.parent / f".{root.name}.guardrail-index.json"


def _index_path(repository: Path, value: Optional[Path]) -> Path:
    return value.resolve() if value is not None else default_index_path(repository)


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
        prog="guardrail-anaphylaxis",
        description="Add, inspect, and exactly remove indexed comment payloads.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="comment-deliver payload files")
    add.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="target repository (default: current directory)",
    )
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
    add.add_argument("--positions", type=_csv, default=list(DEFAULT_FILE_POSITIONS))
    add.add_argument("--count", type=int)
    add.add_argument("--seed", type=int, default=20260805)
    add.add_argument(
        "--instruction-files",
        nargs="?",
        const=list(INSTRUCTION_FILES),
        type=_csv,
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
        subparser.add_argument(
            "--repo",
            type=Path,
            default=Path.cwd(),
            help="target repository (default: current directory)",
        )
        subparser.add_argument("--index", type=Path)
        if command == "remove":
            subparser.add_argument(
                "--apply", action="store_true", help="write files; default is a preview"
            )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repository = args.repo.resolve()
        index_path = _index_path(repository, args.index)
        if args.command == "add":
            if index_path.exists():
                raise ValueError(
                    f"index already exists: {index_path}; remove or choose --index"
                )
            automatic = not args.payload
            payloads = (
                _automatic_payload_pool(args.seed, args.payload_count)
                if automatic
                else _payload_pool(repository, args.payload)
            )
            manifest = scatter_payload(
                repository,
                payloads[0]["payload"],
                condition_id=payloads[0]["id"],
                count=args.count,
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
                write_scatter_manifest(manifest, index_path)
            output = _summary(manifest)
            output["index"] = str(index_path)
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
        print(json.dumps(output, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    return 2
