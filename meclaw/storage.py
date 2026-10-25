"""SQLite conversation storage."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    provider TEXT,
    model TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT,
    content TEXT,
    tool_calls TEXT NULL,
    tool_call_id TEXT NULL,
    name TEXT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT
);
"""

_CONV_COLS = "id, title, provider, model, created_at, updated_at"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return _Conn(conn)

    def create_conversation(self) -> dict:
        now = _now()
        conv = {"id": uuid.uuid4().hex, "title": "Yeni sohbet", "provider": None,
                "model": None, "created_at": now, "updated_at": now}
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO conversations ({_CONV_COLS}) VALUES (?, ?, ?, ?, ?, ?)",
                tuple(conv.values()),
            )
        return conv

    def list_conversations(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_CONV_COLS} FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conversation_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_CONV_COLS} FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if row is None:
                return None
            msg_rows = conn.execute(
                "SELECT role, content, tool_calls, tool_call_id, name FROM messages "
                "WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        conv = dict(row)
        messages = []
        for r in msg_rows:
            msg = {"role": r["role"], "content": r["content"] if r["content"] is not None else ""}
            if r["tool_calls"] is not None:
                msg["tool_calls"] = json.loads(r["tool_calls"])
            if r["tool_call_id"] is not None:
                msg["tool_call_id"] = r["tool_call_id"]
            if r["name"] is not None:
                msg["name"] = r["name"]
            messages.append(msg)
        conv["messages"] = messages
        return conv

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            return cur.rowcount > 0

    def add_messages(self, conversation_id: str, messages: list[dict]) -> None:
        now = _now()
        with self._connect() as conn:
            for m in messages:
                tool_calls = m.get("tool_calls")
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, tool_calls, "
                    "tool_call_id, name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        conversation_id,
                        m["role"],
                        m.get("content", ""),
                        json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                        m.get("tool_call_id"),
                        m.get("name"),
                        now,
                    ),
                )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )

    def update_conversation(self, conversation_id: str, *, title: str | None = None,
                            provider: str | None = None, model: str | None = None) -> None:
        fields = {"title": title, "provider": provider, "model": model}
        fields = {k: v for k, v in fields.items() if v is not None}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE conversations SET {sets} WHERE id = ?",
                (*fields.values(), conversation_id),
            )

    def list_memories(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, content, created_at, updated_at FROM memories ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def add_memory(self, content: str) -> dict:
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO memories (content, created_at, updated_at) VALUES (?, ?, ?)",
                (content, now, now),
            )
            memory_id = cur.lastrowid
        return {"id": memory_id, "content": content, "created_at": now, "updated_at": now}

    def update_memory(self, memory_id: int, content: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE memories SET content = ?, updated_at = ? WHERE id = ?",
                (content, _now(), memory_id),
            )
            return cur.rowcount > 0

    def delete_memory(self, memory_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cur.rowcount > 0

    def clear_memories(self) -> int:
        with self._connect() as conn:
            return conn.execute("DELETE FROM memories").rowcount


class _Conn:
    """Context manager: commit/rollback on exit, always close (Windows file locks)."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False
