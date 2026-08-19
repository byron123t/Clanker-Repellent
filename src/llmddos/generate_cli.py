"""CLI for bounded source generation and static validation."""

from __future__ import annotations

import argparse
import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any, ContextManager, Dict, Optional, Sequence

from .endpoints import load_endpoint_config
from .source_generation import (
    DEFAULT_MAX_TOKENS,
    default_output_directory,
    generate_source_run,
    read_payload,
    select_languages,
    toolchain_inventory,
)
from .opencode_harness import DEFAULT_OPENCODE_TIMEOUT_SECONDS, OpenCodeGenerationHarness
from .provider import RoutedOpenAICompatibleProvider
from .tunnel import managed_ssh_tunnel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "abliterated-remote.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repel generate",
        description=(
            "Generate one statically validated source candidate per requested language with the active local "
            "model discovered from the server, then statically validate it without execution."
        ),
    )
    parser.add_argument("--payload", type=Path, help="UTF-8 payload text file")
    parser.add_argument(
        "--language",
        action="append",
        default=[],
        help="language or comma-separated languages (repeatable; default: all)",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
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
    parser.add_argument(
        "--benign",
        action="store_true",
        help=(
            "use the purely benign control contract: inert declarations only, conservative "
            "side-effect checks, and a separate benign-generation output directory"
        ),
    )
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.8)
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
        help="require non-interactive SSH key authentication instead of prompting",
    )
    parser.add_argument("--list-languages", action="store_true", help="list supported languages and exit")
    parser.add_argument(
        "--list-toolchains",
        action="store_true",
        help="report parser/compiler/linter availability and exit",
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
    if args.payload is None:
        raise ValueError("--payload is required unless listing languages or toolchains")
    if args.validator_timeout <= 0:
        raise ValueError("--validator-timeout must be positive")
    if args.harness == "opencode" and args.opencode_timeout <= 0:
        raise ValueError("--opencode-timeout must be positive")

    payload = read_payload(args.payload)
    if args.retries < 0 or args.retries > 5:
        raise ValueError("--retries must be an integer from 0 to 5")
    output_dir = args.output_dir or default_output_directory(
        PROJECT_ROOT, args.payload, benign=args.benign
    )
    config = load_endpoint_config(args.config)
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
        )
    summary = run_manifest["summary"]
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
                "status": summary["status"],
            },
            indent=2,
        )
    )
    return 0 if summary["status"] in {"passed", "partial"} else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return run(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        print("Cancelled.")
        return 130
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
