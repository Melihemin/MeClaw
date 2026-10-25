from __future__ import annotations

import json
import re
from typing import AsyncIterator

import openai

from meclaw.llm.base import ChatEvent, ToolCall

NO_KEY_MESSAGE = "OPENAI_API_KEY tanımlı değil"

_EXCLUDED = ("audio", "realtime", "transcribe", "tts", "image", "search", "instruct", "pro", "codex")


def to_openai_messages(messages: list[dict]) -> list[dict]:
    """Convert the common message format to OpenAI's."""
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "assistant" and m.get("tool_calls"):
            out.append({
                "role": "assistant",
                "content": m.get("content", ""),
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                        },
                    }
                    for tc in m["tool_calls"]
                ],
            })
        elif role == "tool":
            out.append({"role": "tool", "content": m.get("content", ""), "tool_call_id": m["tool_call_id"]})
        else:
            out.append({"role": role, "content": m.get("content", "")})
    return out


def filter_chat_models(ids: list[str]) -> list[str]:
    """Keep chat-capable model ids (gpt-* and o<digit>*), sorted."""
    return sorted(
        i for i in ids
        if (i.startswith("gpt-") or re.match(r"o\d", i))
        and not any(word in i for word in _EXCLUDED)
    )


class ToolCallAccumulator:
    """Merges streamed tool-call fragments (keyed by index) into ToolCalls."""

    def __init__(self) -> None:
        self._calls: dict[int, dict] = {}

    def add(self, deltas) -> None:
        for d in deltas or []:
            slot = self._calls.setdefault(d.index, {"id": "", "name": "", "arguments": ""})
            if d.id:
                slot["id"] = d.id
            fn = d.function
            if fn is not None:
                if fn.name:
                    slot["name"] += fn.name
                if fn.arguments:
                    slot["arguments"] += fn.arguments

    def result(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for index in sorted(self._calls):
            slot = self._calls[index]
            try:
                args = json.loads(slot["arguments"]) if slot["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            calls.append(ToolCall(id=slot["id"], name=slot["name"], arguments=args))
        return calls


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None, client: openai.AsyncOpenAI | None = None):
        self.api_key = api_key
        if client is not None:
            self.client = client
        elif api_key:
            self.client = openai.AsyncOpenAI(api_key=api_key)
        else:
            self.client = None

    def _require_client(self):
        if self.client is None:
            raise RuntimeError(NO_KEY_MESSAGE)
        return self.client

    async def status(self) -> tuple[bool, str]:
        if self.client is None:
            return False, NO_KEY_MESSAGE
        return True, ""

    async def list_models(self) -> list[str]:
        page = await self._require_client().models.list()
        return filter_chat_models([m.id for m in page.data])

    async def chat(
        self, model: str, messages: list[dict], tools: list[dict]
    ) -> AsyncIterator[ChatEvent]:
        client = self._require_client()
        kwargs: dict = {"model": model, "messages": to_openai_messages(messages), "stream": True}
        if tools:
            kwargs["tools"] = tools
        stream = await client.chat.completions.create(**kwargs)
        acc = ToolCallAccumulator()
        async for part in stream:
            if not part.choices:
                continue
            delta = part.choices[0].delta
            if delta.content:
                yield ChatEvent(type="text", text=delta.content)
            if delta.tool_calls:
                acc.add(delta.tool_calls)
        calls = acc.result()
        if calls:
            yield ChatEvent(type="tool_calls", tool_calls=calls)
