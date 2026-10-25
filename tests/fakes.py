from __future__ import annotations

import copy

from meclaw.llm.base import ChatEvent


class FakeProvider:
    def __init__(
        self,
        name: str = "fake",
        turns: list[list[ChatEvent]] | None = None,
        ready: bool = True,
        reason: str = "",
        models: list[str] | None = None,
        error: Exception | None = None,
        models_error: Exception | None = None,
    ):
        self.name = name
        self.turns = list(turns) if turns else []
        self.ready = ready
        self.reason = reason
        self.models = list(models) if models is not None else ["fake-1"]
        self.error = error
        self.models_error = models_error
        self.calls: list[list[dict]] = []
        self._index = 0

    async def status(self) -> tuple[bool, str]:
        return self.ready, self.reason

    async def list_models(self) -> list[str]:
        if self.models_error:
            raise self.models_error
        return self.models

    async def chat(self, model, messages, tools):
        self.calls.append(copy.deepcopy(messages))
        if self._index >= len(self.turns):
            return
        events = self.turns[self._index]
        self._index += 1
        for event in events:
            yield event
        if self._index == len(self.turns) and self.error:
            raise self.error


def make_registry(path, **ctx_kwargs):
    from meclaw.tools import build_registry
    from meclaw.tools.base import ToolContext
    from tools.finder.explorer_class import Explorer

    return build_registry(ToolContext(Explorer(path), **ctx_kwargs))
