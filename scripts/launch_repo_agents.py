#!/usr/bin/env python3
"""Open Codex and Claude interactively in matched repository variants."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clanker_repellent.cli.repo_cli_launcher import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
