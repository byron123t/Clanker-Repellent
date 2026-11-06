"""CLI for bounded source generation and static validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from typing import Any, ContextManager, Dict, Optional, Sequence

from ..inference.endpoints import load_endpoint_config
from ..generate.source_generation import (
    DEFAULT_MAX_TOKENS,
    GenerationAlreadyComplete,
    default_output_directory,
    generate_source_run,
    read_payload,
    select_languages,
    toolchain_inventory,
)
from ..generate.opencode_harness import DEFAULT_OPENCODE_TIMEOUT_SECONDS, OpenCodeGenerationHarness
from ..generate.functional_structure import FUNCTIONAL_PROFILE
from ..generate.structure import STRUCTURE_PROFILE
from ..inference.provider import RoutedOpenAICompatibleProvider
from ..inference.tunnel import managed_ssh_tunnel


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "abliterated-remote.json"
LOCAL_CONFIG = PROJECT_ROOT / ".repel-generate.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repel generate",
        description=(
            "Generate source candidates for repository evaluation with the active model "
            "discovered from the server. Validate each requested language without executing "
            "the candidate. Use --benign for the inert control contract."
        ),
    )
    parser.add_argument("input", nargs="?", type=Path, help="UTF-8 input file or a directory of .txt files (recursive)")
    parser.add_argument("--payload", type=Path, help="input file or directory (alias for INPUT)")
    parser.add_argument("--catalog", type=Path, help="read a typed catalog input and/or register accepted generated source")
    parser.add_argument("--payload-id", help="catalog input ID instead of --payload")
    parser.add_argument("--register-prefix", help="register passed candidates as PREFIX-language in --catalog")
    parser.add_argument("--tag", action="append", default=[], help="tag registered candidates (repeatable)")
    parser.add_argument(
        "--language", "--format",
        action="append",
        default=[],
        help="language/format or comma-separated targets (repeatable; default: configured targets or all)",
    )
    parser.add_argument("--config", type=Path, default=None,
                        help="endpoint configuration (default: .repel-generate.json, then the bundled remote config)")
    parser.add_argument("--endpoint", help="use this already-running OpenAI-compatible server; keep generation defaults but skip configured SSH/authentication")
    parser.add_argument(
        "--harness",
        choices=("direct", "opencode"),
        default="direct",
        help="inference driver (default: direct OpenAI-compatible completion)",
    )
    parser.add_argument(
        "--opencode-bin",
        default="opencode",
        help="OpenCode executable used with --harness opencode",
    )
    parser.add_argument(
        "--opencode-timeout",
        type=float,
        default=DEFAULT_OPENCODE_TIMEOUT_SECONDS,
        help="maximum seconds for each OpenCode attempt (default: 900)",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--structure", choices=("functional", "data"), default="functional",
                        help="require input-dependent functions (default) or populated data; document targets use structured data, HTML uses markup, SQL uses queries")
    parser.add_argument(
        "--benign",
        action="store_true",
        help=(
            "use the benign control contract with conservative "
            "side-effect checks, and a separate benign-generation output directory"
        ),
    )
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument(
        "--no-thinking", action="store_true", default=None,
        help="ask compatible local servers to disable extended reasoning (direct harness only)",
    )
    parser.add_argument("--thinking", action="store_false", dest="no_thinking",
                        help="override a saved no-thinking preference")
    parser.add_argument(
        "--show-content", action="store_true",
        help="print full model requests and responses (default: metadata only)",
    )
    parser.add_argument("--validator-timeout", type=float, default=20.0)
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="additional independent attempts per language after a failed attempt (0-5)",
    )
    parser.add_argument(
        "--skip-linters",
        action="store_true",
        help="run required parsers/compilers but skip optional standalone linters",
    )
    parser.add_argument(
        "--allow-missing-toolchains",
        action="store_true",
        help="accept partial results when a required compiler/parser is unavailable",
    )
    parser.add_argument(
        "--keep-raw-responses",
        action="store_true",
        help="store complete model responses beside candidates (results are sensitive)",
    )
    parser.add_argument(
        "--batch-ssh",
        action="store_true",
        default=None,
        help="require non-interactive SSH key authentication instead of prompting",
    )
    parser.add_argument("--list-languages", "--list-formats", action="store_true", help="list supported generation targets and exit")
    parser.add_argument(
        "--list-toolchains",
        action="store_true",
        help="report parser/compiler/linter executable presence (usability is checked during validation)",
    )
    return parser


def _print_languages(targets: Sequence[Any]) -> None:
    for target in targets:
        print(f"{target.language}\t{target.output_filename}")


def _print_toolchains(inventory: Sequence[Dict[str, Any]]) -> None:
    for item in inventory:
        availability = "available" if item["available"] else "missing"
        requirement = "required" if item["required"] else "optional"
        print(
            f"{item['language']}\t{item['check']}\t{item['kind']}\t"
            f"{requirement}\t{item['tool']}\t{availability}"
        )


def _tunnel_context(
    config: Dict[str, Any], batch_ssh: bool
) -> ContextManager[Dict[str, Any]]:
    ssh = config.get("ssh")
    if ssh is None:
        return nullcontext({"status": "not_configured"})
    return managed_ssh_tunnel(ssh, interactive_auth=not batch_ssh)


def run(args: argparse.Namespace) -> int:
    targets = select_languages(args.language)
    if args.list_languages:
        _print_languages(targets)
        return 0
    if args.list_toolchains:
        _print_toolchains(toolchain_inventory(targets))
        return 0
    args = argparse.Namespace(**vars(args))
    if args.input is not None:
        if args.payload is not None or args.payload_id is not None:
            raise ValueError("choose INPUT, --payload, or --payload-id")
        args.payload = args.input
        args.input = None
    if args.payload is None and args.payload_id is None:
        raise ValueError("provide an input file or folder, e.g. repel generate ./benign --benign")
    if args.payload is not None and args.payload_id is not None:
        raise ValueError("choose --payload or --payload-id")
    if (args.payload_id or args.register_prefix) and not args.catalog:
        raise ValueError("--payload-id/--register-prefix require --catalog")
    args.config = args.config or (LOCAL_CONFIG if LOCAL_CONFIG.is_file() else DEFAULT_CONFIG)
    config = load_endpoint_config(args.config, **({"endpoint_override": args.endpoint} if args.endpoint else {}))
    defaults = config.get("generation", {})
    if not isinstance(defaults, dict):
        raise ValueError("configuration generation defaults must be an object")
    languages = defaults.get("languages", [])
    if not isinstance(languages, list) or not all(isinstance(value, str) for value in languages):
        raise ValueError("generation.languages must be a list of language names")
    targets = select_languages(args.language or languages)
    for name in ("no_thinking", "batch_ssh"):
        if getattr(args, name) is None:
            value = defaults.get(name, False)
            if not isinstance(value, bool):
                raise ValueError(f"generation.{name} must be a boolean")
            setattr(args, name, value)
    if args.max_tokens is None:
        args.max_tokens = defaults.get("max_tokens", DEFAULT_MAX_TOKENS)
    if not isinstance(args.max_tokens, int) or isinstance(args.max_tokens, bool) or args.max_tokens < 1:
        raise ValueError("generation max_tokens must be a positive integer")
    if args.validator_timeout <= 0:
        raise ValueError("--validator-timeout must be positive")
    if args.harness == "opencode" and args.opencode_timeout <= 0:
        raise ValueError("--opencode-timeout must be positive")
    if args.harness != "direct" and args.no_thinking:
        raise ValueError("--no-thinking requires --harness direct")
    if args.payload is not None and args.payload.is_dir():
        return _run_directory(args, config)

    if args.payload_id:
        from ..payload import catalog
        metadata, payload = catalog.read(args.catalog, args.payload_id)
        if args.benign and not metadata["benign"]:
            raise ValueError("--benign requires a benign catalog input")
    else:
        payload = read_payload(args.payload)
    if args.retries < 0 or args.retries > 5:
        raise ValueError("--retries must be an integer from 0 to 5")
    output_dir = args.output_dir or default_output_directory(
        PROJECT_ROOT, args.payload or Path(args.payload_id + ".txt"), benign=args.benign
    )
    provider = RoutedOpenAICompatibleProvider(config)

    if config.get("ssh") is not None and not args.batch_ssh:
        print("SSH authentication may prompt; credentials are handled by ssh and not stored.")
    with _tunnel_context(config, args.batch_ssh) as tunnel:
        print(f"SSH tunnel: {tunnel['status']}")
        print("Waiting for endpoint health and discovering /v1/models...")
        model = provider.wait_for_model()
        print(f"Model: {model}")
        generation_provider: Any = provider
        if args.harness == "opencode":
            route_name = config.get("_discovery_route") or next(iter(config["models"]))
            route = config["models"][route_name]
            generation_provider = OpenCodeGenerationHarness(
                model=model,
                base_url=route["base_url"],
                api_key=provider.api_key_for_route(route_name),
                binary=args.opencode_bin,
                timeout_seconds=args.opencode_timeout,
            )
        print(f"Harness: {args.harness}")
        print(f"Mode: {'benign' if args.benign else 'standard'}")
        print(f"Structure: {args.structure}")
        run_manifest = generate_source_run(
            provider=generation_provider,
            model=model,
            payload=payload,
            targets=targets,
            output_dir=output_dir,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            run_linters=not args.skip_linters,
            allow_missing_toolchains=args.allow_missing_toolchains,
            keep_raw_responses=args.keep_raw_responses,
            validator_timeout_seconds=args.validator_timeout,
            retries=args.retries,
            benign=args.benign,
            show_content=args.show_content,
            no_thinking=args.no_thinking,
            structure_profile=FUNCTIONAL_PROFILE if args.structure == "functional" else STRUCTURE_PROFILE,
        )
    summary = run_manifest["summary"]
    print("Attempt outcomes: " + json.dumps(run_manifest.get("attempt_status_counts", {}), sort_keys=True))
    if args.register_prefix and any(c.get("status") == "passed" for c in run_manifest["candidates"]):
        from ..payload import catalog
        catalog.import_run(args.catalog, output_dir, prefix=args.register_prefix, tags=args.tag, benign=args.benign)
    for candidate in run_manifest["candidates"]:
        checks = candidate.get("validation", {}).get("checks", [])
        check_summary = ", ".join(
            f"{check['name']}={check['status']}" for check in checks
        )
        attempts = len(candidate.get("attempts", []))
        suffix = f"; checks: {check_summary}" if check_summary else ""
        print(
            f"{candidate['language']}: {candidate.get('status')} "
            f"(attempts={attempts}){suffix}"
        )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir.resolve()),
                "requested": summary["requested"],
                "accepted": summary["accepted"],
                "failed": summary["failed"],
                "pending": summary["pending"],
                "status": summary["status"],
            },
            indent=2,
        )
    )
    return 0 if summary["status"] in {"passed", "partial"} else 1


def _run_directory(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    """Process text inputs without following links or mixing input and output trees."""
    root = args.payload.resolve()
    if args.output_dir is None:
        timestamped = default_output_directory(PROJECT_ROOT, benign=args.benign)
        output = timestamped.parent / root.name / timestamped.name
    else:
        output = args.output_dir.resolve()
    if output == root or root in output.parents:
        raise ValueError("batch output directory must be outside the input directory")
    inputs = []
    for directory, folders, filenames in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders if not (Path(directory) / name).is_symlink())
        for name in sorted(filenames):
            path = Path(directory) / name
            if path.suffix.casefold() == ".txt" and not path.is_symlink() and path.is_file():
                inputs.append(path)
    if not inputs:
        raise ValueError(f"no .txt files found in {root}")
    failed = 0
    skipped = 0
    # Keep any CLI-owned tunnel alive for the batch; child runs reuse its open ports.
    with _tunnel_context(config, args.batch_ssh):
        for number, path in enumerate(inputs, 1):
            relative = path.relative_to(root)
            child = argparse.Namespace(**vars(args))
            child.input = None
            child.payload = path
            child.output_dir = output / relative
            if args.register_prefix:
                identifier = hashlib.sha256(relative.as_posix().encode()).hexdigest()[:16]
                child.register_prefix = f"{args.register_prefix}-{identifier}"
            print(f"Input {number}/{len(inputs)}: {relative}", flush=True)
            try:
                failed += run(child) != 0
            except GenerationAlreadyComplete:
                print("Already complete; existing candidates preserved.", flush=True)
                skipped += 1
            except (OSError, RuntimeError, TimeoutError, ValueError, sqlite3.Error) as exc:
                # Input/model text must not escape through exception messages in a folder run.
                print(f"Input failed: {type(exc).__name__}", flush=True)
                failed += 1
    print(json.dumps({"output_dir": str(output), "inputs": len(inputs),
                      "passed_inputs": len(inputs) - failed, "failed_inputs": failed,
                      "already_complete_inputs": skipped}, indent=2))
    return 1 if failed else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return run(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        print("Cancelled.")
        return 130
    except (OSError, RuntimeError, TimeoutError, ValueError, sqlite3.Error) as exc:
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
