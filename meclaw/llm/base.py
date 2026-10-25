from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatEvent:
    type: Literal["text", "tool_calls"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class Provider(Protocol):
    name: str

    async def status(self) -> tuple[bool, str]: ...

    async def list_models(self) -> list[str]: ...

    def chat(self, model: str, messages: list[dict], tools: list[dict]) -> AsyncIterator[ChatEvent]: ...
