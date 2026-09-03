#!/usr/bin/env python3
"""Remove payloads from an untouched repository using an external scatter index."""

from __future__ import annotations

import sys

from clanker_repellent.cli.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["remove-scattered-payloads", *sys.argv[1:]]))
