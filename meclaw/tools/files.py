"""File tools: thin specs over the low-level Explorer."""
from __future__ import annotations

import fnmatch
from datetime import datetime

from meclaw.tools.base import Confirmation, ToolContext, ToolSpec, as_bool, as_int

MAX_LIST_ENTRIES = 500
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_FILE_BYTES = 1_000_000
EDIT_PREVIEW_CHARS = 280
WRITE_PREVIEW_CHARS = 600


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


_S = {"type": "string"}


def _explorer_tool(
    name: str, description: str, properties: dict, required: list[str], confirm=None
) -> ToolSpec:
    def handler(ctx: ToolContext, **args):
        return getattr(ctx.explorer, name)(**args)

    return ToolSpec(name, description, _obj(properties, required), handler, confirm)


PRUNED_DIRS = {".git", "node_modules", "__pycache__", ".venv"}


def _is_link(entry) -> bool:
    try:
        return entry.is_symlink() or entry.is_junction()
    except OSError:
        return True


def _safe_entries(ctx: ToolContext, folder) -> list:
    """Sorted entries of folder, minus anything resolving outside the workspace."""
    base = ctx.explorer.base_dir
    entries = []
    for entry in folder.iterdir():
        try:
            if not entry.resolve().is_relative_to(base):
                continue
        except (OSError, RuntimeError):
            continue
        entries.append(entry)
    entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
    return entries


def _walk(ctx: ToolContext, path, depth: int, recursive: bool, out: list[tuple[int, str, bool]], limit: int) -> None:
    """Depth-first listing; stops once more than `limit` entries were collected."""
    for entry in _safe_entries(ctx, path):
        if len(out) > limit:
            return
        is_dir = entry.is_dir()
        out.append((depth, entry.name, is_dir))
        if recursive and is_dir and not _is_link(entry) and entry.name not in PRUNED_DIRS:
            _walk(ctx, entry, depth + 1, recursive, out, limit)


def _walk_files(ctx: ToolContext, root):
    """Yield (relative posix path, file) lazily, in sorted order, without leaving the workspace."""
    stack = [root]
    while stack:
        folder = stack.pop()
        try:
            entries = _safe_entries(ctx, folder)
        except OSError:
            continue
        subdirs = []
        for entry in entries:
            try:
                if entry.is_dir():
                    if not _is_link(entry) and entry.name not in PRUNED_DIRS:
                        subdirs.append(entry)
                elif entry.is_file() and not _is_link(entry):
                    yield entry.relative_to(root).as_posix(), entry
            except OSError:
                continue
        stack.extend(reversed(subdirs))


def list_items(ctx: ToolContext, path: str | None = "", recursive: bool | str | None = False) -> str:
    path = path or ""
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
        _walk(ctx, folder, 0, as_bool(recursive, False), entries, MAX_LIST_ENTRIES)
    except OSError:
        return "Failed to list the folder."
    if not entries:
        return "No items found."
    lines = ["Workspace contents:", ""]
    for depth, name, is_dir in entries[:MAX_LIST_ENTRIES]:
        lines.append(f"{'  ' * depth}{'📁' if is_dir else '📄'} {name}")
    if len(entries) > MAX_LIST_ENTRIES:
        lines.append("… (more items not shown)")
    return "\n".join(lines)


def read_file(ctx: ToolContext, filename: str, start_line: int | str | None = None, end_line: int | str | None = None) -> str:
    start_line = as_int(start_line, None)
    end_line = as_int(end_line, None)
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
    start = start_line if start_line is not None else 1
    end = end_line if end_line is not None else total
    if start < 1 or start > total or end < start:
        return "Invalid line range."
    end = min(end, total)
    return f"Lines {start}-{end} of {total}:\n" + "\n".join(lines[start - 1 : end])


def search_files(ctx: ToolContext, query: str | None = "", name_pattern: str | None = "", path: str | None = "") -> str:
    query, name_pattern, path = query or "", name_pattern or "", path or ""
    if not query and not name_pattern:
        return "Provide query or name_pattern."
    try:
        root = ctx.explorer.resolve(path)
    except ValueError:
        return "Path is outside the workspace."
    if not root.is_dir():
        return f"Folder '{path}' not found."
    needle = query.casefold()
    pattern = name_pattern.casefold()
    results: list[str] = []
    for rel, f in _walk_files(ctx, root):
        if len(results) > MAX_SEARCH_RESULTS:
            break
        if pattern and not fnmatch.fnmatch(f.name.casefold(), pattern):
            continue
        if not needle:
            results.append(rel)
            continue
        try:
            if f.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if needle in line.casefold():
                results.append(f"{rel}:{number}: {line.strip()[:200]}")
                if len(results) > MAX_SEARCH_RESULTS:
                    break
    if not results:
        return "No matches."
    if len(results) > MAX_SEARCH_RESULTS:
        return "\n".join(results[:MAX_SEARCH_RESULTS]) + f"\n(results limited to {MAX_SEARCH_RESULTS})"
    return "\n".join(results)


def edit_file(ctx: ToolContext, filename: str, old_text: str | None = "", new_text: str | None = "", mode: str | None = "replace") -> str:
    old_text, new_text, mode = old_text or "", new_text or "", mode or "replace"
    if not filename:
        return "No filename provided."
    try:
        path = ctx.explorer.resolve(filename)
    except ValueError:
        return "Path is outside the workspace."
    if not path.is_file():
        return f"File '{filename}' not found."
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except UnicodeDecodeError:
        return "Failed to read the file."
    eol = "\r\n" if "\r\n" in text else "\n"
    if mode == "append":
        sep = "" if not text or text.endswith("\n") else eol
        result = text + sep + new_text
    elif mode == "replace":
        if not old_text:
            return "old_text is required for replace."
        if eol == "\r\n":
            old_text = old_text.replace("\r\n", "\n").replace("\n", eol)
            new_text = new_text.replace("\r\n", "\n").replace("\n", eol)
        count = text.count(old_text)
        if count == 0:
            return f"Text not found in '{filename}'."
        if count > 1:
            return f"Text occurs {count} times in '{filename}'; give a longer, unique snippet."
        result = text.replace(old_text, new_text)
    else:
        return "Invalid mode; use 'replace' or 'append'."
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(result)
    return f"Edited '{filename}'."


def file_info(ctx: ToolContext, path: str = "") -> str:
    try:
        target = ctx.explorer.resolve(path)
    except ValueError:
        return "Path is outside the workspace."
    if not target.exists():
        return f"'{path}' not found."
    stat = target.stat()
    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    if target.is_dir():
        return f"Type: folder\nItems: {sum(1 for _ in target.iterdir())}\nModified: {modified}"
    info = ["Type: file", f"Size: {stat.st_size} bytes"]
    try:
        if stat.st_size <= MAX_SEARCH_FILE_BYTES:
            info.append(f"Lines: {len(target.read_text(encoding='utf-8').splitlines())}")
    except (OSError, UnicodeDecodeError):
        pass
    info.append(f"Modified: {modified}")
    return "\n".join(info)


# --- confirmation rules ---------------------------------------------------


def _exists(ctx: ToolContext, rel: str, kind: str = "any") -> bool:
    p = ctx.explorer.resolve(rel)
    if kind == "file":
        return p.is_file()
    if kind == "dir":
        return p.is_dir()
    return p.exists()


def _clip(text: str, n: int) -> str:
    return str(text)[:n]


def _confirm_delete_file(ctx, a):
    f = a.get("filename", "")
    return Confirmation(f"‘{f}’ silinecek.") if _exists(ctx, f, "file") else None


def _confirm_remove_folder(ctx, a):
    f = a.get("folder_name", "")
    return Confirmation(f"‘{f}’ klasörü silinecek.") if _exists(ctx, f, "dir") else None


def _confirm_edit(ctx, a):
    f = a.get("filename", "")
    if not _exists(ctx, f, "file"):
        return None
    new = _clip(a.get("new_text", ""), EDIT_PREVIEW_CHARS)
    if a.get("mode") == "append":
        preview = "+ " + new
    else:
        preview = "- " + _clip(a.get("old_text", ""), EDIT_PREVIEW_CHARS) + "\n+ " + new
    return Confirmation(f"‘{f}’ düzenlenecek.", preview)


def _confirm_write(ctx, a):
    f = a.get("filename", "")
    if not _exists(ctx, f, "file"):
        return None
    return Confirmation(f"‘{f}’ üzerine yazılacak.", _clip(a.get("content", ""), WRITE_PREVIEW_CHARS))


def _confirm_overwrite(src_key: str, dst_key: str, verb: str):
    def rule(ctx, a):
        src, dst = a.get(src_key, ""), a.get(dst_key, "")
        if not _exists(ctx, dst):
            return None
        return Confirmation(f"‘{dst}’ üzerine yazılacak (‘{src}’ {verb}).")

    return rule


def _confirm_zip(ctx, a):
    target = f"{a.get('folder_name', '')}.zip"
    return Confirmation(f"‘{target}’ üzerine yazılacak.") if _exists(ctx, target) else None


def _confirm_extract(ctx, a):
    dest = a.get("destination_folder", "")
    p = ctx.explorer.resolve(dest)
    if p.is_dir() and any(p.iterdir()):
        return Confirmation(f"‘{dest}’ klasörüne açılacak; aynı adlı dosyalar değişebilir.")
    return None


FILE_TOOLS: list[ToolSpec] = [
    _explorer_tool("create_file", "Create a new text file in the workspace.", {"filename": _S}, ["filename"]),
    _explorer_tool("delete_file", "Delete a file from the workspace.", {"filename": _S}, ["filename"], confirm=_confirm_delete_file),
    _explorer_tool(
        "copy_file",
        "Copy a file to a new path.",
        {"source_filename": _S, "destination_filename": _S},
        ["source_filename", "destination_filename"],
        confirm=_confirm_overwrite("source_filename", "destination_filename", "kopyalanıyor"),
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
    , confirm=_confirm_write),
    _explorer_tool(
        "rename_file", "Rename a file.", {"old_filename": _S, "new_filename": _S}, ["old_filename", "new_filename"]
    , confirm=_confirm_overwrite("old_filename", "new_filename", "yeniden adlandırılıyor")),
    _explorer_tool(
        "write_word_file",
        "Write content to a .docx file.",
        {"filename": _S, "content": _S, "font_name": _S, "font_size": {"type": "integer"}},
        ["filename", "content"],
        confirm=_confirm_write,
    ),
    _explorer_tool("read_word_file", "Read the content of a .docx file.", {"filename": _S}, ["filename"]),
    _explorer_tool("create_folder", "Create a new folder in the workspace.", {"folder_name": _S}, ["folder_name"]),
    _explorer_tool("remove_folder", "Remove an empty folder from the workspace.", {"folder_name": _S}, ["folder_name"], confirm=_confirm_remove_folder),
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
        confirm=_confirm_overwrite("source_path", "destination_path", "taşınıyor"),
    ),
    _explorer_tool(
        "rename_folder",
        "Rename a folder.",
        {"old_folder_name": _S, "new_folder_name": _S},
        ["old_folder_name", "new_folder_name"],
        confirm=_confirm_overwrite("old_folder_name", "new_folder_name", "yeniden adlandırılıyor"),
    ),
    _explorer_tool(
        "copy_folder",
        "Copy a folder to a new location.",
        {"source_folder_name": _S, "destination_folder_name": _S},
        ["source_folder_name", "destination_folder_name"],
        confirm=_confirm_overwrite("source_folder_name", "destination_folder_name", "kopyalanıyor"),
    ),
    _explorer_tool("zip_folder", "Zip a folder into a .zip archive.", {"folder_name": _S}, ["folder_name"], confirm=_confirm_zip),
    _explorer_tool(
        "extract_archive",
        "Extract a .zip archive into a destination folder.",
        {"archive_name": _S, "destination_folder": _S},
        ["archive_name", "destination_folder"],
        confirm=_confirm_extract,
    ),
    ToolSpec(
        "search_files",
        "Search the workspace by file name pattern and/or text content. Returns matching paths or path:line: text.",
        _obj(
            {
                "query": {"type": "string", "description": "Text to look for inside files (case-insensitive)."},
                "name_pattern": {"type": "string", "description": "File name glob, e.g. *.md (case-insensitive)."},
                "path": {"type": "string", "description": "Folder to search, relative to the workspace root."},
            }
        ),
        search_files,
    ),
    ToolSpec(
        "edit_file",
        "Edit a text file: replace one unique snippet (mode 'replace') or add text at the end (mode 'append').",
        _obj(
            {
                "filename": _S,
                "old_text": {"type": "string", "description": "Exact unique snippet to replace (replace mode)."},
                "new_text": {"type": "string", "description": "Replacement text, or text to append."},
                "mode": {"type": "string", "enum": ["replace", "append"]},
            },
            ["filename", "new_text"],
        ),
        edit_file,
        confirm=_confirm_edit,
    ),
    ToolSpec(
        "file_info",
        "Show type, size, line count or item count, and modification time of a file or folder.",
        _obj({"path": {"type": "string", "description": "File or folder, relative to the workspace root."}}, ["path"]),
        file_info,
    ),
]
