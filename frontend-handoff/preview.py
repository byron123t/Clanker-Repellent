"""Serve frontend assets and fixed sample responses from this directory."""
import argparse
import base64
import hmac
import json
import secrets
import webbrowser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode
from wsgiref.simple_server import WSGIRequestHandler, make_server

ROOT = Path(__file__).resolve().parent
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/style.css": ("style.css", "text/css"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}


class PreviewApp:
    def __init__(self, token, scenario="populated"):
        self.token = token
        data = json.loads((ROOT / "fixtures/responses.json").read_text())
        self.routes = data["scenarios"][scenario]
        self.responses = data["responses"]
        self.bodies = [json.dumps(item["body"]).encode() if item["encoding"] == "json"
                       else base64.b64decode(item["body"], validate=True) for item in self.responses]
        for routes in data["scenarios"].values():
            if not all(isinstance(index, int) and 0 <= index < len(self.responses) for index in routes.values()):
                raise ValueError("Invalid sample response index")
        if not all((ROOT / "web" / name).is_file() for name, _ in ASSETS.values()):
            raise ValueError("Missing frontend asset")

    def __call__(self, env, start):
        headers = [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                   ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                   ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")]
        def send(raw, status="200 OK", mime="application/json; charset=utf-8", extra=()):
            start(status, headers + [("Content-Type", mime), ("Content-Length", str(len(raw))), *extra])
            return [raw]
        def error(message, status):
            return send(json.dumps({"error": message}).encode(), status)
        if env.get("REQUEST_METHOD") != "GET":
            return error("This preview is read-only.", "405 Method Not Allowed")
        path = env.get("PATH_INFO", "/")
        if path in ASSETS:
            name, mime = ASSETS[path]
            return send((ROOT / "web" / name).read_bytes(), mime=mime + "; charset=utf-8")
        if not hmac.compare_digest(env.get("HTTP_AUTHORIZATION", "").encode(), ("Bearer " + self.token).encode()):
            return error("Open the complete URL printed by preview.py.", "401 Unauthorized")
        query = urlencode(sorted(parse_qsl(env.get("QUERY_STRING", ""), keep_blank_values=True)))
        key = path + ("?" + query if query else "")
        if key not in self.routes:
            return error("No saved sample for this request.", "404 Not Found")
        index = self.routes[key]
        item = self.responses[index]
        extra = [("Content-Disposition", item["content_disposition"])] if "content_disposition" in item else []
        return send(self.bodies[index], item["status"], item["content_type"], extra)


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="Preview the frontend with fixed synthetic sample data.")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--scenario", choices=["populated", "empty", "error"], default="populated")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    token = secrets.token_urlsafe(32)
    app = PreviewApp(token, args.scenario)
    if args.check:
        print("PASS: frontend assets and fixed sample responses.")
        return
    with make_server("127.0.0.1", args.port, app, handler_class=QuietHandler) as server:
        url = f"http://127.0.0.1:{server.server_port}/#token={token}"
        print(json.dumps({"url": url, "scenario": args.scenario, "read_only": True}), flush=True)
        if args.open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
