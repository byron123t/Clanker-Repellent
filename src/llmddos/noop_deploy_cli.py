"""CLI for deploying and removing validated native no-op carriers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from .noop_deploy import (
    INDEX_FILENAME,
    POSITIONS,
    DeploymentError,
    deploy_carriers,
    remove_deployment,
    status_deployment,
)


def _positions(value: str):
    values = [item.strip() for item in value.split(",") if item.strip()]
    if not values or any(item not in POSITIONS for item in values):
        raise argparse.ArgumentTypeError("positions must be a comma-separated subset of head,mid,tail")
    return list(dict.fromkeys(values))


def _target_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository/current directory (default: cwd)")
    parser.add_argument("--index", type=Path, help=f"deployment index (default: {INDEX_FILENAME})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anaphylaxis noop deploy",
        description="Place accepted language-native no-op carriers with syntax-aware alignment and host validation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add = subparsers.add_parser("add", help="plan or apply native carrier injections")
    _target_arguments(add)
    add.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="generation run directory containing manifest.json (not a carrier file)",
    )
    add.add_argument("--file", type=Path, help="target one source file instead of all eligible files")
    add.add_argument("--positions", type=_positions, default=list(POSITIONS), help="head,mid,tail (default: all)")
    add.add_argument("--allow-partial", action="store_true", help="allow candidates accepted only because toolchains were missing")
    add.add_argument("--apply", action="store_true", help="write files and the reversible index after all matching files validate; default is a dry run")
    for command, help_text in (("status", "show native-carrier index state"), ("remove", "restore exact preimages")):
        item = subparsers.add_parser(command, help=help_text)
        _target_arguments(item)
        if command == "remove":
            item.add_argument("--apply", action="store_true", help="restore files; default is a preview")
    return parser


def run(args: argparse.Namespace) -> int:
    if args.command == "add":
        output = deploy_carriers(
            run_dir=args.run_dir,
            repository=args.repo,
            positions=args.positions,
            target_file=args.file,
            apply=args.apply,
            allow_partial=args.allow_partial,
            index_path=args.index,
        )
    elif args.command == "remove":
        output = remove_deployment(repository=args.repo, index_path=args.index, apply=args.apply)
    else:
        output = status_deployment(repository=args.repo, index_path=args.index)
    print(json.dumps(output, indent=2))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return run(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        print("Cancelled.")
        return 130
    except (DeploymentError, OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
