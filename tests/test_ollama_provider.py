import asyncio
from types import SimpleNamespace

import ollama
import pytest

from meclaw.llm.ollama import OllamaProvider, to_ollama_messages

TOOLS = [{"type": "function", "function": {"name": "create_file_tool", "parameters": {}}}]


def chunk(content="", tool_calls=None, thinking=None):
    return SimpleNamespace(
        message=SimpleNamespace(content=content, thinking=thinking, tool_calls=tool_calls)
    )


def tool_call(name, arguments):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


class FakeClient:
    def __init__(self, chunks=None, models=None, list_error=None, raise_on="await", fail_with_tools=False):
        self.chunks = chunks or []
        self.models = models or []
        self.list_error = list_error
        self.raise_on = raise_on
        self.fail_with_tools = fail_with_tools
        self.chat_calls = []

    async def list(self):
        if self.list_error:
            raise self.list_error
        return SimpleNamespace(models=[SimpleNamespace(model=m) for m in self.models])

    async def chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        err = ollama.ResponseError("registry.ollama.ai/library/gemma3 does not support tools", 400)
        failing = self.fail_with_tools and kwargs.get("tools")
        if failing and self.raise_on == "await":
            raise err

        async def gen():
            if failing:
                raise err
            for c in self.chunks:
                yield c

        return gen()


def collect(agen):
    async def run():
        return [e async for e in agen]

    return asyncio.run(run())


def make(fake):
    return OllamaProvider("http://localhost:11434", client=fake)


def test_to_ollama_messages():
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "read_file_tool", "arguments": {"filename": "a"}}]},
        {"role": "tool", "content": "hi", "tool_call_id": "c1", "name": "read_file_tool"},
    ]
    assert to_ollama_messages(msgs) == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file_tool", "arguments": {"filename": "a"}}}]},
        {"role": "tool", "content": "hi", "tool_name": "read_file_tool"},
    ]


def test_stream_text_and_tool_calls():
    fake = FakeClient(chunks=[
        chunk("Mer", thinking="hmm"),
        chunk("haba"),
        chunk("", tool_calls=[tool_call("create_file_tool", {"filename": "a"})]),
    ])
    events = collect(make(fake).chat("qwen3:8b", [{"role": "user", "content": "x"}], TOOLS))
    assert [e.text for e in events if e.type == "text"] == ["Mer", "haba"]
    tcs = [e for e in events if e.type == "tool_calls"]
    assert len(tcs) == 1 and events[-1] is tcs[0]
    tc = tcs[0].tool_calls[0]
    assert tc.name == "create_file_tool" and tc.arguments == {"filename": "a"} and tc.id
    assert fake.chat_calls[0]["stream"] is True
    assert fake.chat_calls[0]["model"] == "qwen3:8b"


@pytest.mark.parametrize("raise_on", ["await", "iterate"])
def test_retries_without_tools_when_model_lacks_support(raise_on):
    fake = FakeClient(chunks=[chunk("ok")], fail_with_tools=True, raise_on=raise_on)
    events = collect(make(fake).chat("gemma3", [{"role": "user", "content": "x"}], TOOLS))
    assert [e.text for e in events] == ["ok"]
    assert len(fake.chat_calls) == 2
    assert fake.chat_calls[-1].get("tools") is None


def test_other_response_error_propagates():
    class Bad(FakeClient):
        async def chat(self, **kwargs):
            raise ollama.ResponseError("model not found", 404)

    with pytest.raises(ollama.ResponseError):
        collect(make(Bad()).chat("x", [{"role": "user", "content": "x"}], TOOLS))


def test_list_models_and_status():
    provider = make(FakeClient(models=["qwen3:8b", "llama3.2:latest"]))
    assert asyncio.run(provider.list_models()) == ["llama3.2:latest", "qwen3:8b"]
    assert asyncio.run(provider.status()) == (True, "")


def test_status_when_unreachable():
    provider = make(FakeClient(list_error=ConnectionError("down")))
    ready, reason = asyncio.run(provider.status())
    assert ready is False and "Ollama" in reason
