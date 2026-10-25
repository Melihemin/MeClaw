import os

import dotenv

from meclaw.config import load_settings
from meclaw.settings_store import save_settings


def test_set_keeps_other_lines(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# yorum\nFOO=bar\nOLLAMA_HOST=http://old:11434\n", encoding="utf-8")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    save_settings({"OLLAMA_HOST": "http://new:11434"}, env_path=env)

    text = env.read_text(encoding="utf-8")
    assert "# yorum" in text and "FOO=bar" in text
    assert dotenv.dotenv_values(env)["OLLAMA_HOST"] == "http://new:11434"
    assert os.environ["OLLAMA_HOST"] == "http://new:11434"


def test_creates_missing_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.delenv("MECLAW_DEFAULT_MODEL", raising=False)
    save_settings({"MECLAW_DEFAULT_MODEL": "qwen3:8b"}, env_path=env)
    assert dotenv.dotenv_values(env) == {"MECLAW_DEFAULT_MODEL": "qwen3:8b"}


def test_none_removes_key(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-old\nFOO=bar\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-old")

    save_settings({"OPENAI_API_KEY": None}, env_path=env)

    assert dotenv.dotenv_values(env) == {"FOO": "bar"}
    assert "OPENAI_API_KEY" not in os.environ


def test_multiline_prompt_roundtrip(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    prompt = "Sen Melih'in asistanısın.\n\"Kısa\" yanıt ver: ğüşıöçİ"
    monkeypatch.delenv("MECLAW_SYSTEM_PROMPT", raising=False)
    save_settings({"MECLAW_SYSTEM_PROMPT": prompt}, env_path=env)
    assert dotenv.dotenv_values(env)["MECLAW_SYSTEM_PROMPT"] == prompt


def test_load_settings_reads_new_fields(monkeypatch):
    monkeypatch.setattr("meclaw.config.dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("MECLAW_DEFAULT_PROVIDER", "openai")
    monkeypatch.setenv("MECLAW_DEFAULT_MODEL", "gpt-4o")
    monkeypatch.setenv("MECLAW_SYSTEM_PROMPT", "Kısa yanıt ver.")
    s = load_settings()
    assert (s.default_provider, s.default_model, s.system_prompt) == ("openai", "gpt-4o", "Kısa yanıt ver.")


def test_load_settings_new_fields_default_none(monkeypatch):
    monkeypatch.setattr("meclaw.config.dotenv.load_dotenv", lambda *a, **k: None)
    for k in ("MECLAW_DEFAULT_PROVIDER", "MECLAW_DEFAULT_MODEL", "MECLAW_SYSTEM_PROMPT"):
        monkeypatch.setenv(k, "  ")
    s = load_settings()
    assert (s.default_provider, s.default_model, s.system_prompt) == (None, None, None)


def test_workspace_default_and_override(monkeypatch, tmp_path):
    from meclaw.config import PROJECT_ROOT
    monkeypatch.setattr("meclaw.config.dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("MECLAW_WORKSPACE", raising=False)
    assert load_settings().workspace_dir == PROJECT_ROOT / "workspace"
    monkeypatch.setenv("MECLAW_WORKSPACE", str(tmp_path))
    assert load_settings().workspace_dir == tmp_path


import pytest

from meclaw.config import parse_flag


@pytest.mark.parametrize("value,expected", [
    (None, True), ("", True), ("1", True), ("0", False), ("FALSE", False),
    ("off", False), ("no", False), ("yes", True),
])
def test_parse_flag(value, expected):
    assert parse_flag(value) is expected


def test_flags_load_from_env(monkeypatch):
    monkeypatch.setattr("meclaw.config.dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("MECLAW_INTERNET", "0")
    monkeypatch.delenv("MECLAW_MEMORY", raising=False)
    s = load_settings()
    assert s.internet_enabled is False and s.memory_enabled is True
