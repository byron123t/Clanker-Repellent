#!/usr/bin/env python3
"""Clone the pinned benign repository corpus through the llmddos CLI."""

from __future__ import annotations

import sys

from llmddos.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["clone-benign-repos", *sys.argv[1:]]))
