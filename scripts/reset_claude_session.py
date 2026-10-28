#!/usr/bin/env python3
"""Reset local Claude history only for this exact clanker-repellent checkout.

Preview: python3 scripts/reset_claude_session.py
Reset:   python3 scripts/reset_claude_session.py --apply

Uses Claude's project purge to remove this checkout's saved conversations,
auto memory, prompt-history entries, and Claude project state. Repository files
are preserved. Close any Claude session in this checkout before applying.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Optional, Sequence


REPOSITORY = Path(
    "/Users/bjaytang/Desktop/github/telegram/sandbox/clanker-repellent"
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
        epilog=f"Fixed target: {REPOSITORY}. No other target is accepted.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="preview the reset (default)"
    )
    mode.add_argument(
        "--apply", action="store_true", help="delete this checkout's local Claude state"
    )
    args = parser.parse_args(argv)

    if Path(__file__).resolve().parent != REPOSITORY / "scripts":
        parser.error(f"this script must live in {REPOSITORY / 'scripts'}")
    for name in ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_PROJECT_DIR_NAME"):
        if os.environ.get(name):
            parser.error(f"unset {name} to reset this checkout's default Claude data")
    executable = shutil.which("claude")
    if executable is None:
        parser.error("claude is not installed or is not on PATH")

    command = [
        executable,
        "purge",
        str(REPOSITORY),
        "--yes" if args.apply else "--dry-run",
    ]
    try:
        return subprocess.run(command, cwd=REPOSITORY, check=False).returncode
    except OSError as exc:
        print(f"Cannot run Claude project reset: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
