"""File tools: thin specs over the low-level Explorer."""
from __future__ import annotations

from meclaw.tools.base import ToolContext, ToolSpec

MAX_LIST_ENTRIES = 500


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


_S = {"type": "string"}


def _explorer_tool(name: str, description: str, properties: dict, required: list[str]) -> ToolSpec:
    def handler(ctx: ToolContext, **args):
        return getattr(ctx.explorer, name)(**args)

    return ToolSpec(name, description, _obj(properties, required), handler)


def _walk(path, depth: int, recursive: bool, out: list[tuple[int, str, bool]]) -> None:
    entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    for entry in entries:
        is_dir = entry.is_dir()
        out.append((depth, entry.name, is_dir))
        if recursive and is_dir and not entry.is_symlink():
            _walk(entry, depth + 1, recursive, out)


def list_items(ctx: ToolContext, path: str = "", recursive: bool = False) -> str:
    try:
        folder = ctx.explorer.resolve(path)
    except ValueError:
        return "Path is outside the workspace."
    if not folder.exists():
        return f"Folder '{path}' not found."
    if not folder.is_dir():
        return f"'{path}' is not a folder."
    entries: list[tuple[int, str, bool]] = []
    try:
        _walk(folder, 0, bool(recursive), entries)
    except OSError:
        return "Failed to list the folder."
    if not entries:
        return "No items found."
    lines = ["Workspace contents:", ""]
    for depth, name, is_dir in entries[:MAX_LIST_ENTRIES]:
        lines.append(f"{'  ' * depth}{'📁' if is_dir else '📄'} {name}")
    if len(entries) > MAX_LIST_ENTRIES:
        lines.append(f"… ({len(entries) - MAX_LIST_ENTRIES} more)")
    return "\n".join(lines)


def read_file(ctx: ToolContext, filename: str, start_line: int | None = None, end_line: int | None = None) -> str:
    if start_line is None and end_line is None:
        return ctx.explorer.read_file(filename)
    if not filename:
        return "No filename provided."
    try:
        text = ctx.explorer.resolve(filename).read_text(encoding="utf-8")
    except ValueError:
        return "Path is outside the workspace."
    except FileNotFoundError:
        return f"File '{filename}' not found."
    except Exception:
        return "Failed to read the file."
    lines = text.splitlines()
    total = len(lines)
    start = int(start_line) if start_line is not None else 1
    end = int(end_line) if end_line is not None else total
    if start < 1 or start > total or end < start:
        return "Invalid line range."
    end = min(end, total)
    return f"Lines {start}-{end} of {total}:\n" + "\n".join(lines[start - 1 : end])


FILE_TOOLS: list[ToolSpec] = [
    _explorer_tool("create_file", "Create a new text file in the workspace.", {"filename": _S}, ["filename"]),
    _explorer_tool("delete_file", "Delete a file from the workspace.", {"filename": _S}, ["filename"]),
    _explorer_tool(
        "copy_file",
        "Copy a file to a new path.",
        {"source_filename": _S, "destination_filename": _S},
        ["source_filename", "destination_filename"],
    ),
    ToolSpec(
        "read_file",
        "Read the content of a file, optionally only a range of lines (1-based, inclusive).",
        _obj(
            {
                "filename": _S,
                "start_line": {"type": "integer", "description": "First line to read (1-based)."},
                "end_line": {"type": "integer", "description": "Last line to read (inclusive)."},
            },
            ["filename"],
        ),
        read_file,
    ),
    _explorer_tool(
        "write_file", "Write content to a file.", {"filename": _S, "content": _S}, ["filename", "content"]
    ),
    _explorer_tool(
        "rename_file", "Rename a file.", {"old_filename": _S, "new_filename": _S}, ["old_filename", "new_filename"]
    ),
    _explorer_tool(
        "write_word_file",
        "Write content to a .docx file.",
        {"filename": _S, "content": _S, "font_name": _S, "font_size": {"type": "integer"}},
        ["filename", "content"],
    ),
    _explorer_tool("read_word_file", "Read the content of a .docx file.", {"filename": _S}, ["filename"]),
    _explorer_tool("create_folder", "Create a new folder in the workspace.", {"folder_name": _S}, ["folder_name"]),
    _explorer_tool("remove_folder", "Remove an empty folder from the workspace.", {"folder_name": _S}, ["folder_name"]),
    ToolSpec(
        "list_items",
        "List files and folders in the workspace root or a subfolder, optionally recursively.",
        _obj(
            {
                "path": {"type": "string", "description": "Folder to list, relative to the workspace root (default: root)."},
                "recursive": {"type": "boolean", "description": "Include nested folders' contents."},
            }
        ),
        list_items,
    ),
    _explorer_tool(
        "move_item",
        "Move a file or folder to a new path.",
        {"source_path": _S, "destination_path": _S},
        ["source_path", "destination_path"],
    ),
    _explorer_tool(
        "rename_folder",
        "Rename a folder.",
        {"old_folder_name": _S, "new_folder_name": _S},
        ["old_folder_name", "new_folder_name"],
    ),
    _explorer_tool(
        "copy_folder",
        "Copy a folder to a new location.",
        {"source_folder_name": _S, "destination_folder_name": _S},
        ["source_folder_name", "destination_folder_name"],
    ),
    _explorer_tool("zip_folder", "Zip a folder into a .zip archive.", {"folder_name": _S}, ["folder_name"]),
    _explorer_tool(
        "extract_archive",
        "Extract a .zip archive into a destination folder.",
        {"archive_name": _S, "destination_folder": _S},
        ["archive_name", "destination_folder"],
    ),
]
