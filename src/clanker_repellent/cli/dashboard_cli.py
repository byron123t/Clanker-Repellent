"""Serve the read-only central journal dashboard on loopback."""
import argparse
import json
import secrets
import sqlite3
import webbrowser
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

from ..dashboard.app import DashboardApp
from ..dashboard.demo import create_demo
from ..payload.deployment_store import STORE_DIRECTORY


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repel dashboard", description="Explore journal coverage, placements, and stored snippets in a local read-only dashboard.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--store", type=Path, help="central journal directory (default: .repel-deploy-store)")
    source.add_argument("--demo", type=Path, help="create a new benign demonstration directory and serve its real journal")
    parser.add_argument("--port", type=int, default=8765, help="loopback port; 0 chooses an available port")
    parser.add_argument("--open", action="store_true", help="open the authenticated URL in your browser")
    args = parser.parse_args(argv)
    try:
        if not 0 <= args.port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        store = create_demo(args.demo) if args.demo else args.store or Path.cwd() / STORE_DIRECTORY
        token = secrets.token_urlsafe(32)
        app = DashboardApp(store, token)
        with make_server("127.0.0.1", args.port, app, handler_class=QuietHandler) as server:
            url = f"http://127.0.0.1:{server.server_port}/#token={token}"
            print(json.dumps({"url": url, "store": str(store.resolve()), "read_only": True, "demo": bool(args.demo)}), flush=True)
            if args.open:
                webbrowser.open(url)
            server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Error: {exc}")
        return 2
