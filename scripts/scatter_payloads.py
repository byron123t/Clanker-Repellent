#!/usr/bin/env python3
"""Apply one payload propagation strategy to a disposable repository."""

from __future__ import annotations

import sys

from llmddos.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["scatter-payloads", *sys.argv[1:]]))
