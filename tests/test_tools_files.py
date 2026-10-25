import asyncio

from tests.fakes import make_registry


def runner(tmp_path):
    reg = make_registry(tmp_path)
    return lambda name, **a: asyncio.run(reg.run(name, a))


def test_list_items_path_and_root(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("b")
    run = runner(tmp_path)
    assert run("list_items").startswith("Workspace contents:") and "📁 sub" in run("list_items")
    assert "📄 b.txt" in run("list_items", path="sub") and "a.txt" not in run("list_items", path="sub")
    assert run("list_items", path="..") == "Path is outside the workspace."


def test_list_items_empty_and_order(tmp_path):
    run = runner(tmp_path)
    assert run("list_items") == "No items found."
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "A.txt").write_text("")
    (tmp_path / "zdir").mkdir()
    assert run("list_items") == "Workspace contents:\n\n📁 zdir\n📄 A.txt\n📄 b.txt"


def test_list_items_recursive(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("b")
    out = runner(tmp_path)("list_items", recursive=True)
    assert "📁 sub" in out and "  📄 b.txt" in out


def test_list_items_recursive_limit(tmp_path):
    for i in range(600):
        (tmp_path / f"f{i:03}.txt").write_text("")
    out = runner(tmp_path)("list_items", recursive=True)
    assert out.count("📄") == 500 and out.rstrip().endswith("… (100 more)")


def test_read_file_range(tmp_path):
    (tmp_path / "f.txt").write_text("l1\nl2\nl3\nl4\n")
    run = runner(tmp_path)
    assert run("read_file", filename="f.txt", start_line=2, end_line=3) == "Lines 2-3 of 4:\nl2\nl3"
    assert run("read_file", filename="f.txt") == "l1\nl2\nl3\nl4\n"
    assert run("read_file", filename="f.txt", start_line=3) == "Lines 3-4 of 4:\nl3\nl4"
    assert run("read_file", filename="f.txt", start_line=2, end_line=99) == "Lines 2-4 of 4:\nl2\nl3\nl4"
    assert run("read_file", filename="f.txt", start_line=0) == "Invalid line range."
    assert run("read_file", filename="f.txt", start_line=5) == "Invalid line range."


def test_ported_tools_behave_as_before(tmp_path):
    run = runner(tmp_path)
    assert run("create_file", filename="x.txt") == "File 'x.txt' created successfully."
    assert run("write_file", filename="x.txt", content="hi").startswith("Content written to 'x.txt'")
    assert run("delete_file", filename="x.txt") == "File 'x.txt' deleted successfully."


def test_long_read_truncated(tmp_path):
    (tmp_path / "big.txt").write_text("a" * 50000, encoding="utf-8")
    assert runner(tmp_path)("read_file", filename="big.txt") == "a" * 20000 + "\n…(truncated)"
