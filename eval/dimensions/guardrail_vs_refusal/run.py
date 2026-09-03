#!/usr/bin/env python3
"""Run this research dimension across its configured guardrails.

Thin wrapper over ``eval/runner.py`` that reads the sibling ``config.json`` and
invokes the shared runner once per guardrail, writing results under
``eval/results/<dimension>/<guardrail>.jsonl``.

Endpoints are currently unreachable, so this defaults to ``--dry-run`` (compose +
record without network). Pass ``--live`` once a guardrail endpoint is set in .env.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "eval"))

import runner  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="contact real endpoints (requires guardrail env vars)")
    args = parser.parse_args(argv)

    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    conditions_path = ROOT / config["conditions"]
    out_dir = ROOT / "eval" / "results" / config["dimension"]

    for guardrail in config["guardrails"]:
        guardrail_config = ROOT / "eval" / "configs" / "guardrails" / f"{guardrail}.json"
        records = runner.run(
            guardrail_config,
            runner.read_jsonl(conditions_path),
            runner.load_task(None),
            repeats=config.get("repeats", 1),
            max_tokens=config.get("max_tokens", 256),
            dry_run=not args.live,
            guardrail_name=guardrail,
            dimension=config["dimension"],
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{guardrail}.jsonl"
        with out.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        print(f"{guardrail}: wrote {len(records)} records to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
