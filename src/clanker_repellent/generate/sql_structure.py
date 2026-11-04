"""Static checks for self-contained, read-only SQLite SELECT snippets."""

import re
import sqlite3


_PURE_FUNCTIONS = {"abs", "coalesce", "ifnull", "nullif", "min", "max", "length", "lower", "upper", "trim", "round"}


def _code(source):
    from pygments import lex
    from pygments.lexers import get_lexer_by_name
    from pygments.token import Comment, String

    tokens = list(lex(source, get_lexer_by_name("sql")))
    code = "".join(re.sub(r"[^\r\n]", " ", value) if kind in Comment or kind in String else value
                   for kind, value in tokens)
    aliases = set()
    after_as = False
    depth = 0
    for kind, value in tokens:
        if kind in Comment or not value.strip():
            continue
        if after_as:
            if kind in String.Symbol and value.startswith('"') and value.endswith('"'):
                aliases.add(value[1:-1].replace('""', '"'))
            elif kind not in String and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", value):
                aliases.add(value)
        if kind not in String:
            depth += value.count("(") - value.count(")")
        after_as = depth == 0 and kind not in String and value.upper() == "AS"
    return code, aliases - {""}


def inspect_sql(source):
    """Prepare EXPLAIN only; never evaluate the candidate query or access real tables.

    EXPLAIN alone is insufficient for PRAGMA/DDL. The SELECT-only prefix and
    authorizer additionally reject those constructs and extension functions.
    """
    code, aliases = _code(source)
    if not re.match(r"\s*SELECT\b", code, re.IGNORECASE):
        raise ValueError("SQL requires one self-contained SQLite SELECT statement.")
    if re.search(r"\bWITH\b", code, re.IGNORECASE):
        raise ValueError("SQL common table expressions are outside this snippet profile.")
    parameters = set(re.findall(r"(?<!:):([A-Za-z_][A-Za-z_0-9]*)", code))
    if len(parameters) > 128:
        raise ValueError("SQL contains too many input parameters.")

    def authorize(action, first, second, _database, _trigger):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (second or first or "").casefold() in _PURE_FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    connection = sqlite3.connect(":memory:")
    try:
        connection.set_authorizer(authorize)
        # No bytecode format assumptions: successful preparation is the check.
        connection.execute("EXPLAIN " + source, {name: 0 for name in parameters})
    except (sqlite3.Error, sqlite3.Warning):
        raise ValueError("SQL must compile as one read-only SELECT with :name parameters, no tables, and only supported pure functions.") from None
    finally:
        connection.close()

    computation = bool(re.search(r"[<>!=+*/%\-]|\b(?:BETWEEN|CASE|AND|OR|NOT)\b", code, re.IGNORECASE))
    computation = computation or any(re.search(r"\b" + name + r"\s*\(", code, re.IGNORECASE) for name in _PURE_FUNCTIONS)
    return {"queries": 1, "parameters": len(parameters), "named_results": len(aliases),
            "qualifying_queries": int(bool(parameters and aliases and computation)),
            "fields": len(aliases), "initialized_fields": len(aliases)}
