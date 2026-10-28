"""Authenticated, read-only local HTTP dashboard with packaged static assets."""
from __future__ import annotations

import hmac
import json
import re
import sqlite3
from pathlib import Path
from importlib.resources import files
from urllib.parse import parse_qs

from .reader import JournalReader


_CHECKOUT_ASSETS = Path(__file__).resolve().parents[3] / "dashboard" / "repel_dashboard_ui"
ASSETS = _CHECKOUT_ASSETS if (_CHECKOUT_ASSETS / "index.html").is_file() else files("repel_dashboard_ui")
ROUTE = re.compile(r"/api/(deployments|responses)/([0-9a-f]{32})(?:/(preview|download))?\Z")


class DashboardApp:
    def __init__(self, store, token, *, assets=None):
        self.reader, self.token = JournalReader(store), token
        self.assets = Path(assets).resolve() if assets is not None else ASSETS
        if not all((self.assets / name).is_file() for name in ("index.html", "app.js", "style.css", "favicon.svg")):
            raise ValueError("dashboard assets must contain index.html, app.js, style.css, and favicon.svg")

    def __call__(self, environ, start_response):
        headers = [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                   ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                   ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")]
        def respond(status, raw, mime="application/json; charset=utf-8", extra=()):
            start_response(status, headers + [("Content-Type", mime), ("Content-Length", str(len(raw))), *extra])
            return [raw]
        def document(value, status="200 OK"):
            return respond(status, json.dumps(value, ensure_ascii=True).encode())
        if environ.get("REQUEST_METHOD") != "GET":
            return document({"error": "This dashboard is read-only."}, "405 Method Not Allowed")
        path = environ.get("PATH_INFO", "/")
        assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                  "/style.css": ("style.css", "text/css"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
        if path in assets:
            name, mime = assets[path]
            return respond("200 OK", (self.assets / name).read_bytes(), mime + "; charset=utf-8")
        provided = environ.get("HTTP_AUTHORIZATION", "")
        if not hmac.compare_digest(provided.encode("utf-8"), ("Bearer " + self.token).encode("utf-8")):
            return document({"error": "Open the dashboard URL printed by repel to connect."}, "401 Unauthorized")
        try:
            if path == "/api/summary":
                return document(self.reader.summary())
            if path == "/api/responses":
                return document(self.reader.responses())
            match = ROUTE.fullmatch(path)
            if not match:
                return document({"error": "Not found"}, "404 Not Found")
            kind, identity, action = match.groups()
            if action is None and kind == "deployments":
                return document(self.reader.deployment(identity))
            if action not in {"preview", "download"}:
                raise LookupError("Not found")
            query = parse_qs(environ.get("QUERY_STRING", ""))
            number = int(query.get("file", ["0"])[0])
            step = int(query.get("step", ["0"])[0])
            version = query.get("version", ["insertion" if kind == "deployments" else "before"])[0]
            key, filename = self.reader.object_key(identity, number, step, version, response=kind == "responses")
            if action == "preview":
                return document({**self.reader.preview(key), "filename": filename})
            handle, size = self.reader.open_object(key)
            try:
                start_response("200 OK", headers + [("Content-Type", "application/octet-stream"),
                    ("Content-Length", str(size)), ("Content-Disposition", f'attachment; filename="{filename}"')])
                return environ.get("wsgi.file_wrapper", FileIterator)(handle)
            except BaseException:
                handle.close()
                raise
        except LookupError:
            return document({"error": "The requested record or version does not exist."}, "404 Not Found")
        except sqlite3.OperationalError:
            return document({"error": "The journal is busy or unavailable. Retry shortly."}, "503 Service Unavailable")
        except (OSError, ValueError, sqlite3.Error, KeyError, TypeError):
            return document({"error": "The journal or object failed validation. No content was returned."}, "422 Unprocessable Content")


class FileIterator:
    def __init__(self, handle):
        self.handle = handle

    def __iter__(self):
        return self

    def __next__(self):
        chunk = self.handle.read(65536)
        if not chunk:
            raise StopIteration
        return chunk

    def close(self):
        self.handle.close()
