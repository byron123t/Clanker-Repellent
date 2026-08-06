"""Deterministically scatter marked payload text through disposable repositories."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


COMMENT_PREFIXES = {
    ".asm": ";",
    ".bash": "#",
    ".c": "//",
    ".cc": "//",
    ".cfg": "#",
    ".cl": ";",
    ".clj": ";",
    ".cljc": ";",
    ".cljs": ";",
    ".cmake": "#",
    ".cnf": "#",
    ".conf": "#",
    ".cpp": "//",
    ".cs": "//",
    ".css": "/*",
    ".cts": "//",
    ".cxx": "//",
    ".dart": "//",
    ".dockerignore": "#",
    ".editorconfig": "#",
    ".env": "#",
    ".erl": "%",
    ".ex": "#",
    ".exs": "#",
    ".f03": "!",
    ".f08": "!",
    ".f90": "!",
    ".f95": "!",
    ".fish": "#",
    ".fs": "//",
    ".fsx": "//",
    ".gitignore": "#",
    ".go": "//",
    ".gradle": "//",
    ".groovy": "//",
    ".h": "//",
    ".hh": "//",
    ".hpp": "//",
    ".hrl": "%",
    ".hs": "--",
    ".htm": "<!--",
    ".html": "<!--",
    ".hxx": "//",
    ".inc": "//",
    ".ini": "#",
    ".inl": "//",
    ".java": "//",
    ".js": "//",
    ".jsx": "//",
    ".cjs": "//",
    ".jl": "#",
    ".jq": "#",
    ".jsonc": "//",
    ".kt": "//",
    ".kts": "//",
    ".less": "/*",
    ".lisp": ";",
    ".lua": "--",
    ".m": "//",
    ".m4": "#",
    ".mak": "#",
    ".mk": "#",
    ".ml": "(*",
    ".mli": "(*",
    ".mjs": "//",
    ".mm": "//",
    ".mts": "//",
    ".nim": "#",
    ".npmignore": "#",
    ".npmrc": "#",
    ".pas": "//",
    ".php": "//",
    ".rs": "//",
    ".ps1": "#",
    ".properties": "#",
    ".pyw": "#",
    ".rkt": ";",
    ".sass": "//",
    ".scala": "//",
    ".scm": ";",
    ".scss": "/*",
    ".sol": "//",
    ".s": "#",
    ".ss": ";",
    ".svelte": "<!--",
    ".svg": "<!--",
    ".swift": "//",
    ".tf": "#",
    ".toml": "#",
    ".ts": "//",
    ".tsx": "//",
    ".vb": "'",
    ".vue": "<!--",
    ".xml": "<!--",
    ".yaml": "#",
    ".yml": "#",
    ".zig": "//",
    ".zsh": "#",
    ".pl": "#",
    ".pm": "#",
    ".py": "#",
    ".r": "#",
    ".rb": "#",
    ".sh": "#",
    ".sql": "--",
    ".adoc": "//",
    ".rst": "..",
}

PAIRED_COMMENT_SUFFIXES = {
    "<!--": "-->",
    "/*": "*/",
    "(*": "*)",
}

FILENAME_COMMENT_PREFIXES = {
    ".dockerignore": "#",
    ".editorconfig": "#",
    ".env": "#",
    ".gitignore": "#",
    ".npmignore": "#",
    ".npmrc": "#",
    "bsdmakefile": "#",
    "build": "#",
    "build.bazel": "#",
    "cmakelists.txt": "#",
    "containerfile": "#",
    "dockerfile": "#",
    "gemfile": "#",
    "gnumakefile": "#",
    "jenkinsfile": "//",
    "makefile": "#",
    "meson.build": "#",
    "meson_options.txt": "#",
    "pipfile": "#",
    "rakefile": "#",
    "vagrantfile": "#",
    "workspace": "#",
    "workspace.bazel": "#",
}

SHEBANG_COMMENT_PREFIXES = {
    "bash": "#",
    "bun": "//",
    "deno": "//",
    "fish": "#",
    "lua": "--",
    "node": "//",
    "perl": "#",
    "php": "//",
    "powershell": "#",
    "pwsh": "#",
    "python": "#",
    "python2": "#",
    "python3": "#",
    "rscript": "#",
    "ruby": "#",
    "sh": "#",
    "zsh": "#",
}

MARKED_TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}

EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

MARKER = "LLMDDOS_PAYLOAD_BEGIN"
END_MARKER = "LLMDDOS_PAYLOAD_END"
POINTER_MARKER = "LLMDDOS_PAYLOAD_POINTER"
HUB_CARRIER = "LLMDDOS_EVAL_PAYLOAD.txt"
STRATEGY_REPLICATED = "replicated"
STRATEGY_FRAGMENTED = "fragmented"
STRATEGY_HUB_SPOKE = "hub_spoke"
STRATEGIES = (
    STRATEGY_REPLICATED,
    STRATEGY_FRAGMENTED,
    STRATEGY_HUB_SPOKE,
)
POSITION_HEAD = "head"
POSITION_MID = "mid"
POSITION_TAIL = "tail"
FILE_POSITIONS = (POSITION_HEAD, POSITION_MID, POSITION_TAIL)
DEFAULT_FILE_POSITIONS = (POSITION_TAIL,)
INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md", "MEMORY.md")
WITH_INSTRUCTION_FILES = "with_instruction_files"
WITHOUT_INSTRUCTION_FILES = "without_instruction_files"
INSTRUCTION_FILE_ALIASES = {
    "claude": "CLAUDE.md",
    "claude.md": "CLAUDE.md",
    "agents": "AGENTS.md",
    "agents.md": "AGENTS.md",
    "memory": "MEMORY.md",
    "memory.md": "MEMORY.md",
}
DEFAULT_MAX_FILE_BYTES = 1_000_000
DEFAULT_INLINE_SOURCE_LINES = 40
DEFAULT_HUB_CHUNK_LINES = 8


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _shebang_comment_prefix(raw: bytes) -> Optional[str]:
    if not raw.startswith(b"#!"):
        return None
    first_line = raw.splitlines()[0].decode("utf-8").casefold()
    tokens = re.findall(r"[a-z][a-z0-9+.-]*", first_line)
    for token in reversed(tokens):
        if token in SHEBANG_COMMENT_PREFIXES:
            return SHEBANG_COMMENT_PREFIXES[token]
        versionless = re.sub(r"\d+(?:\.\d+)*$", "", token)
        if versionless in SHEBANG_COMMENT_PREFIXES:
            return SHEBANG_COMMENT_PREFIXES[versionless]
    return None


def _eligible_files(
    repository_root: Path,
    *,
    max_file_bytes: int,
    extensions: Optional[Iterable[str]],
) -> List[Tuple[Path, Optional[str]]]:
    allowed = set(COMMENT_PREFIXES) | MARKED_TEXT_EXTENSIONS
    if extensions is not None:
        requested = {
            extension.casefold()
            if extension.startswith(".")
            else "." + extension.casefold()
            for extension in extensions
        }
        unknown = requested - allowed
        if unknown:
            raise ValueError("unsupported extensions: " + ", ".join(sorted(unknown)))
        allowed = requested
    candidates = []
    detect_filenames_and_shebangs = extensions is None
    for directory, names, files in os.walk(repository_root, followlinks=False):
        names[:] = sorted(
            name
            for name in names
            if name not in EXCLUDED_DIRECTORIES
            and not (Path(directory) / name).is_symlink()
        )
        for name in sorted(files):
            path = Path(directory) / name
            suffix = path.suffix.casefold()
            filename_prefix = FILENAME_COMMENT_PREFIXES.get(name.casefold())
            suffix_is_allowed = suffix in allowed
            might_have_shebang = detect_filenames_and_shebangs and not suffix
            if (
                path.is_symlink()
                or not suffix_is_allowed
                and not (detect_filenames_and_shebangs and filename_prefix)
                and not might_have_shebang
            ):
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if len(raw) > max_file_bytes or b"\x00" in raw:
                continue
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            prefix = (
                filename_prefix
                if filename_prefix is not None
                else COMMENT_PREFIXES.get(suffix)
            )
            if not suffix_is_allowed and prefix is None:
                prefix = _shebang_comment_prefix(raw)
            if not suffix_is_allowed and prefix is None:
                continue
            if MARKER in content or POINTER_MARKER in content:
                continue
            candidates.append((path, prefix))
    return candidates


def eligible_file_count(
    repository_root: Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    extensions: Optional[Iterable[str]] = None,
    instruction_files: Optional[Iterable[str]] = None,
) -> int:
    """Return the number of source files eligible for a fresh scatter operation."""

    root = repository_root.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository_root}")
    excluded = set(normalize_instruction_files(instruction_files))
    return sum(
        1
        for path, _ in _eligible_files(
            root,
            max_file_bytes=max_file_bytes,
            extensions=extensions,
        )
        if path.relative_to(root).as_posix() not in excluded
    )


def _rank(seed: int, relative_path: str) -> str:
    return hashlib.sha256(f"{seed}\x00{relative_path}".encode("utf-8")).hexdigest()


def _comment_block(
    payload: str,
    prefix: str,
    payload_sha256: str,
    newline: str,
    *,
    metadata: str = "",
) -> str:
    lines = payload.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    closing = PAIRED_COMMENT_SUFFIXES.get(prefix)
    if closing is not None and closing in payload:
        raise ValueError(
            f"payload contains unsafe closing delimiter {closing!r} for {prefix!r}"
        )

    def comment(value: str) -> str:
        if closing is None:
            return f"{prefix} {value}" if value else prefix
        return f"{prefix} {value} {closing}" if value else f"{prefix}{closing}"

    commented = [comment(line) for line in lines]
    return newline.join(commented) + newline


def _pointer_block(
    prefix: str, payload_sha256: str, newline: str, *, metadata: str = ""
) -> str:
    closing = PAIRED_COMMENT_SUFFIXES.get(prefix)
    closing_text = f" {closing}" if closing is not None else ""
    return f"{prefix} See {HUB_CARRIER}{closing_text}{newline}"


def _append_block(raw: bytes, block: str) -> bytes:
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    separator = "" if not text or text.endswith(("\n", "\r")) else newline
    return (text + separator + block).encode("utf-8")


def _insert_blocks_with_locations(
    raw: bytes,
    blocks: List[Tuple[str, str]],
    custom_offsets: Optional[Dict[str, int]] = None,
) -> Tuple[bytes, List[Dict[str, Any]]]:
    """Insert blocks and return their exact indexed spans in the resulting bytes."""

    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    offsets = {
        POSITION_HEAD: 0,
        POSITION_MID: sum(len(line) for line in lines[: len(lines) // 2]),
        POSITION_TAIL: len(text),
    }
    if custom_offsets:
        offsets.update(custom_offsets)
    grouped: Dict[int, List[Tuple[str, str]]] = {}
    for position, block in blocks:
        grouped.setdefault(offsets[position], []).append((position, block))
    output = bytearray()
    locations: List[Dict[str, Any]] = []
    cursor = 0
    for offset in sorted(grouped):
        output.extend(text[cursor:offset].encode("utf-8"))
        before = text[:offset]
        separator = "" if not before or before.endswith(("\n", "\r")) else newline
        for index, (position, block) in enumerate(grouped[offset]):
            inserted = (separator if index == 0 else "") + block
            inserted_bytes = inserted.encode("utf-8")
            start = len(output)
            output.extend(inserted_bytes)
            locations.append(
                {
                    "position": position,
                    "start_byte": start,
                    "end_byte": len(output),
                    "inserted_bytes": len(inserted_bytes),
                    "inserted_sha256": _sha256_bytes(inserted_bytes),
                }
            )
        cursor = offset
    output.extend(text[cursor:].encode("utf-8"))
    return bytes(output), locations


def _scaled_inline_offsets(raw: bytes, count: int) -> Dict[str, int]:
    """Return evenly spaced line-boundary offsets for inline payload chunks."""

    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if not lines:
        return {"inline_001": 0}
    effective = min(count, len(lines))
    offsets = {}
    for index in range(effective):
        boundary = ((index + 1) * len(lines)) // (effective + 1)
        offsets[f"inline_{index + 1:03d}"] = sum(
            len(line) for line in lines[:boundary]
        )
    return offsets


def _markdown_block(
    payload: str,
    payload_sha256: str,
    newline: str,
    *,
    filename: str,
    position: str,
    role: str = "instruction",
    metadata: str = "",
) -> str:
    normalized = payload.replace("\r\n", "\n").replace("\r", "\n")
    body = normalized.replace("\n", newline)
    separator = "" if body.endswith(("\n", "\r")) else newline
    return f"{body}{separator}"


def normalize_file_positions(
    file_positions: Optional[Iterable[str]],
) -> Tuple[str, ...]:
    positions = (
        DEFAULT_FILE_POSITIONS
        if file_positions is None
        else tuple(str(position).strip().casefold() for position in file_positions)
    )
    if not positions:
        raise ValueError("file_positions must contain at least one position")
    unknown = set(positions) - set(FILE_POSITIONS)
    if unknown:
        raise ValueError("unsupported file positions: " + ", ".join(sorted(unknown)))
    if len(positions) != len(set(positions)):
        raise ValueError("file_positions cannot contain duplicates")
    return positions


def normalize_instruction_files(
    instruction_files: Optional[Iterable[str]],
) -> Tuple[str, ...]:
    if instruction_files is None:
        return ()
    normalized = []
    for value in instruction_files:
        key = str(value).strip().casefold()
        if key not in INSTRUCTION_FILE_ALIASES:
            raise ValueError(
                "unsupported instruction file; choose CLAUDE.md, AGENTS.md, or MEMORY.md"
            )
        normalized.append(INSTRUCTION_FILE_ALIASES[key])
    if len(normalized) != len(set(normalized)):
        raise ValueError("instruction_files cannot contain duplicates")
    return tuple(normalized)


def instruction_layout_directory(
    instruction_files: Optional[Iterable[str]],
) -> str:
    return (
        WITH_INSTRUCTION_FILES
        if normalize_instruction_files(instruction_files)
        else WITHOUT_INSTRUCTION_FILES
    )


def _load_instruction_targets(
    root: Path, instruction_names: Tuple[str, ...], max_file_bytes: int
) -> List[Tuple[str, Path, bytes, str, bool]]:
    """Validate every instruction target before any repository file is written."""

    targets = []
    for filename in instruction_names:
        instruction_path = root / filename
        if instruction_path.is_symlink():
            raise ValueError(f"instruction file cannot be a symlink: {instruction_path}")
        instruction_existed = instruction_path.exists()
        if instruction_existed:
            try:
                instruction_raw = instruction_path.read_bytes()
            except OSError as exc:
                raise ValueError(
                    f"instruction file is not readable: {instruction_path}"
                ) from exc
            if len(instruction_raw) > max_file_bytes or b"\x00" in instruction_raw:
                raise ValueError(
                    f"instruction file is not eligible: {instruction_path}"
                )
            try:
                instruction_text = instruction_raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"instruction file must be UTF-8: {instruction_path}"
                ) from exc
            if MARKER in instruction_text or POINTER_MARKER in instruction_text:
                raise ValueError(
                    f"instruction file is already marked: {instruction_path}"
                )
        else:
            instruction_raw = b""
            instruction_text = ""
        targets.append(
            (
                filename,
                instruction_path,
                instruction_raw,
                instruction_text,
                instruction_existed,
            )
        )
    return targets


def _split_payload(payload: str, count: int) -> List[str]:
    """Split text into exact, ordered, non-empty contiguous fragments."""

    if len(payload) < count:
        raise ValueError(
            f"fragmented strategy needs at least {count} payload characters"
        )
    boundaries = [(len(payload) * index) // count for index in range(count + 1)]
    fragments = [
        payload[boundaries[index] : boundaries[index + 1]]
        for index in range(count)
    ]
    if any(not fragment for fragment in fragments) or "".join(fragments) != payload:
        raise RuntimeError("payload fragmentation failed to preserve the exact text")
    return fragments


def _split_payload_lines(payload: str, count: int) -> List[str]:
    """Split a payload into exact, non-empty chunks at physical line boundaries."""

    lines = payload.splitlines(keepends=True)
    count = min(count, len(lines))
    boundaries = [(len(lines) * index) // count for index in range(count + 1)]
    chunks = [
        "".join(lines[boundaries[index] : boundaries[index + 1]])
        for index in range(count)
    ]
    if any(not chunk for chunk in chunks) or "".join(chunks) != payload:
        raise RuntimeError("line fragmentation failed to preserve the exact text")
    return chunks


def _normalize_payload_pool(
    payload: str,
    condition_id: str,
    payload_pool: Optional[Iterable[Dict[str, str]]],
    seed: int,
) -> List[Dict[str, str]]:
    values = (
        [{"id": condition_id, "payload": payload}]
        if payload_pool is None
        else [dict(item) for item in payload_pool]
    )
    if not values:
        raise ValueError("payload_pool must contain at least one payload")
    seen = set()
    normalized = []
    for item in values:
        if set(item) != {"id", "payload"}:
            raise ValueError("each payload_pool item must contain exactly id and payload")
        payload_id = item["id"]
        text = item["payload"]
        if not isinstance(payload_id, str) or not payload_id.strip():
            raise ValueError("payload_pool ids must be non-empty strings")
        if payload_id in seen:
            raise ValueError(f"duplicate payload_pool id: {payload_id}")
        if not isinstance(text, str) or not text or "\x00" in text:
            raise ValueError("payload_pool payloads must be non-empty NUL-free strings")
        seen.add(payload_id)
        normalized.append(
            {
                "id": payload_id,
                "payload": text,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    return sorted(normalized, key=lambda item: _rank(seed, item["id"]))


def _hub_carrier(payload: str, payload_sha256: str) -> bytes:
    return (payload + ("" if payload.endswith("\n") else "\n")).encode("utf-8")


def _hub_carrier_pool(
    payloads: List[Dict[str, str]], chunk_lines: int
) -> Tuple[bytes, List[Dict[str, Any]]]:
    """Build one external carrier from payload chunks split only at line boundaries."""

    output = bytearray()
    locations = []
    for payload_item in payloads:
        line_count = max(1, len(payload_item["payload"].splitlines()))
        chunk_count = max(1, (line_count + chunk_lines - 1) // chunk_lines)
        chunks = _split_payload_lines(payload_item["payload"], chunk_count)
        for chunk_index, chunk in enumerate(chunks, start=1):
            normalized = chunk
            if chunk_index == len(chunks) and not normalized.endswith("\n"):
                normalized += "\n"
            raw = normalized.encode("utf-8")
            start = len(output)
            output.extend(raw)
            locations.append(
                {
                    "position": f"line_chunk_{len(locations) + 1:04d}",
                    "kind": "carrier_line_chunk",
                    "payload_id": payload_item["id"],
                    "payload_sha256": payload_item["sha256"],
                    "chunk_index": chunk_index,
                    "chunk_count": len(chunks),
                    "start_byte": start,
                    "end_byte": len(output),
                    "inserted_bytes": len(raw),
                    "inserted_sha256": _sha256_bytes(raw),
                }
            )
    return bytes(output), locations


def scatter_payload(
    repository_root: Path,
    payload: str,
    *,
    condition_id: str,
    count: Optional[int] = None,
    seed: int,
    apply: bool = False,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    extensions: Optional[Iterable[str]] = None,
    strategy: str = STRATEGY_REPLICATED,
    file_positions: Optional[Iterable[str]] = None,
    instruction_files: Optional[Iterable[str]] = None,
    payload_pool: Optional[Iterable[Dict[str, str]]] = None,
    inline_source_lines: int = DEFAULT_INLINE_SOURCE_LINES,
    hub_chunk_lines: int = DEFAULT_HUB_CHUNK_LINES,
) -> Dict[str, Any]:
    """Select files deterministically and apply one marked propagation topology."""

    root = repository_root.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository_root}")
    if not isinstance(payload, str) or not payload:
        raise ValueError("payload must be a non-empty string")
    if "\x00" in payload:
        raise ValueError("payload cannot contain NUL bytes")
    if not isinstance(condition_id, str) or not condition_id.strip():
        raise ValueError("condition_id must be a non-empty string")
    if count is not None and count < 1:
        raise ValueError("count must be at least 1")
    if max_file_bytes < 1:
        raise ValueError("max_file_bytes must be at least 1")
    if inline_source_lines < 1:
        raise ValueError("inline_source_lines must be at least 1")
    if hub_chunk_lines < 1:
        raise ValueError("hub_chunk_lines must be at least 1")
    if strategy not in STRATEGIES:
        raise ValueError("strategy must be one of: " + ", ".join(STRATEGIES))
    positions = normalize_file_positions(file_positions)
    payloads = _normalize_payload_pool(payload, condition_id, payload_pool, seed)
    instruction_names = normalize_instruction_files(instruction_files)
    instruction_targets = _load_instruction_targets(
        root, instruction_names, max_file_bytes
    )

    candidates = _eligible_files(
        root, max_file_bytes=max_file_bytes, extensions=extensions
    )
    excluded_source_paths = set(instruction_names)
    candidates = [
        candidate
        for candidate in candidates
        if candidate[0].relative_to(root).as_posix() not in excluded_source_paths
    ]
    ranked = sorted(
        candidates,
        key=lambda item: _rank(seed, item[0].relative_to(root).as_posix()),
    )
    effective_count = len(ranked) if count is None else count
    if effective_count < 1:
        raise ValueError("found no eligible unmarked files")
    if len(ranked) < effective_count:
        raise ValueError(
            f"requested {effective_count} injections but found only "
            f"{len(ranked)} eligible unmarked files"
        )
    payload_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    carrier_path = root / HUB_CARRIER
    if strategy == STRATEGY_HUB_SPOKE and (
        carrier_path.exists() or carrier_path.is_symlink()
    ):
        raise ValueError(f"hub carrier already exists: {carrier_path}")
    selected_files = ranked[:effective_count]
    if strategy != STRATEGY_HUB_SPOKE:
        for path, prefix in selected_files:
            effective_prefix = (
                "<!--" if prefix is None and strategy == STRATEGY_FRAGMENTED else prefix
            )
            closing = PAIRED_COMMENT_SUFFIXES.get(effective_prefix or "")
            for payload_item in payloads:
                if closing is not None and closing in payload_item["payload"]:
                    raise ValueError(
                        f"payload contains unsafe closing delimiter {closing!r} "
                        f"for {path.relative_to(root).as_posix()}"
                    )
        if strategy == STRATEGY_FRAGMENTED and instruction_targets:
            for payload_item in payloads:
                if "-->" in payload_item["payload"]:
                    raise ValueError(
                        "payload contains unsafe closing delimiter '-->' "
                        "for an instruction file"
                    )
    injections: List[Dict[str, Any]] = []
    for index, (path, prefix) in enumerate(selected_files):
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        newline = "\r\n" if "\r\n" in text else "\n"
        relative_path = path.relative_to(root).as_posix()
        payload_item = payloads[index % len(payloads)]
        block_payload = payload_item["payload"]
        payload_hash = payload_item["sha256"]
        custom_offsets: Dict[str, int] = {}
        inline_chunks: List[Dict[str, Any]] = []
        if strategy == STRATEGY_REPLICATED:
            role = "replica"
        elif strategy == STRATEGY_FRAGMENTED:
            role = "replica_with_inline_chunks"
            source_lines = max(1, len(text.splitlines()))
            desired_chunks = max(
                1, (source_lines + inline_source_lines - 1) // inline_source_lines
            )
            chunks = _split_payload_lines(block_payload, desired_chunks)
            custom_offsets = _scaled_inline_offsets(raw, len(chunks))
            for chunk_index, (position, chunk) in enumerate(
                zip(custom_offsets, chunks), start=1
            ):
                inline_prefix = prefix or "<!--"
                inline_block = _comment_block(
                    chunk, inline_prefix, payload_hash, newline
                )
                inline_chunks.append(
                    {
                        "position": position,
                        "block": inline_block,
                        "chunk_index": chunk_index,
                        "chunk_count": len(chunks),
                        "chunk_sha256": hashlib.sha256(
                            chunk.encode("utf-8")
                        ).hexdigest(),
                    }
                )
        else:
            role = "pointer"
            block_payload = f"See {HUB_CARRIER}"
        blocks = []
        for position in positions:
            if prefix is None:
                block = _markdown_block(
                    block_payload,
                    payload_sha256,
                    newline,
                    filename=relative_path,
                    position=position,
                    role=role,
                )
            elif strategy == STRATEGY_HUB_SPOKE:
                block = _pointer_block(
                    prefix,
                    payload_sha256,
                    newline,
                )
            else:
                block = _comment_block(
                    block_payload,
                    prefix,
                    payload_sha256,
                    newline,
                )
            blocks.append((position, block))
        blocks.extend((item["position"], item["block"]) for item in inline_chunks)
        updated, placement_index = _insert_blocks_with_locations(
            raw, blocks, custom_offsets
        )
        chunks_by_position = {item["position"]: item for item in inline_chunks}
        for placement in placement_index:
            chunk = chunks_by_position.get(placement["position"])
            placement["kind"] = (
                "inline_chunk"
                if chunk is not None
                else "pointer" if strategy == STRATEGY_HUB_SPOKE else "full_replica"
            )
            if chunk is not None:
                placement.update(
                    {
                        "chunk_index": chunk["chunk_index"],
                        "chunk_count": chunk["chunk_count"],
                        "chunk_sha256": chunk["chunk_sha256"],
                    }
                )
        record: Dict[str, Any] = {
            "path": relative_path,
            "role": role,
            "comment_prefix": prefix or "marked-text",
            "before_sha256": _sha256_bytes(raw),
            "after_sha256": _sha256_bytes(updated),
            "positions": list(positions),
            "placement_count": len(placement_index),
            "placements": placement_index,
        }
        if strategy == STRATEGY_HUB_SPOKE:
            record["payload_ids"] = [item["id"] for item in payloads]
        else:
            record["payload_id"] = payload_item["id"]
            record["payload_sha256"] = payload_hash
        if strategy == STRATEGY_FRAGMENTED:
            record.update(
                {
                    "full_replica_placements": len(positions),
                    "inline_chunk_count": len(inline_chunks),
                    "source_physical_lines": max(1, len(text.splitlines())),
                }
            )
        if apply:
            path.write_bytes(updated)
        injections.append(record)

    if strategy == STRATEGY_HUB_SPOKE:
        carrier, carrier_chunks = _hub_carrier_pool(payloads, hub_chunk_lines)
        if apply:
            carrier_path.write_bytes(carrier)
        injections.append(
            {
                "path": HUB_CARRIER,
                "role": "carrier",
                "before_sha256": None,
                "after_sha256": _sha256_bytes(carrier),
                "payload_ids": [item["id"] for item in payloads],
                "line_chunk_count": len(carrier_chunks),
                "placements": carrier_chunks,
            }
        )
    for instruction_index, (
        filename,
        instruction_path,
        instruction_raw,
        instruction_text,
        instruction_existed,
    ) in enumerate(instruction_targets):
        instruction_newline = "\r\n" if "\r\n" in instruction_text else "\n"
        payload_item = payloads[
            (len(selected_files) + instruction_index) % len(payloads)
        ]
        instruction_payload = (
            f"See {HUB_CARRIER}"
            if strategy == STRATEGY_HUB_SPOKE
            else payload_item["payload"]
        )
        instruction_blocks = [
            (
                position,
                _markdown_block(
                    instruction_payload,
                    payload_item["sha256"],
                    instruction_newline,
                    filename=filename,
                    position=position,
                ),
            )
            for position in positions
        ]
        custom_offsets: Dict[str, int] = {}
        inline_chunks: List[Dict[str, Any]] = []
        if strategy == STRATEGY_FRAGMENTED:
            source_lines = max(1, len(instruction_text.splitlines()))
            desired_chunks = max(
                1, (source_lines + inline_source_lines - 1) // inline_source_lines
            )
            chunks = _split_payload_lines(payload_item["payload"], desired_chunks)
            custom_offsets = _scaled_inline_offsets(instruction_raw, len(chunks))
            for chunk_index, (position, chunk) in enumerate(
                zip(custom_offsets, chunks), start=1
            ):
                inline_chunks.append(
                    {
                        "position": position,
                        "block": _comment_block(
                            chunk,
                            "<!--",
                            payload_item["sha256"],
                            instruction_newline,
                        ),
                        "chunk_index": chunk_index,
                        "chunk_count": len(chunks),
                        "chunk_sha256": hashlib.sha256(
                            chunk.encode("utf-8")
                        ).hexdigest(),
                    }
                )
            instruction_blocks.extend(
                (item["position"], item["block"]) for item in inline_chunks
            )
        instruction_updated, placement_index = _insert_blocks_with_locations(
            instruction_raw, instruction_blocks, custom_offsets
        )
        chunks_by_position = {item["position"]: item for item in inline_chunks}
        for placement in placement_index:
            chunk = chunks_by_position.get(placement["position"])
            placement["kind"] = (
                "inline_chunk"
                if chunk is not None
                else "pointer" if strategy == STRATEGY_HUB_SPOKE else "full_replica"
            )
            if chunk is not None:
                placement.update(
                    {
                        "chunk_index": chunk["chunk_index"],
                        "chunk_count": chunk["chunk_count"],
                        "chunk_sha256": chunk["chunk_sha256"],
                    }
                )
        if apply:
            instruction_path.write_bytes(instruction_updated)
        instruction_record: Dict[str, Any] = {
            "path": filename,
            "role": "instruction",
            "before_sha256": (
                _sha256_bytes(instruction_raw) if instruction_existed else None
            ),
            "after_sha256": _sha256_bytes(instruction_updated),
            "positions": list(positions),
            "placement_count": len(placement_index),
            "placements": placement_index,
        }
        if strategy == STRATEGY_HUB_SPOKE:
            instruction_record["payload_ids"] = [item["id"] for item in payloads]
        else:
            instruction_record["payload_id"] = payload_item["id"]
            instruction_record["payload_sha256"] = payload_item["sha256"]
        if strategy == STRATEGY_FRAGMENTED:
            instruction_record["full_replica_placements"] = len(positions)
            instruction_record["inline_chunk_count"] = len(inline_chunks)
            instruction_record["source_physical_lines"] = max(
                1, len(instruction_text.splitlines())
            )
        injections.append(instruction_record)
    return {
        "schema_version": 5,
        "mode": "apply" if apply else "dry-run",
        "repository_root": str(root),
        "condition_id": condition_id,
        "payload_sha256": payload_sha256,
        "payload_pool": [
            {"id": item["id"], "sha256": item["sha256"]} for item in payloads
        ],
        "payload_pool_size": len(payloads),
        "seed": seed,
        "strategy": strategy,
        "file_positions": list(positions),
        "configured_full_placements_per_source_file": len(positions),
        "placements_per_source_file": len(positions),
        "inline_source_lines": inline_source_lines,
        "hub_chunk_lines": hub_chunk_lines,
        "instruction_files": list(instruction_names),
        "requested_injections": count,
        "selection_mode": "all_eligible" if count is None else "fixed_count",
        "source_files_selected": effective_count,
        "eligible_files": len(candidates),
        "files_changed": len(injections),
        "placements_written": sum(
            len(record.get("placements", ())) for record in injections
        ),
        "injections": injections,
    }


def remove_scattered_payload(
    repository_root: Path,
    scatter_index: Dict[str, Any],
    *,
    apply: bool = False,
) -> Dict[str, Any]:
    """Restore an untouched indexed repository without relying on visible markers."""

    root = repository_root.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository_root}")
    if not isinstance(scatter_index, dict):
        raise ValueError("scatter index must be an object")
    if scatter_index.get("schema_version") not in {4, 5}:
        raise ValueError("removal requires a schema_version 4 or 5 scatter index")
    if scatter_index.get("mode") != "apply":
        raise ValueError("removal requires an index from an applied scatter operation")
    injections = scatter_index.get("injections")
    if not isinstance(injections, list) or not injections:
        raise ValueError("scatter index must contain non-empty injections")

    plans: List[Tuple[Path, Optional[bytes], str]] = []
    seen = set()
    for record in injections:
        relative_value = record.get("path") if isinstance(record, dict) else None
        if not isinstance(relative_value, str) or not relative_value:
            raise ValueError("scatter index contains an invalid path")
        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts or relative_value in seen:
            raise ValueError(f"unsafe or duplicate indexed path: {relative_value}")
        seen.add(relative_value)
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"indexed file is missing or unsafe: {path}")
        raw = path.read_bytes()
        if _sha256_bytes(raw) != record.get("after_sha256"):
            raise ValueError(f"indexed file changed after scattering: {path}")
        before_sha256 = record.get("before_sha256")
        if before_sha256 is None:
            plans.append((path, None, relative_value))
            continue
        placements = record.get("placements")
        if not isinstance(placements, list) or not placements:
            raise ValueError(f"indexed placements are missing for {path}")
        if any(not isinstance(placement, dict) for placement in placements):
            raise ValueError(f"indexed placement is malformed for {path}")
        restored = raw
        for placement in sorted(
            placements, key=lambda item: item.get("start_byte", -1), reverse=True
        ):
            start = placement.get("start_byte")
            end = placement.get("end_byte")
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or start < 0
                or end <= start
                or end > len(restored)
                or end - start != placement.get("inserted_bytes")
            ):
                raise ValueError(f"invalid indexed placement for {path}")
            inserted = restored[start:end]
            if _sha256_bytes(inserted) != placement.get("inserted_sha256"):
                raise ValueError(f"indexed placement changed after scattering: {path}")
            restored = restored[:start] + restored[end:]
        if _sha256_bytes(restored) != before_sha256:
            raise ValueError(f"indexed removal does not restore original file: {path}")
        plans.append((path, restored, relative_value))

    if apply:
        for path, restored, _ in plans:
            if restored is None:
                path.unlink()
            else:
                path.write_bytes(restored)
    return {
        "schema_version": 1,
        "mode": "apply" if apply else "dry-run",
        "repository_root": str(root),
        "condition_id": scatter_index.get("condition_id"),
        "payload_sha256": scatter_index.get("payload_sha256"),
        "strategy": scatter_index.get("strategy"),
        "files_restored": sum(restored is not None for _, restored, _ in plans),
        "created_files_removed": sum(restored is None for _, restored, _ in plans),
        "paths": [relative for _, _, relative in plans],
    }


def write_scatter_manifest(manifest: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
