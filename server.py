"""FastAPI chat server for MeClaw."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from meclaw.agent import run_agent
from meclaw.config import load_settings
from meclaw.llm.base import Provider
from meclaw.llm.ollama import OllamaProvider
from meclaw.llm.openai import OpenAIProvider
from meclaw.storage import Storage
from meclaw.tools.registry import ToolRegistry
from tools.finder.explorer_class import Explorer

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_TITLE = "Yeni sohbet"
TITLE_LENGTH = 40
DEFAULT_ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-*.…]+")


class ChatRequest(BaseModel):
    conversation_id: str
    provider: str
    model: str
    message: str


def sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def redact(text: str) -> str:
    """Hide API keys (full or masked) that provider errors may echo back."""
    return _KEY_PATTERN.sub("sk-***", text)


def create_app(
    providers: dict[str, Provider],
    registry: ToolRegistry,
    storage: Storage,
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    app = FastAPI()
    # Reject foreign Host headers so DNS rebinding cannot reach the local API.
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=allowed_hosts or DEFAULT_ALLOWED_HOSTS
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def get_provider(name: str) -> Provider:
        provider = providers.get(name)
        if provider is None:
            raise HTTPException(404, detail=f"Unknown provider: {name}")
        return provider

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/providers")
    async def list_providers():
        result = []
        for name, provider in providers.items():
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
        history = storage.get_conversation(req.conversation_id)["messages"]
        new_messages: list[dict] = []

        async def gen():
            try:
                try:
                    async for event in run_agent(provider, req.model, history, registry, new_messages):
                        if event.type == "text":
                            yield sse("text", {"text": event.text})
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
                # Runs on normal end and on client disconnect (GeneratorExit/CancelledError);
                # run_agent records partial text on those too, so it is saved here.
                if new_messages:
                    try:
                        storage.add_messages(req.conversation_id, new_messages)
                    except Exception:
                        logger.exception("Saving messages failed")
            yield sse("done", {"conversation_id": req.conversation_id})

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def build_default_app() -> FastAPI:
    settings = load_settings()
    providers = {
        "ollama": OllamaProvider(settings.ollama_host),
        "openai": OpenAIProvider(settings.openai_api_key),
    }
    return create_app(providers, ToolRegistry(Explorer()), Storage(settings.db_path))


if __name__ == "__main__":
    uvicorn.run(build_default_app(), host="127.0.0.1", port=8000)
