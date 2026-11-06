"""Conservative checks for populated data structures; never execute candidate code.

Python uses its AST. Other languages use Pygments' built-in lexers followed by
small, language-specific declaration checks. Native parsers/compilers remain
responsible for syntax and types. This is a structural minimum, not a semantic
quality or safety proof.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Dict, List


from .llvm_structure import DATA_HINT, llvm_metrics

STRUCTURE_PROFILE = "populated-data-v1"
LANGUAGE_HINTS = {
    "llvm": DATA_HINT,
    "lua": "Use a named local table with at least two distinct named fields and initialized literal values. Use local name = {field = value, other = value} syntax without calls or imports.",
    "sql": "Use one self-contained SQLite SELECT with at least two distinct AS column_name aliases and literal values. Use no tables, input parameters, CTEs, writes, schema changes, or external functions.",
    "html": "Use a static HTML fragment or a complete HTML5 document. Include a container such as section, article, ul, dl, or table with a unique nonempty id and at least two populated semantic descendants, such as a heading and paragraph, list items, or table cells. Prefer a heading plus a populated list or table. Use plain semantic elements, inline text formatting, and id/class/aria-/data- metadata only; no scripts, styles, event handlers, templates, hidden content, embedded media, forms, or external URLs. Complete documents need <!DOCTYPE html> and may include UTF-8 charset metadata.",
    "python": "Use a named dictionary with at least two distinct literal keys and initialized values, or a class with at least two initialized data attributes. A list of such records is also suitable.",
    "bash": "Use two distinct named indexed arrays as table columns, each containing at least two literal entries. Use plain array assignments, no commands, substitutions, or associative arrays.",
    "c": "Define a named struct with at least two separately declared fields and an externally visible const instance or array initializing every field. Use no headers; avoid static unused declarations and empty translation units.",
    "cpp": "Define one named struct with at least two separately declared fields, then initialize every field in a file-scope inline constexpr instance or array. Use the declaration form inline constexpr YourStruct example = {...}; with your own names and literal values. Use built-in field types such as const char* and int, no headers, helper globals, static declarations, anonymous namespaces, or function wrappers. The inline keyword is required to avoid unused-constant warnings under -Werror.",
    "go": "Use package annotation. Define a named struct with at least two fields and a package-level variable initialized with a composite literal populating both fields. Use gofmt formatting. Do not use package main or imports.",
    "java": "Use public final class Generated with at least two separately declared, initialized static final data fields. Use literal initializers, no imports, constructors, or main method.",
    "javascript": "Use a named const object with at least two distinct named properties and initialized literal values, or an array of such objects. Do not use calls or imports.",
    "typescript": "Use a named const object with at least two distinct named properties and initialized literal values, optionally with a matching interface. An array of such objects is also suitable. Do not use calls or imports.",
    "ruby": "Use a named constant hash with at least two distinct symbol or string keys and initialized literal values, or an array of such hashes. Use no require statements or calls.",
    "rust": "Define a pub struct with at least two separately declared pub fields and a pub const instance initializing each named field. Use &'static str for text. Avoid imports, calls, unused private declarations, and main. Use rustfmt formatting.",
    "swift": "Define a named struct with at least two separately declared let properties initialized with literals, or a named dictionary with at least two initialized keys. Do not use imports or calls.",
}


@dataclass
class Atom:
    value: str
    kind: str = "code"


@dataclass
class Group:
    opener: str
    items: List[Any]


def _lex(source: str, language: str) -> List[Atom]:
    from pygments import lex
    from pygments.lexers import get_lexer_by_name
    from pygments.token import Comment, Error, Number, String

    tokens: List[Atom] = []
    directives = []
    string_open = False
    for kind, value in lex(source, get_lexer_by_name(language)):
        if kind in Comment.Preproc and language in {"c", "cpp", "swift"}:
            raise ValueError("preprocessor-dependent structure is not supported")
        if kind in Comment.Preproc and language == "rust":
            directives.append(value)
        if kind in Comment:
            string_open = False
            if "\n" in value:
                tokens.append(Atom("\n"))
        elif kind in String.Symbol and language == "ruby":
            string_open = False
            tokens.append(Atom(value.rstrip(":"), "symbol"))
            if value.endswith(":"):
                tokens.append(Atom(":"))
        elif kind in String:
            if string_open:
                tokens[-1].value += value
            else:
                tokens.append(Atom(value, "string"))
            string_open = True
        elif kind in Number or re.fullmatch(r"(?:0[xX][\da-fA-F]+|\d[\d_]*(?:\.[\d_]*)?(?:[eE][+-]?\d+)?)[uUlLfFnN]*", value):
            string_open = False
            tokens.append(Atom(value, "number"))
        elif kind in Error:
            raise ValueError("unsupported lexical form")
        else:
            string_open = False
            for word in re.findall(r"\n|=>|:=|[A-Za-z_$][A-Za-z_0-9$]*|[^\s]", value):
                tokens.append(Atom(word))
    if re.search(r"\bcfg(?:_attr)?\s*\(", "".join(directives)):
        raise ValueError("conditional structure is not supported")
    return tokens


def _groups(tokens: List[Atom]) -> List[Any]:
    root: List[Any] = []
    stack = [root]
    closers = []
    for token in tokens:
        if token.kind == "code" and token.value in {"(", "[", "{"}:
            group = Group(token.value, [])
            stack[-1].append(group)
            stack.append(group.items)
            closers.append({"(": ")", "[": "]", "{": "}"}[token.value])
        elif token.kind == "code" and token.value in {")", "]", "}"}:
            if not closers or token.value != closers.pop():
                raise ValueError("unbalanced declaration")
            stack.pop()
        else:
            stack[-1].append(token)
    if closers:
        raise ValueError("unbalanced declaration")
    return root


def _is(item: Any, value: str) -> bool:
    return isinstance(item, Atom) and item.kind == "code" and item.value == value


def _word(item: Any) -> bool:
    return isinstance(item, Atom) and item.kind == "code" and bool(re.fullmatch(r"[A-Za-z_$][A-Za-z_0-9$]*", item.value))


def _clean(items: List[Any]) -> List[Any]:
    return [item for item in items if not _is(item, "\n")]


def _parts(items: List[Any], separators: set) -> List[List[Any]]:
    parts: List[List[Any]] = [[]]
    for item in items:
        if isinstance(item, Atom) and item.kind == "code" and item.value in separators:
            if parts[-1]:
                parts.append([])
        elif not _is(item, "\n"):
            parts[-1].append(item)
    return [part for part in parts if part]


def _map_fields(group: Group, *, assignment: bool = False) -> int:
    keys = set()
    for part in _parts(group.items, {","}):
        if len(part) < 3 or not isinstance(part[0], Atom):
            continue
        if not (_word(part[0]) or part[0].kind in {"string", "symbol"}):
            continue
        arrow = len(part) >= 4 and _is(part[1], "=") and _is(part[2], ">")
        if (_is(part[1], ":") or _is(part[1], "=>") or arrow or assignment and _is(part[1], "=")) and _literal_value(part[3:] if arrow else part[2:]):
            key = part[0].value.strip(":")
            if part[0].kind == "string":
                try:
                    decoded = ast.literal_eval(key)
                    key = decoded if isinstance(decoded, str) else key
                except (ValueError, SyntaxError):
                    pass
            keys.add(key)
    return len(keys)


def _literal_value(items: List[Any]) -> bool:
    """Allow literal data, not constructors or other call expressions, as field defaults."""
    return bool(items) and all(
        (isinstance(item, Group) and item.opener in {"[", "{"} and bool(item.items))
        or (isinstance(item, Atom) and (item.kind in {"string", "number", "symbol"}
                                      or item.value in {"true", "false", "null", "nil", "None", "-", "+"}))
        for item in items
    )


def _record_fields(group: Group, language: str):
    names = set()
    initialized = set()
    separators = {","} if language == "rust" else {";", "\n"}
    for part in _parts(group.items, separators):
        if any(isinstance(item, Group) and item.opener in {"(", "{"} for item in part):
            continue  # Methods and nested definitions do not count as data fields.
        equal = next((i for i, item in enumerate(part) if _is(item, "=")), len(part))
        declaration = part[:equal]
        colon = next((i for i, item in enumerate(declaration) if _is(item, ":")), len(declaration))
        words = [item.value for item in declaration if _word(item)]
        if len(words) < 2:
            continue
        if language in {"rust", "swift"}:
            before_type = [item.value for item in declaration[:colon] if _word(item)]
            if not before_type:
                continue
            name = before_type[-1]
        elif language == "go":
            name = words[0]
        else:
            name = words[-1]
        names.add(name)
        if equal < len(part) and _literal_value(part[equal + 1:]):
            initialized.add(name)
    return len(names), len(initialized)


def _python_fields(value: ast.AST) -> int:
    if isinstance(value, ast.Dict):
        keys = {key.value for key, item in zip(value.keys, value.values)
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and _python_literal(item)}
        return len(keys)
    if isinstance(value, (ast.List, ast.Tuple)):
        return max((_python_fields(item) for item in value.elts), default=0)
    return 0


def _python_literal(value: ast.AST) -> bool:
    try:
        ast.literal_eval(value)
        return True
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return False


def _python_structure(source: str):
    tree = ast.parse(source)
    fields = 0
    for statement in tree.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            if any(isinstance(target, ast.Name) for target in targets):
                fields = max(fields, _python_fields(statement.value))
        elif isinstance(statement, ast.ClassDef):
            attributes = set()
            for item in statement.body:
                if not isinstance(item, (ast.Assign, ast.AnnAssign)) or item.value is None:
                    continue
                # Calls and properties alone cannot turn an empty wrapper into a data model.
                if not _python_literal(item.value):
                    continue
                targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                attributes.update(target.id for target in targets if isinstance(target, ast.Name))
            fields = max(fields, len(attributes))
    return fields


def structure_metrics(language: str, source: str) -> Dict[str, Any]:
    """Return only counts and fixed labels, never identifiers, literals, or source text."""
    metrics: Dict[str, Any] = {"profile": STRUCTURE_PROFILE, "fields": 0, "initialized_fields": 0}
    if language == "llvm":
        return dict(metrics, **llvm_metrics(source))
    if language == "html":
        from .html_structure import html_metrics
        return dict(metrics, **html_metrics(source))
    if language == "sql":
        from .sql_structure import inspect_sql
        return dict(metrics, **inspect_sql(source))
    if language == "python":
        fields = _python_structure(source)
        return dict(metrics, fields=fields, initialized_fields=fields)
    nodes = _groups(_lex(source, language))
    flat = _clean(nodes)
    if language == "rust":
        for i, item in enumerate(flat):
            if _is(item, "#"):
                for attribute in flat[i + 1:i + 3]:
                    if isinstance(attribute, Group) and attribute.opener == "[" and any(
                        _is(value, "cfg") or _is(value, "cfg_attr") for value in attribute.items
                    ):
                        raise ValueError("conditional structure is not supported")
    definitions = {}
    keyword = "class" if language == "java" else "struct"
    for i, item in enumerate(flat):
        if not _is(item, keyword):
            continue
        if language == "go":
            name = flat[i - 1] if i >= 2 and _is(flat[i - 2], "type") else None
            body = flat[i + 1] if i + 1 < len(flat) else None
        else:
            name = flat[i + 1] if i + 1 < len(flat) else None
            body = flat[i + 2] if i + 2 < len(flat) else None
        if not _word(name) or not isinstance(body, Group) or body.opener != "{":
            continue
        fields, initialized = _record_fields(body, language)
        definitions[name.value] = fields
        if initialized >= 2:
            metrics.update(fields=fields, initialized_fields=initialized)

    arrays = set()
    for part in _parts(nodes, {";", "\n"}):
        if language == "cpp" and not any(_is(item, keyword) for item in part for keyword in {"struct", "class", "typedef"}):
            # C++ direct list initialization does not require an equals sign.
            for i, item in enumerate(part):
                if isinstance(item, Group) and item.opener == "{":
                    for name, fields in definitions.items():
                        if fields >= 2 and any(_is(atom, name) for atom in part[:i]):
                            count = len(_parts(item.items, {","}))
                            if count >= 2:
                                metrics.update(fields=fields, initialized_fields=count)
        for i, item in enumerate(part):
            if not _is(item, "=") or not i:
                continue
            before = part[:i]
            after = part[i + 1:]
            if not after or not any(_word(atom) for atom in before):
                continue
            group = after[0]
            if language == "bash" and isinstance(group, Group) and group.opener == "(":
                values = _clean(group.items)
                if len(values) >= 2 and all(isinstance(value, Atom) for value in values):
                    arrays.add(before[-1].value if _word(before[-1]) else "")
                continue
            if language in {"javascript", "typescript", "ruby", "swift", "lua"} and isinstance(group, Group):
                required = {"javascript": {"const", "let", "var"}, "typescript": {"const", "let", "var"},
                            "ruby": set(), "swift": {"let", "var"}, "lua": {"local"}}[language]
                if required and not any(_is(atom, word) for atom in before for word in required):
                    continue
                allowed = {"["} if language == "swift" else {"{"}
                candidates = [group] if group.opener in allowed else []
                if group.opener == "[":
                    candidates += [child for child in group.items if isinstance(child, Group) and child.opener in allowed]
                fields = max((_map_fields(candidate, assignment=language == "lua") for candidate in candidates), default=0)
                if fields >= 2:
                    metrics.update(fields=fields, initialized_fields=fields)
            for name, fields in definitions.items():
                if fields < 2:
                    continue
                initializer = group
                if _is(group, name) and len(after) >= 2:
                    initializer = after[1]
                elif not any(_is(atom, name) for atom in before):
                    continue
                if not isinstance(initializer, Group) or initializer.opener != "{":
                    continue
                candidates = [initializer] + [child for child in initializer.items if isinstance(child, Group) and child.opener == "{"]
                count = max(((_map_fields(value) if language in {"rust", "go"} else len(_parts(value.items, {","})))
                             for value in candidates), default=0)
                if count >= 2:
                    metrics.update(fields=fields, initialized_fields=count)
    if language == "bash" and len(arrays - {""}) >= 2:
        metrics.update(fields=len(arrays - {""}), initialized_fields=len(arrays - {""}))
    return metrics
