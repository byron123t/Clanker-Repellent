"""Generate synthetic file-change records and example bytes for the read-only viewer."""
import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
objects = {}

def put(raw):
    key = hashlib.sha256(raw).hexdigest()
    objects[key] = base64.b64encode(raw).decode()
    return key

def percent(part, whole):
    return round(100 * part / whole, 1) if whole else None

def sample_section():
    label = b"repel.notes.v1"
    body = bytes([len(label)]) + label + b"Project note: examples use consistent names."
    return b"\0" + bytes([len(body)]) + body

def project(name, kind, suffix, eligible, selected, phase="applied", known=True):
    identity = hashlib.sha256(name.encode()).hexdigest()[:32]
    paths = [f"src/module_{i:03d}{suffix}" for i in range(eligible)]
    chosen = sorted(range(0, eligible, max(1, eligible // selected)))[:selected] if selected else []
    files = []
    for index in chosen:
        if kind == "wasm_custom_section":
            before = b"\0asm\x01\0\0\0"
            note = sample_section()
        else:
            declaration = f"static const int sample_value = {index};" if suffix == ".c" else f"const value = {index};"
            before = ((f"/* Example {index}: formatting conventions. */\n" * (index % 5 + 1) + declaration + "\n") if suffix != ".md" else f"# Documentation sample {index}\n\nExamples use short, descriptive names.\n").encode()
            text = f"Project note {index}: examples use consistent names."
            note = (f"\n> {text}\n" if suffix == ".md" else f"\n/* {text} */\n").encode()
        offset = (0, before.find(b"\n") + 1, len(before))[index % 3]
        if kind == "wasm_custom_section": offset = len(before)
        after = before[:offset] + note + before[offset:]
        files.append({"number": len(files), "path": paths[index], "kind": kind, "role": "placement", "pending": False,
                      "before_bytes": len(before), "after_bytes": len(after), "before_sha256": put(before), "after_sha256": put(after),
                      "payload_ids": [f"{name}-note-{index:03d}"], "edits": [{"step": 0, "offset": offset, "inserted_bytes": len(note), "removed_bytes": 0,
                      "sha256": put(note), "location_percent": percent(offset, len(before)) or 0}],
                      "spans": [{"start": offset, "end": offset + len(note), "step": 0, "start_percent": percent(offset, len(after)), "width_percent": percent(len(note), len(after))}],
                      "placements": 1, "inserted_bytes": len(note)})
    if name in {"native-util", "build-staging"}:
        pending = name == "build-staging"
        before = bytes(range(128)); after = before + b"Sample document version.\n"
        files.append({"number": len(files), "path": "build/example.bin", "kind": "artifact", "role": "artifact", "pending": pending,
                      "before_bytes": len(before), "after_bytes": len(before if pending else after), "before_sha256": put(before), "after_sha256": put(before if pending else after),
                      "payload_ids": [], "edits": [], "spans": [], "placements": 0, "inserted_bytes": 0})
    total = sum(f["after_bytes"] for f in files if f["role"] == "placement")
    inserted = sum(f["inserted_bytes"] for f in files)
    root = "/sample-workspace/" + name
    return {"id": identity, "repository": root, "repository_name": name, "index": root + "/.repel-carrier-index.json",
            "state": phase, "mode": "retained" if selected else "snapshot", "benign": True, "created_at": "2026-10-28T14:30:00+00:00", "updated_at": "2026-10-28T14:35:00+00:00",
            "selection": {"random": True, "seed": 42, "count": selected}, "types": [kind] if selected else [],
            "metrics": {"eligible_files": eligible if known else None, "placed_files": selected, "selected_files": selected,
                        "coverage_percent": percent(selected, eligible) if known else None, "placements": selected,
                        "inserted_bytes": inserted, "after_bytes": total, "density_percent": percent(inserted, total), "artifacts": len(files) - selected,
                        "scope": "sample file inventory" if known else "denominator not recorded"},
            "eligible_paths": paths if known else [], "files": files,
            "examples": {}}

def main():
    objects.clear()
    records = [project("native-util", "native_retained_string", ".c", 42, 8),
               project("web-client", "javascript_global_data", ".js", 62, 12),
               project("wasm-runtime", "wasm_custom_section", ".wasm", 6, 3),
               project("markdown-core", "typescript", ".ts", 13, 5),
               project("docs-site", "document_data", ".md", 280, 12, "restored"),
               project("legacy-import", "javascript_global_data", ".js", 5, 2, known=False),
               project("build-staging", "artifact", ".bin", 0, 0, "prepared", known=False)]
    responses = []
    for path, mime, before, note in [
        ("/example.html", "text/html", b"<!doctype html><title>Sample page</title>", b"\n<!-- Project note: examples use consistent names. -->"),
        ("/example.js", "text/javascript", b"const example = 42;\n", b"// Project note: examples use consistent names.\n"),
        ("/example.wasm", "application/wasm", b"\0asm\x01\0\0\0", sample_section()),
    ]:
        responses.append({"id": hashlib.sha256(path.encode()).hexdigest()[:32], "request": {"method": "GET", "path": path},
                          "status": "200 OK", "created_at": "2026-10-28T14:34:00+00:00", "content_type": mime,
                          "before_sha256": put(before), "after_sha256": put(before + note)})
    summaries = [{k: v for k, v in record.items() if k not in {"files", "eligible_paths", "examples"}} for record in records]
    journal = {"schema_version": 1, "summary": {"store": "Local sample files / synthetic file-change records", "demo": False, "template": True, "deployments": summaries,
                "total_deployments": len(records), "response_count": len(responses), "errors": [], "limit": 200},
               "deployments": {record["id"]: record for record in records}, "responses": responses}
    folder = ROOT / "fixtures"; folder.mkdir(exist_ok=True)
    (folder / "journal.json").write_text(json.dumps(journal, indent=2) + "\n")
    (folder / "objects.json").write_text(json.dumps(objects, indent=2) + "\n")
    print(f"Built {len(records)} synthetic records and {len(objects)} sample content objects.")

if __name__ == "__main__": main()
