"""Memory tools: remember and forget notes about the user."""
from __future__ import annotations

from meclaw.memory import MAX_MEMORY_CHARS
from meclaw.tools.base import ToolContext, ToolSpec


def remember(ctx: ToolContext, content: str) -> str:
    text = str(content).strip()
    if not text:
        return "Memory is empty."
    if len(text) > MAX_MEMORY_CHARS:
        return f"Memory is too long (max {MAX_MEMORY_CHARS} characters)."
    return f"Saved memory #{ctx.storage.add_memory(text)['id']}."


def forget(ctx: ToolContext, memory_id: int) -> str:
    memory_id = int(memory_id)
    if ctx.storage.delete_memory(memory_id):
        return f"Forgot memory #{memory_id}."
    return f"No memory #{memory_id}."


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
