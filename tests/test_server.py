import pytest

from meclaw.llm.base import ChatEvent, ToolCall
from meclaw.storage import Storage
from server import create_app
from tests.fakes import FakeProvider, make_registry
from tests.helpers import make_client, parse_sse


@pytest.fixture
def store(tmp_path):
    return Storage(tmp_path / "test.db")


@pytest.fixture
def registry(tmp_path):
    return make_registry(tmp_path / "ws")


@pytest.fixture
def client(registry, store):
    return make_client(create_app({"fake": FakeProvider()}, registry, store))


def make_chat(provider, registry, store):
    c = make_client(create_app({"fake": provider}, registry, store))
    cid = c.post("/api/conversations").json()["id"]
    return c, cid


def body(cid, message):
    return {"conversation_id": cid, "provider": "fake", "model": "fake-1", "message": message}


def test_index_served(client):
    assert client.get("/").status_code == 200


def test_providers_never_500(registry, store):
    down = FakeProvider(name="down", ready=False, reason="kapalı")

    class Boom(FakeProvider):
        async def status(self):
            raise RuntimeError("x")

    c = make_client(create_app({"down": down, "boom": Boom(name="boom")}, registry, store))
    r = c.get("/api/providers")
    assert r.status_code == 200
    assert {p["name"]: p["ready"] for p in r.json()} == {"down": False, "boom": False}


def test_models(client):
    assert client.get("/api/models", params={"provider": "fake"}).json() == {"models": ["fake-1"]}


def test_models_provider_failure_503(registry, store):
    p = FakeProvider(models_error=RuntimeError("401 invalid key"))
    r = make_client(create_app({"fake": p}, registry, store)).get("/api/models", params={"provider": "fake"})
    assert r.status_code == 503 and "invalid key" in r.json()["detail"]


def test_models_unknown_provider_404(client):
    assert client.get("/api/models", params={"provider": "x"}).status_code == 404


def test_conversation_crud(client):
    cid = client.post("/api/conversations").json()["id"]
    assert client.get(f"/api/conversations/{cid}").json()["messages"] == []
    assert [c["id"] for c in client.get("/api/conversations").json()] == [cid]
    assert client.delete(f"/api/conversations/{cid}").status_code == 204
    assert client.get(f"/api/conversations/{cid}").status_code == 404
    assert client.delete(f"/api/conversations/{cid}").status_code == 404


def test_chat_streams_and_saves(registry, store, tmp_path):
    p = FakeProvider(turns=[
        [ChatEvent("tool_calls", tool_calls=[ToolCall("1", "create_file", {"filename": "a.txt"})])],
        [ChatEvent("text", "Tamam")],
    ])
    c, cid = make_chat(p, registry, store)
    events = parse_sse(c.post("/api/chat", json=body(cid, "dosya aç")).text)
    assert [e for e, _ in events] == ["tool", "text", "done"]
    assert events[0][1]["name"] == "create_file"
    assert events[0][1]["arguments"] == {"filename": "a.txt"}
    assert events[1][1] == {"text": "Tamam"}
    assert events[2][1] == {"conversation_id": cid}
    conv = c.get(f"/api/conversations/{cid}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "tool", "assistant"]
    assert conv["title"] == "dosya aç" and conv["provider"] == "fake" and conv["model"] == "fake-1"
    assert (tmp_path / "ws" / "a.txt").exists()


def test_chat_streams_turkish(registry, store):
    p = FakeProvider(turns=[[ChatEvent("text", "ğüşıöçİ")]])
    c, cid = make_chat(p, registry, store)
    text = c.post("/api/chat", json=body(cid, "merhaba")).text
    assert "ğüşıöçİ" in text
    assert chr(92) + "u" not in text


def test_chat_title_truncated_to_40(registry, store):
    c, cid = make_chat(FakeProvider(turns=[[ChatEvent("text", "ok")]]), registry, store)
    msg = "abcdefghij" * 6
    c.post("/api/chat", json=body(cid, f"  {msg}  "))
    assert c.get(f"/api/conversations/{cid}").json()["title"] == msg[:40]


def test_chat_title_kept_on_second_message(registry, store):
    c, cid = make_chat(FakeProvider(turns=[[ChatEvent("text", "a")], [ChatEvent("text", "b")]]), registry, store)
    c.post("/api/chat", json=body(cid, "birinci"))
    c.post("/api/chat", json=body(cid, "ikinci"))
    assert c.get(f"/api/conversations/{cid}").json()["title"] == "birinci"


def test_chat_provider_error_mid_stream(registry, store):
    p = FakeProvider(turns=[[ChatEvent("text", "Yarım")]], error=RuntimeError("Ollama kapandı"))
    c, cid = make_chat(p, registry, store)
    events = parse_sse(c.post("/api/chat", json=body(cid, "x")).text)
    assert [e for e, _ in events] == ["text", "error", "done"] and "Ollama kapandı" in events[1][1]["message"]
    assert [m["content"] for m in c.get(f"/api/conversations/{cid}").json()["messages"]] == ["x", "Yarım"]


def test_chat_unknown_conversation_404(client):
    assert client.post("/api/chat", json={"conversation_id": "nope", "provider": "fake", "model": "fake-1", "message": "x"}).status_code == 404


def test_chat_empty_message_400(client):
    cid = client.post("/api/conversations").json()["id"]
    r = client.post("/api/chat", json={"conversation_id": cid, "provider": "fake", "model": "fake-1", "message": "   "})
    assert r.status_code == 400 and client.get(f"/api/conversations/{cid}").json()["messages"] == []


def test_chat_unknown_provider_404(client):
    cid = client.post("/api/conversations").json()["id"]
    r = client.post("/api/chat", json={"conversation_id": cid, "provider": "x", "model": "m", "message": "hi"})
    assert r.status_code == 404
    assert client.get(f"/api/conversations/{cid}").json()["messages"] == []


def test_rejects_foreign_host_header(client):
    r = client.get("/api/conversations", headers={"Host": "evil.example.com"})
    assert r.status_code == 400
    assert client.get("/api/conversations", headers={"Host": "localhost:8000"}).status_code == 200


def test_chat_error_redacts_api_key(registry, store, caplog):
    secret = "Incorrect API key provided: sk-abc**********wxyz"
    p = FakeProvider(turns=[[ChatEvent("text", "a")]], error=RuntimeError(secret))
    c, cid = make_chat(p, registry, store)
    with caplog.at_level("ERROR"):
        text = c.post("/api/chat", json=body(cid, "x")).text
    assert "sk-abc" not in text and "wxyz" not in text and "sk-***" in text
    assert "sk-abc" not in caplog.text and "wxyz" not in caplog.text


def test_models_error_redacts_api_key(registry, store):
    p = FakeProvider(models_error=RuntimeError("Incorrect API key provided: sk-abc…wxyz"))
    r = make_client(create_app({"fake": p}, registry, store)).get("/api/models", params={"provider": "fake"})
    assert r.status_code == 503 and "wxyz" not in r.json()["detail"] and "sk-***" in r.json()["detail"]
