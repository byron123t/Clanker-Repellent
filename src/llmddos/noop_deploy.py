"""Safely place validated language-native no-op carriers in a repository.

This module is deliberately separate from :mod:`payload_scatter`.  The latter delivers
opaque text as comments; this module consumes *already accepted* candidates from a no-op
generation run and places source syntax at statement boundaries.  Nothing here executes a
candidate.  Every applied change is recorded in a private, hash-based index so removal can
restore the exact original bytes.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


INDEX_FILENAME = ".anaphylaxis-noop-index.json"
POSITIONS = ("head", "mid", "tail")
SOURCE_EXTENSIONS: Dict[str, Tuple[str, ...]] = {
    "python": (".py", ".pyw"),
    "c": (".c", ".h"),
    "cpp": (".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"),
    "rust": (".rs",),
    "go": (".go",),
    "java": (".java",),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
    "typescript": (".ts", ".tsx", ".mts", ".cts"),
    "ruby": (".rb",),
    "bash": (".sh", ".bash", ".zsh"),
    "swift": (".swift",),
}
EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
    "results",
}


@dataclass(frozen=True)
class Carrier:
    candidate_id: str
    language: str
    source: str
    source_sha256: str
    relative_path: str


class DeploymentError(ValueError):
    """Raised when a carrier cannot be placed without risking a bad write."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"cannot read JSON manifest: {path}") from exc
    if not isinstance(document, dict):
        raise DeploymentError(f"manifest must contain a JSON object: {path}")
    return document


def load_accepted_carriers(run_dir: Path, *, allow_partial: bool = False) -> List[Carrier]:
    """Load only source files accepted by a completed no-op generation run.

    The manifest is authoritative: a stray source file, a failed candidate, or a symlink is
    never deployed.  ``allow_partial`` is explicit because a missing compiler/parser should
    not silently turn into a repository write.
    """

    root = run_dir.resolve()
    if root.is_file():
        raise DeploymentError(
            "--run-dir must point to the generation directory containing manifest.json, "
            f"not a candidate file: {root}; use {root.parent.parent}"
        )
    if not root.is_dir():
        raise DeploymentError(f"generation run directory does not exist: {root}")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise DeploymentError(f"--run-dir must contain manifest.json: {root}")
    document = _read_json(manifest_path)
    if document.get("kind") != "anaphylaxis_noop_generation":
        raise DeploymentError(f"not a no-op generation manifest: {manifest_path}")
    candidates = document.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise DeploymentError("generation manifest has no candidates")
    result: List[Carrier] = []
    seen_languages = set()
    for item in candidates:
        if not isinstance(item, dict):
            raise DeploymentError("generation manifest contains an invalid candidate")
        status = item.get("status")
        accepted = bool(item.get("accepted"))
        if not accepted or status not in ({"passed", "partial"} if allow_partial else {"passed"}):
            continue
        language = item.get("language")
        candidate_id = item.get("candidate_id") or item.get("template_id") or language
        candidate = item.get("candidate")
        if not isinstance(candidate_id, str) or not isinstance(language, str):
            raise DeploymentError("accepted candidate is missing candidate_id or language")
        if not isinstance(candidate, dict) or not isinstance(candidate.get("relative_path"), str):
            raise DeploymentError(f"accepted candidate has no source path: {candidate_id}")
        relative = Path(candidate["relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise DeploymentError(f"candidate path leaves generation directory: {candidate_id}")
        source_path = (root / relative).resolve()
        try:
            source_path.relative_to(root)
        except ValueError as exc:
            raise DeploymentError(f"candidate path leaves generation directory: {candidate_id}") from exc
        if source_path.is_symlink() or not source_path.is_file():
            raise DeploymentError(f"accepted candidate source is missing or symlinked: {candidate_id}")
        try:
            source = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise DeploymentError(f"cannot read accepted candidate: {source_path}") from exc
        if not source or "\x00" in source:
            raise DeploymentError(f"accepted candidate is empty or contains NUL: {source_path}")
        expected_hash = candidate.get("sha256")
        actual_hash = _sha256_text(source)
        if expected_hash != actual_hash:
            raise DeploymentError(f"accepted candidate hash changed: {candidate_id}")
        if language in seen_languages:
            raise DeploymentError(f"multiple accepted carriers for language: {language}")
        seen_languages.add(language)
        result.append(
            Carrier(
                candidate_id=candidate_id,
                language=language,
                source=source,
                source_sha256=actual_hash,
                relative_path=relative.as_posix(),
            )
        )
    if not result:
        suffix = " (or no passed candidates)" if not allow_partial else ""
        raise DeploymentError(f"generation run contains no deployable accepted carriers{suffix}")
    return result


def detect_language(path: Path, source: str = "") -> Optional[str]:
    """Return the native carrier language for a source path, including common shebangs."""

    suffix = path.suffix.casefold()
    matches = [language for language, extensions in SOURCE_EXTENSIONS.items() if suffix in extensions]
    if matches:
        # Header files are intentionally treated as C++ only when their spelling makes that
        # clear; otherwise C is the least surprising standalone carrier dialect.
        if suffix in {".hh", ".hpp", ".hxx"}:
            return "cpp"
        return matches[0]
    first = source.splitlines()[0].casefold() if source.startswith("#!") else ""
    if "python" in first:
        return "python"
    if "ruby" in first:
        return "ruby"
    if "bash" in first or re.search(r"(?:^|[\s/])(?:ba)?sh(?:\s|$)|(?:^|[\s/])zsh(?:\s|$)", first):
        return "bash"
    return None


def _is_candidate_file(path: Path, root: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    if any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(root).parts):
        return False
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    if not raw or b"\x00" in raw:
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return detect_language(path, text) is not None


def eligible_source_files(root: Path) -> List[Path]:
    """Find UTF-8 source files without following symlinks or generated directories."""

    paths: List[Path] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_DIRECTORIES)
        base = Path(directory)
        for filename in sorted(filenames):
            candidate = base / filename
            if _is_candidate_file(candidate, root):
                paths.append(candidate)
    return paths


def _newline_for(source: str) -> str:
    return "\r\n" if "\r\n" in source and source.count("\r\n") >= source.count("\n") / 2 else "\n"


def _python_multiline_string_lines(source: str) -> set[int]:
    """Return zero-based lines that are continuation lines of a Python string token."""

    preserved: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.STRING:
                continue
            start, end = token.start[0] - 1, token.end[0] - 1
            if end > start:
                preserved.update(range(start + 1, end + 1))
    except (IndentationError, tokenize.TokenError):
        # The candidate itself was already validated.  If this is ever triggered, prefixing all
        # lines remains the safe failure mode because host validation below will reject bad code.
        return set()
    return preserved


def _multiline_literal_lines(source: str, language: str) -> set[int]:
    """Find continuation lines of common native multiline literal forms.

    These are lexical spans only; no generated source is evaluated.  Preserving continuation
    lines keeps a payload's literal value stable when a carrier is nested in a function, class,
    namespace, or conditional block.
    """

    if language == "python":
        return _python_multiline_string_lines(source)
    patterns: List[str] = []
    if language in {"javascript", "typescript", "go"}:
        patterns.append(r"(?<!\\)`(?:\\.|[^`])*`")
    if language in {"cpp"}:
        patterns.append(r'R"(?P<tag>[A-Za-z0-9_]*)\((?s:.*?)\)(?P=tag)"')
    if language == "rust":
        patterns.append(r'r(?P<hash>#+)"(?s:.*?)"(?P=hash)')
    if language == "swift":
        patterns.extend((r'#"""(?s:.*?)"""#', r'"""(?s:.*?)"""'))
    if language == "java":
        patterns.append(r'"""(?s:.*?)"""')
    if language in {"javascript", "typescript"}:
        # JavaScript string literals are handled above; this also covers a generated text block
        # if a future language form uses triple quotes in a comment-like fixture.
        patterns.append(r'"""(?s:.*?)"""')
    preserved: set[int] = set()
    for pattern in patterns:
        try:
            matches = re.finditer(pattern, source)
        except re.error:
            continue
        for match in matches:
            start = source.count("\n", 0, match.start())
            end = source.count("\n", 0, match.end())
            if end > start:
                preserved.update(range(start + 1, end + 1))
    return preserved


def align_carrier(source: str, language: str, indent: str, newline: str = "\n") -> str:
    """Indent a carrier for a statement boundary while preserving literal payload bytes.

    Python is the special case: continuation lines inside a triple-quoted string are not
    prefixed, so placing a carrier inside a function does not silently change the payload's
    literal contents.  Bash heredocs and Ruby heredocs are kept top-level by the deployment
    planner because their terminators are column-sensitive.
    """

    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()
    if not lines:
        raise DeploymentError("carrier source is empty")
    preserve = _multiline_literal_lines(normalized, language)
    output: List[str] = []
    for index, line in enumerate(lines):
        prefix = "" if index in preserve else indent
        output.append(prefix + line)
    return newline.join(output) + newline


def _disambiguate_carrier(source: str, language: str, ordinal: int) -> str:
    """Give repeated placements distinct declaration names without touching literal payloads."""

    if ordinal == 0:
        return source
    suffix = f"_{ordinal + 1}"
    replacements: Dict[str, Tuple[str, ...]] = {
        "python": (r"^(\s*class\s+)(_NoopUnit)(\s*:)",),
        "c": (
            r"^(\s*static\s+const\s+char\s+)(noop_unit)(\s*\[)",
            r"^(\s*typedef\s+int\s+)(noop_translation_unit)(\s*;)",
        ),
        "cpp": (
            r"^(\s*namespace\s+)(noop_unit)(\s*\{)",
            r"^(\s*constexpr\s+auto\s+)(text)(\s*=)",
        ),
        "rust": (
            r"^(\s*mod\s+)(noop_unit)(\s*\{)",
            r"^(\s*const\s+)(TEXT)(\s*:)",
        ),
        "go": (r"^(\s*const\s+)(noopUnit)(\s*=)",),
        "java": (
            r"^(\s*final\s+class\s+)(NoopUnit)(\s*\{)",
            r"^(\s*private\s+)(NoopUnit)(\(\))",
        ),
        "javascript": (r"^(\s*class\s+)(NoopUnit)(\s*\{)",),
        "typescript": (r"^(\s*class\s+)(NoopUnit)(\s*\{)",),
        "ruby": (r"^(\s*)(NOOP_UNIT)(\s*=)",),
        "swift": (r"^(\s*private\s+enum\s+)(NoopUnit)(\s*\{)",),
    }
    result = source
    for pattern in replacements.get(language, ()):
        result = re.sub(
            pattern,
            lambda match: match.group(1) + match.group(2) + suffix + match.group(3),
            result,
            flags=re.MULTILINE,
        )
    return result


def _line_starts(source: str) -> List[int]:
    starts = [0]
    starts.extend(index + 1 for index, value in enumerate(source) if value == "\n")
    return starts


def _prologue_line(source: str) -> int:
    lines = source.splitlines(keepends=True)
    line = 0
    if lines and lines[0].startswith("#!"):
        line = 1
    # Preserve Python's encoding cookie and common license/shebang prologues.  A cookie is only
    # meaningful on the first two physical lines, so do not move it below the carrier.
    for candidate in range(line, min(len(lines), 2)):
        if re.match(r"\s*#.*coding[:=]\s*[-\w.]+", lines[candidate]):
            line = candidate + 1
    # A Python carrier before a future import makes the host file invalid.  Module docstrings
    # and future imports are the only AST constructs that must precede ordinary statements, so
    # advance the insertion point past them while retaining all original bytes.
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in tree.body:
            is_docstring = (
                isinstance(node, ast.Expr)
                and isinstance(getattr(node, "value", None), ast.Constant)
                and isinstance(node.value.value, str)
            )
            is_future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
            if not (is_docstring or is_future):
                break
            line = max(line, int(getattr(node, "end_lineno", line + 1)))
    return line


def _package_import_prologue_line(source: str, language: str) -> int:
    """Find a safe top-level insertion line after Go/Java package and imports."""

    lines = source.splitlines(keepends=True)
    line = 0
    index = 0
    if language == "go":
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index < len(lines) and re.match(r"\s*package\s+[A-Za-z_]\w*\s*$", lines[index].strip()):
            index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index < len(lines) and re.match(r"\s*import\s*\(\s*$", lines[index]):
            index += 1
            while index < len(lines):
                finished = re.match(r"\s*\)\s*$", lines[index])
                index += 1
                if finished:
                    break
        elif index < len(lines) and re.match(r"\s*import\b", lines[index]):
            index += 1
        line = index
    elif language == "java":
        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                index += 1
                continue
            if re.match(r"(?:package|import)\b", stripped):
                index += 1
                continue
            break
        line = index
    return line


def _indent_at(source: str, offset: int, language: str) -> str:
    starts = _line_starts(source)
    line_index = max(0, min(len(starts) - 1, next((i for i, value in enumerate(starts) if value > offset), len(starts)) - 1))
    lines = source.splitlines()
    for index in range(line_index, len(lines)):
        if lines[index].strip():
            return re.match(r"[ \t]*", lines[index]).group(0)
    for index in range(line_index - 1, -1, -1):
        if lines[index].strip():
            return re.match(r"[ \t]*", lines[index]).group(0)
    return ""


def _offset_for_position(source: str, position: str, language: str = "") -> int:
    starts = _line_starts(source)
    if position == "head":
        line = _prologue_line(source)
        if language in {"go", "java"}:
            line = max(line, _package_import_prologue_line(source, language))
        line = min(line, len(starts) - 1)
        return starts[line]
    if position == "tail":
        return len(source)
    line = min(max(len(starts) // 2, 0), len(starts) - 1)
    return starts[line]


def _insertion_text(source: str, offset: int, carrier: str, newline: str) -> str:
    body = carrier.replace("\n", newline)
    if not body.endswith(newline):
        body += newline
    leading = "" if offset == 0 or source[:offset].endswith(("\n", "\r")) else newline
    following = "" if offset == len(source) or source[offset:].startswith(("\n", "\r")) else newline
    return leading + body + following


def _validate_host_source(path: Path, language: str, source: str, timeout: float = 15.0) -> Dict[str, Any]:
    """Run syntax-oriented checks without executing or linking repository code."""

    if language == "python":
        try:
            ast.parse(source, filename=str(path))
            compile(source, str(path), "exec", dont_inherit=True)
            return {"status": "passed", "tool": "python-builtin"}
        except (SyntaxError, ValueError, TypeError) as exc:
            return {"status": "failed", "tool": "python-builtin", "diagnostic": f"{type(exc).__name__}: {exc}"}

    checks: Dict[str, Tuple[Sequence[str], List[str], bool]] = {
        "c": (("cc", "clang", "gcc"), ["-std=c11", "-fsyntax-only"], False),
        "cpp": (("c++", "clang++", "g++"), ["-std=c++17", "-fsyntax-only"], False),
        "javascript": (("node",), ["--check"], False),
        "typescript": (("tsc",), ["--pretty", "false", "--noEmit", "--skipLibCheck"], False),
        "ruby": (("ruby",), ["-cw"], False),
        "bash": (("bash",), ["-n"], False),
        "go": (("gofmt",), ["-d"], True),
        "rust": (("rustc",), ["--edition=2021", "--crate-type=lib", "--emit=metadata"], False),
        "java": (("javac",), ["-proc:none", "-Xlint:none"], False),
        "swift": (("swiftc",), ["-typecheck"], False),
    }
    spec = checks.get(language)
    if spec is None:
        return {"status": "unavailable", "tool": None, "reason": f"unsupported host language: {language}"}
    tools, args, require_clean_stdout = spec
    executable = next((shutil.which(item) for item in tools if shutil.which(item)), None)
    if executable is None:
        return {"status": "unavailable", "tool": tools[0]}
    with tempfile.TemporaryDirectory(prefix="anaphylaxis-host-check-") as directory:
        workdir = Path(directory)
        temporary = workdir / path.name
        temporary.write_text(source, encoding="utf-8")
        command = [executable] + args
        if language == "java":
            classes = workdir / "classes"
            classes.mkdir()
            command.extend(["-d", str(classes), str(temporary)])
        elif language == "rust":
            command.extend([str(temporary), "-o", str(workdir / "host.rmeta")])
        elif language == "typescript":
            command.extend(["--target", "ES2020", str(temporary)])
        else:
            command.append(str(temporary))
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"status": "error", "tool": Path(executable).name, "diagnostic": str(exc)}
        passed = result.returncode == 0 and (not require_clean_stdout or not result.stdout.strip())
        diagnostic = (result.stderr or result.stdout)[-2000:]
        return {"status": "passed" if passed else "failed", "tool": Path(executable).name, "diagnostic": diagnostic if not passed else ""}


def _placement_candidates(source: str, position: str, language: str) -> Iterable[Tuple[int, str]]:
    """Yield the requested placement and nearby physical statement boundaries."""

    preferred = _offset_for_position(source, position, language)
    yield preferred, _indent_at(source, preferred, language) if position == "mid" else ""
    if position != "mid":
        return
    starts = _line_starts(source)
    preferred_line = max(0, starts.index(preferred) if preferred in starts else len(starts) // 2)
    # A midpoint can land inside a parenthesized expression, multiline string, or Go import
    # block. Try nearby physical boundaries in deterministic order and let the parser choose.
    for distance in range(1, len(starts)):
        for line in (preferred_line - distance, preferred_line + distance):
            if 0 <= line < len(starts):
                offset = starts[line]
                yield offset, _indent_at(source, offset, language)


def inject_file(source: str, carrier: Carrier, positions: Sequence[str], path: Path) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Create one candidate post-image, refusing a syntactically unsafe placement."""

    newline = _newline_for(source)
    requested = list(dict.fromkeys(positions))
    if any(position not in POSITIONS for position in requested):
        raise DeploymentError("positions must be chosen from head, mid, tail")
    if not requested:
        raise DeploymentError("at least one position is required")
    language = carrier.language
    carrier_source = carrier.source
    if language == "go":
        # The generated Go fixture is a complete translation unit.  A repository file already
        # owns its package clause, so retain only the inert declaration when embedding it.
        carrier_source = re.sub(r"(?m)^\s*package\s+[A-Za-z_]\w*\s*\n", "", carrier_source, count=1)
    if language == "python":
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            raise DeploymentError(f"refusing invalid existing Python file: {path}: {exc}") from exc
    # Heredoc terminators are column-sensitive.  Keep those carriers at file scope instead of
    # guessing whether the surrounding function uses an indentation-aware delimiter.
    safe_positions = requested
    if language == "bash" and "mid" in safe_positions:
        safe_positions = [item for item in safe_positions if item != "mid"]
    if language == "ruby" and "mid" in safe_positions:
        safe_positions = [item for item in safe_positions if item != "mid"]
    if language == "java" and "mid" in safe_positions:
        # A top-level carrier class cannot safely be placed inside an arbitrary Java method.
        safe_positions = [item for item in safe_positions if item != "mid"]
    if not safe_positions:
        raise DeploymentError(f"no safe requested position for {language} in {path}")

    current = source
    records: List[Dict[str, Any]] = []
    # Process in requested order and validate the complete host after every insertion.
    for position in safe_positions:
        accepted: Optional[Tuple[str, int, str, str]] = None
        last_report: Dict[str, Any] = {}
        for offset, indent in _placement_candidates(current, position, language):
            aligned = align_carrier(
                _disambiguate_carrier(carrier_source, language, len(records)),
                language,
                indent,
                newline,
            )
            inserted = _insertion_text(current, offset, aligned, newline)
            candidate = current[:offset] + inserted + current[offset:]
            report = _validate_host_source(path, language, candidate)
            last_report = report
            if report["status"] == "passed":
                accepted = (candidate, offset, indent, inserted)
                break
        if accepted is None:
            diagnostic = last_report.get("diagnostic") or "host parser rejected placement"
            raise DeploymentError(f"{path} {position} placement failed: {diagnostic}")
        current, offset, indent, inserted_text = accepted
        records.append(
            {
                "position": position,
                "offset": offset,
                "indent": indent,
                "inserted_text": inserted_text,
                "inserted_bytes": len(inserted_text.encode("utf-8")),
                "inserted_sha256": _sha256_text(inserted_text),
                "validation": last_report,
            }
        )
    return current, records, {"language": language, "positions": safe_positions}


def _atomic_write(path: Path, data: bytes, *, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, document: Dict[str, Any]) -> None:
    _atomic_write(path, (json.dumps(document, indent=2) + "\n").encode("utf-8"))


def _indexed_target(root: Path, value: Any) -> Path:
    if not isinstance(value, str):
        raise DeploymentError("deployment index contains a non-string path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise DeploymentError(f"deployment index path leaves repository: {value}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DeploymentError(f"deployment index path leaves repository: {value}") from exc
    return path


def deploy_carriers(
    *,
    run_dir: Path,
    repository: Path,
    positions: Sequence[str] = ("head", "mid", "tail"),
    target_file: Optional[Path] = None,
    apply: bool = False,
    allow_partial: bool = False,
    index_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Plan or apply native carrier injections for a current-directory repository."""

    root = repository.resolve()
    if not root.is_dir():
        raise DeploymentError(f"repository is not a directory: {root}")
    carriers = load_accepted_carriers(run_dir, allow_partial=allow_partial)
    by_language = {carrier.language: carrier for carrier in carriers}
    if target_file is not None:
        candidate = target_file if target_file.is_absolute() else root / target_file
        candidate = candidate.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise DeploymentError(f"target file must be inside repository: {target_file}") from exc
        if not _is_candidate_file(candidate, root):
            raise DeploymentError(f"target file is not an eligible UTF-8 source file: {candidate}")
        files = [candidate]
    else:
        files = eligible_source_files(root)
    if not files:
        raise DeploymentError("no eligible source files found")
    planned: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    integration_failures: List[str] = []
    for path in files:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        language = detect_language(path, text)
        carrier = by_language.get(language or "")
        relative = path.relative_to(root).as_posix()
        if carrier is None:
            skipped.append({"path": relative, "reason": f"no accepted {language or 'matching'} carrier"})
            continue
        try:
            updated, placements, _ = inject_file(text, carrier, positions, path)
        except DeploymentError as exc:
            skipped.append({"path": relative, "reason": str(exc)})
            integration_failures.append(relative)
            continue
        if updated == text:
            skipped.append({"path": relative, "reason": "no change"})
            continue
        planned.append(
            {
                "path": relative,
                "language": language,
                "candidate_id": carrier.candidate_id,
                "carrier_sha256": carrier.source_sha256,
                "before_sha256": _sha256_bytes(raw),
                "after_sha256": _sha256_text(updated),
                "placements": placements,
                "bytes_before": len(raw),
                "bytes_after": len(updated.encode("utf-8")),
                "mode": stat.S_IMODE(path.stat().st_mode),
                "_updated": updated,
            }
        )
    if apply and integration_failures:
        joined = ", ".join(integration_failures[:5])
        suffix = "..." if len(integration_failures) > 5 else ""
        raise DeploymentError(
            "refusing partial deployment; host integration failed for " + joined + suffix
        )
    requested_index = index_path or (root / INDEX_FILENAME)
    if requested_index.is_symlink():
        raise DeploymentError(f"deployment index cannot be a symlink: {requested_index}")
    index = requested_index.resolve()
    manifest: Dict[str, Any] = {
        "schema_version": 1,
        "kind": "anaphylaxis_noop_deployment",
        "repository_root": str(root),
        "run_dir": str(run_dir.resolve()),
        "positions_requested": list(positions),
        "allow_partial": allow_partial,
        "files": [
            {key: value for key, value in record.items() if key != "_updated"}
            for record in planned
        ],
        "skipped": skipped,
        "files_changed": len(planned),
        "status": "planned" if not apply else "applied",
    }
    if apply:
        if index.exists() or index.is_symlink():
            raise DeploymentError(f"deployment index already exists; remove it first: {index}")
        preimage_root = index.with_name(index.name + ".preimage")
        if preimage_root.exists() or preimage_root.is_symlink():
            raise DeploymentError(f"preimage directory already exists; remove it first: {preimage_root}")
        preimage_root.mkdir(parents=True, mode=0o700)
        try:
            for record in planned:
                path = root / record["path"]
                current = path.read_bytes()
                if _sha256_bytes(current) != record["before_sha256"]:
                    raise DeploymentError(f"file changed during planning: {path}")
                backup = preimage_root / record["path"]
                backup.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(backup, current)
                _atomic_write(
                    path,
                    record.pop("_updated").encode("utf-8"),
                    mode=int(record.get("mode", stat.S_IMODE(path.stat().st_mode))),
                )
            _atomic_json(index, manifest)
        except Exception:
            # Do not leave a partially applied native deployment if its audit index cannot be
            # written.  Restore from the private preimages before surfacing the error.
            for record in planned:
                path = root / record["path"]
                backup = preimage_root / record["path"]
                if backup.is_file():
                    _atomic_write(path, backup.read_bytes(), mode=int(record.get("mode", 0o600)))
            shutil.rmtree(preimage_root, ignore_errors=True)
            raise
    return {**manifest, "index": str(index), "dry_run": not apply}


def remove_deployment(*, repository: Path, index_path: Optional[Path] = None, apply: bool = False) -> Dict[str, Any]:
    """Restore files from a native-carrier index, failing closed on intervening edits."""

    root = repository.resolve()
    requested_index = index_path or (root / INDEX_FILENAME)
    if requested_index.is_symlink():
        raise DeploymentError(f"deployment index cannot be a symlink: {requested_index}")
    index = requested_index.resolve()
    document = _read_json(index)
    if document.get("kind") != "anaphylaxis_noop_deployment" or document.get("repository_root") != str(root):
        raise DeploymentError(f"index does not belong to this repository: {index}")
    rows = document.get("files")
    if not isinstance(rows, list):
        raise DeploymentError(f"deployment index has no files: {index}")
    clean = True
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise DeploymentError("deployment index contains an invalid file record")
        path = _indexed_target(root, row["path"])
        if not path.is_file() or path.is_symlink() or _sha256_bytes(path.read_bytes()) != row.get("after_sha256"):
            clean = False
    if not clean:
        raise DeploymentError("indexed files changed after deployment; refusing approximate removal")
    if apply:
        preimage_root = index.with_name(index.name + ".preimage")
        for row in rows:
            backup = preimage_root / row["path"]
            if not backup.is_file() or backup.is_symlink():
                raise DeploymentError(f"missing preimage backup for {row['path']}: {backup}")
        for row in rows:
            path = _indexed_target(root, row["path"])
            # The original bytes are intentionally represented by a reversible patch-free
            # operation: deployment indexes store the preimage hash only, so restore requires a
            # clean Git checkout or the explicit backup created below.
            backup = preimage_root / row["path"]
            _atomic_write(path, backup.read_bytes(), mode=int(row.get("mode", stat.S_IMODE(path.stat().st_mode))))
        shutil.rmtree(preimage_root, ignore_errors=False)
        index.unlink()
        return {"status": "removed", "files_restored": len(rows), "index": str(index)}
    return {"status": "removable", "files_restored": len(rows), "index": str(index)}


def status_deployment(*, repository: Path, index_path: Optional[Path] = None) -> Dict[str, Any]:
    root = repository.resolve()
    requested_index = index_path or (root / INDEX_FILENAME)
    if requested_index.is_symlink():
        raise DeploymentError(f"deployment index cannot be a symlink: {requested_index}")
    index = requested_index.resolve()
    document = _read_json(index)
    rows = document.get("files")
    if document.get("kind") != "anaphylaxis_noop_deployment" or not isinstance(rows, list):
        raise DeploymentError(f"invalid native-carrier deployment index: {index}")
    changed = 0
    for row in rows:
        path = _indexed_target(root, row.get("path", ""))
        if not path.is_file() or _sha256_bytes(path.read_bytes()) != row.get("after_sha256"):
            changed += 1
    return {"status": "clean" if changed == 0 else "changed", "files": len(rows), "changed": changed, "index": str(index)}
