"""Write user-editable settings back to the project's .env file."""
from __future__ import annotations

import os
from pathlib import Path

import dotenv

from meclaw.config import PROJECT_ROOT

ENV_PATH = PROJECT_ROOT / ".env"


def save_settings(changes: dict[str, str | None], env_path: Path = ENV_PATH) -> None:
    """Apply ``{ENV_NAME: value}`` to .env and os.environ; ``None`` removes the key.

    Other lines in the file (comments, unrelated keys) are left untouched.
    """
    env_path.touch(exist_ok=True)
    for key, value in changes.items():
        if value is None:
            if key in dotenv.dotenv_values(env_path):
                dotenv.unset_key(env_path, key)
            os.environ.pop(key, None)
        else:
            dotenv.set_key(env_path, key, value)
            os.environ[key] = value
