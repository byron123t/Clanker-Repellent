"""Manage snippet catalogs without printing snippet content."""
import argparse
import json
import sqlite3
from pathlib import Path
from ..payload import catalog


DEFAULT_CATALOG = Path(__file__).resolve().parents[3] / "payloads" / "catalog-v1"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repel catalog", description="Organize snippets by language, document type, and tags.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["init", "add", "list", "import-run"]:
        p = sub.add_parser(name)
        p.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
        if name in {"add", "list", "import-run"}:
            p.add_argument("--tag", action="append", default=[])
            p.add_argument("--benign", action="store_true")
        if name in {"add", "list"}:
            p.add_argument("--kind", choices=catalog.KINDS, required=name == "add")
            p.add_argument("--language")
            p.add_argument("--document-type", choices=catalog.DOC_TYPES)
        if name == "add":
            p.add_argument("--id", required=True)
            p.add_argument("--file", type=Path, required=True)
        if name == "import-run":
            p.add_argument("--run-dir", type=Path, required=True)
            p.add_argument("--prefix", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = catalog.initialize(args.catalog)
        elif args.command == "add":
            result = catalog.add(args.catalog, identifier=args.id, text=args.file.read_bytes().decode("utf-8"),
                                 kind=args.kind, language=args.language, document_type=args.document_type,
                                 tags=args.tag, benign=args.benign)
        elif args.command == "import-run":
            result = catalog.import_run(args.catalog, args.run_dir, prefix=args.prefix, tags=args.tag, benign=args.benign)
        else:
            result = catalog.select(args.catalog, tags=args.tag, kind=args.kind, language=args.language,
                                    document_type=args.document_type, benign=args.benign)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"Error: {exc}")
        return 2
