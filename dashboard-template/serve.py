"""Read-only viewer API for local synthetic file-change records and sample bytes."""
import argparse
import base64
import codecs
import hashlib
import hmac
import json
import re
import secrets
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIRequestHandler, make_server

ROOT = Path(__file__).resolve().parent
ROUTE = re.compile(r"/api/(deployments|responses)/([0-9a-f]{32})(?:/(preview|download))?\Z")
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}

class FixtureApp:
    def __init__(self, token, scenario="populated"):
        self.token, self.scenario = token, scenario
        self.journal = json.loads((ROOT / "fixtures/journal.json").read_text())
        self.objects = json.loads((ROOT / "fixtures/objects.json").read_text())
        for key in self.objects: self.object(key)
        if not all((ROOT / "web" / value[0]).is_file() for value in ASSETS.values()):
            raise ValueError("web/ must contain index.html, app.js, style.css, and favicon.svg")

    def object(self, key):
        raw = base64.b64decode(self.objects[key], validate=True)
        if hashlib.sha256(raw).hexdigest() != key: raise ValueError("Fixture object checksum mismatch")
        return raw

    def __call__(self, env, start):
        headers = [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"),
                   ("X-Frame-Options", "DENY"), ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")]
        def send(raw, status="200 OK", mime="application/json; charset=utf-8", extra=()):
            start(status, headers + [("Content-Type", mime), ("Content-Length", str(len(raw))), *extra]); return [raw]
        def document(value, status="200 OK"): return send(json.dumps(value, ensure_ascii=True).encode(), status)
        if env.get("REQUEST_METHOD") != "GET": return document({"error": "Read-only fixture API."}, "405 Method Not Allowed")
        path = env.get("PATH_INFO", "/")
        if path in ASSETS:
            name, mime = ASSETS[path]; return send((ROOT / "web" / name).read_bytes(), mime=mime + "; charset=utf-8")
        auth = env.get("HTTP_AUTHORIZATION", "").encode()
        if not hmac.compare_digest(auth, ("Bearer " + self.token).encode()): return document({"error": "Use the authenticated URL printed by serve.py."}, "401 Unauthorized")
        try:
            if path == "/api/summary":
                if self.scenario == "error": return document({"error": "Simulated journal unavailability. Restart without --scenario error."}, "503 Service Unavailable")
                summary = dict(self.journal["summary"])
                if self.scenario == "empty": summary.update(deployments=[], total_deployments=0, response_count=0)
                return document(summary)
            if path == "/api/responses": return document({"responses": [] if self.scenario == "empty" else self.journal["responses"]})
            match = ROUTE.fullmatch(path)
            if not match or self.scenario == "empty": raise LookupError()
            kind, identity, action = match.groups()
            record = self.journal["deployments"][identity] if kind == "deployments" else next(r for r in self.journal["responses"] if r["id"] == identity)
            if action is None:
                if kind == "responses": raise LookupError()
                return document(record)
            query = parse_qs(env.get("QUERY_STRING", ""))
            version = query.get("version", ["insertion" if kind == "deployments" else "before"])[0]
            if kind == "responses":
                if version not in {"before", "after"}: raise ValueError()
                key, filename = record[version + "_sha256"], identity + "-" + version + ".bin"
            else:
                number, step = int(query.get("file", ["0"])[0]), int(query.get("step", ["0"])[0])
                if number < 0 or step < 0: raise LookupError()
                row = record["files"][number]
                if version == "insertion": key, filename = row["edits"][step]["sha256"], f"snippet-{identity[:8]}-{number}-{step}.txt"
                elif version in {"before", "after"}:
                    suffix = Path(row["path"]).suffix
                    if not re.fullmatch(r"\.[a-zA-Z0-9]{1,10}", suffix): suffix = ".bin"
                    key, filename = row[version + "_sha256"], f"example-{identity[:8]}-{number}-{version}{suffix}"
                else: raise ValueError()
            raw = self.object(key)
            if action == "download": return send(raw, mime="application/octet-stream", extra=[("Content-Disposition", f'attachment; filename="{filename}"')])
            preview = raw[:65536]; truncated = len(raw) > len(preview)
            try:
                if b"\0" in preview: raise UnicodeError()
                text = codecs.getincrementaldecoder("utf-8")().decode(preview, final=not truncated); encoding = "utf-8"
            except UnicodeError: text, encoding = base64.b64encode(preview).decode(), "base64"
            return document({"text": text, "encoding": encoding, "bytes": len(raw), "preview_bytes": len(preview), "truncated": truncated, "sha256": key, "filename": filename})
        except (LookupError, StopIteration): return document({"error": "Fixture record or version not found."}, "404 Not Found")
        except (ValueError, TypeError): return document({"error": "Invalid fixture query or object checksum."}, "422 Unprocessable Content")

class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args): pass

def main():
    parser = argparse.ArgumentParser(description="Serve a read-only visualization of synthetic file-change records from this folder.")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--scenario", choices=["populated", "empty", "error"], default="populated")
    parser.add_argument("--check", action="store_true", help="validate local assets and fixture hashes without serving")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535: parser.error("port must be between 0 and 65535")
    token = secrets.token_urlsafe(32); app = FixtureApp(token, args.scenario)
    if args.check: print("PASS: standalone assets and fixture hashes."); return
    with make_server("127.0.0.1", args.port, app, handler_class=QuietHandler) as server:
        url = f"http://127.0.0.1:{server.server_port}/#token={token}"
        print(json.dumps({"url": url, "mode": "synthetic sample viewer", "read_only": True, "scenario": args.scenario}), flush=True)
        if args.open: webbrowser.open(url)
        try: server.serve_forever()
        except KeyboardInterrupt: pass

if __name__ == "__main__": main()
