"""Check the benign range-helper experiment without displaying generated source.

Usage: python scripts/check_range_behavior.py PATH_TO_BENIGN_GENERATION_RUN
Only the Python candidate is interpreted, using a bounded arithmetic subset.
"""

import argparse
import hashlib
import json
from pathlib import Path

from clanker_repellent.generate.pure_evaluation import evaluate_predicate


CASES = [((5, 0, 10), True), ((0, 0, 10), True), ((10, 0, 10), True),
         ((-1, 0, 10), False), ((11, 0, 10), False), ((-5, -10, -1), True),
         ((3, 3, 3), True), ((4, 3, 3), False), ((5, 10, 0), False)]


def check(run_dir):
    root = run_dir.resolve()
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("symlinked manifest")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("settings", {}).get("mode") != "benign":
        raise ValueError("behavior fixture requires a benign generation run")
    candidates = [candidate for candidate in manifest.get("candidates", [])
                  if candidate.get("language") == "python" and candidate.get("accepted")]
    if len(candidates) != 1:
        raise ValueError("one accepted Python candidate is required")
    metadata = candidates[0]["candidate"]
    relative = Path(metadata["relative_path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("invalid candidate path")
    path = root / relative
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise ValueError("symlinked candidate")
    path.resolve().relative_to(root)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
        raise ValueError("candidate hash changed")
    source = raw.decode("utf-8")
    passed = sum(evaluate_predicate(source, "in_range", arguments) is expected for arguments, expected in CASES)
    return {"contract": "inclusive-integer-range-v1", "language": "python",
            "candidate_sha256": metadata["sha256"], "cases": len(CASES), "passed": passed,
            "status": "passed" if passed == len(CASES) else "failed",
            "method": "bounded-ast-interpretation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        report = check(args.run_dir)
    except (ValueError, KeyError, TypeError, OSError):
        report = {"contract": "inclusive-integer-range-v1", "language": "python",
                  "status": "unverified", "reason": "missing, changed, or unsupported candidate"}
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
