from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator

import ollama

from meclaw.llm.base import ChatEvent, ToolCall


def to_ollama_messages(messages: list[dict]) -> list[dict]:
    """Convert the common message format to Ollama's."""
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "assistant" and m.get("tool_calls"):
            out.append({
                "role": "assistant",
                "content": m.get("content", ""),
                "tool_calls": [
                    {"function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in m["tool_calls"]
                ],
            })
        elif role == "tool":
            out.append({"role": "tool", "content": m.get("content", ""), "tool_name": m.get("name", "")})
        else:
            out.append({"role": role, "content": m.get("content", "")})
    return out


def _lacks_tool_support(err: ollama.ResponseError) -> bool:
    return "does not support tools" in str(getattr(err, "error", "") or err)


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str, client: ollama.AsyncClient | None = None):
        self.host = host
        self.client = client if client is not None else ollama.AsyncClient(host=host)

    async def status(self) -> tuple[bool, str]:
        try:
            await asyncio.wait_for(self.client.list(), 3)
        except Exception:
            return False, f"Ollama'ya ulaşılamıyor ({self.host})"
        return True, ""

    async def list_models(self) -> list[str]:
        response = await self.client.list()
        return sorted(m.model for m in response.models)

    async def _stream(self, model: str, messages: list[dict], tools: list[dict] | None):
        stream = await self.client.chat(
            model=model, messages=messages, tools=tools or None, stream=True
        )
        async for part in stream:
            yield part

    async def chat(
        self, model: str, messages: list[dict], tools: list[dict]
    ) -> AsyncIterator[ChatEvent]:
        converted = to_ollama_messages(messages)
        yielded = False
        pending: list[ToolCall] = []
        use_tools: list[dict] | None = tools
        while True:
            try:
                async for part in self._stream(model, converted, use_tools):
                    msg = part.message
                    if msg.content:
                        yielded = True
                        yield ChatEvent(type="text", text=msg.content)
                    for tc in msg.tool_calls or []:
                        pending.append(ToolCall(
                            id=uuid.uuid4().hex,
                            name=tc.function.name,
                            arguments=dict(tc.function.arguments or {}),
                        ))
                break
            except ollama.ResponseError as err:
                if use_tools and not yielded and not pending and _lacks_tool_support(err):
                    use_tools = None
                    continue
                raise
        if pending:
            yield ChatEvent(type="tool_calls", tool_calls=pending)
