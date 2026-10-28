#!/usr/bin/env python3
"""Restore an unchanged evaluation workspace using its external placement index."""

from __future__ import annotations

import sys

from clanker_repellent.cli.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["remove-scattered-payloads", *sys.argv[1:]]))
