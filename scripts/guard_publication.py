#!/usr/bin/env python3
"""Block a commit or publish step unless an indexed repository is clean."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clanker_repellent.payload.publication_guard import (  # noqa: E402
    STATE_CLEAN,
    classify_indexed_repository,
    resolve_scatter_index,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--scatter-manifest", type=Path)
    args = parser.parse_args()
    try:
        scatter, source = resolve_scatter_index(
            args.repository, args.scatter_manifest
        )
        result = classify_indexed_repository(args.repository, scatter)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if result["state"] != STATE_CLEAN:
        print(
            "publication blocked: "
            f"state={result['state']} manifest={source} repository={args.repository}"
        )
        return 3
    print(f"publication guard: clean repository={args.repository} manifest={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
