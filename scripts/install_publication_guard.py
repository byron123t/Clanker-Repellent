#!/usr/bin/env python3
"""Install the Clanker Repellent publication check as a pre-commit hook."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clanker_repellent.payload.publication_guard import install_pre_commit_guard  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--scatter-manifest", type=Path, required=True)
    args = parser.parse_args()
    guard_script = Path(__file__).resolve().with_name("guard_publication.py")
    try:
        hook = install_pre_commit_guard(
            args.repository,
            args.scatter_manifest,
            guard_script,
            python_executable=Path(sys.executable),
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"installed publication guard: {hook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
