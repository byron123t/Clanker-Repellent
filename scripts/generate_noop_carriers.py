#!/usr/bin/env python3
"""Source-tree entry point for inert payload-carrier generation."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llmddos.noop_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
