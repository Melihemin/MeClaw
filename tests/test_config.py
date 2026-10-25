from meclaw.config import PROJECT_ROOT, load_settings


def test_defaults(monkeypatch):
    for k in ("OLLAMA_HOST", "OPENAI_API_KEY", "MECLAW_DB_PATH"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("meclaw.config.dotenv.load_dotenv", lambda *a, **k: None)
    s = load_settings()
    assert s.ollama_host == "http://localhost:11434"
    assert s.openai_api_key is None
    assert s.db_path == PROJECT_ROOT / "data" / "meclaw.db"


def test_blank_api_key_is_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    monkeypatch.setattr("meclaw.config.dotenv.load_dotenv", lambda *a, **k: None)
    assert load_settings().openai_api_key is None
