"""Opt-in HTTP response retention, with exact original entity-body archives.

This is a WSGI integration for an application the operator controls. It is not a
packet interceptor. TCP/TLS framing and already-delivered traffic are outside its
scope; saved packet-capture files can use the deployment snapshot lifecycle.
"""
from __future__ import annotations

import gzip
import io
import json
import random
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .deployment_store import DeploymentStore, atomic_bytes, digest, _edits
from .retained_deploy import _frame, html_carrier, javascript_carrier, wasm_carrier


HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}


class TrafficArchive:
    def __init__(self, root):
        self.store = DeploymentStore(root, create=True)
        with self.store.locked() as db:
            db.execute("CREATE TABLE IF NOT EXISTS responses (id TEXT PRIMARY KEY, metadata TEXT NOT NULL, sha256 TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO settings VALUES ('enabled','false')")

    def enable(self, enabled):
        with self.store.locked() as db:
            db.execute("UPDATE settings SET value=? WHERE key='enabled'", ("true" if enabled else "false",))

    def enabled(self):
        with self.store.locked() as db:
            return db.execute("SELECT value FROM settings WHERE key='enabled'").fetchone()[0] == "true"

    def record(self, before, after, *, status, headers_before, headers_after, request):
        identity = uuid.uuid4().hex
        with self.store.locked() as db:
            metadata = {"id": identity, "status": status, "headers_before": headers_before,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "headers_after": headers_after, "request": request,
                        "before_sha256": self.store.put(before), "after_sha256": self.store.put(after),
                        "edits": _edits(self.store, before, after, [])}
            value = json.dumps(metadata, sort_keys=True)
            db.execute("INSERT INTO responses VALUES (?,?,?)", (identity, value, digest(value.encode())))
        return identity

    def list(self):
        with self.store.locked() as db:
            rows = db.execute("SELECT id,metadata,sha256 FROM responses ORDER BY rowid").fetchall()
        if any(digest(data.encode()) != expected for _, data, expected in rows):
            raise ValueError("response metadata checksum changed")
        # Response headers and strings remain private unless explicitly restored.
        return [{"id": identity, "before_sha256": json.loads(data)["before_sha256"],
                 "after_sha256": json.loads(data)["after_sha256"]} for identity, data, _ in rows]

    def restore(self, identity, output):
        with self.store.locked() as db:
            row = db.execute("SELECT metadata,sha256 FROM responses WHERE id=?", (identity,)).fetchone()
            if row is None or digest(row[0].encode()) != row[1]:
                raise ValueError("response record missing or corrupt")
            metadata = json.loads(row[0])
            body = self.store.get(metadata["before_sha256"])
            self.store.get(metadata["after_sha256"])
            for edit in metadata["edits"]:
                self.store.get(edit["inserted_sha256"])
                self.store.get(edit["removed_sha256"])
        from .deployment_store import location
        output = location(output)
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        atomic_bytes(output / "body.bin", body)
        atomic_bytes(output / "response.json", (json.dumps({"status": metadata["status"],
                     "headers": metadata["headers_before"], "body_sha256": metadata["before_sha256"]}, indent=2) + "\n").encode())
        return {"id": identity, "output": str(output), "body_sha256": metadata["before_sha256"]}


class RetainedResponseMiddleware:
    def __init__(self, app, *, archive, entries, randomize=False, seed=0, max_bytes=2_000_000):
        if max_bytes < 1:
            raise ValueError("HTTP buffering limit must be positive")
        self.app, self.archive, self.entries = app, TrafficArchive(archive), list(entries)
        self.randomize, self.seed, self.max_bytes = randomize, seed, max_bytes

    def __call__(self, environ, start_response):
        info, writes = {}, []
        def capture(status, headers, exc_info=None):
            info.update(status=status, headers=list(headers), exc_info=exc_info)
            return writes.append
        iterable = self.app(environ, capture)
        def chunks():
            try:
                iterator = iter(iterable)
                while True:
                    try:
                        chunk = next(iterator)
                    except StopIteration:
                        yield from writes
                        writes.clear()
                        break
                    yield from writes
                    writes.clear()
                    yield chunk
            finally:
                if hasattr(iterable, "close"):
                    iterable.close()
        stream = iter(chunks())
        try:
            first = next(stream, b"")
            headers = info["headers"]
            values = {k.lower(): v for k, v in headers}
            mime = values.get("content-type", "").split(";")[0].strip().lower()
            kind = {"text/html": "html", "application/javascript": "javascript", "text/javascript": "javascript",
                    "application/wasm": "wasm"}.get(mime)
            encoding = values.get("content-encoding", "identity").lower()
            from email.message import Message
            content_type = Message()
            content_type["Content-Type"] = values.get("content-type", "")
            charset = content_type.get_content_charset()
            try:
                enabled = self.archive.enabled()
            except (ValueError, OSError, sqlite3.Error):
                enabled = False
            cache_control = ",".join(v for k, v in headers if k.lower() == "cache-control").lower()
            eligible = (kind is not None and info["status"].startswith("200 ")
                        and environ.get("REQUEST_METHOD") != "HEAD" and "HTTP_RANGE" not in environ
                        and "content-range" not in values and "no-transform" not in cache_control
                        and charset in {None, "utf-8", "utf8", "us-ascii"}
                        and encoding in {"identity", "gzip"} and enabled)
            records = []
            for meta, text in self.entries:
                if (meta["kind"] == "data" or meta["kind"] == "document" and meta["document_type"] == kind
                        or meta["kind"] == "source" and (kind == "javascript" and meta["language"] in {"javascript", "typescript"}
                            or kind == "wasm" and meta["language"] in {"c", "cpp"})):
                    records.append(_frame(text))
            if not eligible or not records:
                start_response(info["status"], headers, info.get("exc_info"))
                yield first
                yield from stream
                return
            body = bytearray(first)
            for chunk in stream:
                body.extend(chunk)
                if len(body) > self.max_bytes:
                    break
            if len(body) > self.max_bytes:
                start_response(info["status"], headers, info.get("exc_info"))
                yield bytes(body)
                yield from stream
                return
            original = bytes(body)
            try:
                decoded = original
                if encoding == "gzip":
                    with gzip.GzipFile(fileobj=io.BytesIO(original)) as compressed:
                        decoded = compressed.read(self.max_bytes + 1)
                    if len(decoded) > self.max_bytes:
                        raise ValueError("decoded response exceeds buffer limit")
                if self.randomize:
                    rng = random.Random(f"{self.seed}:{environ.get('PATH_INFO', '')}")
                    records = [rng.choice(records)]
                if kind == "html":
                    transformed = html_carrier(decoded.decode("utf-8"), records).encode("utf-8")
                elif kind == "javascript":
                    decoded.decode("utf-8")
                    transformed = decoded + javascript_carrier(records)
                else:
                    transformed = wasm_carrier(decoded, records)
                if encoding == "gzip":
                    transformed = gzip.compress(transformed, mtime=0)
                stale = {"content-length", "etag", "last-modified", "content-md5", "digest", "content-digest", "repr-digest", "accept-ranges", "cache-control"}
                changed_headers = [(k, v) for k, v in headers if k.lower() not in stale]
                changed_headers += [("Content-Length", str(len(transformed))), ("Cache-Control", "no-store")]
                self.archive.record(original, transformed, status=info["status"], headers_before=headers,
                                    headers_after=changed_headers,
                                    request={"method": environ.get("REQUEST_METHOD"), "path": environ.get("PATH_INFO")})
            except (OSError, ValueError, EOFError, sqlite3.Error):
                # Never send an unjournaled transformation or reinterpret unsupported bytes.
                start_response(info["status"], headers, info.get("exc_info"))
                yield original
                return
            start_response(info["status"], changed_headers, info.get("exc_info"))
            yield transformed
        finally:
            stream.close()


def upstream_application(upstream):
    """Small fixed-upstream WSGI adapter for local testing (no redirect following)."""
    import http.client
    from urllib.parse import urlsplit, quote_from_bytes
    parsed = urlsplit(upstream)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise ValueError("upstream must be an HTTP(S) base URL without credentials/query/fragment")
    def app(environ, start_response):
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(parsed.hostname, parsed.port, timeout=30)
        route = parsed.path.rstrip("/") + quote_from_bytes(environ.get("PATH_INFO", "/").encode("latin-1"), safe="/")
        if environ.get("QUERY_STRING"):
            route += "?" + environ["QUERY_STRING"]
        headers = {key[5:].replace("_", "-"): value for key, value in environ.items() if key.startswith("HTTP_")}
        hop = HOP_HEADERS | {x.strip().lower() for x in headers.get("CONNECTION", "").split(",")} | {"host"}
        headers = {k: v for k, v in headers.items() if k.lower() not in hop}
        length = int(environ.get("CONTENT_LENGTH") or 0)
        if length < 0 or length > 16_000_000:
            start_response("413 Content Too Large", [("Content-Length", "0")])
            return []
        body = environ["wsgi.input"].read(length) if length else None
        if environ.get("CONTENT_TYPE"):
            headers["Content-Type"] = environ["CONTENT_TYPE"]
        try:
            connection.request(environ["REQUEST_METHOD"], route, body=body, headers=headers)
            response = connection.getresponse()
            response_headers = response.getheaders()
            hop |= {x.strip().lower() for k, value in response_headers if k.lower() == "connection" for x in value.split(",")}
            response_headers = [(k, v) for k, v in response_headers if k.lower() not in hop]
            start_response(f"{response.status} {response.reason}", response_headers)
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            connection.close()
    return app
