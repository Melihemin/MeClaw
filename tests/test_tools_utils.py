import asyncio
import math
from datetime import datetime, timedelta, timezone

import pytest

from meclaw.tools.utils import format_datetime, safe_eval
from tests.fakes import make_registry


def runner(tmp_path):
    reg = make_registry(tmp_path)
    return lambda name, **a: asyncio.run(reg.run(name, a))


def test_format_datetime():
    dt = datetime(2026, 10, 25, 21, 40, tzinfo=timezone(timedelta(hours=3)))
    assert format_datetime(dt) == "2026-10-25 21:40, Pazar (25 Ekim 2026), UTC+03:00"


def test_format_datetime_negative_half_hour_offset():
    dt = datetime(2026, 1, 5, 9, 5, tzinfo=timezone(timedelta(hours=-5, minutes=-30)))
    assert format_datetime(dt) == "2026-01-05 09:05, Pazartesi (5 Ocak 2026), UTC-05:30"


def test_get_datetime_tool(tmp_path):
    out = runner(tmp_path)("get_datetime")
    assert "UTC" in out and "(" in out


@pytest.mark.parametrize("expr,value", [
    ("1234*5678", 7006652), ("2**10", 1024), ("(1+2)*3/4", 2.25), ("sqrt(16)+pi", 4 + math.pi),
    ("max(3, 7, 2)", 7), ("round(2.567, 2)", 2.57), ("-5 % 3", 1), ("7 // 2", 3),
    ("2**1000", 2**1000), ("-e", -math.e),
])
def test_calculate_ok(expr, value):
    assert safe_eval(expr) == pytest.approx(value)


@pytest.mark.parametrize("expr", [
    "__import__('os')", "().__class__", "open('x')", "a", "2**10001", "lambda: 1", "[1, 2]",
    "1 if 1 else 2", "True", "'a'", "1j", "2**-1001", "10000000**101", "sqrt(x=4)", "math.sqrt(4)",
    "abs(*[1])", "1 < 2",
])
def test_safe_eval_rejects(expr):
    with pytest.raises(ValueError, match="Unsupported expression"):
        safe_eval(expr)


@pytest.mark.parametrize("expr", ["__import__('os')", "a", "2**10001", "[1, 2]"])
def test_calculate_tool_rejects(tmp_path, expr):
    assert runner(tmp_path)("calculate", expression=expr) == "Unsupported expression"


def test_calculate_too_long(tmp_path):
    assert runner(tmp_path)("calculate", expression="1" * 201) == "Expression too long (max 200 characters)."


def test_calculate_tool_output(tmp_path):
    run = runner(tmp_path)
    assert run("calculate", expression="1234*5678") == "1234*5678 = 7006652"
    assert run("calculate", expression="1/0") == "Error: division by zero"
    assert run("calculate", expression="4/2") == "4/2 = 2"
    assert run("calculate", expression="1/3") == "1/3 = 0.333333333333"
    assert run("calculate", expression="sqrt(-1)").startswith("Error: ")
    assert run("calculate", expression="5 % 0") == "Error: division by zero"
