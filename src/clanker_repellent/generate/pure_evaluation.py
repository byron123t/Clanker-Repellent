"""Bounded interpretation of integer helpers; never eval, exec, import, or native execution.

This deliberately limited interpreter supports contract examples, not arbitrary Python.
Unsupported syntax, excessive work, and oversized values fail closed.
"""
import ast
import operator

_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
_COMPARE = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
            ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}
_ALLOWED = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If,
            ast.Assign, ast.AugAssign, ast.Name, ast.Load, ast.Store, ast.Constant,
            ast.Expr, ast.Pass, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.BinOp,
            ast.UnaryOp, ast.Not, ast.UAdd, ast.USub, ast.IfExp, ast.While,
            ast.Break, ast.Continue, ast.Tuple, ast.Call, *_BINARY, *_COMPARE)


class IntegerProgram:
    """Parse once and interpret bounded integer/bool examples without running Python code."""

    def __init__(self, source, name, parameters=None):
        if not isinstance(source, str) or len(source.encode('utf-8')) > 65536:
            raise ValueError('Integer helper source exceeds the 64 KiB limit.')
        try:
            tree = ast.parse(source)
        except (SyntaxError, RecursionError):
            raise ValueError('Use valid Python in the bounded integer helper subset.') from None
        nodes = list(ast.walk(tree))
        if len(nodes) > 2000 or any(not isinstance(node, _ALLOWED) for node in nodes):
            raise ValueError('Unsupported syntax in bounded integer helper.')
        functions = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                functions.append(node)
            elif not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                      and isinstance(node.value.value, str)):
                raise ValueError('Only the requested helper and documentation are allowed at top level.')
        if len(functions) != 1 or functions[0].name != name:
            raise ValueError('Define exactly the requested helper: ' + name)
        self.function = functions[0]
        args = self.function.args
        if (self.function.decorator_list or args.defaults or args.kw_defaults or args.vararg
                or args.kwarg or args.kwonlyargs or any(isinstance(node, ast.FunctionDef)
                                                      and node is not self.function for node in nodes)):
            raise ValueError('Decorators, nested helpers, defaults, and variable arguments are unsupported.')
        self.names = [arg.arg for arg in args.posonlyargs + args.args]
        if len(set(self.names)) != len(self.names) or len(self.names) > 16:
            raise ValueError('Use at most 16 distinct integer parameters.')
        if parameters is not None and self.names != parameters:
            raise ValueError('Parameter order/names must be: ' + ', '.join(parameters))
        for node in nodes:
            if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in {'abs', 'min', 'max'}
                    or self.function.name in {'abs', 'min', 'max'} or set(self.names) & {'abs', 'min', 'max'}):
                raise ValueError('Integer intrinsics cannot be shadowed.')
            if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name)
                    or node.func.id not in {'abs', 'min', 'max'} or node.keywords
                    or not 1 <= len(node.args) <= 16):
                raise ValueError('Only bounded abs/min/max integer intrinsics are supported.')

    def evaluate(self, arguments, *, max_steps=20000):
        try:
            return self._evaluate(arguments, max_steps)
        except (TypeError, KeyError, RecursionError, ArithmeticError):
            raise ValueError('Undefined integer computation in contract example.') from None

    def _evaluate(self, arguments, max_steps):
        if type(max_steps) is not int or not 1 <= max_steps <= 100000:
            raise ValueError('Step budget must be between 1 and 100000.')
        if (len(arguments) != len(self.names) or any(type(v) not in {int, bool}
                or abs(v) > 2 ** 63 for v in arguments)):
            raise ValueError('Expected bounded integer/bool arguments matching the helper signature.')
        values = dict(zip(self.names, arguments))
        budget = [max_steps]

        def step():
            budget[0] -= 1
            if budget[0] < 0:
                raise ValueError('Integer helper exceeded the deterministic step budget.')

        def bounded(value):
            if type(value) not in {int, bool} or abs(value) > 2 ** 127:
                raise ValueError('Integer helper exceeded the value bound.')
            return value

        def expression(node):
            step()
            if isinstance(node, ast.Constant) and type(node.value) in {int, bool}:
                result = node.value
            elif isinstance(node, ast.Name):
                result = values[node.id]
            elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
                result = _BINARY[type(node.op)](expression(node.left), expression(node.right))
            elif isinstance(node, ast.UnaryOp):
                value = expression(node.operand)
                result = not value if isinstance(node.op, ast.Not) else -value if isinstance(node.op, ast.USub) else +value
            elif isinstance(node, ast.BoolOp):
                result = expression(node.values[0])
                for value in node.values[1:]:
                    if isinstance(node.op, ast.And) and not result or isinstance(node.op, ast.Or) and result:
                        break
                    result = expression(value)
            elif isinstance(node, ast.Compare):
                previous, result = expression(node.left), True
                for operation, comparator in zip(node.ops, node.comparators):
                    current = expression(comparator)
                    if not _COMPARE[type(operation)](previous, current):
                        result = False
                        break
                    previous = current
            elif isinstance(node, ast.IfExp):
                result = expression(node.body if expression(node.test) else node.orelse)
            elif isinstance(node, ast.Call):
                args = [expression(arg) for arg in node.args]
                if node.func.id in values:
                    raise ValueError('Integer intrinsics cannot be shadowed.')
                if node.func.id == 'abs':
                    if len(args) != 1:
                        raise ValueError('abs requires one argument.')
                    result = abs(args[0])
                else:
                    if len(args) < 2:
                        raise ValueError('min/max require two or more integer arguments.')
                    result = (min if node.func.id == 'min' else max)(args)
            else:
                raise ValueError('Unsupported integer expression.')
            return bounded(result)

        def assign(target, value):
            if isinstance(target, ast.Name) and type(value) in {int, bool}:
                values[target.id] = bounded(value)
            elif isinstance(target, ast.Tuple) and isinstance(value, tuple) and len(target.elts) == len(value):
                for child, item in zip(target.elts, value):
                    assign(child, item)
            else:
                raise ValueError('Use scalar locals or flat tuple unpacking.')

        def statements(body):
            for node in body:
                step()
                if isinstance(node, ast.Return):
                    return 'return', expression(node.value)
                if isinstance(node, ast.If):
                    signal, value = statements(node.body if expression(node.test) else node.orelse)
                    if signal:
                        return signal, value
                elif isinstance(node, ast.While):
                    broke = False
                    while expression(node.test):
                        signal, value = statements(node.body)
                        if signal == 'return':
                            return signal, value
                        if signal == 'break':
                            broke = True
                            break
                    if not broke:
                        signal, value = statements(node.orelse)
                        if signal:
                            return signal, value
                elif isinstance(node, ast.Assign):
                    if isinstance(node.value, ast.Tuple):
                        if len(node.value.elts) > 16:
                            raise ValueError('Tuple unpacking is limited to 16 scalar values.')
                        value = tuple(expression(item) for item in node.value.elts)
                    else:
                        value = expression(node.value)
                    for target in node.targets:
                        assign(target, value)
                elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                    assign(node.target, bounded(_BINARY[type(node.op)](values[node.target.id], expression(node.value))))
                elif isinstance(node, ast.Break):
                    return 'break', None
                elif isinstance(node, ast.Continue):
                    return 'continue', None
                elif isinstance(node, ast.Pass) or (isinstance(node, ast.Expr)
                        and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                    pass
                else:
                    raise ValueError('Unsupported integer statement.')
            return None, None

        signal, result = statements(self.function.body)
        if signal != 'return' or type(result) not in {int, bool}:
            raise ValueError('Helper must return an integer or boolean.')
        return result


def evaluate_predicate(source, name, arguments):
    """Compatibility wrapper: require a Boolean result, never truthy integers."""
    result = IntegerProgram(source, name).evaluate(arguments)
    if type(result) is not bool:
        raise ValueError('Python behavior check requires a Boolean predicate result.')
    return result
