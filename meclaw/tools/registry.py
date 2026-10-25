"""Maps tool names to Explorer methods and exposes tool definitions."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from tools.finder.explorer_class import Explorer

logger = logging.getLogger(__name__)

DEFAULT_DEFINITIONS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "tools" / "finder" / "tool_definitions.json"
)

MAX_RESULT_CHARS = 20000


class ToolRegistry:
    def __init__(self, explorer: Explorer, definitions_path: Path = DEFAULT_DEFINITIONS_PATH):
        self._explorer = explorer
        with open(definitions_path, encoding="utf-8") as f:
            self._definitions: list[dict] = json.load(f)
        self._names = {d["function"]["name"] for d in self._definitions}

    @property
    def explorer(self) -> Explorer:
        return self._explorer

    def definitions(self) -> list[dict]:
        return list(self._definitions)

    def names(self) -> set[str]:
        return set(self._names)

    def _list_items(self) -> str:
        items = self._explorer.list_items()
        if not items:
            return "No items found."
        lines = ["Workspace contents:", ""]
        for item in items:
            icon = "📁" if item["type"] == "dir" else "📄"
            lines.append(f"{icon} {item['name']}")
        return "\n".join(lines)

    @staticmethod
    def _cap(result: str) -> str:
        if len(result) > MAX_RESULT_CHARS:
            return result[:MAX_RESULT_CHARS] + "\n…(truncated)"
        return result

    def run(self, name: str, arguments: dict | None) -> str:
        if name not in self._names:
            return f"Unknown tool: {name}"
        args = arguments or {}
        try:
            if name == "list_items_tool":
                return self._list_items()
            method_name = name[: -len("_tool")] if name.endswith("_tool") else name
            method = getattr(self._explorer, method_name, None)
            if method is None:
                return f"Unknown tool: {name}"
            return self._cap(str(method(**args)))
        except TypeError as exc:
            return f"Invalid arguments for {name}: {exc}"
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return f"Tool {name} failed: {exc}"
