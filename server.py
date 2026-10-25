"""FastAPI chat server for MeClaw."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from meclaw import files
from meclaw.agent import SYSTEM_PROMPT, ConfirmRequest, close_open_tool_calls, run_agent
from meclaw.config import DEFAULT_WORKSPACE, Settings, load_settings
from meclaw.llm.base import Provider
from meclaw.llm.ollama import OllamaProvider
from meclaw.llm.openai import OpenAIProvider
from meclaw.settings_store import save_settings
from meclaw.storage import Storage
from meclaw.tools import build_registry
from meclaw.tools.base import ToolContext, ToolRegistry
from tools.finder.explorer_class import Explorer

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_TITLE = "Yeni sohbet"
TITLE_LENGTH = 40
DEFAULT_ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-*.…]+")
_HOST_PATTERN = re.compile(r"^https?://\S+$")
MAX_PROMPT_LENGTH = 8000
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
LOCAL_HEADER = "X-MeClaw"
CONFIRM_TIMEOUT = 300  # seconds a destructive tool call waits for the user's decision

# apply_settings(changes) saves {ENV_NAME: value | None} and returns the reloaded
# settings plus freshly built providers.
ApplySettings = Callable[[dict], tuple[Settings, dict[str, Provider]]]


class ChatRequest(BaseModel):
    conversation_id: str
    provider: str
    model: str
    message: str


class ConfirmDecision(BaseModel):
    confirm_id: str
    approved: bool


class SettingsUpdate(BaseModel):
    ollama_host: str | None = None
    openai_api_key: str | None = None
    clear_openai_api_key: bool = False
    default_provider: str | None = None
    default_model: str | None = None
    system_prompt: str | None = None
    workspace: str | None = None


def sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def redact(text: str) -> str:
    """Hide API keys (full or masked) that provider errors may echo back."""
    return _KEY_PATTERN.sub("sk-***", text)


def _resolve(fut: asyncio.Future, approved: bool) -> None:
    if not fut.done():
        fut.set_result(approved)


def open_in_file_manager(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - local desktop action on a workspace folder
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def is_drive_root(path: Path) -> bool:
    return path.resolve().parent == path.resolve()


def create_app(
    providers: dict[str, Provider],
    registry: ToolRegistry,
    storage: Storage,
    allowed_hosts: list[str] | None = None,
    settings: Settings | None = None,
    apply_settings: ApplySettings | None = None,
    make_registry: Callable[[Settings], ToolRegistry] | None = None,
    open_folder: Callable[[Path], None] = open_in_file_manager,
) -> FastAPI:
    app = FastAPI()
    # Reject foreign Host headers so DNS rebinding cannot reach the local API.
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=allowed_hosts or DEFAULT_ALLOWED_HOSTS
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    # Replaced as a whole when settings are saved, so in-flight chats keep their provider.
    state = SimpleNamespace(settings=settings, providers=providers, registry=registry)
    # Pending confirmations: id -> (loop the waiting chat runs on, its decision future).
    state.pending: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Future]] = {}
    hosts = allowed_hosts or DEFAULT_ALLOWED_HOSTS

    def require_local(request: Request) -> None:
        # Uploads and "open folder" are plain POSTs a foreign page could send blind; the
        # custom header forces a CORS preflight that a cross-site page cannot pass.
        if request.headers.get(LOCAL_HEADER) != "1":
            raise HTTPException(403, detail="Forbidden")
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in hosts:
            raise HTTPException(403, detail="Forbidden")

    def workspace_path(rel: str, *, kind: str = "any") -> Path:
        try:
            path = state.registry.explorer.resolve(rel)
        except ValueError:
            raise HTTPException(400, detail="Path is outside the workspace.")
        if not path.exists():
            raise HTTPException(404, detail="Not found")
        if kind == "dir" and not path.is_dir():
            raise HTTPException(400, detail="Not a folder")
        if kind == "file" and not path.is_file():
            raise HTTPException(400, detail="Not a file")
        return path

    def get_provider(name: str) -> Provider:
        provider = state.providers.get(name)
        if provider is None:
            raise HTTPException(404, detail=f"Unknown provider: {name}")
        return provider

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/providers")
    async def list_providers():
        result = []
        for name, provider in state.providers.items():
            try:
                ready, reason = await provider.status()
            except Exception as exc:
                reason = redact(str(exc))
                logger.error("Provider status failed: %s: %s", name, reason)
                ready = False
            result.append({"name": name, "ready": bool(ready), "reason": reason})
        return result

    @app.get("/api/models")
    async def list_models(provider: str):
        p = get_provider(provider)
        try:
            return {"models": await p.list_models()}
        except Exception as exc:
            detail = redact(str(exc))
            logger.error("Listing models failed: %s: %s", provider, detail)
            raise HTTPException(503, detail=detail)

    def settings_payload() -> dict:
        s = state.settings
        key = s.openai_api_key or ""
        return {
            "ollama_host": s.ollama_host,
            "openai_key_set": bool(key),
            "openai_key_hint": f"…{key[-4:]}" if len(key) >= 8 else "",
            "default_provider": s.default_provider or "",
            "default_model": s.default_model or "",
            "system_prompt": s.system_prompt or "",
            "system_prompt_default": SYSTEM_PROMPT,
            "workspace": str(s.workspace_dir),
            "workspace_default": str(DEFAULT_WORKSPACE),
            "providers": list(state.providers),
        }

    def require_settings() -> None:
        if state.settings is None or apply_settings is None:
            raise HTTPException(404, detail="Settings are not available")

    @app.get("/api/settings")
    def get_settings():
        require_settings()
        return settings_payload()

    @app.put("/api/settings")
    def put_settings(req: SettingsUpdate):
        require_settings()
        changes: dict[str, str | None] = {}
        if req.ollama_host is not None:
            host = req.ollama_host.strip()
            if host and not _HOST_PATTERN.match(host):
                raise HTTPException(400, detail="Ollama adresi http:// veya https:// ile başlamalı.")
            changes["OLLAMA_HOST"] = host or None
        if req.clear_openai_api_key:
            changes["OPENAI_API_KEY"] = None
        elif req.openai_api_key and req.openai_api_key.strip():
            changes["OPENAI_API_KEY"] = req.openai_api_key.strip()
        if req.default_provider is not None:
            name = req.default_provider.strip()
            if name and name not in state.providers:
                raise HTTPException(400, detail=f"Bilinmeyen sağlayıcı: {name}")
            changes["MECLAW_DEFAULT_PROVIDER"] = name or None
        if req.default_model is not None:
            changes["MECLAW_DEFAULT_MODEL"] = req.default_model.strip() or None
        if req.system_prompt is not None:
            prompt = req.system_prompt.strip()
            if len(prompt) > MAX_PROMPT_LENGTH:
                raise HTTPException(400, detail=f"Sistem istemi en fazla {MAX_PROMPT_LENGTH} karakter olabilir.")
            changes["MECLAW_SYSTEM_PROMPT"] = None if prompt in ("", SYSTEM_PROMPT) else prompt
        if req.workspace is not None:
            raw = req.workspace.strip()
            if raw:
                folder = Path(raw)
                if not folder.is_absolute() or is_drive_root(folder):
                    raise HTTPException(
                        400, detail="Çalışma klasörü tam bir yol olmalı ve sürücü kökü olamaz."
                    )
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise HTTPException(400, detail=f"Klasör oluşturulamadı: {exc.strerror or exc}")
            changes["MECLAW_WORKSPACE"] = raw or None
        if changes:
            old_workspace = state.settings.workspace_dir
            state.settings, state.providers = apply_settings(changes)
            if make_registry and state.settings.workspace_dir != old_workspace:
                state.registry = make_registry(state.settings)
        return settings_payload()

    @app.get("/api/files")
    def list_files(path: str = ""):
        workspace_path(path, kind="dir")
        return files.list_dir(state.registry.explorer, path)

    @app.get("/api/files/preview")
    def preview_file(path: str):
        workspace_path(path, kind="file")
        return files.preview(state.registry.explorer, path)

    @app.get("/api/files/download")
    def download_file(path: str, inline: bool = False):
        target = workspace_path(path, kind="file")
        return FileResponse(
            target,
            filename=target.name,
            content_disposition_type="inline" if inline else "attachment",
            headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"},
        )

    @app.post("/api/files/upload")
    async def upload_file(request: Request, name: str, path: str = ""):
        require_local(request)
        workspace_path(path, kind="dir")
        if int(request.headers.get("content-length") or 0) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, detail="Dosya 50 MB sınırını aşıyor.")
        data = await request.body()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, detail="Dosya 50 MB sınırını aşıyor.")
        try:
            saved = files.save_upload(state.registry.explorer, path, name, data)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc))
        return {"path": saved}

    @app.post("/api/workspace/open", status_code=204)
    def open_workspace(request: Request, path: str = ""):
        require_local(request)
        open_folder(workspace_path(path, kind="dir"))
        return Response(status_code=204)

    @app.get("/api/conversations")
    def list_conversations():
        return storage.list_conversations()

    @app.post("/api/conversations")
    def create_conversation():
        return storage.create_conversation()

    @app.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: str):
        conv = storage.get_conversation(conversation_id)
        if conv is None:
            raise HTTPException(404, detail="Conversation not found")
        return conv

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str):
        if not storage.delete_conversation(conversation_id):
            raise HTTPException(404, detail="Conversation not found")
        return Response(status_code=204)

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        conv = storage.get_conversation(req.conversation_id)
        if conv is None:
            raise HTTPException(404, detail="Conversation not found")
        provider = get_provider(req.provider)
        text = req.message.strip()
        if not text:
            raise HTTPException(400, detail="Message must not be empty")

        storage.add_messages(req.conversation_id, [{"role": "user", "content": req.message}])
        title = text[:TITLE_LENGTH] if conv["title"] == DEFAULT_TITLE else None
        storage.update_conversation(
            req.conversation_id, title=title, provider=req.provider, model=req.model
        )
        # Heals conversations saved with unanswered tool calls by older builds.
        history = close_open_tool_calls(storage.get_conversation(req.conversation_id)["messages"])
        system_prompt = (state.settings and state.settings.system_prompt) or SYSTEM_PROMPT
        tools = state.registry
        new_messages: list[dict] = []
        # This stream's own futures. ask() looks here, not in state.pending, because a
        # decision POST pops state.pending before ask() may have started waiting.
        my_pending: dict[str, asyncio.Future] = {}

        def register(confirm_id: str) -> asyncio.Future:
            fut = my_pending.get(confirm_id)
            if fut is None:
                loop = asyncio.get_running_loop()
                fut = loop.create_future()
                my_pending[confirm_id] = fut
                state.pending[confirm_id] = (loop, fut)
            return fut

        async def ask(confirm_req: ConfirmRequest) -> bool:
            fut = register(confirm_req.id)
            try:
                return await asyncio.wait_for(fut, CONFIRM_TIMEOUT)
            except TimeoutError:
                return False
            finally:
                state.pending.pop(confirm_req.id, None)
                my_pending.pop(confirm_req.id, None)

        async def gen():
            try:
                try:
                    async for event in run_agent(
                        provider, req.model, history, tools, new_messages, system_prompt,
                        confirm=ask,
                    ):
                        if event.type == "text":
                            yield sse("text", {"text": event.text})
                        elif event.type == "confirm":
                            # Registered before the event goes out, so a fast decision
                            # cannot arrive ahead of its future.
                            register(event.id)
                            yield sse("confirm", {
                                "id": event.id,
                                "name": event.name,
                                "description": event.description,
                                "preview": event.preview,
                            })
                        elif event.type == "confirm_result":
                            yield sse("confirm_result", {"id": event.id, "approved": event.approved})
                        else:
                            yield sse("tool", {
                                "name": event.name,
                                "arguments": event.arguments,
                                "result": event.result,
                            })
                except Exception as exc:
                    message = redact(str(exc))
                    logger.error(
                        "Chat failed (provider=%s, model=%s): %s", req.provider, req.model, message
                    )
                    yield sse("error", {"message": message})
            finally:
                # A closed stream can no longer show a decision: drop its waiting futures.
                for confirm_id, fut in list(my_pending.items()):
                    state.pending.pop(confirm_id, None)
                    fut.cancel()
                my_pending.clear()
                # Runs on normal end and on client disconnect (GeneratorExit/CancelledError);
                # run_agent records partial text on those too, so it is saved here.
                if new_messages:
                    try:
                        storage.add_messages(req.conversation_id, close_open_tool_calls(new_messages))
                    except Exception:
                        logger.exception("Saving messages failed")
            yield sse("done", {"conversation_id": req.conversation_id})

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/chat/confirm", status_code=204)
    def confirm_tool(request: Request, decision: ConfirmDecision):
        require_local(request)
        # pop() claims the entry atomically, so a repeated decision gets 404.
        entry = state.pending.pop(decision.confirm_id, None)
        if entry is None or entry[1].done():
            raise HTTPException(404, detail="Confirmation not found")
        loop, fut = entry
        # The request may run on another thread or loop; resolve on the future's own loop.
        loop.call_soon_threadsafe(_resolve, fut, decision.approved)
        return Response(status_code=204)

    return app


def build_providers(settings: Settings) -> dict[str, Provider]:
    return {
        "ollama": OllamaProvider(settings.ollama_host),
        "openai": OpenAIProvider(settings.openai_api_key),
    }


def build_registry_for(settings: Settings) -> ToolRegistry:
    return build_registry(ToolContext(Explorer(settings.workspace_dir)))


def apply_env_settings(changes: dict) -> tuple[Settings, dict[str, Provider]]:
    save_settings(changes)
    settings = load_settings()
    return settings, build_providers(settings)


def build_default_app() -> FastAPI:
    settings = load_settings()
    return create_app(
        build_providers(settings),
        build_registry_for(settings),
        Storage(settings.db_path),
        settings=settings,
        apply_settings=apply_env_settings,
        make_registry=build_registry_for,
    )


if __name__ == "__main__":
    uvicorn.run(build_default_app(), host="127.0.0.1", port=8000)
