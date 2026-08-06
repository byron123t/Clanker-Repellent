#!/usr/bin/env python3
"""Remove an indexed evaluation payload without payload-string matching."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llmddos.publication_guard import (  # noqa: E402
    clean_indexed_repository,
    resolve_scatter_index,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--scatter-manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output-manifest", type=Path)
    args = parser.parse_args()
    try:
        scatter, source = resolve_scatter_index(
            args.repository, args.scatter_manifest
        )
        result = clean_indexed_repository(
            args.repository, scatter, apply=args.apply
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    result["scatter_manifest"] = str(source)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output_manifest:
        args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.output_manifest.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
