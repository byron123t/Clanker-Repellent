#!/usr/bin/env python3
"""Clone the pinned benign repository corpus through the clanker_repellent CLI."""

from __future__ import annotations

import sys

from clanker_repellent.cli.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["clone-benign-repos", *sys.argv[1:]]))
