"""Deterministic, recoverable data carriers for native and web distributions.

Text (including source snippets) is always data here, never evaluated. Native
retention is performed before linking; WASM custom sections are added after the
last optimizer. Verification measures recoverability, not decompiler rendering.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import random
import stat
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .carrier_deploy import (
    EXCLUDED_DIRECTORIES, INDEX_FILENAME, DeploymentError, _indexed_target,
    _read_json, _sha256_bytes, apply_deployment_plan, load_accepted_carriers,
)
from ..generate.source_generation import MAX_PAYLOAD_BYTES, benign_policy_error


NATIVE_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx"}
WEB_EXTENSIONS = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts"}
HTML_EXTENSIONS = {".html", ".htm"}
DOCUMENT_EXTENSIONS = {".md", ".markdown", ".rst", ".txt"}
SUPPORTED_EXTENSIONS = NATIVE_EXTENSIONS | WEB_EXTENSIONS | HTML_EXTENSIONS | DOCUMENT_EXTENSIONS | {".wasm"}
WASM_HEADER = b"\0asm\x01\0\0\0"
WASM_SECTION = b"repel.notes.v1"
FRAME_HEADER = re.compile(rb"REPEL_EMBED_V1 ([0-9]{1,10}) ([0-9a-f]{64})\n")
FRAME_END = b"\nREPEL_EMBED_END\n"
LITERAL = re.compile(r'''"(?:[^"\\\r\n]|\\[\s\S])*"|'(?:[^'\\\r\n]|\\[\s\S])*'|`(?:[^`\\]|\\[\s\S])*`''')
RECORD_LITERAL_START = re.compile(r'''["'`](?=R|\\[xu])''')


def _frame(text: str) -> bytes:
    raw = text.encode("utf-8")
    return (f"REPEL_EMBED_V1 {len(raw)} {_sha256_bytes(raw)}\n".encode("ascii")
            + raw + FRAME_END)


def _records(payloads: Sequence[Path], run_dir: Optional[Path], benign: bool,
             allow_partial: bool) -> List[bytes]:
    if bool(payloads) == bool(run_dir):
        raise DeploymentError("retained deployment requires either --payload or --run-dir")
    texts = []
    if run_dir is not None:
        if benign and _read_json(run_dir / "manifest.json").get("settings", {}).get("mode") != "benign":
            raise DeploymentError("--benign requires a benign generation run")
        texts = [c.source for c in load_accepted_carriers(run_dir, allow_partial=allow_partial)]
    for path in payloads:
        raw = path.read_bytes()
        if not raw or len(raw) > MAX_PAYLOAD_BYTES or b"\0" in raw:
            raise DeploymentError("payload must be nonempty, NUL-free UTF-8, at most 1 MB")
        texts.append(raw.decode("utf-8"))
    if benign:
        for text in texts:
            error = benign_policy_error(text)
            if error:
                raise DeploymentError(error)
    return list(dict.fromkeys(_frame(text) for text in texts))


def _c_literal(raw: bytes) -> str:
    # Three-digit octal escapes cannot absorb the next byte, unlike C hex escapes.
    values = []
    for byte in raw:
        if 32 <= byte < 127 and byte not in (34, 63, 92):
            values.append(chr(byte))
        else:
            values.append(f"\\{byte:03o}")
    # Bound physical line lengths without splitting an escape sequence.
    return "\n".join('"' + "".join(values[i:i + 64]) + '"' for i in range(0, len(values), 64))


def native_carrier(records: Sequence[bytes], identity: str) -> bytes:
    """Retain a referenced UTF-8 string and accessor through supported linkers."""

    symbol = "repel_note_" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    keep, api = symbol.upper() + "_KEEP", symbol.upper() + "_API"
    blob = b"\0".join(records)
    source = f'''
/* Repel retained data; retrieve with {symbol}_read(). */
#if defined(_MSC_VER)
#define {keep}
#define {api} __declspec(dllexport)
#elif defined(__clang__) || defined(__GNUC__)
#if defined(__ELF__)
#if defined(__has_attribute)
#if __has_attribute(retain)
#define {keep} __attribute__((used, retain))
#endif
#endif
#ifndef {keep}
#error Repel retained data requires ELF retain support (Clang 13+ or GCC 11+).
#endif
#else
#define {keep} __attribute__((used))
#endif
#define {api} {keep}
#else
#error Repel retained data requires Clang, GCC, or MSVC.
#endif
{keep} static const char {symbol}[] =
{_c_literal(blob)};
#ifdef __cplusplus
extern "C" {{
#endif
{api} const char *{symbol}_read(void);
{api} const char *{symbol}_read(void) {{ return {symbol}; }}
#ifdef __cplusplus
}}
#endif
#undef {keep}
#undef {api}
'''
    return source.encode("ascii")


def javascript_carrier(records: Sequence[bytes]) -> bytes:
    statements = ["\n;/* Repel retained data. */\n"]
    for record in records:
        digest = FRAME_HEADER.match(record).group(2).decode("ascii")
        # Escaping '<' also makes this safe if a bundler inlines it into HTML.
        literal = json.dumps(record.decode("utf-8"), ensure_ascii=True).replace("<", "\\u003c")
        statements.append(
            'Object.defineProperty(globalThis, "repel:' + digest + '", '
            + '{value: ' + literal + ', configurable: true});\n'
        )
    return "".join(statements).encode("ascii")


class _HTMLBodyEnd(HTMLParser):
    """Find an actual closing tag, ignoring tag-like text in scripts/comments."""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.offsets = [0]
        self.offsets.extend(match.end() for match in re.finditer("\n", source))
        self.position = len(source)
        self.feed(source)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"body", "html"}:
            line, column = self.getpos()
            self.position = min(self.position, self.offsets[line - 1] + column)


def html_carrier(source: str, records: Sequence[bytes]) -> str:
    # A data block requires no inline executable script or CSP relaxation.
    data = json.dumps([r.decode("utf-8") for r in records], ensure_ascii=True)
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    newline = "\r\n" if "\r\n" in source else "\n"
    block = newline + '<script type="application/json" data-repel-notes="v1">' + data + '</script>' + newline
    offset = _HTMLBodyEnd(source).position
    return source[:offset] + block + source[offset:]


def _uleb(value: int) -> bytes:
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _read_uleb(raw: bytes, offset: int) -> Tuple[int, int]:
    value = 0
    for shift in range(0, 35, 7):
        if offset >= len(raw):
            break
        byte = raw[offset]
        offset += 1
        if shift == 28 and byte & 0xf0:
            break
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise DeploymentError("invalid WASM section length")


def wasm_carrier(raw: bytes, records: Sequence[bytes]) -> bytes:
    if not raw.startswith(WASM_HEADER):
        raise DeploymentError("expected an uncompressed WebAssembly version 1 module")
    offset = len(WASM_HEADER)
    while offset < len(raw):
        section_id = raw[offset]
        size, start = _read_uleb(raw, offset + 1)
        end = start + size
        if end > len(raw):
            raise DeploymentError("truncated WASM section")
        if section_id == 0:
            length, name_start = _read_uleb(raw, start)
            if name_start + length > end:
                raise DeploymentError("truncated WASM custom section name")
            if raw[name_start:name_start + length] == WASM_SECTION:
                raise DeploymentError("WASM already contains repel.notes.v1; remove its deployment first")
        offset = end
    body = _uleb(len(WASM_SECTION)) + WASM_SECTION + b"\0".join(records)
    return raw + b"\0" + _uleb(len(body)) + body


def _files(root: Path, target_files: Sequence[Path]) -> List[Path]:
    def supported(path: Path) -> bool:
        return (path.suffix.lower() in SUPPORTED_EXTENSIONS
                and not path.name.lower().endswith((".d.ts", ".d.mts", ".d.cts")))

    if target_files:
        paths = []
        for value in target_files:
            if value.is_absolute():
                try:
                    value = value.relative_to(root)
                except ValueError as exc:
                    raise DeploymentError("target file must be inside repository") from exc
            path = _indexed_target(root, value.as_posix())
            if (not path.is_file() or not supported(path)
                    or any(p in {"payloads", "results", ".git"} for p in value.parts)):
                raise DeploymentError(f"unsupported retained target: {value}; native executables must be rebuilt from C/C++")
            paths.append(path)
        return sorted(set(paths))
    paths = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRECTORIES
                         and not d.endswith(".preimage") and not (base / d).is_symlink())
        for name in sorted(names):
            path = base / name
            if supported(path) and path.is_file() and not path.is_symlink():
                paths.append(path)
    return sorted(paths)


def deploy_retained(*, repository: Path, payloads: Sequence[Path] = (), run_dir: Optional[Path] = None,
                    target_files: Sequence[Path] = (), benign: bool = False, allow_partial: bool = False,
                    apply: bool = False, index_path: Optional[Path] = None,
                    catalog_entries=(), randomize=False, seed=0, count=None, payload_count=None,
                    store_path=None, snapshots=()) -> Dict[str, Any]:
    root = repository.resolve()
    if not root.is_dir():
        raise DeploymentError("repository is not a directory")
    records = [_frame(text) for metadata, text in catalog_entries] if catalog_entries else _records(payloads, run_dir, benign, allow_partial)
    rng = random.Random(seed)
    def compatible(path):
        if not catalog_entries:
            return records
        from .carrier_deploy import detect_language
        result = []
        doc_types = {".md": "markdown", ".markdown": "markdown", ".rst": "rst", ".txt": "plain", ".html": "html", ".htm": "html"}
        for metadata, text in catalog_entries:
            if (metadata["kind"] == "data"
                or metadata["kind"] == "source" and metadata["language"] == detect_language(path)
                or metadata["kind"] == "document" and metadata["document_type"] == doc_types.get(path.suffix.lower())):
                result.append(_frame(text))
        return result
    files = _files(root, target_files)
    incompatible = [p for p in files if not compatible(p)]
    if target_files and incompatible:
        raise DeploymentError("explicit target has no type-compatible catalog payload")
    files = [p for p in files if compatible(p)]
    if count is not None:
        if count < 1 or count > len(files):
            raise DeploymentError("--count exceeds compatible files or is not positive")
        files = sorted(rng.sample(files, count)) if randomize else files[:count]
    if payload_count is not None and payload_count < 1:
        raise DeploymentError("--payload-count must be positive")
    if not files:
        raise DeploymentError("no supported native/web/WASM files found")
    input_paths = {p.resolve() for p in payloads}
    generation_root = run_dir.resolve() if run_dir else None
    updates, rows = {}, []
    for path in files:
        if path.resolve() in input_paths or (generation_root and generation_root in path.parents):
            raise DeploymentError("input payloads and generation runs must be outside the selected target files")
        file_records = compatible(path)
        selected_count = payload_count or (1 if randomize else len(file_records))
        if selected_count > len(file_records):
            raise DeploymentError("--payload-count exceeds a target's compatible payload pool")
        file_records = rng.sample(file_records, selected_count) if randomize else file_records[:selected_count]
        raw = path.read_bytes()
        suffix = path.suffix.lower()
        relative = path.relative_to(root).as_posix()
        if suffix == ".wasm":
            updated, kind = wasm_carrier(raw, file_records), "wasm_custom_section"
        else:
            if b"\0" in raw:
                raise DeploymentError(f"NUL in text target: {relative}")
            source = raw.decode("utf-8")
            if b"REPEL_EMBED_V1" in raw:
                raise DeploymentError(f"target already contains retained records: {relative}")
            if suffix in NATIVE_EXTENSIONS:
                updated = raw + native_carrier(file_records, relative + _sha256_bytes(b"".join(file_records)))
                if b"\r\n" in raw:
                    updated = raw + updated[len(raw):].replace(b"\n", b"\r\n")
                kind = "native_retained_string"
            elif suffix in HTML_EXTENSIONS:
                updated, kind = html_carrier(source, file_records).encode("utf-8"), "html_data_block"
            elif suffix in DOCUMENT_EXTENSIONS:
                newline = "\r\n" if "\r\n" in source else "\n"
                if suffix in {".md", ".markdown"}:
                    body = json.dumps([r.decode("utf-8") for r in file_records], ensure_ascii=True, indent=2)
                    longest = max((len(m.group()) for m in re.finditer(r"`+", body)), default=0)
                    fence = "`" * max(3, longest + 1)
                    block = "\n\n" + fence + "json\n" + body + "\n" + fence + "\n"
                elif suffix == ".rst":
                    block = "\n\n.. code-block:: json\n\n   " + json.dumps([r.decode("utf-8") for r in file_records]) + "\n"
                else:
                    block = "\n" + json.dumps([r.decode("utf-8") for r in file_records], ensure_ascii=True) + "\n"
                updated, kind = raw + block.replace("\r\n", "\n").replace("\n", newline).encode("utf-8"), "document_data"
            else:
                appended = javascript_carrier(file_records)
                if b"\r\n" in raw:
                    appended = appended.replace(b"\n", b"\r\n")
                updated, kind = raw + appended, "javascript_global_data"
        rows.append({"path": relative, "carrier_kind": kind,
                     "content_sha256": [FRAME_HEADER.match(r).group(2).decode() for r in file_records], "before_sha256": _sha256_bytes(raw),
                     "after_sha256": _sha256_bytes(updated), "bytes_before": len(raw),
                     "bytes_after": len(updated), "mode": stat.S_IMODE(path.stat().st_mode)})
        updates[relative] = updated
    requested_index = index_path or root / INDEX_FILENAME
    if requested_index.is_symlink():
        raise DeploymentError("deployment index cannot be a symlink")
    index = requested_index.resolve()
    manifest = {"schema_version": 1, "kind": "repel_carrier_deployment", "repository_root": str(root),
                "retention": "data-v1", "benign": benign,
                "selection": {"random": randomize, "seed": seed, "count": count, "payload_count": payload_count}, "files": rows, "files_changed": len(rows),
                "payload_metadata": [metadata for metadata, text in catalog_entries],
                "contents": [{"sha256": FRAME_HEADER.match(r).group(2).decode(),
                              "bytes": int(FRAME_HEADER.match(r).group(1))} for r in records],
                "status": "applied" if apply else "planned"}
    if apply:
        apply_deployment_plan(root, index, manifest, updates, store_path=store_path, snapshots=snapshots)
    return {**manifest, "index": str(index), "dry_run": not apply}


def _decode_literal(literal: str) -> bytes:
    """Decode static JS/JSON strings without evaluating any source code."""
    value = literal[1:-1]
    if literal[0] == "`" and "${" in value:
        return b""
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
    def replace(match):
        text = match.group(1)
        if text.startswith("u{"):
            return chr(int(text[2:-1], 16))
        if text.startswith(("u", "x")) and len(text) > 1:
            return chr(int(text[1:], 16))
        if text in {"\n", "\r", "\r\n"}:
            return ""
        return escapes.get(text, text)
    try:
        decoded = re.sub(r"\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|\r\n|[\s\S])", replace, value)
        decoded = decoded.encode("utf-16", "surrogatepass").decode("utf-16")
        return decoded.encode("utf-8")
    except (ValueError, UnicodeError):
        return b""


def recover_hashes(raw: bytes, *, web_text: bool = False) -> set:
    """Return hashes of complete, checksum-valid records, never their contents."""
    found = set()
    def scan(data):
        for match in FRAME_HEADER.finditer(data):
            length = int(match.group(1))
            end = match.end() + length
            if data[end:end + len(FRAME_END)] == FRAME_END:
                digest = _sha256_bytes(data[match.end():end])
                if digest == match.group(2).decode("ascii"):
                    found.add(digest)
    scan(raw)
    if web_text:
        source = raw.decode("utf-8", errors="replace")
        # Do not tokenize unrelated JS with a string regex: a quote inside a
        # comment or regex literal can otherwise swallow a later record. Each
        # record starts a standalone literal; inspect those starts independently.
        for start in RECORD_LITERAL_START.finditer(source):
            match = LITERAL.match(source, start.start())
            if match:
                scan(_decode_literal(match.group()))
    return found


def verify_artifacts(*, repository: Path, artifacts: Sequence[Path],
                     index_path: Optional[Path] = None) -> Dict[str, Any]:
    root = repository.resolve()
    index = index_path or root / INDEX_FILENAME
    if index.is_symlink():
        raise DeploymentError("deployment index cannot be a symlink")
    document = _read_json(index)
    if document.get("schema_version") == 2:
        from .deployment_store import load_manifest
        document = load_manifest(root, index)
    if (document.get("kind") != "repel_carrier_deployment" or document.get("retention") != "data-v1"
            or document.get("repository_root") != str(root)):
        raise DeploymentError("verification requires this repository's retained deployment index")
    contents = document.get("contents")
    if (not isinstance(contents, list) or not contents or any(not isinstance(c, dict)
            or not isinstance(c.get("sha256"), str) or not re.fullmatch("[0-9a-f]{64}", c["sha256"])
            for c in contents)):
        raise DeploymentError("retained deployment index has invalid content hashes")
    expected = {key for row in document["files"] for key in row.get("content_sha256", [])}
    if not expected:
        expected = {row["sha256"] for row in contents}
    if not artifacts:
        raise DeploymentError("specify at least one built --artifact")
    rows = []
    file_expectations = {str(root / row["path"]): set(row["content_sha256"]) for row in document["files"] if row.get("content_sha256")}
    for value in artifacts:
        path = value if value.is_absolute() else root / value
        path = path.absolute()
        raw = path.read_bytes()
        suffix = path.suffix.lower()
        if suffix == ".gz":
            try:
                raw = gzip.decompress(raw)
            except (OSError, EOFError) as exc:
                raise DeploymentError(f"invalid gzip artifact: {value}") from exc
            suffix = path.with_suffix("").suffix.lower()
        found = recover_hashes(raw, web_text=suffix in WEB_EXTENSIONS | HTML_EXTENSIONS | DOCUMENT_EXTENSIONS)
        required = file_expectations.get(str(path), expected)
        missing = sorted(required - found)
        rows.append({"path": str(path), "status": "missing" if missing else "verified",
                     "records_found": len(required & found), "missing_sha256": missing})
    return {"status": "verified" if all(r["status"] == "verified" for r in rows) else "missing",
            "artifacts": rows, "expected_records": len(expected)}
