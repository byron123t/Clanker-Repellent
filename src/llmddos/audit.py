"""Blinded human-audit sampling and heuristic validation."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


VALID_HUMAN_OUTCOMES = {
    "task_completed",
    "scoped_refusal",
    "full_refusal",
    "task_failure",
}


def audit_id(trial_id: str) -> str:
    return hashlib.sha256(("audit-v1|" + trial_id).encode("utf-8")).hexdigest()[:16]


def _task_from_row(row: Dict[str, Any]) -> str:
    content = row["messages"][-1]["content"]
    first_line = content.splitlines()[0]
    return first_line.removeprefix("Task: ")


def _load(paths: Sequence[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("status") == "ok":
                    rows.append(row)
    return rows


def export_blinded_sample(
    input_paths: Sequence[Path],
    output_path: Path,
    sample_size: Optional[int] = None,
    seed: int = 20260802,
) -> int:
    rows = _load(input_paths)
    if sample_size is not None and sample_size < 1:
        raise ValueError("sample_size must be positive")
    random.Random(seed).shuffle(rows)
    if sample_size is not None:
        rows = rows[:sample_size]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "audit_id",
                "task",
                "expected_terms",
                "response_text",
                "human_outcome",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "audit_id": audit_id(row["trial_id"]),
                    "task": _task_from_row(row),
                    "expected_terms": json.dumps(row["expected_terms"], ensure_ascii=False),
                    "response_text": row["response_text"],
                    "human_outcome": "",
                    "notes": "",
                }
            )
    return len(rows)


def evaluate_audit(input_paths: Sequence[Path], audit_path: Path) -> Dict[str, Any]:
    result_rows = _load(input_paths)
    by_audit_id = {audit_id(row["trial_id"]): row for row in result_rows}
    confusion: Dict[str, Counter] = defaultdict(Counter)
    evaluated = 0
    agreements = 0
    with audit_path.open("r", encoding="utf-8", newline="") as handle:
        for audit_row in csv.DictReader(handle):
            human = audit_row["human_outcome"].strip()
            if not human:
                continue
            if human not in VALID_HUMAN_OUTCOMES:
                raise ValueError(f"Invalid human_outcome {human!r} for {audit_row['audit_id']}")
            source = by_audit_id.get(audit_row["audit_id"])
            if source is None:
                raise ValueError(f"Unknown audit_id {audit_row['audit_id']}")
            heuristic = source["metrics"]["outcome"]
            confusion[human][heuristic] += 1
            evaluated += 1
            agreements += int(human == heuristic)
    labels = sorted(VALID_HUMAN_OUTCOMES)
    return {
        "evaluated": evaluated,
        "accuracy": agreements / evaluated if evaluated else None,
        "labels": labels,
        "confusion_matrix": {
            human: {heuristic: confusion[human][heuristic] for heuristic in labels}
            for human in labels
        },
    }
