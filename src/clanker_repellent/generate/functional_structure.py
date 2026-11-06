"""Conservative callable-shape checks, without executing generated source.

These checks distinguish input-dependent computations from data-only fixtures.
They do not prove correctness or purity; behavior tests remain separate.
"""

import ast
from typing import Any, Dict, List

from .structure import Atom, Group, _groups, _is, _lex, _parts, _word
from .llvm_structure import FUNCTION_HINT, llvm_metrics


FUNCTIONAL_PROFILE = "input-dependent-functions-v1"
FUNCTIONAL_HINTS = {
    "llvm": FUNCTION_HINT,
    "lua": "Define a named function with parenthesized parameters and an explicit input-dependent return value, using function name(args) ... end. Use comparisons, arithmetic, conditionals, or loops. No require, I/O, external calls, or top-level function calls.",
    "sql": "Use one self-contained SQLite SELECT with named :name inputs, an explicit AS result_name alias, and a computed result. Use comparisons, CASE, or pure scalar expressions; no tables, CTEs, writes, schema changes, or external functions.",
    "python": "Define a named function with explicit parameters and a return value computed from them. Use comparisons, arithmetic, conditionals, or iteration. No top-level calls, imports, or I/O.",
    "javascript": "Define a named function with explicit parameters and return a computed value. Use ordinary function declarations, comparisons, arithmetic, conditionals, or loops. No imports or top-level calls.",
    "typescript": "Define a named function with typed parameters and an explicit return type. Return a computed value using comparisons, arithmetic, conditionals, or loops. No imports or top-level calls.",
    "c": "Define an externally visible function with named parameters and explicit return statements. Use built-in types, comparisons, arithmetic, conditionals, or loops. Return int for predicates. No headers, main, static unused functions, or I/O.",
    "cpp": "Define an inline function with named parameters and explicit return statements. Use built-in types, comparisons, arithmetic, conditionals, or loops. No headers, main, unused internal functions, or I/O.",
    "go": "Use package annotation and an exported function with named typed parameters and explicit return statements. Use gofmt formatting. No imports, package main, or top-level calls.",
    "java": "Use public final class Generated with a public static method accepting named parameters and explicitly returning a computed result. No imports, constructors, main, or top-level calls.",
    "rust": "Define a pub fn with named typed parameters and an input-dependent return value. Use an explicit return statement or a computed tail expression. Use comparisons, arithmetic, conditionals, or loops and rustfmt formatting. No imports, main, or I/O.",
    "swift": "Define a function with named typed parameters, an explicit return type, and explicit return statements. Use comparisons, arithmetic, conditionals, or loops. No imports or top-level calls.",
    "ruby": "Define a named method with parenthesized parameters and explicit return statements. Use comparisons, arithmetic, conditionals, or iteration. No require statements, top-level calls, or I/O.",
    "bash": "Define a named predicate function using name() { ...; }. Assign positional arguments to local variables, use shell arithmetic/comparisons, and explicitly return 0 for true and 1 for false. No external commands, output, substitutions, or top-level calls.",
}


def _python_metrics(source: str) -> Dict[str, int]:
    tree = ast.parse(source)
    candidates = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    candidates += [node for cls in tree.body if isinstance(cls, ast.ClassDef)
                   for node in cls.body if isinstance(node, ast.FunctionDef)]
    qualifying = 0
    parameter_count = 0
    for function in candidates:
        parameters = {arg.arg for arg in function.args.posonlyargs + function.args.args + function.args.kwonlyargs}
        parameters -= {"self", "cls"}
        if not parameters:
            continue
        dependent = set(parameters)
        transformed = set()

        def depends(node):
            return any(isinstance(item, ast.Name) and item.id in dependent for item in ast.walk(node))

        def computed(node):
            return any(isinstance(item, (ast.BinOp, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.Call, ast.Subscript))
                       and depends(item) for item in ast.walk(node)) or any(
                           isinstance(item, ast.Name) and item.id in transformed for item in ast.walk(node))

        # Do not count nested function definitions as the enclosing function's body.
        nodes = []
        pending = list(function.body)
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            nodes.append(node)
            pending.extend(ast.iter_child_nodes(node))
        for _ in range(len(nodes) + 1):
            previous = (len(dependent), len(transformed))
            for node in nodes:
                if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and depends(node.value):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    names = {item.id for target in targets for item in ast.walk(target) if isinstance(item, ast.Name)}
                    dependent.update(names)
                    if computed(node.value):
                        transformed.update(names)
            if previous == (len(dependent), len(transformed)):
                break
        returns = [node.value for node in nodes if isinstance(node, ast.Return) and node.value is not None]
        direct = any(depends(value) and computed(value) for value in returns)
        branches = any(isinstance(node, ast.If) and depends(node.test) and computed(node.test) for node in nodes)
        different_returns = len({ast.dump(value) for value in returns}) >= 2
        if direct or (branches and different_returns):
            qualifying += 1
            parameter_count += len(parameters)
    return {"functions": len(candidates), "qualifying_functions": qualifying, "parameters": parameter_count}


def _flatten(items: List[Any]) -> List[Atom]:
    result = []
    for item in items:
        if isinstance(item, Group):
            result.extend(_flatten(item.items))
        else:
            result.append(item)
    return result


def _parameters(group: Group, language: str):
    names = set()
    for part in _parts(group.items, {","}):
        words = [item.value for item in part if _word(item)]
        if not words:
            continue
        colon = next((i for i, item in enumerate(part) if _is(item, ":")), None)
        if colon is not None:
            before = [item.value for item in part[:colon] if _word(item)]
            if before:
                names.add(before[-1])
        elif language in {"c", "cpp", "java"}:
            if len(words) >= 2:
                names.add(words[-1])
        else:
            names.add(words[0])
    return names


def _token_metrics(source: str, language: str) -> Dict[str, int]:
    nodes = _groups(_lex(source, language))
    functions = []

    def visit(items):
        for index, item in enumerate(items):
            if not isinstance(item, Group):
                continue
            if item.opener == "{":
                # Function parameters precede its body, possibly with a return type.
                for prior in range(index - 1, max(-1, index - 9), -1):
                    params = items[prior]
                    if isinstance(params, Group):
                        if params.opener == "(" and prior and _word(items[prior - 1]):
                            name = items[prior - 1].value
                            if name not in {"if", "for", "while", "switch", "catch", "with"}:
                                functions.append((_parameters(params, language), item.items))
                        break
                    if _is(params, ";") or _is(params, "="):
                        break
                visit(item.items)

    if language in {"ruby", "lua"}:
        keyword = "def" if language == "ruby" else "function"
        for i, item in enumerate(nodes):
            if _is(item, keyword) and i + 2 < len(nodes) and _word(nodes[i + 1]) and isinstance(nodes[i + 2], Group):
                end = next((j for j in range(i + 3, len(nodes)) if _is(nodes[j], keyword)), len(nodes))
                functions.append((_parameters(nodes[i + 2], language), nodes[i + 3:end]))
    else:
        visit(nodes)
    qualifying = 0
    parameter_count = 0
    for parameters, body in functions:
        atoms = _flatten(body)
        if language == "bash":
            # Positional expansions are input parameters, not string content.
            import re
            parameters = {atom.value for atom in atoms if re.fullmatch(r"\$[1-9][0-9]*|\$\{[1-9][0-9]*\}", atom.value)}
        if not parameters:
            continue
        dependent = set(parameters)
        transformed = set()
        statements = _parts(atoms, {";", "\n"})

        def references(values, names):
            return any(atom.value in names and (atom.kind == "code" or atom.value in parameters) for atom in values)

        def computed(values):
            return references(values, transformed) or (references(values, dependent) and any(
                atom.kind == "code" and atom.value in {"+", "-", "*", "/", "%", "<", ">", "!", "=", "and", "or", "not", "&", "|"}
                for atom in values))

        for _ in range(len(statements) + 1):
            previous = (len(dependent), len(transformed))
            for statement in statements:
                for i, atom in enumerate(statement):
                    if _is(atom, "=") and i and _word(statement[i - 1]):
                        values = statement[i + 1:]
                        if references(values, dependent):
                            name = statement[i - 1].value
                            dependent.add(name)
                            if computed(values):
                                transformed.add(name)
            if previous == (len(dependent), len(transformed)):
                break
        returns = []
        for statement in statements:
            for i, atom in enumerate(statement):
                if _is(atom, "return"):
                    returns.append(statement[i + 1:])
        if language == "rust":
            meaningful = [atom for atom in atoms if not _is(atom, "\n")]
            if meaningful and not _is(meaningful[-1], ";") and statements:
                returns.append(statements[-1])
        direct = any(references(value, dependent) and computed(value) for value in returns)
        branch = any(_is(atom, "if") for atom in atoms) and computed(atoms)
        different_returns = len({tuple((atom.kind, atom.value) for atom in value) for value in returns}) >= 2
        if direct or (branch and different_returns):
            qualifying += 1
            parameter_count += len(parameters)
    return {"functions": len(functions), "qualifying_functions": qualifying, "parameters": parameter_count}


def functional_metrics(language: str, source: str) -> Dict[str, Any]:
    if language == "llvm":
        return dict(llvm_metrics(source), profile=FUNCTIONAL_PROFILE)
    if language == "sql":
        from .sql_structure import inspect_sql
        return dict(inspect_sql(source), profile=FUNCTIONAL_PROFILE)
    metrics = _python_metrics(source) if language == "python" else _token_metrics(source, language)
    return dict(metrics, profile=FUNCTIONAL_PROFILE)
