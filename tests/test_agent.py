import asyncio

import pytest

from meclaw.agent import run_agent
from meclaw.llm.base import ChatEvent, ToolCall
from meclaw.tools.registry import ToolRegistry
from tests.fakes import FakeProvider
from tools.finder.explorer_class import Explorer


@pytest.fixture
def registry(tmp_path):
    return ToolRegistry(Explorer(base_dir=str(tmp_path)))


def collect(agen):
    async def _run():
        return [e async for e in agen]

    return asyncio.run(_run())


def test_plain_text_reply(registry):
    p = FakeProvider(turns=[[ChatEvent("text", "Mer"), ChatEvent("text", "haba")]])
    new = []
    events = collect(run_agent(p, "m", [{"role": "user", "content": "selam"}], registry, new))
    assert [e.text for e in events] == ["Mer", "haba"]
    assert new == [{"role": "assistant", "content": "Merhaba"}]
    assert p.calls[0][0]["role"] == "system" and p.calls[0][1]["content"] == "selam"


def test_tool_result_goes_back_to_model(registry, tmp_path):
    call = ToolCall("c1", "create_file_tool", {"filename": "n.txt"})
    p = FakeProvider(turns=[[ChatEvent("tool_calls", tool_calls=[call])], [ChatEvent("text", "Oluşturdum.")]])
    new = []
    events = collect(run_agent(p, "m", [{"role": "user", "content": "x"}], registry, new))
    assert events[0].type == "tool" and events[0].result == "File 'n.txt' created successfully."
    assert events[-1].text == "Oluşturdum."
    assert p.calls[1][-1] == {"role": "tool", "content": "File 'n.txt' created successfully.", "tool_call_id": "c1", "name": "create_file_tool"}
    assert [m["role"] for m in new] == ["assistant", "tool", "assistant"]
    assert new[0]["tool_calls"] == [{"id": "c1", "name": "create_file_tool", "arguments": {"filename": "n.txt"}}]


def test_turn_limit(registry):
    call = ToolCall("c", "list_items_tool", {})
    p = FakeProvider(turns=[[ChatEvent("tool_calls", tool_calls=[call])]] * 6)
    events = collect(run_agent(p, "m", [{"role": "user", "content": "x"}], registry, []))
    assert len(p.calls) == 5 and events[-1].type == "text" and events[-1].text


def test_partial_text_saved_on_error(registry):
    p = FakeProvider(turns=[[ChatEvent("text", "Yarım")]], error=RuntimeError("down"))
    new = []
    with pytest.raises(RuntimeError):
        collect(run_agent(p, "m", [{"role": "user", "content": "x"}], registry, new))
    assert new == [{"role": "assistant", "content": "Yarım"}]


def test_multiple_tool_calls_in_one_turn(registry):
    calls = [ToolCall("a", "create_file_tool", {"filename": "1.txt"}), ToolCall("b", "create_file_tool", {"filename": "2.txt"})]
    p = FakeProvider(turns=[[ChatEvent("tool_calls", tool_calls=calls)], [ChatEvent("text", "ok")]])
    new = []
    collect(run_agent(p, "m", [{"role": "user", "content": "x"}], registry, new))
    assert [m["role"] for m in new] == ["assistant", "tool", "tool", "assistant"]
    assert [m.get("tool_call_id") for m in new[1:3]] == ["a", "b"]


def test_partial_text_kept_on_generator_close(registry):
    p = FakeProvider(turns=[[ChatEvent("text", "Yar"), ChatEvent("text", "ım")]])
    new = []

    async def _run():
        agen = run_agent(p, "m", [{"role": "user", "content": "x"}], registry, new)
        await agen.__anext__()
        await agen.aclose()

    asyncio.run(_run())
    assert new == [{"role": "assistant", "content": "Yar"}]
