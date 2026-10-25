"""Workspace file browsing for the Files panel: listing, previews and uploads."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from tools.finder.explorer_class import Explorer

MAX_PREVIEW_BYTES = 200_000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}
_UNSAFE_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def relative(explorer: Explorer, path: Path) -> str:
    rel = path.relative_to(explorer.base_dir).as_posix()
    return "" if rel == "." else rel


def list_dir(explorer: Explorer, rel: str) -> dict:
    """Entries of a workspace folder, folders first. Raises ValueError,
    FileNotFoundError or NotADirectoryError."""
    folder = explorer.resolve(rel)
    if not folder.exists():
        raise FileNotFoundError(rel)
    if not folder.is_dir():
        raise NotADirectoryError(rel)
    entries = []
    for child in folder.iterdir():
        stat = child.stat()
        is_dir = child.is_dir()
        entries.append({
            "name": child.name,
            "path": relative(explorer, child),
            "type": "dir" if is_dir else "file",
            "size": None if is_dir else stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].casefold()))
    return {"path": relative(explorer, folder), "entries": entries}


def preview(explorer: Explorer, rel: str) -> dict:
    """Describe a file for the preview pane: text, docx, image, binary or too_large."""
    path = explorer.resolve(rel)
    if not path.exists():
        raise FileNotFoundError(rel)
    if path.is_dir():
        raise IsADirectoryError(rel)
    size = path.stat().st_size
    result = {"name": path.name, "path": relative(explorer, path), "size": size}
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return {**result, "kind": "image"}
    if suffix == ".docx":
        return {**result, "kind": "docx", "content": explorer.read_word_file(result["path"])}
    if size > MAX_PREVIEW_BYTES:
        return {**result, "kind": "too_large"}
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        return {**result, "kind": "binary"}
    try:
        return {**result, "kind": "text", "content": data.decode("utf-8")}
    except UnicodeDecodeError:
        return {**result, "kind": "binary"}


def clean_name(name: str) -> str:
    """Reduce an uploaded file name to a safe single path component ('' if unusable)."""
    base = name.replace("\\", "/").split("/")[-1].strip()
    if base in ("", ".", ".."):
        return ""
    return _UNSAFE_NAME_CHARS.sub("_", base)


def unique_path(folder: Path, name: str) -> Path:
    candidate = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while candidate.exists():
        candidate = folder / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def save_upload(explorer: Explorer, rel_dir: str, name: str, data: bytes) -> str:
    """Write ``data`` into a workspace folder without overwriting; returns the new relative path."""
    folder = explorer.resolve(rel_dir)
    if not folder.is_dir():
        raise NotADirectoryError(rel_dir)
    safe = clean_name(name)
    if not safe:
        raise ValueError("Invalid file name.")
    target = unique_path(folder, safe)
    explorer.resolve(relative(explorer, target))  # re-check containment of the final path
    with open(target, "xb") as f:
        f.write(data)
    return relative(explorer, target)
