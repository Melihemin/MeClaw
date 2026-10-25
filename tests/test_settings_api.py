from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meclaw.agent import SYSTEM_PROMPT
from meclaw.config import Settings
from meclaw.llm.base import ChatEvent
from meclaw.storage import Storage
from meclaw.tools.registry import ToolRegistry
from server import create_app
from tests.fakes import FakeProvider
from tools.finder.explorer_class import Explorer

KEY = "sk-test-abcdefgh12345678"
BASE = Settings(ollama_host="http://localhost:11434", openai_api_key=None, db_path=Path("x.db"))


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
            "MECLAW_SYSTEM_PROMPT": "system_prompt",
        }
        updates = {fields[k]: v for k, v in changes.items()}
        if updates.get("ollama_host", "") is None:
            updates["ollama_host"] = "http://localhost:11434"
        self.settings = replace(self.settings, **updates)
        self.provider = FakeProvider(turns=[[ChatEvent("text", "ok")]])
        return self.settings, {"fake": self.provider}


@pytest.fixture
def h():
    return Harness(FakeProvider(turns=[[ChatEvent("text", "ok")]]))


@pytest.fixture
def client(tmp_path, h):
    app = create_app(
        {"fake": h.provider},
        ToolRegistry(Explorer(base_dir=str(tmp_path / "ws"))),
        Storage(tmp_path / "t.db"),
        settings=BASE,
        apply_settings=h.apply,
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
    assert h.provider.calls[0][0] == {"role": "system", "content": "Kısa yanıt ver."}


def test_settings_unavailable_without_apply(tmp_path):
    app = create_app({"fake": FakeProvider()}, ToolRegistry(Explorer(base_dir=str(tmp_path / "ws"))), Storage(tmp_path / "t.db"))
    c = TestClient(app, base_url="http://127.0.0.1")
    assert c.get("/api/settings").status_code == 404
    assert c.put("/api/settings", json={}).status_code == 404
