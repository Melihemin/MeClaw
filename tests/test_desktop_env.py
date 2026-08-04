from pathlib import Path

from desktop_app import build_server_command
from tools.desktop_env import load_env_settings, save_env_settings


def test_load_env_settings(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_API=abc123\nDEBUG=true\n", encoding="utf-8")

    settings = load_env_settings(env_path)

    assert settings["TELEGRAM_API"] == "abc123"
    assert settings["DEBUG"] == "true"


def test_save_env_settings(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    save_env_settings(env_path, {"TELEGRAM_API": "new-token", "DEBUG": "false"})

    content = env_path.read_text(encoding="utf-8")
    assert "TELEGRAM_API=new-token" in content
    assert "DEBUG=false" in content


def test_build_server_command_contains_run_flag() -> None:
    command = build_server_command()
    assert "--run-server" in command
