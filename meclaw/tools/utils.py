"""Utility tools: current date/time and a safe calculator."""
from __future__ import annotations

import ast
import math
import operator
from datetime import datetime

from meclaw.tools.base import ToolContext, ToolSpec

MAX_EXPRESSION_CHARS = 200
MAX_EXPONENT = 1000
MAX_RESULT_BITS = 10_000
MAX_ROUND_DIGITS = 400

_WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_NAMES = {"pi": math.pi, "e": math.e}
_FUNCTIONS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil,
    "log": math.log, "log10": math.log10, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "min": min, "max": max,
}


class _Unsupported(ValueError):
    def __init__(self):
        super().__init__("Unsupported expression")


def format_datetime(dt: datetime) -> str:
    offset = dt.utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    sign = "+" if minutes >= 0 else "-"
    hours, mins = divmod(abs(minutes), 60)
    return (
        f"{dt:%Y-%m-%d %H:%M}, {_WEEKDAYS[dt.weekday()]} "
        f"({dt.day} {_MONTHS[dt.month - 1]} {dt.year}), UTC{sign}{hours:02d}:{mins:02d}"
    )


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _eval(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if _is_number(node.value):
            return node.value
        raise _Unsupported()
    if isinstance(node, ast.Name):
        if node.id in _NAMES:
            return _NAMES[node.id]
        raise _Unsupported()
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise _Unsupported()
        return op(_eval(node.operand))
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise _Unsupported()
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow):
            if not _is_number(right) or abs(right) > MAX_EXPONENT:
                raise _Unsupported()
            if _is_int(left) and _is_int(right) and right > 0 and abs(left).bit_length() * right > MAX_RESULT_BITS:
                raise _Unsupported()
        elif isinstance(node.op, ast.Mult):
            if _is_int(left) and _is_int(right) and abs(left).bit_length() + abs(right).bit_length() > MAX_RESULT_BITS:
                raise _Unsupported()
        return op(left, right)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS or node.keywords:
            raise _Unsupported()
        if any(isinstance(a, ast.Starred) for a in node.args):
            raise _Unsupported()
        args = [_eval(a) for a in node.args]
        if node.func.id == "round" and len(args) == 2 and (not _is_int(args[1]) or abs(args[1]) > MAX_ROUND_DIGITS):
            raise _Unsupported()
        try:
            return _FUNCTIONS[node.func.id](*args)
        except TypeError:
            raise _Unsupported() from None
    raise _Unsupported()


def safe_eval(expression: str) -> int | float:
    """Evaluate an arithmetic expression by walking its AST; never uses eval/exec."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise _Unsupported() from None
    try:
        result = _eval(tree)
    except RecursionError:
        raise _Unsupported() from None
    if not _is_number(result):
        raise _Unsupported()
    return result


def _format_number(value: int | float) -> str:
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return format(value, ".12g")
    return str(value)


def get_datetime(ctx: ToolContext) -> str:
    return format_datetime(datetime.now().astimezone())


def calculate(ctx: ToolContext, expression: str) -> str:
    if len(expression) > MAX_EXPRESSION_CHARS:
        return f"Expression too long (max {MAX_EXPRESSION_CHARS} characters)."
    try:
        value = safe_eval(expression)
    except _Unsupported:
        return "Unsupported expression"
    except ZeroDivisionError:
        return "Error: division by zero"
    except (ArithmeticError, ValueError) as exc:
        return f"Error: {exc}"
    if isinstance(value, float) and not math.isfinite(value):
        return "Error: result is not finite"
    try:
        text = _format_number(value)
    except ValueError:
        return "Error: result too large"
    return f"{expression} = {text}"


UTIL_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "get_datetime",
        "Get the current local date, time, weekday and UTC offset.",
        {"type": "object", "properties": {}},
        get_datetime,
    ),
    ToolSpec(
        "calculate",
        "Evaluate an arithmetic expression (+ - * / // % **, parentheses, pi, e, and sqrt, abs, round, "
        "floor, ceil, log, log10, sin, cos, tan, min, max). Max 200 characters.",
        {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "e.g. '(1+2)*3/4' or 'sqrt(16)+pi'."}},
            "required": ["expression"],
        },
        calculate,
    ),
]
