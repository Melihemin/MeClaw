"""Tool core: specs, context and the registry that runs them."""
from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from tools.finder.explorer_class import Explorer

if TYPE_CHECKING:
    from meclaw.storage import Storage

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 20000


@dataclass
class Confirmation:
    description: str
    preview: str = ""


@dataclass
class ToolContext:
    explorer: Explorer
    storage: "Storage | None" = None
    internet: bool = True
    memory: bool = True


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable
    confirm: Callable[[ToolContext, dict], Confirmation | None] | None = None


class ToolRegistry:
    def __init__(self, ctx: ToolContext, specs: list[ToolSpec]):
        self._ctx = ctx
        self._specs = {s.name: s for s in specs}

    @property
    def explorer(self) -> Explorer:
        return self._ctx.explorer

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {"name": s.name, "description": s.description, "parameters": s.parameters},
            }
            for s in self._specs.values()
        ]

    def names(self) -> set[str]:
        return set(self._specs)

    def needs_confirmation(self, name: str, arguments: dict | None) -> Confirmation | None:
        spec = self._specs.get(name)
        if spec is None or spec.confirm is None:
            return None
        try:
            return spec.confirm(self._ctx, arguments or {})
        except Exception:
            logger.exception("Confirm rule for %s failed", name)
            return None

    @staticmethod
    def _cap(result: str) -> str:
        if len(result) > MAX_RESULT_CHARS:
            return result[:MAX_RESULT_CHARS] + "\n…(truncated)"
        return result

    async def run(self, name: str, arguments: dict | None) -> str:
        spec = self._specs.get(name)
        if spec is None:
            return f"Unknown tool: {name}"
        args = arguments or {}
        try:
            if inspect.iscoroutinefunction(spec.handler):
                result = await spec.handler(self._ctx, **args)
            else:
                result = await asyncio.to_thread(spec.handler, self._ctx, **args)
                if inspect.isawaitable(result):
                    result = await result
            return self._cap(str(result))
        except TypeError as exc:
            return f"Invalid arguments for {name}: {exc}"
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return f"Tool {name} failed: {exc}"
