"""The metric expression evaluator, and what it refuses.

The three worked examples in ASQI's `metric_expression.py` docstring are checked here
against our evaluator, because matching their arithmetic is the compatibility claim. What
is not shared is the last step: they validate the tree and then call `eval()`, so their
allowlist is load bearing for safety. This one never calls `eval`, so a node type nobody
thought about raises instead of running.
"""

import pytest

from touchstone.errors import ScoreCardError
from touchstone.expressions import evaluate, names


def test_matches_the_asqi_worked_examples():
    assert evaluate("accuracy", {"accuracy": 0.85}) == 0.85
    assert evaluate("0.7 * a + 0.3 * b", {"a": 0.8, "b": 0.9}) == pytest.approx(0.83)
    assert evaluate("min(x, y, z)", {"x": 0.9, "y": 0.7, "z": 0.8}) == 0.7
    assert evaluate(
        "(0.6 * acc + 0.4 * rel) if (faith >= 0.7 and retr >= 0.6) else -1",
        {"acc": 0.8, "rel": 0.9, "faith": 0.8, "retr": 0.7},
    ) == pytest.approx(0.84)


def test_the_hard_gate_fails_closed():
    """The same expression with a gate that does not open returns the sentinel, not the
    score. A gate that silently passed would be the failure this whole tool exists against."""
    assert (
        evaluate(
            "(0.6 * acc + 0.4 * rel) if (faith >= 0.7 and retr >= 0.6) else -1",
            {"acc": 0.8, "rel": 0.9, "faith": 0.5, "retr": 0.7},
        )
        == -1
    )


def test_names_reports_every_variable_read():
    assert names("0.7 * a + min(b, c)") == {"a", "b", "c"}


@pytest.mark.parametrize(
    "expression",
    [
        '__import__("os").system("ls")',
        'open("/etc/passwd")',
        "().__class__",
        "a.__dict__",
        "[a for a in range(10)]",
        "lambda: 1",
        "a ** b",
        "pow(10, 10000000)",
        "a if a else (yield)",
    ],
)
def test_refuses_anything_that_is_not_arithmetic(expression):
    with pytest.raises(ScoreCardError):
        evaluate(expression, {"a": 1.0, "b": 2.0})


def test_an_undeclared_variable_names_what_was_available():
    with pytest.raises(ScoreCardError, match="no value for 'missing'"):
        evaluate("missing + 1", {"present": 1.0})


def test_division_by_zero_is_an_error_not_an_infinity():
    with pytest.raises(ScoreCardError, match="division by zero"):
        evaluate("a / b", {"a": 1.0, "b": 0.0})


def test_a_string_constant_is_not_a_number():
    with pytest.raises(ScoreCardError, match="not a number"):
        evaluate("'0.9'", {})


def test_no_expression_reaches_a_real_builtin():
    """`round` is on the allowlist and is ours, not the interpreter's, so it cannot be
    reached with the arguments that make the builtin do something else."""
    assert evaluate("round(a, 2)", {"a": 0.8567}) == pytest.approx(0.86)
    with pytest.raises(ScoreCardError, match="keyword is not allowed"):
        evaluate("round(a, ndigits=2)", {"a": 0.8567})
