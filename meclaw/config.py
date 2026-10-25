"""Application settings loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    openai_api_key: str | None
    db_path: Path


def load_settings() -> Settings:
    dotenv.load_dotenv()
    ollama_host = os.getenv("OLLAMA_HOST", "").strip() or "http://localhost:11434"
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip() or None
    db_env = (os.getenv("MECLAW_DB_PATH") or "").strip()
    db_path = Path(db_env) if db_env else PROJECT_ROOT / "data" / "meclaw.db"
    return Settings(ollama_host=ollama_host, openai_api_key=api_key, db_path=db_path)
