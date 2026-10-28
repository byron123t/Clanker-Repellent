"""Private, content-addressed deployment journal and exact byte restoration."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path


STORE_DIRECTORY = ".repel-deploy-store"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def location(value):
    path = Path(value).absolute()
    if path.is_symlink():
        raise ValueError("metadata root/index cannot be a symlink")
    return path.parent.resolve() / path.name


def safe_path(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError("invalid indexed path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or relative == Path("."):
        raise ValueError("indexed path leaves repository")
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"symlink in indexed path: {value}")
    return path


def sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_bytes(path, raw, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".repel-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class DeploymentStore:
    def __init__(self, path, *, create=False):
        requested = location(path)
        if create:
            requested.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not requested.is_dir():
            raise ValueError("deployment store is missing")
        self.root = requested.resolve()
        self.database = safe_path(self.root, "journal.sqlite3")
        self.create = create

    @contextmanager
    def locked(self):
        lock = safe_path(self.root, "store.lock")
        fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise ValueError("deployment store is busy; another operation holds its lock") from exc
        try:
            if not self.create and not self.database.is_file():
                raise ValueError("deployment journal is missing")
            db = sqlite3.connect(str(self.database))
            try:
                os.chmod(self.database, 0o600)
                db.execute("PRAGMA synchronous=FULL")
                db.execute("CREATE TABLE IF NOT EXISTS deployments (id TEXT PRIMARY KEY, root TEXT NOT NULL, index_path TEXT NOT NULL, state TEXT NOT NULL, manifest TEXT NOT NULL, manifest_sha256 TEXT NOT NULL)")
                with db:
                    yield db
            finally:
                db.close()
        finally:
            os.close(fd)

    def put(self, raw):
        key = digest(raw)
        path = safe_path(self.root, f"objects/{key[:2]}/{key}")
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError("content-addressed object is corrupt")
        else:
            atomic_bytes(path, raw)
        return key

    def get(self, key):
        if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("invalid object hash")
        path = safe_path(self.root, f"objects/{key[:2]}/{key}")
        if not path.is_file():
            raise ValueError("missing preimage/object backup")
        raw = path.read_bytes()
        if digest(raw) != key:
            raise ValueError("preimage/object hash changed")
        return raw

    def read(self, db, identity, root, index):
        row = db.execute("SELECT root,index_path,state,manifest,manifest_sha256 FROM deployments WHERE id=?", (identity,)).fetchone()
        if row is None or row[0] != str(root) or row[1] != str(index):
            raise ValueError("deployment journal does not belong to this repository/index")
        if digest(row[3].encode()) != row[4]:
            raise ValueError("deployment journal manifest hash changed")
        manifest = json.loads(row[3])
        paths = [item["path"] for item in manifest["files"]]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate paths in deployment journal")
        return manifest, row[2]

    def write(self, db, identity, manifest, state):
        value = _json(manifest)
        db.execute("UPDATE deployments SET state=?,manifest=?,manifest_sha256=? WHERE id=?",
                   (state, value, digest(value.encode()), identity))
        db.commit()


def is_journal_index(document):
    return isinstance(document, dict) and document.get("schema_version") == 2 and document.get("kind") == "repel_carrier_deployment"


def _pointer(repository, index):
    root = Path(repository).resolve()
    requested = location(index)
    pointer = json.loads(requested.read_text(encoding="utf-8"))
    if not is_journal_index(pointer) or pointer.get("repository_root") != str(root):
        raise ValueError("invalid deployment store pointer for this repository")
    if (not isinstance(pointer.get("store"), str) or not isinstance(pointer.get("deployment_id"), str)
            or len(pointer["deployment_id"]) != 32 or any(c not in "0123456789abcdef" for c in pointer["deployment_id"])):
        raise ValueError("invalid deployment store location/id")
    store = DeploymentStore(pointer["store"])
    return root, requested.resolve(), pointer["deployment_id"], store


def load_manifest(repository, index):
    root, index, identity, store = _pointer(repository, index)
    with store.locked() as db:
        return store.read(db, identity, root, index)[0]


def _edits(store, before, after, placements):
    """Offsets are bytes in the image BEFORE that step, so replay is unambiguous."""
    edits = []
    current = before
    if placements and all("inserted_text" in p for p in placements):
        for placement in placements:
            offset = len(current.decode("utf-8")[:placement["offset"]].encode("utf-8"))
            inserted = placement["inserted_text"].encode("utf-8")
            edits.append({"step": len(edits), "offset_before_step": offset, "removed_bytes": 0,
                          "removed_sha256": store.put(b""), "inserted_bytes": len(inserted),
                          "inserted_sha256": store.put(inserted)})
            current = current[:offset] + inserted + current[offset:]
        if current == after:
            return edits
        raise ValueError("source insertion records do not replay to the final bytes")
    start = 0
    stop = min(len(before), len(after))
    while start < stop and before[start] == after[start]:
        start += 1
    suffix = 0
    while suffix < stop - start and before[len(before) - suffix - 1] == after[len(after) - suffix - 1]:
        suffix += 1
    old = before[start:len(before) - suffix if suffix else len(before)]
    new = after[start:len(after) - suffix if suffix else len(after)]
    return [{"step": 0, "offset_before_step": start, "removed_bytes": len(old),
             "removed_sha256": store.put(old), "inserted_bytes": len(new), "inserted_sha256": store.put(new)}]


def _current(path):
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("indexed target is not a regular file")
    return digest(path.read_bytes())


def _matches_after(root, row):
    path = safe_path(root, row["path"])
    if _current(path) != row["after_sha256"]:
        return False
    return row["after_sha256"] is None or stat.S_IMODE(path.stat().st_mode) == row.get("after_mode", row["mode"])


def _restore(store, db, identity, root, index, manifest, state, *, apply):
    prepared = []
    for row in manifest["files"]:
        path = safe_path(root, row["path"])
        current = _current(path)
        if row.get("pending") and not (state == "prepared" and current == row["before_sha256"]):
            raise ValueError("artifact snapshot is not sealed; run deploy seal after the build")
        permitted = {row["after_sha256"]}
        if state in {"prepared", "removing", "restored"}:
            permitted.add(row["before_sha256"])
        if current not in permitted:
            raise ValueError("indexed files changed after deployment; refusing approximate removal")
        if current is not None:
            modes = {row.get("after_mode", row["mode"])}
            if state in {"prepared", "removing", "restored"}:
                modes.add(row["mode"])
            if stat.S_IMODE(path.stat().st_mode) not in modes:
                raise ValueError("indexed file permissions changed after deployment")
        original = store.get(row["before_sha256"]) if row["before_sha256"] is not None else None
        # Validate the full postimage and edit blobs as well before any writes.
        if row["after_sha256"] is not None:
            store.get(row["after_sha256"])
        for edit in row.get("edits", []):
            store.get(edit["inserted_sha256"])
            store.get(edit["removed_sha256"])
        prepared.append((row, path, current, original))
    if not apply:
        return {"status": "removable", "files_restored": len(prepared), "index": str(index)}
    store.write(db, identity, manifest, "removing")
    for row, path, observed, original in prepared:
        path = safe_path(root, row["path"])
        if _current(path) != observed:
            raise ValueError("target changed during removal; journal retained for recovery")
        if original is None:
            path.unlink(missing_ok=True)
            if path.parent.exists():
                sync_directory(path.parent)
        else:
            atomic_bytes(path, original, row["mode"])
    store.write(db, identity, manifest, "restored")
    index.unlink(missing_ok=True)
    sync_directory(index.parent)
    return {"status": "removed", "files_restored": len(prepared), "index": str(index), "deployment_id": identity}


def apply_plan(root, index, manifest, updates, *, store_path=None, snapshots=()):
    root, index = Path(root).resolve(), location(index)
    if not root.is_dir():
        raise ValueError("repository is not a directory")
    store = DeploymentStore(store_path or root / STORE_DIRECTORY, create=True)
    with store.locked() as db:
        if index.exists():
            raise ValueError("deployment index already exists; remove it first")
        if not updates and not snapshots:
            raise ValueError("no matching files to deploy")
        if db.execute("SELECT 1 FROM deployments WHERE root=? AND index_path=? AND state IN ('prepared','applied','removing')",
                      (str(root), str(index))).fetchone():
            raise ValueError("unfinished deployment journal exists; restore its index before adding")
        rows = [dict(row) for row in manifest["files"]]
        seen = {row["path"] for row in rows}
        for value in snapshots:
            value = Path(value)
            if value.is_absolute():
                value = value.relative_to(root)
            relative = value.as_posix()
            if relative in seen:
                raise ValueError("snapshot overlaps a selected target or another snapshot")
            path = safe_path(root, relative)
            original = path.read_bytes() if path.is_file() else None
            rows.append({"path": relative, "before_sha256": digest(original) if original is not None else None,
                         "after_sha256": digest(original) if original is not None else None,
                         "mode": stat.S_IMODE(path.stat().st_mode) if original is not None else 0o600,
                         "role": "artifact", "pending": True})
            seen.add(relative)
        for row in rows:
            path = safe_path(root, row["path"])
            if path == index or path == store.root or store.root in path.parents:
                raise ValueError("target overlaps deployment metadata")
            if _current(path) != row["before_sha256"]:
                raise ValueError("file changed during planning")
            before = path.read_bytes() if row["before_sha256"] is not None else b""
            after = updates.get(row["path"], before)
            if row["before_sha256"] is not None:
                store.put(before)
            if row["after_sha256"] is not None and store.put(after) != row["after_sha256"]:
                raise ValueError("postimage hash does not match plan")
            row["edits"] = _edits(store, before, after, row.get("placements", []))
            row["after_mode"] = row["mode"]
            row["bytes_before"], row["bytes_after"] = len(before), len(after)
        identity = uuid.uuid4().hex
        stored = {**manifest, "schema_version": 2, "files": rows, "deployment_id": identity, "store": str(store.root)}
        value = _json(stored)
        db.execute("INSERT INTO deployments VALUES (?,?,?,?,?,?)",
                   (identity, str(root), str(index), "prepared", value, digest(value.encode())))
        db.commit()
        pointer = {"schema_version": 2, "kind": "repel_carrier_deployment", "repository_root": str(root),
                   "deployment_id": identity, "store": str(store.root)}
        try:
            atomic_bytes(index, (_json(pointer) + "\n").encode())
            for row in rows:
                if row["path"] not in updates:
                    continue
                path = safe_path(root, row["path"])
                if _current(path) != row["before_sha256"]:
                    raise ValueError("file changed during deployment")
                atomic_bytes(path, updates[row["path"]], row["mode"])
            store.write(db, identity, stored, "applied")
        except Exception:
            # Snapshots have not been handed to a build yet, so cancel them safely.
            rollback = {**stored, "files": [{**r, "pending": False} for r in rows]}
            _restore(store, db, identity, root, index, rollback, "prepared", apply=True)
            raise
        manifest.update({"schema_version": 2, "deployment_id": identity, "store": str(store.root)})


def restore(repository, index, *, apply=False):
    root, index, identity, store = _pointer(repository, index)
    with store.locked() as db:
        manifest, state = store.read(db, identity, root, index)
        return _restore(store, db, identity, root, index, manifest, state, apply=apply)


def recover(repository, index, *, store_path=None, apply=False):
    if Path(index).exists() or Path(index).is_symlink():
        return restore(repository, index, apply=apply)
    root, index = Path(repository).resolve(), location(index)
    store = DeploymentStore(store_path or root / STORE_DIRECTORY)
    with store.locked() as db:
        rows = db.execute("SELECT id FROM deployments WHERE root=? AND index_path=? AND state IN ('prepared','applied','removing')",
                          (str(root), str(index))).fetchall()
        if len(rows) != 1:
            raise ValueError("no unique unfinished deployment journal for this repository/index")
        manifest, state = store.read(db, rows[0][0], root, index)
        return _restore(store, db, rows[0][0], root, index, manifest, state, apply=apply)


def status(repository, index):
    root, index, identity, store = _pointer(repository, index)
    with store.locked() as db:
        manifest, state = store.read(db, identity, root, index)
        changed = sum(not _matches_after(root, r) for r in manifest["files"])
        pending = sum(bool(r.get("pending")) for r in manifest["files"])
        return {"status": "pending" if pending else ("clean" if not changed else "changed"),
                "journal_state": state, "files": len(manifest["files"]), "changed": changed,
                "pending_artifacts": pending, "index": str(index), "deployment_id": identity}


def seal(repository, index):
    """Accept build results for explicitly snapshotted artifacts, never source edits."""
    root, index, identity, store = _pointer(repository, index)
    with store.locked() as db:
        manifest, state = store.read(db, identity, root, index)
        if state != "applied":
            raise ValueError("only an applied deployment can be sealed")
        count = 0
        for row in manifest["files"]:
            path = safe_path(root, row["path"])
            if not row.get("pending"):
                if not _matches_after(root, row):
                    raise ValueError("source/previously sealed artifact changed; refusing seal")
                continue
            if not path.is_file():
                raise ValueError("build artifact is missing; nothing was sealed")
            raw = path.read_bytes()
            original = store.get(row["before_sha256"]) if row["before_sha256"] else b""
            row.update(after_sha256=store.put(raw), bytes_after=len(raw), pending=False,
                       after_mode=stat.S_IMODE(path.stat().st_mode), edits=_edits(store, original, raw, []))
            count += 1
        if not count:
            raise ValueError("no pending artifact snapshots")
        store.write(db, identity, manifest, "applied")
        return {"status": "sealed", "artifacts": count, "deployment_id": identity}


def inspect(repository, index, *, include_text=False):
    root, index, identity, store = _pointer(repository, index)
    with store.locked() as db:
        manifest, state = store.read(db, identity, root, index)
        for row in manifest["files"]:
            for placement in row.get("placements", []):
                if not include_text:
                    placement.pop("inserted_text", None)
            if include_text:
                import base64
                for edit in row["edits"]:
                    raw = store.get(edit["inserted_sha256"])
                    try:
                        edit["inserted_text"] = raw.decode("utf-8")
                    except UnicodeError:
                        edit["inserted_base64"] = base64.b64encode(raw).decode("ascii")
        return {**manifest, "journal_state": state}
