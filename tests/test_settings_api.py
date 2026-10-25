from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meclaw.agent import SYSTEM_PROMPT
from meclaw.config import Settings, parse_flag
from meclaw.llm.base import ChatEvent, ToolCall
from meclaw.storage import Storage
from server import create_app
from tests.fakes import FakeProvider, make_registry

KEY = "sk-test-abcdefgh12345678"
BASE = Settings(
    ollama_host="http://localhost:11434", openai_api_key=None, db_path=Path("x.db"),
    workspace_dir=Path("C:/varsayilan/workspace"),
)


class Harness:
    """Fake apply_settings: records env changes and rebuilds providers from them."""

    def __init__(self, provider):
        self.provider = provider
        self.settings = BASE
        self.calls: list[dict] = []

    def apply(self, changes):
        self.calls.append(changes)
        fields = {
            "OLLAMA_HOST": "ollama_host", "OPENAI_API_KEY": "openai_api_key",
            "MECLAW_DEFAULT_PROVIDER": "default_provider", "MECLAW_DEFAULT_MODEL": "default_model",
            "MECLAW_SYSTEM_PROMPT": "system_prompt", "MECLAW_WORKSPACE": "workspace_dir",
            "MECLAW_INTERNET": "internet_enabled", "MECLAW_MEMORY": "memory_enabled",
        }
        updates = {fields[k]: v for k, v in changes.items()}
        for flag in ("internet_enabled", "memory_enabled"):
            if flag in updates:
                updates[flag] = parse_flag(updates[flag])
        if updates.get("ollama_host", "") is None:
            updates["ollama_host"] = "http://localhost:11434"
        if "workspace_dir" in updates:
            updates["workspace_dir"] = Path(updates["workspace_dir"] or BASE.workspace_dir)
        self.settings = replace(self.settings, **updates)
        self.provider = FakeProvider(turns=[[ChatEvent("text", "ok")]])
        return self.settings, {"fake": self.provider}


@pytest.fixture
def h():
    return Harness(FakeProvider(turns=[[ChatEvent("text", "ok")]]))


@pytest.fixture
def built():
    return []


@pytest.fixture
def client(tmp_path, h, built):
    def build(settings):
        built.append(settings.workspace_dir)
        return make_registry(
            settings.workspace_dir, storage=storage,
            internet=settings.internet_enabled, memory=settings.memory_enabled,
        )

    storage = Storage(tmp_path / "t.db")
    app = create_app(
        {"fake": h.provider},
        make_registry(tmp_path / "ws", storage=storage),
        storage,
        settings=BASE,
        apply_settings=h.apply,
        make_registry=build,
    )
    return TestClient(app, base_url="http://127.0.0.1")


def test_get_settings_defaults(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["ollama_host"] == "http://localhost:11434"
    assert data["openai_key_set"] is False and data["openai_key_hint"] == ""
    assert data["system_prompt"] == "" and data["system_prompt_default"] == SYSTEM_PROMPT
    assert data["default_provider"] == "" and data["default_model"] == ""
    assert data["providers"] == ["fake"]


def test_put_key_never_echoed(client, h):
    r = client.put("/api/settings", json={"openai_api_key": KEY})
    assert r.status_code == 200
    assert h.calls == [{"OPENAI_API_KEY": KEY}]
    assert KEY not in r.text and KEY not in client.get("/api/settings").text
    assert r.json()["openai_key_set"] is True and r.json()["openai_key_hint"] == "…5678"


def test_blank_key_keeps_existing(client, h):
    client.put("/api/settings", json={"openai_api_key": KEY})
    client.put("/api/settings", json={"openai_api_key": "  ", "default_model": "m"})
    assert h.calls[-1] == {"MECLAW_DEFAULT_MODEL": "m"}


def test_clear_key(client, h):
    client.put("/api/settings", json={"openai_api_key": KEY})
    r = client.put("/api/settings", json={"clear_openai_api_key": True})
    assert h.calls[-1] == {"OPENAI_API_KEY": None}
    assert r.json()["openai_key_set"] is False


def test_empty_strings_remove_optional_settings(client, h):
    client.put("/api/settings", json={"default_provider": "", "default_model": "", "system_prompt": "", "ollama_host": ""})
    assert h.calls[-1] == {
        "MECLAW_DEFAULT_PROVIDER": None, "MECLAW_DEFAULT_MODEL": None,
        "MECLAW_SYSTEM_PROMPT": None, "OLLAMA_HOST": None,
    }


def test_prompt_equal_to_default_is_removed(client, h):
    client.put("/api/settings", json={"system_prompt": SYSTEM_PROMPT})
    assert h.calls[-1] == {"MECLAW_SYSTEM_PROMPT": None}


@pytest.mark.parametrize("payload", [
    {"ollama_host": "localhost:11434"},
    {"ollama_host": "ftp://x"},
    {"default_provider": "nope"},
    {"system_prompt": "x" * 8001},
])
def test_invalid_settings_rejected(client, h, payload):
    r = client.put("/api/settings", json=payload)
    assert r.status_code == 400 and h.calls == []


def test_put_rebuilds_providers(client, h):
    old = h.provider
    client.put("/api/settings", json={"default_model": "m"})
    assert h.provider is not old
    cid = client.post("/api/conversations").json()["id"]
    client.post("/api/chat", json={"conversation_id": cid, "provider": "fake", "model": "m", "message": "x"})
    assert h.provider.calls and not old.calls


def test_custom_system_prompt_reaches_model(client, h):
    client.put("/api/settings", json={"system_prompt": "Kısa yanıt ver."})
    cid = client.post("/api/conversations").json()["id"]
    client.post("/api/chat", json={"conversation_id": cid, "provider": "fake", "model": "m", "message": "x"})
    system = h.provider.calls[0][0]
    assert system["role"] == "system" and system["content"].startswith("Kısa yanıt ver.\n\n")


def test_settings_unavailable_without_apply(tmp_path):
    app = create_app({"fake": FakeProvider()}, make_registry(tmp_path / "ws"), Storage(tmp_path / "t.db"))
    c = TestClient(app, base_url="http://127.0.0.1")
    assert c.get("/api/settings").status_code == 404
    assert c.put("/api/settings", json={}).status_code == 404


def test_workspace_in_payload(client):
    data = client.get("/api/settings").json()
    assert Path(data["workspace"]) == BASE.workspace_dir


def test_workspace_change_rebuilds_tools(client, h, built, tmp_path):
    new = tmp_path / "yeni alan"
    r = client.put("/api/settings", json={"workspace": str(new)})
    assert r.status_code == 200
    assert h.calls[-1] == {"MECLAW_WORKSPACE": str(new)}
    assert new.is_dir() and built == [new]
    assert Path(r.json()["workspace"]) == new
    listing = client.get("/api/files").json()
    assert listing["entries"] == []


def test_same_workspace_does_not_rebuild(client, built, tmp_path):
    client.put("/api/settings", json={"workspace": str(tmp_path / "a")})
    client.put("/api/settings", json={"default_model": "m"})
    assert len(built) == 1


def test_blank_workspace_resets_to_default(client, h):
    client.put("/api/settings", json={"workspace": ""})
    assert h.calls[-1] == {"MECLAW_WORKSPACE": None}


@pytest.mark.parametrize("value", ["goreli/klasor", "C:\\", "/"])
def test_bad_workspace_rejected(client, h, value):
    assert client.put("/api/settings", json={"workspace": value}).status_code == 400
    assert h.calls == []


LOCAL = {"X-MeClaw": "1"}


def chat(client, text="x"):
    cid = client.post("/api/conversations").json()["id"]
    return client.post("/api/chat", json={"conversation_id": cid, "provider": "fake", "model": "m", "message": text})


def test_flags_saved_and_rebuild(client, h, built):
    client.put("/api/settings", json={"internet_enabled": False})
    assert h.calls[-1] == {"MECLAW_INTERNET": "0"} and len(built) == 1
    client.put("/api/settings", json={"internet_enabled": True})
    assert h.calls[-1] == {"MECLAW_INTERNET": None} and len(built) == 2
    client.put("/api/settings", json={"memory_enabled": False})
    assert h.calls[-1] == {"MECLAW_MEMORY": "0"} and len(built) == 3
    data = client.get("/api/settings").json()
    assert data["internet_enabled"] is True and data["memory_enabled"] is False


def test_memories_api(client):
    r = client.post("/api/memories", json={"content": " Adım Melih "}, headers=LOCAL)
    mid = r.json()["id"]
    assert client.get("/api/memories").json()[0]["content"] == "Adım Melih"
    r = client.put(f"/api/memories/{mid}", json={"content": "Melih Emin"}, headers=LOCAL)
    assert r.status_code == 200 and r.json()["content"] == "Melih Emin" and r.json()["id"] == mid
    assert client.put("/api/memories/999", json={"content": "x"}, headers=LOCAL).status_code == 404
    assert client.post("/api/memories", json={"content": " "}, headers=LOCAL).status_code == 400
    assert client.post("/api/memories", json={"content": "x" * 501}, headers=LOCAL).status_code == 400
    assert client.put(f"/api/memories/{mid}", json={"content": ""}, headers=LOCAL).status_code == 400
    assert client.post("/api/memories", json={"content": "x"}).status_code == 403
    assert client.put(f"/api/memories/{mid}", json={"content": "x"}).status_code == 403
    assert client.delete(f"/api/memories/{mid}").status_code == 403
    assert client.delete("/api/memories").status_code == 403
    assert client.delete(f"/api/memories/{mid}", headers=LOCAL).status_code == 204
    assert client.delete(f"/api/memories/{mid}", headers=LOCAL).status_code == 404
    client.post("/api/memories", json={"content": "a"}, headers=LOCAL)
    assert client.delete("/api/memories", headers=LOCAL).json() == {"deleted": 1}


def test_memories_reach_system_prompt(client, h):
    client.post("/api/memories", json={"content": "Adım Melih"}, headers=LOCAL)
    chat(client)
    assert "[1] Adım Melih" in h.provider.calls[0][0]["content"]


def test_memory_off_keeps_prompt_plain(client, h):
    client.post("/api/memories", json={"content": "Adım Melih"}, headers=LOCAL)
    client.put("/api/settings", json={"memory_enabled": False})
    chat(client)
    assert h.provider.calls[0][0] == {"role": "system", "content": SYSTEM_PROMPT}


def test_no_settings_means_plain_prompt(tmp_path):
    provider = FakeProvider(turns=[[ChatEvent("text", "ok")]])
    storage = Storage(tmp_path / "t.db")
    storage.add_memory("Adım Melih")
    c = TestClient(create_app({"fake": provider}, make_registry(tmp_path / "ws"), storage), base_url="http://127.0.0.1")
    chat(c)
    assert provider.calls[0][0] == {"role": "system", "content": SYSTEM_PROMPT}


def test_disabled_internet_tool_unknown(client, h):
    client.put("/api/settings", json={"internet_enabled": False})
    call = ToolCall("c1", "web_search", {"query": "x"})
    h.provider.turns = [[ChatEvent("tool_calls", tool_calls=[call])], [ChatEvent("text", "ok")]]
    text = chat(client).text
    assert "Unknown tool: web_search" in text and "event: done" in text
