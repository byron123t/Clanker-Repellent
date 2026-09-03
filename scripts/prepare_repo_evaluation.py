#!/usr/bin/env python3
"""Create or reset disposable payload-injected repository workspaces."""

from __future__ import annotations

import sys

from clanker_repellent.cli.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["prepare-repo-evaluation", *sys.argv[1:]]))
