"""Bounded interpretation of a small Python arithmetic/predicate subset.

No generated code is passed to eval/exec, imported, or invoked. Unsupported AST
forms fail closed. This helper supports independent behavioral fixtures, not
arbitrary Python execution or a proof of correctness.
"""

import ast
import operator


_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
_COMPARE = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
            ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}
_ALLOWED = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If,
            ast.Assign, ast.Name, ast.Load, ast.Store, ast.Constant, ast.Expr, ast.Pass,
            ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.BinOp, ast.UnaryOp,
            ast.Not, ast.UAdd, ast.USub, *_BINARY, *_COMPARE)


def evaluate_predicate(source, name, arguments):
    """Interpret one numeric predicate; return a boolean or a fixed error."""
    try:
        return _evaluate(source, name, arguments)
    except (ValueError, TypeError, KeyError, SyntaxError, RecursionError, ArithmeticError):
        raise ValueError("Python behavior check requires the supported pure predicate subset.") from None


def _evaluate(source, name, arguments):
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    if len(nodes) > 2000 or any(not isinstance(node, _ALLOWED) for node in nodes):
        raise ValueError()
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) or isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            raise ValueError()
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(functions) != 1:
        raise ValueError()
    function = functions[0]
    args = function.args
    if function.decorator_list or args.defaults or args.kw_defaults or args.vararg or args.kwarg or args.kwonlyargs:
        raise ValueError()
    names = [arg.arg for arg in args.posonlyargs + args.args]
    if len(names) != len(arguments) or len(set(names)) != len(names):
        raise ValueError()
    if any(type(value) not in {int, bool} or abs(value) > 2 ** 63 for value in arguments):
        raise ValueError()
    values = dict(zip(names, arguments))
    steps = 1000

    def expression(node):
        nonlocal steps
        steps -= 1
        if steps < 0:
            raise ValueError()
        if isinstance(node, ast.Constant) and type(node.value) in {int, bool}:
            result = node.value
        elif isinstance(node, ast.Name):
            result = values[node.id]
        elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            result = _BINARY[type(node.op)](expression(node.left), expression(node.right))
        elif isinstance(node, ast.UnaryOp):
            value = expression(node.operand)
            if isinstance(node.op, ast.Not):
                result = not value
            elif isinstance(node.op, ast.USub):
                result = -value
            elif isinstance(node.op, ast.UAdd):
                result = +value
            else:
                raise ValueError()
        elif isinstance(node, ast.BoolOp):
            result = expression(node.values[0])
            for value in node.values[1:]:
                if isinstance(node.op, ast.And) and not result or isinstance(node.op, ast.Or) and result:
                    break
                result = expression(value)
        elif isinstance(node, ast.Compare):
            previous = expression(node.left)
            result = True
            for operation, comparator in zip(node.ops, node.comparators):
                current = expression(comparator)
                if not _COMPARE[type(operation)](previous, current):
                    result = False
                    break
                previous = current
        else:
            raise ValueError()
        if type(result) not in {int, bool} or abs(result) > 2 ** 127:
            raise ValueError()
        return result

    def statements(body):
        nonlocal steps
        for node in body:
            steps -= 1
            if steps < 0:
                raise ValueError()
            if isinstance(node, ast.Return):
                return True, expression(node.value)
            if isinstance(node, ast.If):
                returned, value = statements(node.body if expression(node.test) else node.orelse)
                if returned:
                    return True, value
            elif isinstance(node, ast.Assign) and all(isinstance(target, ast.Name) for target in node.targets):
                value = expression(node.value)
                for target in node.targets:
                    values[target.id] = value
            elif isinstance(node, ast.Pass) or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                                               and isinstance(node.value.value, str)):
                pass
            elif not isinstance(node, ast.If):
                raise ValueError()
        return False, None

    returned, result = statements(function.body)
    if not returned or type(result) is not bool:
        raise ValueError()
    return result
