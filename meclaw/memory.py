"""Assistant memory: the rules block and facts appended to the system prompt."""
from __future__ import annotations

MAX_MEMORY_CHARS = 500
MAX_PROMPT_MEMORIES = 100

MEMORY_RULES = (
    "You have a long-term memory about the user. Save durable personal facts (name, "
    "preferences, ongoing projects, important relationships) with the `remember` tool "
    "without being asked. Never save temporary details or secrets such as passwords, API "
    "keys or ID numbers. If a known fact is wrong or outdated, remove it with `forget` and "
    "save the corrected one. Briefly mention when you saved something."
)


def build_system_prompt(base: str, memories: list[dict], memory_enabled: bool) -> str:
    if not memory_enabled:
        return base
    newest = sorted(memories, key=lambda m: m["id"])[-MAX_PROMPT_MEMORIES:]
    lines = [f"[{m['id']}] {m['content']}" for m in newest] or ["(none yet)"]
    return f"{base}\n\n{MEMORY_RULES}\n\nKnown facts about the user:\n" + "\n".join(lines)
