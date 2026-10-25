import pytest
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


def test_search_by_name_and_content(tmp_path):
    (tmp_path / "notlar").mkdir()
    (tmp_path / "notlar" / "fatura.md").write_text("Ekim faturası ğüş\nikinci satır", encoding="utf-8")
    (tmp_path / "a.txt").write_text("FATURA no 5", encoding="utf-8")
    (tmp_path / "resim.bin").write_bytes(b"\xff\xfe fatura \x00\x80")
    run = runner(tmp_path)
    assert "notlar/fatura.md" in run("search_files", name_pattern="*.MD")
    out = run("search_files", query="fatura")
    assert "notlar/fatura.md:1: Ekim faturası ğüş" in out and "a.txt:1: FATURA no 5" in out and "resim.bin" not in out
    assert out.index("a.txt") < out.index("notlar/fatura.md")
    assert "a.txt" not in run("search_files", query="fatura", name_pattern="*.md")
    assert run("search_files") == "Provide query or name_pattern."
    assert run("search_files", query="yokyok") == "No matches."
    assert run("search_files", name_pattern="*.md", path="..") == "Path is outside the workspace."


def test_search_files_result_limit(tmp_path):
    for i in range(60):
        (tmp_path / f"f{i:02}.txt").write_text("eşleşme", encoding="utf-8")
    out = runner(tmp_path)("search_files", query="eşleşme")
    assert out.count("\n") + 1 == 51 and out.endswith("(results limited to 50)")


def test_search_skips_large_files(tmp_path):
    (tmp_path / "big.txt").write_text("iğne " + "a" * 1_000_000, encoding="utf-8")
    assert "No matches." == runner(tmp_path)("search_files", query="iğne")


def test_edit_file_replace(tmp_path):
    (tmp_path / "f.txt").write_bytes(b"a\r\nb\r\nc\r\n")
    (tmp_path / "g.txt").write_text("x x", encoding="utf-8")
    run = runner(tmp_path)
    assert run("edit_file", filename="f.txt", old_text="b", new_text="B") == "Edited 'f.txt'."
    assert (tmp_path / "f.txt").read_bytes() == b"a\r\nB\r\nc\r\n"
    assert run("edit_file", filename="f.txt", old_text="zzz", new_text="x") == "Text not found in 'f.txt'."
    assert (
        run("edit_file", filename="g.txt", old_text="x", new_text="y")
        == "Text occurs 2 times in 'g.txt'; give a longer, unique snippet."
    )
    assert run("edit_file", filename="yok.txt", old_text="a", new_text="b") == "File 'yok.txt' not found."


def test_edit_file_append(tmp_path):
    (tmp_path / "f.txt").write_text("son", encoding="utf-8")
    runner(tmp_path)("edit_file", filename="f.txt", new_text="yeni", mode="append")
    assert (tmp_path / "f.txt").read_text() == "son\nyeni"


def test_file_info(tmp_path):
    (tmp_path / "f.txt").write_text("a\nb\nc\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x").write_text("")
    run = runner(tmp_path)
    out = run("file_info", path="f.txt")
    assert "Type: file" in out and "Size: " in out and "Lines: 3" in out and "Modified: " in out
    assert "Type: folder" in run("file_info", path="sub") and "Items: 1" in run("file_info", path="sub")
    assert run("file_info", path="nope") == "'nope' not found."


def _mk(root, spec):
    for p in (spec or "").split(","):
        if not p:
            continue
        if p.endswith("/"):
            (root / p).mkdir(parents=True, exist_ok=True)
        else:
            (root / p).parent.mkdir(parents=True, exist_ok=True)
            (root / p).write_text("x")


@pytest.mark.parametrize("name,args,setup,expected", [
    ("delete_file", {"filename": "a.txt"}, "a.txt", "‘a.txt’ silinecek."),
    ("delete_file", {"filename": "yok.txt"}, None, None),
    ("remove_folder", {"folder_name": "sub"}, "sub/", "‘sub’ klasörü silinecek."),
    ("edit_file", {"filename": "a.txt", "old_text": "x", "new_text": "y"}, "a.txt", "‘a.txt’ düzenlenecek."),
    ("edit_file", {"filename": "yok.txt", "old_text": "x", "new_text": "y"}, None, None),
    ("write_file", {"filename": "a.txt", "content": "z"}, "a.txt", "‘a.txt’ üzerine yazılacak."),
    ("write_file", {"filename": "yeni.txt", "content": "z"}, None, None),
    ("write_word_file", {"filename": "r.docx", "content": "z"}, "r.docx", "‘r.docx’ üzerine yazılacak."),
    ("copy_file", {"source_filename": "a.txt", "destination_filename": "b.txt"}, "a.txt,b.txt", "‘b.txt’ üzerine yazılacak (‘a.txt’ kopyalanıyor)."),
    ("copy_file", {"source_filename": "a.txt", "destination_filename": "c.txt"}, "a.txt", None),
    ("move_item", {"source_path": "a.txt", "destination_path": "b.txt"}, "a.txt,b.txt", "‘b.txt’ üzerine yazılacak (‘a.txt’ taşınıyor)."),
    ("rename_file", {"old_filename": "a.txt", "new_filename": "b.txt"}, "a.txt,b.txt", "‘b.txt’ üzerine yazılacak (‘a.txt’ yeniden adlandırılıyor)."),
    ("rename_folder", {"old_folder_name": "sub", "new_folder_name": "sub2"}, "sub/,sub2/", "‘sub2’ üzerine yazılacak (‘sub’ yeniden adlandırılıyor)."),
    ("copy_folder", {"source_folder_name": "sub", "destination_folder_name": "sub2"}, "sub/,sub2/", "‘sub2’ üzerine yazılacak (‘sub’ kopyalanıyor)."),
    ("zip_folder", {"folder_name": "sub"}, "sub/,sub.zip", "‘sub.zip’ üzerine yazılacak."),
    ("extract_archive", {"archive_name": "a.zip", "destination_folder": "out"}, "a.zip,out/x.txt", "‘out’ klasörüne açılacak; aynı adlı dosyalar değişebilir."),
    ("extract_archive", {"archive_name": "a.zip", "destination_folder": "bos"}, "a.zip,bos/", None),
    ("create_file", {"filename": "a.txt"}, "a.txt", None),
])
def test_confirmation_rules(tmp_path, name, args, setup, expected):
    _mk(tmp_path, setup)
    c = make_registry(tmp_path).needs_confirmation(name, args)
    assert (c.description if c else None) == expected


def test_edit_confirmation_preview(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    reg = make_registry(tmp_path)
    c = reg.needs_confirmation("edit_file", {"filename": "a.txt", "old_text": "eski", "new_text": "yeni"})
    assert c.preview == "- eski\n+ yeni"
    c1 = reg.needs_confirmation("edit_file", {"filename": "a.txt", "old_text": "o" * 500, "new_text": "n"})
    assert c1.preview == "- " + "o" * 280 + "\n+ n"
    c3 = reg.needs_confirmation("edit_file", {"filename": "a.txt", "new_text": "yeni", "mode": "append"})
    assert c3.preview == "+ yeni"
    c2 = reg.needs_confirmation("write_file", {"filename": "a.txt", "content": "y" * 1000})
    assert c2.preview == "y" * 600
    assert reg.needs_confirmation("delete_file", {"filename": "a.txt"}).preview == ""
