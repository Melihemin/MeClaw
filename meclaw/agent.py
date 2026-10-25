from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable, Literal
from uuid import uuid4

from meclaw.llm.base import Provider, ToolCall
from meclaw.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    'You are a friendly and conversational AI assistant for Melih Emin KILICOGLU. '
    'You can chat naturally, answer questions, and assist with general tasks. '
    'When the user\'s request involves managing files and folders (such as creating, reading, deleting, or renaming), '
    'proactively use the appropriate tools to fulfill the request. '
    'Always explain the results of your actions clearly and kindly after using a tool. '
    '\n\nSTRICT RULES FOR CONVERSATION: '
    '1. If the user is just chatting normally (e.g., "how are you", "hello"), respond directly and naturally like a human. '
    '2. NEVER mention your internal tools, say things like "No tool call is needed", or explain your decision-making process. Just give the final answer.'
)

MAX_TURNS = 5
LIMIT_MESSAGE = "Araç kullanım sınırına ulaşıldı; model son bir yanıt üretemedi."
DENIED_PREFIX = "Denied by the user: "


@dataclass
class ConfirmRequest:
    id: str
    name: str
    arguments: dict
    description: str
    preview: str


ConfirmHook = Callable[[ConfirmRequest], Awaitable[bool]]


@dataclass
class AgentEvent:
    type: Literal["text", "tool", "confirm", "confirm_result"]
    text: str = ""
    name: str = ""
    arguments: dict = field(default_factory=dict)
    result: str = ""
    id: str = ""
    description: str = ""
    preview: str = ""
    approved: bool = False


async def _ask(confirm: ConfirmHook | None, req: ConfirmRequest) -> bool:
    if confirm is None:
        return False
    try:
        return bool(await confirm(req))
    except Exception:
        # Only Exception: cancellation (client disconnect) must still propagate.
        logger.exception("Confirm hook failed for %s", req.name)
        return False


async def run_agent(
    provider: Provider,
    model: str,
    history: list[dict],
    registry: ToolRegistry,
    new_messages: list[dict],
    system_prompt: str = SYSTEM_PROMPT,
    confirm: ConfirmHook | None = None,
) -> AsyncIterator[AgentEvent]:
    messages = [{"role": "system", "content": system_prompt}] + list(history)
    tools = registry.definitions()

    for _ in range(MAX_TURNS):
        text = ""
        calls: list[ToolCall] = []
        try:
            async for event in provider.chat(model, messages, tools):
                if event.type == "text":
                    text += event.text
                    yield AgentEvent("text", text=event.text)
                elif event.type == "tool_calls":
                    calls.extend(event.tool_calls)
        except BaseException:
            # Includes CancelledError/GeneratorExit (client disconnect): keep partial text.
            if text:
                new_messages.append({"role": "assistant", "content": text})
            raise

        if not calls:
            msg = {"role": "assistant", "content": text}
            messages.append(msg)
            new_messages.append(dict(msg))
            return

        msg = {
            "role": "assistant",
            "content": text,
            "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in calls],
        }
        messages.append(msg)
        new_messages.append({**msg, "tool_calls": [dict(tc) for tc in msg["tool_calls"]]})

        for c in calls:
            needed = registry.needs_confirmation(c.name, c.arguments)
            if needed is None:
                result = await registry.run(c.name, c.arguments)
            else:
                req = ConfirmRequest(
                    uuid4().hex, c.name, c.arguments, needed.description, needed.preview
                )
                yield AgentEvent(
                    "confirm", name=c.name, arguments=c.arguments, id=req.id,
                    description=req.description, preview=req.preview,
                )
                approved = await _ask(confirm, req)
                yield AgentEvent("confirm_result", name=c.name, id=req.id, approved=approved)
                if approved:
                    result = await registry.run(c.name, c.arguments)
                else:
                    result = DENIED_PREFIX + req.description
            tool_msg = {"role": "tool", "content": result, "tool_call_id": c.id, "name": c.name}
            messages.append(tool_msg)
            new_messages.append(dict(tool_msg))
            yield AgentEvent("tool", name=c.name, arguments=c.arguments, result=result)

    new_messages.append({"role": "assistant", "content": LIMIT_MESSAGE})
    yield AgentEvent("text", text=LIMIT_MESSAGE)
