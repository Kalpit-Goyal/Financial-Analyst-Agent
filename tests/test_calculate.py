import pytest

import mcp_server.financial_tools as ft


@pytest.mark.parametrize("expr,expected", [
    ("1 + 2 * 3", 7),
    ("(394.3 - 365.8) / 365.8 * 100", (394.3 - 365.8) / 365.8 * 100),
    ("-5 + 2", -3),
    ("2 ** 10", 1024),
    ("10 % 4", 2),
])
def test_arithmetic(expr, expected):
    assert ft.safe_eval(expr) == pytest.approx(expected)


@pytest.mark.parametrize("expr", [
    "__import__('os').system('echo hi')",
    "open('/etc/passwd')",
    "().__class__",
    "[1, 2]",
    "x + 1",
    "2 ** 1000",
    "9 ** 9 ** 9",
    "True + 1",
    "1 / 0",
    "1 +",
    "1" * 300,
])
def test_unsafe_or_invalid_expressions_are_rejected(expr):
    result = ft.calculate(expr)
    assert "error" in result and "result" not in result


def test_tool_returns_a_rounded_result():
    assert ft.calculate("1 / 3") == {"expression": "1 / 3", "result": 0.333333}
