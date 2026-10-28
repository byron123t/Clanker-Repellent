"""Versioned payload catalog: immutable UTF-8 objects and typed metadata."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .deployment_store import atomic_bytes, digest, safe_path, location


KINDS = ("source", "document", "data")
DOC_TYPES = ("plain", "markdown", "html", "rst")
SLUG = re.compile(r"[a-z0-9][a-z0-9_.-]{0,119}\Z")


def initialize(root):
    root = location(root)
    schema = b'{"schema_version":1,"kind":"repel_payload_catalog","index":"catalog.sqlite3","objects":"objects/sha256","entries":"entries/<kind>/<type>/<id>.json"}\n'
    if root.exists():
        if (safe_path(root, "catalog.sqlite3").exists() or safe_path(root, "entries").exists()
                or safe_path(root, "objects").exists() or safe_path(root, "catalog.json").read_bytes() != schema):
            raise ValueError("catalog already initialized or contains existing data")
    else:
        root.mkdir(parents=True, mode=0o700)
        atomic_bytes(root / "catalog.json", schema)
    db = _connect(root)
    try:
        with db:
            db.execute("CREATE TABLE entries (id TEXT PRIMARY KEY, metadata TEXT NOT NULL, metadata_sha256 TEXT NOT NULL)")
    finally:
        db.close()
    return {"catalog": str(root), "schema_version": 1}


def _connect(root):
    import os
    path = safe_path(Path(root).resolve(), "catalog.sqlite3")
    db = sqlite3.connect(str(path))
    os.chmod(path, 0o600)
    db.execute("PRAGMA synchronous=FULL")
    return db


def _root(root):
    root = location(root)
    schema = json.loads(safe_path(root, "catalog.json").read_text())
    if schema.get("kind") != "repel_payload_catalog" or schema.get("schema_version") != 1:
        raise ValueError("unsupported payload catalog")
    if not safe_path(root, "catalog.sqlite3").is_file():
        raise ValueError("catalog index missing")
    return root.resolve()


def add(root, *, identifier, text, kind, language=None, document_type=None, tags=(), benign=False,
        validation=None, provenance=None):
    from ..generate.source_generation import LANGUAGES, benign_policy_error, select_languages, validate_snippet
    root = _root(root)
    if not isinstance(identifier, str) or not SLUG.fullmatch(identifier):
        raise ValueError("payload id must be a lowercase slug, at most 120 characters")
    if kind not in KINDS:
        raise ValueError("unknown payload kind")
    if kind == "source" and language not in LANGUAGES:
        raise ValueError("source payloads require a supported language")
    if kind == "document" and document_type not in DOC_TYPES:
        raise ValueError("document payloads require a supported document type")
    if kind != "source" and language is not None:
        raise ValueError("language applies only to source payloads")
    if kind != "document" and document_type is not None:
        raise ValueError("document type applies only to document payloads")
    tags = sorted(set(tags))
    if any(not isinstance(t, str) or not SLUG.fullmatch(t) for t in tags):
        raise ValueError("tags must be lowercase slugs")
    raw = text.encode("utf-8")
    if not raw or b"\0" in raw or len(raw) > 2_000_000:
        raise ValueError("payload must be nonempty NUL-free UTF-8, at most 2 MB")
    if benign:
        error = benign_policy_error(text)
        if error:
            raise ValueError(error)
    if kind == "source":
        # The catalog never trusts caller-supplied validation labels.
        report = validate_snippet(select_languages([language])[0], text, run_linters=False)
        if report["status"] != "passed":
            raise ValueError("source payload did not pass its static language validation")
        validation = {"status": "passed"}
    key = digest(raw)
    object_path = f"objects/sha256/{key[:2]}/{key}"
    subtype = language or document_type or "plain"
    entry_path = f"entries/{kind}/{subtype}/{identifier}.json"
    metadata = {"schema_version": 1, "id": identifier, "kind": kind, "language": language,
                "document_type": document_type, "tags": tags, "benign": bool(benign),
                "encoding": "utf-8", "sha256": key, "bytes": len(raw), "object": object_path,
                "entry": entry_path, "validation": validation, "provenance": provenance}
    serialized = json.dumps(metadata, sort_keys=True, indent=2) + "\n"
    db = _connect(root)
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT metadata FROM entries WHERE id=?", (identifier,)).fetchone()
        if existing:
            if existing[0] == serialized:
                read(root, identifier)  # An idempotent import still verifies the stored objects.
                return metadata
            raise ValueError("payload id already exists with different metadata/content")
        path = safe_path(root, object_path)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("catalog object hash changed")
        if not path.exists():
            atomic_bytes(path, raw)
        entry = safe_path(root, entry_path)
        if entry.exists() and entry.read_text() != serialized:
            raise ValueError("orphan catalog entry conflicts with new metadata")
        atomic_bytes(entry, serialized.encode())
        db.execute("INSERT INTO entries VALUES (?,?,?)", (identifier, serialized, digest(serialized.encode())))
        db.commit()
    finally:
        db.close()
    return metadata


def select(root, *, identifiers=(), tags=(), kind=None, language=None, document_type=None, benign=False):
    root = _root(root)
    db = _connect(root)
    try:
        rows = db.execute("SELECT metadata,metadata_sha256 FROM entries ORDER BY id").fetchall()
    finally:
        db.close()
    entries = []
    for serialized, expected in rows:
        if digest(serialized.encode()) != expected:
            raise ValueError("catalog metadata checksum changed")
        item = json.loads(serialized)
        if identifiers and item["id"] not in identifiers:
            continue
        if not set(tags).issubset(item["tags"]):
            continue
        if kind and kind != item["kind"] or language and language != item["language"]:
            continue
        if document_type and document_type != item["document_type"]:
            continue
        if benign and not item["benign"]:
            continue
        if safe_path(root, item["entry"]).read_text() != serialized:
            raise ValueError("catalog entry metadata changed")
        entries.append(item)
    if identifiers and set(identifiers) != {item["id"] for item in entries}:
        raise ValueError("requested payload id is missing or excluded by type/tag/benign filters")
    return entries


def read(root, identifier):
    root = _root(root)
    item = select(root, identifiers=[identifier])[0]
    raw = safe_path(root, item["object"]).read_bytes()
    if digest(raw) != item["sha256"] or len(raw) != item["bytes"]:
        raise ValueError("catalog payload hash/length changed")
    return item, raw.decode("utf-8")


def import_run(root, run_dir, *, prefix, tags=(), benign=False):
    from .carrier_deploy import load_accepted_carriers
    manifest = json.loads((Path(run_dir) / "manifest.json").read_text())
    is_benign = manifest.get("settings", {}).get("mode") == "benign"
    if benign and not is_benign:
        raise ValueError("--benign requires a benign generation run")
    return [add(root, identifier=f"{prefix}-{carrier.language}", text=carrier.source,
                kind="source", language=carrier.language, tags=tags, benign=is_benign,
                provenance={"kind": "generation", "candidate_id": carrier.candidate_id,
                            "sha256": carrier.source_sha256})
            for carrier in load_accepted_carriers(Path(run_dir))]
