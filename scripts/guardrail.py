#!/usr/bin/env python3
"""Run the small GuardrailAnaphylaxis repository payload CLI."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llmddos.repo_tool import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
