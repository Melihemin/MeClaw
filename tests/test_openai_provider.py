import asyncio
from types import SimpleNamespace

import pytest

from meclaw.llm.base import ToolCall
from meclaw.llm.openai import (
    OpenAIProvider,
    ToolCallAccumulator,
    filter_chat_models,
    to_openai_messages,
)

TOOLS = [{"type": "function", "function": {"name": "create_file", "parameters": {}}}]
NO_KEY = "OPENAI_API_KEY tanımlı değil"


def delta(index=0, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


def chunk(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))])


class FakeClient:
    def __init__(self, chunks=None, models=None):
        self.chunks = chunks or []
        self.model_ids = models or []
        self.calls = []
        self.models = SimpleNamespace(list=self._list)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _list(self):
        return SimpleNamespace(data=[SimpleNamespace(id=m) for m in self.model_ids])

    async def _create(self, **kwargs):
        self.calls.append(kwargs)

        async def gen():
            for c in self.chunks:
                yield c

        return gen()


def collect(agen):
    async def run():
        return [e async for e in agen]

    return asyncio.run(run())


def make(fake):
    return OpenAIProvider("sk-test", client=fake)


def test_to_openai_messages():
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "read_file", "arguments": {"filename": "ç.txt"}}]},
        {"role": "tool", "content": "hi", "tool_call_id": "c1", "name": "read_file"},
    ]
    out = to_openai_messages(msgs)
    assert out[0] == {"role": "system", "content": "s"}
    assert out[1] == {"role": "user", "content": "u"}
    assert out[2] == {"role": "assistant", "content": "a"}
    assert out[3]["content"] == ""
    assert out[3]["tool_calls"] == [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"filename": "ç.txt"}'}}]
    assert out[4] == {"role": "tool", "content": "hi", "tool_call_id": "c1"}


def test_filter_chat_models():
    ids = ["gpt-4o", "gpt-4o-audio-preview", "o3-mini", "dall-e-3", "text-embedding-3-small", "gpt-4o-realtime-preview", "gpt-4o-mini-tts", "o4-mini", "o1-pro", "gpt-5-pro", "gpt-5-codex"]
    assert filter_chat_models(ids) == ["gpt-4o", "o3-mini", "o4-mini"]


def test_accumulator_merges_fragments():
    acc = ToolCallAccumulator()
    acc.add([delta(index=0, id="c1", name="create_file", arguments='{"file')])
    acc.add([delta(index=0, arguments='name": "a.txt"}')])
    assert acc.result() == [ToolCall("c1", "create_file", {"filename": "a.txt"})]


def test_accumulator_parallel_calls_ordered_by_index():
    acc = ToolCallAccumulator()
    acc.add([delta(index=1, id="b", name="y", arguments="{}"), delta(index=0, id="a", name="x", arguments="{}")])
    assert [t.id for t in acc.result()] == ["a", "b"]


def test_accumulator_invalid_json_gives_empty_args():
    acc = ToolCallAccumulator()
    acc.add([delta(index=0, id="c", name="x", arguments="{bad")])
    assert acc.result()[0].arguments == {}


def test_status_without_key():
    assert asyncio.run(OpenAIProvider(None).status()) == (False, NO_KEY)


def test_status_with_key_makes_no_call():
    fake = FakeClient()
    assert asyncio.run(make(fake).status()) == (True, "")
    assert fake.calls == []


def test_list_models_filters_and_sorts():
    fake = FakeClient(models=["o4-mini", "dall-e-3", "gpt-4o"])
    assert asyncio.run(make(fake).list_models()) == ["gpt-4o", "o4-mini"]


def test_list_models_without_key():
    with pytest.raises(RuntimeError, match=NO_KEY):
        asyncio.run(OpenAIProvider(None).list_models())


def test_chat_without_key():
    with pytest.raises(RuntimeError, match=NO_KEY):
        collect(OpenAIProvider(None).chat("gpt-4o", [{"role": "user", "content": "x"}], TOOLS))


def test_stream_text_then_tool_calls():
    fake = FakeClient(chunks=[
        SimpleNamespace(choices=[]),
        chunk("Mer"),
        chunk("haba"),
        chunk(None, [delta(0, "c1", "create_file", '{"filename"')]),
        chunk(None, [delta(0, None, None, ': "a"}')]),
        chunk(None),
    ])
    events = collect(make(fake).chat("gpt-4o", [{"role": "user", "content": "x"}], TOOLS))
    assert [e.text for e in events if e.type == "text"] == ["Mer", "haba"]
    tcs = [e for e in events if e.type == "tool_calls"]
    assert len(tcs) == 1 and events[-1] is tcs[0]
    assert tcs[0].tool_calls == [ToolCall("c1", "create_file", {"filename": "a"})]
    call = fake.calls[0]
    assert call["stream"] is True and call["model"] == "gpt-4o" and call["tools"] == TOOLS


def test_empty_tools_omits_tools_param():
    fake = FakeClient(chunks=[chunk("ok")])
    events = collect(make(fake).chat("gpt-4o", [{"role": "user", "content": "x"}], []))
    assert [e.text for e in events] == ["ok"]
    assert "tools" not in fake.calls[0]
