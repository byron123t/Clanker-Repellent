#!/usr/bin/env python3
"""Place test comments in a disposable repository using a selected layout."""

from __future__ import annotations

import sys

from clanker_repellent.cli.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["scatter-payloads", *sys.argv[1:]]))
