#!/usr/bin/env python3
"""Streaming chat client entry point (source-checkout convenience wrapper).

The implementation lives in ``clanker_repellent.inference.interactive``; this
script only ensures ``src`` is importable from a source checkout and re-exports
the module's names so it can be run directly or loaded by tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clanker_repellent.inference import interactive as _interactive  # noqa: E402

# Re-export every public and private name so callers that load this file by
# path (e.g. tests) see the full module surface.
globals().update({k: v for k, v in vars(_interactive).items() if k != "__name__"})

if __name__ == "__main__":
    raise SystemExit(_interactive.main())
