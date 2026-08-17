#!/usr/bin/env python3
"""Source-tree entry point for ``repel noop deploy``."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llmddos.noop_deploy_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
