#!/usr/bin/env python3
"""Run the Clanker Repellent repository CLI from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clanker_repellent.cli.repo_tool import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
