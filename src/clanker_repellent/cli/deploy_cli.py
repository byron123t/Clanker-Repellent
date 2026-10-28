"""CLI for placing and removing validated source snippets."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional, Sequence

from ..payload.carrier_deploy import (
    INDEX_FILENAME,
    POSITIONS,
    DeploymentError,
    deploy_carriers,
    remove_deployment,
    status_deployment,
)
from ..payload.retained_deploy import deploy_retained, verify_artifacts
from ..payload import catalog, deployment_store
from ..payload.carrier_deploy import Carrier


def _positions(value: str):
    values = [item.strip() for item in value.split(",") if item.strip()]
    if not values or any(item not in (*POSITIONS, "random") for item in values):
        raise argparse.ArgumentTypeError("positions must be a comma-separated subset of head,mid,tail")
    return list(dict.fromkeys(values))


def _target_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository/current directory (default: cwd)")
    parser.add_argument("--index", type=Path, help=f"deployment index (default: {INDEX_FILENAME})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repel deploy",
        description="Place validated source snippets or retained native/web/WASM data, with exact restoration.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add = subparsers.add_parser("add", help="preview or apply source snippet placement")
    _target_arguments(add)
    inputs = add.add_mutually_exclusive_group(required=True)
    inputs.add_argument(
        "--run-dir",
        type=Path,
        help="generation run directory containing manifest.json (not an individual source file)",
    )
    inputs.add_argument("--payload", type=Path, action="append", default=[], help="UTF-8 text to retain as data; repeat for multiple notes (requires --retain)")
    inputs.add_argument("--catalog", type=Path, help="snippet catalog organized by type")
    add.add_argument("--id", action="append", default=[], help="catalog snippet ID (repeatable)")
    add.add_argument("--tag", action="append", default=[], help="required catalog tag (repeatable)")
    add.add_argument("--kind", choices=catalog.KINDS)
    add.add_argument("--language")
    add.add_argument("--document-type", choices=catalog.DOC_TYPES)
    add.add_argument("--random", action="store_true", help="repeatable random selection of files, snippets, and supported source locations")
    add.add_argument("--seed", type=int, default=0)
    add.add_argument("--count", type=int, help="number of compatible target files")
    add.add_argument("--payload-count", type=int, help="retained records per file; default: one with --random, otherwise all")
    add.add_argument("--store", type=Path, help="private centralized journal/object store")
    add.add_argument("--snapshot", type=Path, action="append", default=[], help="capture an artifact before building; run deploy seal afterwards")
    add.add_argument("--retain", action="store_true", help="retain text/snippets as recoverable C/C++, JS/TS, HTML or WASM data; verify the final build")
    add.add_argument("--benign", action="store_true", help="enforce the benign content checks (requires --retain)")
    add.add_argument("--file", type=Path, action="append", default=[], help="target an exact file; repeat with --retain (default: all eligible files)")
    add.add_argument("--positions", type=_positions, help="head,mid,tail (default: all); source placement only")
    add.add_argument("--allow-partial", action="store_true", help="allow candidates accepted only because toolchains were missing")
    add.add_argument("--apply", action="store_true", help="write files and reversible index; retained data requires a subsequent build/verify; default is a dry run")
    verify = subparsers.add_parser("verify", help="check that retained text is recoverable from each final build artifact")
    _target_arguments(verify)
    verify.add_argument("--artifact", type=Path, action="append", required=True, help="built executable, bundle, HTML or WASM file; relative to --repo; repeat to check several")
    for command in ["seal", "recover"]:
        item = subparsers.add_parser(command, help="seal snapshotted build artifacts" if command == "seal" else "resume exact restoration after an interrupted operation")
        _target_arguments(item)
        if command == "recover":
            item.add_argument("--apply", action="store_true")
            item.add_argument("--store", type=Path, help="locate a shared journal if the index pointer was lost")
    snapshot = subparsers.add_parser("snapshot", help="save original executable, response, or packet-capture bytes before an external transformation")
    _target_arguments(snapshot)
    snapshot.add_argument("--artifact", type=Path, action="append", required=True)
    snapshot.add_argument("--store", type=Path)
    snapshot.add_argument("--apply", action="store_true")
    inspect = subparsers.add_parser("inspect", help="show journal locations, byte offsets, and hashes")
    _target_arguments(inspect)
    inspect.add_argument("--include-text", action="store_true", help="also show stored snippets (binary content uses base64)")
    for command, help_text in (("status", "show indexed source snippet state"), ("remove", "restore original file contents exactly")):
        item = subparsers.add_parser(command, help=help_text)
        _target_arguments(item)
        if command == "remove":
            item.add_argument("--apply", action="store_true", help="restore files; default is a preview")
    return parser


def run(args: argparse.Namespace) -> int:
    if args.command == "add":
        entries = []
        if args.catalog:
            items = catalog.select(args.catalog, identifiers=args.id, tags=args.tag, kind=args.kind,
                                   language=args.language, document_type=args.document_type, benign=args.benign)
            if not items:
                raise DeploymentError("no catalog snippets match the filters")
            entries = [catalog.read(args.catalog, item["id"]) for item in items]
        elif args.id or args.tag or args.kind or args.language or args.document_type:
            raise DeploymentError("type/tag/id filters require --catalog")
        if args.retain:
            if args.positions:
                raise DeploymentError("--positions applies to source placement, not --retain")
            output = deploy_retained(
                repository=args.repo, payloads=args.payload, run_dir=args.run_dir,
                target_files=args.file, benign=args.benign, apply=args.apply,
                allow_partial=args.allow_partial, index_path=args.index,
                catalog_entries=entries, randomize=args.random, seed=args.seed, count=args.count,
                payload_count=args.payload_count, store_path=args.store, snapshots=args.snapshot,
            )
        else:
            if args.payload or args.benign and not args.catalog:
                raise DeploymentError("--payload and --benign require --retain")
            if args.payload_count is not None:
                raise DeploymentError("--payload-count currently applies to retained deployment")
            if any(item[0]["kind"] != "source" for item in entries):
                raise DeploymentError("document/data catalog entries require --retain")
            if len(args.file) > 1:
                raise DeploymentError("repeated --file requires --retain")
            output = deploy_carriers(
                run_dir=args.run_dir,
                repository=args.repo,
                positions=args.positions or (["random"] if args.random else list(POSITIONS)),
                target_file=args.file[0] if args.file else None,
                apply=args.apply,
                allow_partial=args.allow_partial,
                index_path=args.index,
                carriers=[Carrier(m["id"], m["language"], text, m["sha256"], m["object"]) for m, text in entries] if entries else None,
                randomize=args.random, seed=args.seed, count=args.count,
                store_path=args.store, snapshots=args.snapshot,
            )
    elif args.command == "snapshot":
        root = args.repo.resolve()
        output = {"schema_version": 2, "kind": "repel_carrier_deployment", "repository_root": str(root),
                  "files": [], "status": "planned", "artifacts": [str(p) for p in args.artifact]}
        if args.apply:
            deployment_store.apply_plan(root, args.index or root / INDEX_FILENAME, output, {},
                                        store_path=args.store, snapshots=args.artifact)
            output["status"] = "applied"
    elif args.command == "seal":
        output = deployment_store.seal(args.repo, args.index or args.repo.resolve() / INDEX_FILENAME)
    elif args.command == "inspect":
        output = deployment_store.inspect(args.repo, args.index or args.repo.resolve() / INDEX_FILENAME, include_text=args.include_text)
    elif args.command == "recover":
        output = deployment_store.recover(args.repo, args.index or args.repo.resolve() / INDEX_FILENAME, store_path=args.store, apply=args.apply)
    elif args.command == "verify":
        output = verify_artifacts(repository=args.repo, artifacts=args.artifact, index_path=args.index)
    elif args.command == "remove":
        output = remove_deployment(repository=args.repo, index_path=args.index, apply=args.apply)
    else:
        output = status_deployment(repository=args.repo, index_path=args.index)
    print(json.dumps(output, indent=2))
    if args.command == "verify" and output["status"] != "verified":
        return 3
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return run(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        print("Cancelled.")
        return 130
    except (DeploymentError, OSError, UnicodeError, ValueError, sqlite3.Error) as exc:
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
