"""Read-only, checksum-verified views of a deployment/response journal."""
from __future__ import annotations

import base64
import codecs
import hashlib
import json
import re
import shlex
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ..payload.deployment_store import digest, location, safe_path


def percentage(part, whole):
    return round(100 * part / whole, 1) if whole else None


def placement_spans(row):
    """Map byte ranges through subsequent edits, including split/deleted ranges."""
    spans = []
    length = row.get("bytes_before", 0)
    for step, edit in enumerate(row.get("edits", [])):
        offset, removed, inserted = (edit[k] for k in ("offset_before_step", "removed_bytes", "inserted_bytes"))
        if any(not isinstance(v, int) or v < 0 for v in (offset, removed, inserted)) or offset + removed > length:
            raise ValueError("journal contains an invalid byte edit")
        following = []
        end, shift = offset + removed, inserted - removed
        for start, stop, previous in spans:
            if start < offset:
                following.append((start, min(stop, offset), previous))
            if stop > end:
                following.append((max(start, end) + shift, stop + shift, previous))
        if inserted:
            following.append((offset, offset + inserted, step))
        spans = [(a, b, s) for a, b, s in following if b > a]
        length += shift
    if row.get("edits") and length != row.get("bytes_after", length):
        raise ValueError("journal edits disagree with final file size")
    return [{"start": a, "end": b, "step": step, "start_percent": percentage(a, length) or 0,
             "width_percent": percentage(b - a, length) or 0} for a, b, step in sorted(spans)]


def file_view(row, number):
    artifact = row.get("role") == "artifact"
    spans = [] if artifact else placement_spans(row)
    edits, length = [], row.get("bytes_before", 0)
    for step, edit in enumerate(row.get("edits", [])):
        edits.append({"step": step, "offset": edit["offset_before_step"], "inserted_bytes": edit["inserted_bytes"],
                      "removed_bytes": edit["removed_bytes"], "sha256": edit["inserted_sha256"],
                      "location_percent": percentage(edit["offset_before_step"], length) or 0})
        length += edit["inserted_bytes"] - edit["removed_bytes"]
    return {"number": number, "path": row["path"], "kind": row.get("language") or row.get("carrier_kind", "artifact"),
            "role": "artifact" if artifact else "placement", "pending": bool(row.get("pending")),
            "before_bytes": row.get("bytes_before", 0), "after_bytes": row.get("bytes_after", 0),
            "before_sha256": row.get("before_sha256"), "after_sha256": row.get("after_sha256"),
            "payload_ids": [row["candidate_id"]] if row.get("candidate_id") else row.get("content_sha256", []),
            "edits": edits, "spans": spans,
            "placements": 0 if artifact else sum(e["inserted_bytes"] > 0 for e in edits),
            "inserted_bytes": sum(s["end"] - s["start"] for s in spans)}


def deployment_view(identity, root, index, state, manifest):
    files = [file_view(row, i) for i, row in enumerate(manifest["files"])]
    placed = [row for row in files if row["role"] == "placement" and row["placements"]]
    coverage = manifest.get("coverage", {})
    eligible = coverage.get("eligible_files")
    if not isinstance(eligible, int) or eligible < len(placed):
        eligible = None
    paths = coverage.get("eligible_paths", [])
    total_bytes = sum(row["after_bytes"] for row in placed)
    inserted = sum(row["inserted_bytes"] for row in placed)
    return {"id": identity, "repository": root, "repository_name": Path(root).name, "index": index,
            "state": state, "mode": "retained" if manifest.get("retention") else ("source" if placed else "snapshot"),
            "benign": bool(manifest.get("benign")), "created_at": manifest.get("created_at"),
            "updated_at": manifest.get("updated_at"), "selection": manifest.get("selection", {}),
            "metrics": {"eligible_files": eligible, "placed_files": len(placed),
                        "selected_files": coverage.get("selected_files"), "coverage_percent": percentage(len(placed), eligible),
                        "placements": sum(row["placements"] for row in files), "inserted_bytes": inserted,
                        "after_bytes": total_bytes, "density_percent": percentage(inserted, total_bytes),
                        "artifacts": sum(row["role"] == "artifact" for row in files),
                        "scope": coverage.get("scope", "denominator not recorded")},
            "eligible_paths": paths, "files": files,
            "examples": {"inspect": shlex.join(["repel", "deploy", "inspect", "--repo", root, "--index", index, "--include-text"]),
                         "status": shlex.join(["repel", "deploy", "status", "--repo", root, "--index", index]),
                         "restore": shlex.join(["repel", "deploy", "remove", "--repo", root, "--index", index, "--apply"])}}


class JournalReader:
    def __init__(self, store):
        self.root = location(store)
        if not self.root.is_dir():
            raise ValueError("journal store is missing; use --store or create a benign --demo")
        self.database = safe_path(self.root, "journal.sqlite3")
        if not self.database.is_file():
            raise ValueError("journal.sqlite3 is missing from the selected store")

    @contextmanager
    def connection(self):
        path = safe_path(self.root, "journal.sqlite3")
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            db.execute("PRAGMA query_only=ON")
            yield db
        finally:
            db.close()

    def _deployment(self, identity):
        with self.connection() as db:
            row = db.execute("SELECT root,index_path,state,manifest,manifest_sha256 FROM deployments WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("deployment not found")
        root, index, state, raw, expected = row
        if digest(raw.encode()) != expected:
            raise ValueError("journal manifest checksum failed")
        manifest = json.loads(raw)
        if manifest.get("repository_root") != root or manifest.get("deployment_id") != identity:
            raise ValueError("journal identity binding failed")
        return root, index, state, manifest

    def summary(self):
        with self.connection() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            total = db.execute("SELECT COUNT(*) FROM deployments").fetchone()[0] if "deployments" in tables else 0
            ids = [r[0] for r in db.execute("SELECT id FROM deployments ORDER BY rowid DESC LIMIT 200")] if total else []
            response_count = db.execute("SELECT COUNT(*) FROM responses").fetchone()[0] if "responses" in tables else 0
        deployments, errors = [], []
        for identity in ids:
            try:
                view = self.deployment(identity)
                deployments.append({k: v for k, v in view.items() if k not in {"files", "eligible_paths", "examples"}})
            except (ValueError, LookupError, KeyError, TypeError):
                errors.append({"id": identity, "error": "Record integrity or schema check failed"})
        marker = safe_path(self.root, "dashboard-demo.json")
        demo = marker.is_file() and json.loads(marker.read_text()).get("kind") == "repel_dashboard_demo"
        return {"store": str(self.root), "demo": demo, "deployments": deployments, "total_deployments": total,
                "response_count": response_count, "errors": errors, "limit": 200}

    def deployment(self, identity):
        root, index, state, manifest = self._deployment(identity)
        return deployment_view(identity, root, index, state, manifest)

    def _response(self, identity):
        with self.connection() as db:
            row = db.execute("SELECT metadata,sha256 FROM responses WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("response not found")
        if digest(row[0].encode()) != row[1]:
            raise ValueError("response metadata checksum failed")
        result = json.loads(row[0])
        if result.get("id") != identity:
            raise ValueError("response identity binding failed")
        return result

    def responses(self):
        with self.connection() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='responses'").fetchone():
                return {"responses": []}
            ids = [r[0] for r in db.execute("SELECT id FROM responses ORDER BY rowid DESC LIMIT 200")]
        result = []
        for identity in ids:
            record = self._response(identity)
            result.append({"id": identity, "request": record["request"], "status": record["status"],
                           "created_at": record.get("created_at"), "before_sha256": record["before_sha256"],
                           "after_sha256": record["after_sha256"], "content_type": next((v for k, v in record["headers_before"] if k.lower() == "content-type"), "unknown")})
        return {"responses": result}

    def object_key(self, identity, file_number, step, version, *, response=False):
        if response:
            record = self._response(identity)
            if version not in {"before", "after"}:
                raise ValueError("invalid response version")
            return record[version + "_sha256"], identity + "-" + version + ".bin"
        _, _, _, manifest = self._deployment(identity)
        if file_number < 0 or file_number >= len(manifest["files"]):
            raise LookupError("file not found")
        row = manifest["files"][file_number]
        if version == "insertion":
            if step < 0 or step >= len(row.get("edits", [])):
                raise LookupError("placement not found")
            return row["edits"][step]["inserted_sha256"], f"snippet-{identity[:8]}-{file_number}-{step}.txt"
        if version not in {"before", "after"}:
            raise ValueError("invalid file version")
        key = row.get(version + "_sha256")
        if key is None:
            raise LookupError("this file did not exist in the selected version")
        suffix = Path(row["path"]).suffix
        if not re.fullmatch(r"\.[a-zA-Z0-9]{1,10}", suffix):
            suffix = ".bin"
        return key, f"example-{identity[:8]}-{file_number}-{version}{suffix}"

    def open_object(self, key):
        if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("invalid object key")
        path = safe_path(self.root, f"objects/{key[:2]}/{key}")
        handle = path.open("rb")
        try:
            actual = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                actual.update(chunk)
            if actual.hexdigest() != key:
                raise ValueError("object checksum failed; content withheld")
            size = handle.tell()
            handle.seek(0)
            return handle, size
        except BaseException:
            handle.close()
            raise

    def preview(self, key, *, limit=65536):
        handle, size = self.open_object(key)
        with handle:
            raw = handle.read(limit)
        truncated = size > limit
        try:
            if b"\0" in raw:
                raise UnicodeError("binary data")
            decoder = codecs.getincrementaldecoder("utf-8")()
            text = decoder.decode(raw, final=not truncated)
            encoding = "utf-8"
        except UnicodeError:
            text, encoding = base64.b64encode(raw).decode(), "base64"
        return {"text": text, "encoding": encoding, "bytes": size, "preview_bytes": len(raw),
                "truncated": truncated, "sha256": key}
