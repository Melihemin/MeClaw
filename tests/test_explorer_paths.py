import pytest

from tools.finder.explorer_class import Explorer

OUTSIDE = "Path is outside the workspace."


@pytest.fixture
def explorer(tmp_path):
    return Explorer(base_dir=str(tmp_path / "ws"))


def test_rejects_parent_traversal(explorer, tmp_path):
    assert explorer.create_file("../escape.txt") == OUTSIDE
    assert not (tmp_path / "escape.txt").exists()
    assert explorer.read_file("../../etc/passwd") == OUTSIDE


def test_rejects_absolute_path(explorer, tmp_path):
    assert explorer.write_file(str(tmp_path / "abs.txt"), "x") == OUTSIDE
    assert not (tmp_path / "abs.txt").exists()


def test_rejects_traversal_in_second_argument(explorer):
    explorer.create_file("a.txt")
    assert explorer.copy_file("a.txt", "../b.txt") == OUTSIDE
    assert explorer.move_item("a.txt", "../moved.txt") == OUTSIDE
    assert explorer.extract_archive("x.zip", "../out") == OUTSIDE


def test_allows_nested_paths(explorer, tmp_path):
    explorer.create_folder("sub")
    assert explorer.create_file("sub/a.txt") == "File 'sub/a.txt' created successfully."
    assert (tmp_path / "ws" / "sub" / "a.txt").exists()
