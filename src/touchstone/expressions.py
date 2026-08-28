# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Arithmetic over metrics, with no `eval` anywhere in the path.

The idea is ASQI's `metric_expression.py`: parse the formula, walk the tree, refuse any
node that is not on an allowlist. What is different is the last step. ASQI validates the
tree and then hands it to `eval()` with an emptied `__builtins__`, so the allowlist is the
only thing between a score card and the interpreter, and the safety argument is a comment
listing three reasons the call is fine. This module evaluates the tree itself. There is no
call to defend, and the failure mode of a missed node type is a raised error rather than
an executed one.

Score cards are written by analysts and travel between organisations, which is the reason
to care: the file that decides a grade is not always written by the person running it.
"""

import ast
from collections.abc import Callable
from statistics import fmean

from touchstone.errors import ScoreCardError

BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
}

COMPARE: dict[type[ast.cmpop], Callable[[float, float], bool]] = {
    ast.Gt: lambda left, right: left > right,
    ast.GtE: lambda left, right: left >= right,
    ast.Lt: lambda left, right: left < right,
    ast.LtE: lambda left, right: left <= right,
    ast.Eq: lambda left, right: left == right,
    ast.NotEq: lambda left, right: left != right,
}

FUNCTIONS: dict[str, Callable[..., float]] = {
    "min": min,
    "max": max,
    "avg": lambda *args: fmean(args),
    "abs": abs,
    "round": lambda value, digits=0.0: float(round(value, int(digits))),
}
"""No `pow` and no `**`. Neither is needed to weight an average, and both let one line of
a score card occupy the machine for an afternoon."""

ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Compare,
    ast.BoolOp,
    ast.IfExp,
    ast.operator,
    ast.unaryop,
    ast.cmpop,
    ast.boolop,
)
"""The whole grammar of a metric expression. Checked over every node before evaluation
rather than only over the nodes evaluation reaches: `a if a else (yield)` never runs the
`yield`, and a score card containing one is still malformed."""


def names(expression: str) -> set[str]:
    """Every variable the expression reads. Used to check a score card before it runs.

    A called function is not a variable: `min(a, b)` reads two, not three.
    """
    tree = _parse(expression)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    read = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    return read - called


def evaluate(expression: str, values: dict[str, float]) -> float:
    """The value of the expression under `values`. Raises rather than returning a default."""
    result = _evaluate(_parse(expression).body, expression, values)
    if isinstance(result, bool):
        return float(result)
    return result


def _parse(expression: str) -> ast.Expression:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ScoreCardError(f"{expression!r}: {exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ScoreCardError(f"{expression!r}: {_name(node)} is not allowed")
        if isinstance(node, ast.BinOp) and type(node.op) not in BINARY:
            raise ScoreCardError(f"{expression!r}: {_name(node.op)} is not allowed")
        if isinstance(node, ast.Compare) and any(type(op) not in COMPARE for op in node.ops):
            raise ScoreCardError(f"{expression!r}: that comparison is not allowed")
    return tree


def _evaluate(node: ast.expr, expression: str, values: dict[str, float]) -> float | bool:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise ScoreCardError(f"{expression!r}: {node.value!r} is not a number")
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in values:
            known = ", ".join(sorted(values)) or "none"
            raise ScoreCardError(f"{expression!r}: no value for {node.id!r}. Declared: {known}")
        return values[node.id]

    if isinstance(node, ast.BinOp):
        operation = BINARY.get(type(node.op))
        if operation is None:
            raise ScoreCardError(f"{expression!r}: {_name(node.op)} is not allowed")
        left = _number(_evaluate(node.left, expression, values))
        right = _number(_evaluate(node.right, expression, values))
        if isinstance(node.op, ast.Div) and right == 0:
            raise ScoreCardError(f"{expression!r}: division by zero")
        return operation(left, right)

    if isinstance(node, ast.UnaryOp):
        operand = _evaluate(node.operand, expression, values)
        if isinstance(node.op, ast.USub):
            return -_number(operand)
        if isinstance(node.op, ast.UAdd):
            return _number(operand)
        if isinstance(node.op, ast.Not):
            return not operand
        raise ScoreCardError(f"{expression!r}: {_name(node.op)} is not allowed")

    if isinstance(node, ast.Compare):
        left = _number(_evaluate(node.left, expression, values))
        for operator, right_node in zip(node.ops, node.comparators, strict=True):
            comparison = COMPARE.get(type(operator))
            if comparison is None:
                raise ScoreCardError(f"{expression!r}: {_name(operator)} is not allowed")
            right = _number(_evaluate(right_node, expression, values))
            if not comparison(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.BoolOp):
        results = [_evaluate(value, expression, values) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(results)
        return any(results)

    if isinstance(node, ast.IfExp):
        branch = node.body if _evaluate(node.test, expression, values) else node.orelse
        return _evaluate(branch, expression, values)

    if isinstance(node, ast.Call):
        return _call(node, expression, values)

    raise ScoreCardError(f"{expression!r}: {_name(node)} is not allowed here")


def _call(node: ast.Call, expression: str, values: dict[str, float]) -> float:
    if not isinstance(node.func, ast.Name):
        raise ScoreCardError(f"{expression!r}: only plain function names may be called")
    function = FUNCTIONS.get(node.func.id)
    if function is None:
        allowed = ", ".join(sorted(FUNCTIONS))
        raise ScoreCardError(f"{expression!r}: {node.func.id}() is not allowed. Allowed: {allowed}")

    arguments = [_number(_evaluate(argument, expression, values)) for argument in node.args]
    if not arguments:
        raise ScoreCardError(f"{expression!r}: {node.func.id}() needs at least one argument")
    try:
        return float(function(*arguments))
    except TypeError as exc:
        raise ScoreCardError(
            f"{expression!r}: {node.func.id}() does not take {len(arguments)} argument(s)"
        ) from exc


def _number(value: float | bool) -> float:
    return float(value)


def _name(node: ast.AST) -> str:
    return type(node).__name__
