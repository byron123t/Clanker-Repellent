"""Local HTTP response adapter and private response-archive controls."""
import argparse
import json
import sqlite3
from pathlib import Path

from ..payload import catalog
from ..payload.traffic import RetainedResponseMiddleware, TrafficArchive, upstream_application


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repel traffic")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["proxy", "enable", "disable", "list", "restore"]:
        p = sub.add_parser(name)
        p.add_argument("--archive", type=Path, required=True)
        if name == "restore":
            p.add_argument("--request-id", required=True)
            p.add_argument("--output", type=Path, required=True)
        if name == "proxy":
            p.add_argument("--upstream", required=True, help="HTTP(S) base URL of your application")
            p.add_argument("--host", default="127.0.0.1")
            p.add_argument("--port", type=int, default=8081)
            p.add_argument("--catalog", type=Path, required=True)
            p.add_argument("--id", action="append", default=[])
            p.add_argument("--tag", action="append", default=[])
            p.add_argument("--benign", action="store_true")
            p.add_argument("--random", action="store_true")
            p.add_argument("--seed", type=int, default=0)
            p.add_argument("--max-bytes", type=int, default=2_000_000)
            p.add_argument("--apply", action="store_true", help="enable transformations when starting; otherwise pass through")
    args = parser.parse_args(argv)
    try:
        archive = TrafficArchive(args.archive)
        if args.command == "proxy":
            from wsgiref.simple_server import make_server
            selected = catalog.select(args.catalog, identifiers=args.id, tags=args.tag, benign=args.benign)
            if not selected:
                raise ValueError("no catalog payloads match the selection")
            entries = [catalog.read(args.catalog, item["id"]) for item in selected]
            app = RetainedResponseMiddleware(upstream_application(args.upstream), archive=args.archive,
                                            entries=entries, randomize=args.random, seed=args.seed, max_bytes=args.max_bytes)
            with make_server(args.host, args.port, app) as server:
                archive.enable(args.apply)
                print(json.dumps({"listening": f"http://{args.host}:{server.server_port}", "enabled": args.apply}), flush=True)
                server.serve_forever()
            return 0
        if args.command in {"enable", "disable"}:
            archive.enable(args.command == "enable")
            result = {"enabled": archive.enabled()}
        elif args.command == "list":
            result = archive.list()
        else:
            result = archive.restore(args.request_id, args.output)
        print(json.dumps(result, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Error: {exc}")
        return 2
