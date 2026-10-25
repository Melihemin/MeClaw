import pytest

from meclaw.tools.registry import ToolRegistry
from tools.finder.explorer_class import Explorer


@pytest.fixture
def registry(tmp_path):
    return ToolRegistry(Explorer(base_dir=str(tmp_path)))


def test_definitions_cover_all_tools(registry):
    names = {d["function"]["name"] for d in registry.definitions()}
    assert len(names) == 16 and names == registry.names()


def test_run_known_tool(registry, tmp_path):
    assert registry.run("create_file_tool", {"filename": "a.txt"}) == "File 'a.txt' created successfully."
    assert (tmp_path / "a.txt").exists()


def test_run_unknown_tool(registry):
    assert registry.run("nope", {}) == "Unknown tool: nope"


def test_run_bad_arguments(registry):
    assert registry.run("create_file_tool", {"wrong": 1}).startswith("Invalid arguments for create_file_tool")


def test_none_arguments_treated_as_empty(registry):
    assert registry.run("list_items_tool", None) == "No items found."


def test_list_items_is_readable(registry):
    registry.run("create_folder_tool", {"folder_name": "docs"})
    registry.run("create_file_tool", {"filename": "a.txt"})
    out = registry.run("list_items_tool", {})
    assert out.startswith("Workspace contents:") and "📁 docs" in out and "📄 a.txt" in out


def test_long_result_truncated(registry, tmp_path):
    (tmp_path / "big.txt").write_text("a" * 50000, encoding="utf-8")
    out = registry.run("read_file_tool", {"filename": "big.txt"})
    assert out == "a" * 20000 + chr(10) + "…(truncated)"
