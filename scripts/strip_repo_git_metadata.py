#!/usr/bin/env python3
"""Strip Git metadata from task repositories through the clanker_repellent CLI."""

from __future__ import annotations

import sys

from clanker_repellent.cli.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["strip-repo-git-metadata", *sys.argv[1:]]))
