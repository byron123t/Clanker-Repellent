#!/usr/bin/env python3
"""Aggregate eval runner JSONL into a per-group refusal-rate table.

Groups records by (guardrail, dimension, family, placement) and reports the
full-refusal rate with a Wilson 95% interval, reusing
``clanker_repellent.measurement.metrics.wilson_interval``. Provider/infra rows
(dry-run rows, or outcomes that are neither completion nor refusal) are excluded
from the denominator so ordinary model failure is not counted as a payload effect.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clanker_repellent.measurement.metrics import wilson_interval  # noqa: E402

SCORED = {"task_completed", "scoped_refusal", "full_refusal", "task_failure"}


def read_records(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def summarize(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("outcome") not in SCORED:
            continue
        key = (record.get("guardrail", ""), record.get("dimension", ""),
               record.get("family", ""), record.get("placement", ""))
        groups[key].append(record)

    rows: List[Dict[str, Any]] = []
    for (guardrail, dimension, family, placement), items in sorted(groups.items()):
        total = len(items)
        refusals = sum(1 for r in items if r.get("outcome") == "full_refusal")
        low, high = wilson_interval(refusals, total)
        rows.append({
            "guardrail": guardrail, "dimension": dimension, "family": family,
            "placement": placement, "n": total, "full_refusals": refusals,
            "refusal_rate": round(refusals / total, 4) if total else 0.0,
            "ci95_low": round(low, 4), "ci95_high": round(high, 4),
        })
    return rows


def render_table(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "(no scored rows; run the dimensions against a reachable endpoint)"
    headers = ["guardrail", "dimension", "family", "placement", "n", "refusal_rate", "ci95"]
    lines = ["\t".join(headers)]
    for row in rows:
        lines.append("\t".join([
            row["guardrail"], row["dimension"], row["family"], row["placement"],
            str(row["n"]), f"{row['refusal_rate']:.3f}",
            f"[{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]",
        ]))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate eval result JSONL into refusal rates.")
    parser.add_argument("results", nargs="+", type=Path, help="one or more runner JSONL outputs")
    parser.add_argument("--json", action="store_true", help="emit grouped rows as JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    rows = summarize(read_records(args.results))
    print(json.dumps(rows, indent=2) if args.json else render_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
