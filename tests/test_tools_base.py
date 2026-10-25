import asyncio

from meclaw.tools.base import ToolContext, ToolRegistry, ToolSpec
from tests.fakes import make_registry
from tools.finder.explorer_class import Explorer

EMPTY = {"type": "object", "properties": {}}


def test_definitions_shape_and_names(tmp_path):
    reg = make_registry(tmp_path)
    names = {d["function"]["name"] for d in reg.definitions()}
    assert names == reg.names() and {"create_file", "list_items", "read_file"} <= names
    assert len(names) == 26
    assert all(not n.endswith("_tool") for n in names)
    assert all(d["type"] == "function" and d["function"]["parameters"]["type"] == "object" for d in reg.definitions())


def test_unknown_and_bad_args(tmp_path):
    reg = make_registry(tmp_path)
    assert asyncio.run(reg.run("nope", {})) == "Unknown tool: nope"
    assert asyncio.run(reg.run("create_file", {"wrong": 1})).startswith("Invalid arguments for create_file")


def test_none_arguments_treated_as_empty(tmp_path):
    assert asyncio.run(make_registry(tmp_path).run("list_items", None)) == "No items found."


def test_sync_and_async_handlers_and_failure(tmp_path):
    async def ahandler(ctx, x):
        return f"async {x}"

    def boom(ctx):
        raise RuntimeError("kaboom")

    reg = ToolRegistry(ToolContext(Explorer(tmp_path)), [
        ToolSpec("a", "", EMPTY, ahandler),
        ToolSpec("b", "", EMPTY, boom),
    ])
    assert asyncio.run(reg.run("a", {"x": 1})) == "async 1"
    assert asyncio.run(reg.run("b", None)) == "Tool b failed: kaboom"


def test_result_truncated(tmp_path):
    reg = ToolRegistry(ToolContext(Explorer(tmp_path)), [ToolSpec("big", "", EMPTY, lambda ctx: "x" * 20001)])
    assert asyncio.run(reg.run("big", {})) == "x" * 20000 + "\n…(truncated)"


def test_needs_confirmation_fails_closed(tmp_path):
    def bad(ctx, args):
        raise ValueError("x")

    reg = ToolRegistry(ToolContext(Explorer(tmp_path)), [
        ToolSpec("t", "", EMPTY, lambda ctx: "ok", confirm=bad),
        ToolSpec("u", "", EMPTY, lambda ctx: "ok"),
    ])
    conf = reg.needs_confirmation("t", {})
    assert conf is not None and "‘t’" in conf.description
    assert reg.needs_confirmation("u", {}) is None
    assert reg.needs_confirmation("nope", {}) is None


def test_coercion_helpers():
    from meclaw.tools.base import as_bool, as_int

    assert as_bool(None, True) is True and as_bool("false", True) is False and as_bool("0", True) is False
    assert as_bool("True", False) is True and as_bool("1", False) is True and as_bool(True, False) is True
    assert as_int(None, 5) == 5 and as_int("7", 5) == 7 and as_int(3, 5) == 3 and as_int("x", 5) == 5
