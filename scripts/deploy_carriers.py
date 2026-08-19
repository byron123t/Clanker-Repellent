#!/usr/bin/env python3
"""Source-tree entry point for ``repel deploy``."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llmddos.deploy_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
