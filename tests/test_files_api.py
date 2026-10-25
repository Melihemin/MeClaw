from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meclaw.storage import Storage
from meclaw.tools.registry import ToolRegistry
from server import create_app
from tests.fakes import FakeProvider
from tools.finder.explorer_class import Explorer

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
LOCAL = {"X-MeClaw": "1"}


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "notlar.txt").write_text("merhaba ğüşıöç", encoding="utf-8")
    (root / "alt").mkdir()
    (root / "alt" / "ic.md").write_text("# başlık", encoding="utf-8")
    (root / "resim.png").write_bytes(PNG)
    (root / "veri.bin").write_bytes(b"\x00\x01\x02" * 10)
    (root / "buyuk.txt").write_text("x" * 200_001, encoding="utf-8")
    Explorer(base_dir=str(root)).write_word_file("belge.docx", "Word içeriği")
    return root


@pytest.fixture
def opened():
    return []


@pytest.fixture
def client(tmp_path, ws, opened):
    app = create_app(
        {"fake": FakeProvider()},
        ToolRegistry(Explorer(base_dir=str(ws))),
        Storage(tmp_path / "t.db"),
        open_folder=opened.append,
    )
    return TestClient(app, base_url="http://127.0.0.1")


def test_list_root_dirs_first(client):
    r = client.get("/api/files")
    assert r.status_code == 200
    data = r.json()
    assert data["path"] == ""
    names = [e["name"] for e in data["entries"]]
    assert names[0] == "alt"
    assert set(names) == {"alt", "belge.docx", "buyuk.txt", "notlar.txt", "resim.png", "veri.bin"}
    alt = data["entries"][0]
    assert alt["type"] == "dir" and alt["path"] == "alt"
    notes = next(e for e in data["entries"] if e["name"] == "notlar.txt")
    assert notes["type"] == "file" and notes["size"] == len("merhaba ğüşıöç".encode()) and notes["modified"]


def test_list_subfolder(client):
    data = client.get("/api/files", params={"path": "alt"}).json()
    assert data["path"] == "alt"
    assert data["entries"][0]["path"] == "alt/ic.md"


@pytest.mark.parametrize("path", ["..", "../..", "alt/../../x"])
def test_list_outside_rejected(client, path):
    assert client.get("/api/files", params={"path": path}).status_code == 400


def test_list_missing_404_and_file_400(client):
    assert client.get("/api/files", params={"path": "yok"}).status_code == 404
    assert client.get("/api/files", params={"path": "notlar.txt"}).status_code == 400


@pytest.mark.parametrize("path,kind", [
    ("notlar.txt", "text"),
    ("alt/ic.md", "text"),
    ("belge.docx", "docx"),
    ("resim.png", "image"),
    ("veri.bin", "binary"),
    ("buyuk.txt", "too_large"),
])
def test_preview_kinds(client, path, kind):
    data = client.get("/api/files/preview", params={"path": path}).json()
    assert data["kind"] == kind and data["name"] == Path(path).name


def test_preview_content(client):
    assert client.get("/api/files/preview", params={"path": "notlar.txt"}).json()["content"] == "merhaba ğüşıöç"
    assert client.get("/api/files/preview", params={"path": "belge.docx"}).json()["content"] == "Word içeriği"


def test_preview_outside_rejected(client):
    assert client.get("/api/files/preview", params={"path": "../t.db"}).status_code == 400


def test_download(client):
    r = client.get("/api/files/download", params={"path": "notlar.txt"})
    assert r.status_code == 200 and r.content == "merhaba ğüşıöç".encode()
    assert r.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in r.headers["content-security-policy"]
    inline = client.get("/api/files/download", params={"path": "resim.png", "inline": "1"})
    assert inline.headers["content-disposition"].startswith("inline") and inline.content == PNG


def test_download_folder_400(client):
    assert client.get("/api/files/download", params={"path": "alt"}).status_code == 400


def test_upload_and_no_overwrite(client, ws):
    r = client.post("/api/files/upload", params={"path": "alt", "name": "yeni.txt"}, content=b"bir", headers=LOCAL)
    assert r.status_code == 200 and r.json()["path"] == "alt/yeni.txt"
    r2 = client.post("/api/files/upload", params={"path": "alt", "name": "yeni.txt"}, content=b"iki", headers=LOCAL)
    assert r2.json()["path"] == "alt/yeni (1).txt"
    assert (ws / "alt" / "yeni.txt").read_bytes() == b"bir"
    assert (ws / "alt" / "yeni (1).txt").read_bytes() == b"iki"


@pytest.mark.parametrize("name,expected", [("../kacis.txt", "kacis.txt"), ("a:b?.txt", "a_b_.txt")])
def test_upload_name_sanitized(client, ws, name, expected):
    r = client.post("/api/files/upload", params={"path": "", "name": name}, content=b"x", headers=LOCAL)
    assert r.json()["path"] == expected and (ws / expected).exists()


@pytest.mark.parametrize("name", ["", "..", "."])
def test_upload_bad_name_400(client, name):
    r = client.post("/api/files/upload", params={"path": "", "name": name}, content=b"x", headers=LOCAL)
    assert r.status_code == 400


def test_upload_requires_local_header(client, ws):
    r = client.post("/api/files/upload", params={"path": "", "name": "x.txt"}, content=b"x")
    assert r.status_code == 403 and not (ws / "x.txt").exists()


def test_upload_rejects_foreign_origin(client, ws):
    headers = {**LOCAL, "Origin": "http://evil.example.com"}
    r = client.post("/api/files/upload", params={"path": "", "name": "x.txt"}, content=b"x", headers=headers)
    assert r.status_code == 403 and not (ws / "x.txt").exists()


def test_upload_same_origin_ok(client):
    headers = {**LOCAL, "Origin": "http://127.0.0.1:8000"}
    r = client.post("/api/files/upload", params={"path": "", "name": "x.txt"}, content=b"x", headers=headers)
    assert r.status_code == 200


def test_upload_outside_rejected(client):
    r = client.post("/api/files/upload", params={"path": "..", "name": "x.txt"}, content=b"x", headers=LOCAL)
    assert r.status_code == 400


def test_upload_too_large(client, monkeypatch):
    monkeypatch.setattr("server.MAX_UPLOAD_BYTES", 10)
    r = client.post("/api/files/upload", params={"path": "", "name": "x.txt"}, content=b"x" * 11, headers=LOCAL)
    assert r.status_code == 413


def test_open_folder(client, ws, opened):
    assert client.post("/api/workspace/open", params={"path": "alt"}, headers=LOCAL).status_code == 204
    assert opened == [ws / "alt"]
    assert client.post("/api/workspace/open", headers=LOCAL).status_code == 204
    assert opened[-1] == ws


def test_open_folder_guarded(client, opened):
    assert client.post("/api/workspace/open").status_code == 403
    assert client.post("/api/workspace/open", params={"path": ".."}, headers=LOCAL).status_code == 400
    assert opened == []
