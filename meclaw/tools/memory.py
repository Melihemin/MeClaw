"""Memory tools: remember and forget notes about the user."""
from __future__ import annotations

from meclaw.memory import MAX_MEMORY_CHARS
from meclaw.tools.base import ToolContext, ToolSpec

MAX_ID = 2**63 - 1  # SQLite integer range


def remember(ctx: ToolContext, content: str) -> str:
    text = str(content).strip()
    if not text:
        return "Memory is empty."
    if len(text) > MAX_MEMORY_CHARS:
        return f"Memory is too long (max {MAX_MEMORY_CHARS} characters)."
    return f"Saved memory #{ctx.storage.add_memory(text)['id']}."


def forget(ctx: ToolContext, memory_id: int) -> str:
    given = memory_id
    if isinstance(memory_id, str) and memory_id.strip().isdecimal():
        memory_id = int(memory_id)
    if (
        isinstance(memory_id, int) and not isinstance(memory_id, bool)
        and 1 <= memory_id <= MAX_ID and ctx.storage.delete_memory(memory_id)
    ):
        return f"Forgot memory #{memory_id}."
    return f"No memory #{given}."



MEMORY_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "remember",
        "Save a durable fact about the user to long-term memory (max 500 characters).",
        {
            "type": "object",
            "properties": {"content": {"type": "string", "description": "The fact to remember."}},
            "required": ["content"],
        },
        remember,
    ),
    ToolSpec(
        "forget",
        "Delete a memory by its id (shown as [id] in the known facts).",
        {
            "type": "object",
            "properties": {"memory_id": {"type": "integer", "description": "Id of the memory."}},
            "required": ["memory_id"],
        },
        forget,
    ),
]
