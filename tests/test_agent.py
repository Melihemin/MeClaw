import asyncio

import pytest

from meclaw.agent import run_agent
from meclaw.llm.base import ChatEvent, ToolCall
from tests.fakes import FakeProvider, make_registry


@pytest.fixture
def registry(tmp_path):
    return make_registry(tmp_path)


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
    call = ToolCall("c1", "create_file", {"filename": "n.txt"})
    p = FakeProvider(turns=[[ChatEvent("tool_calls", tool_calls=[call])], [ChatEvent("text", "Oluşturdum.")]])
    new = []
    events = collect(run_agent(p, "m", [{"role": "user", "content": "x"}], registry, new))
    assert events[0].type == "tool" and events[0].result == "File 'n.txt' created successfully."
    assert events[-1].text == "Oluşturdum."
    assert p.calls[1][-1] == {"role": "tool", "content": "File 'n.txt' created successfully.", "tool_call_id": "c1", "name": "create_file"}
    assert [m["role"] for m in new] == ["assistant", "tool", "assistant"]
    assert new[0]["tool_calls"] == [{"id": "c1", "name": "create_file", "arguments": {"filename": "n.txt"}}]


def test_turn_limit(registry):
    call = ToolCall("c", "list_items", {})
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
    calls = [ToolCall("a", "create_file", {"filename": "1.txt"}), ToolCall("b", "create_file", {"filename": "2.txt"})]
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


def delete_turns(*names):
    calls = [ToolCall(f"c{i}", "delete_file", {"filename": n}) for i, n in enumerate(names, 1)]
    return FakeProvider(turns=[[ChatEvent("tool_calls", tool_calls=calls)], [ChatEvent("text", "tamam")]])


def test_confirmed_tool_runs(registry, tmp_path):
    (tmp_path / "a.txt").write_text("x")
    seen = []

    async def yes(req):
        seen.append(req)
        return True

    new = []
    events = collect(run_agent(delete_turns("a.txt"), "m", [{"role": "user", "content": "sil"}], registry, new, confirm=yes))
    assert [e.type for e in events] == ["confirm", "confirm_result", "tool", "text"]
    assert seen[0].description == "‘a.txt’ silinecek."
    assert seen[0].name == "delete_file" and seen[0].arguments == {"filename": "a.txt"}
    assert events[0].id == seen[0].id == events[1].id and len(seen[0].id) == 32
    assert events[0].description == "‘a.txt’ silinecek." and events[0].name == "delete_file"
    assert events[1].approved is True
    assert not (tmp_path / "a.txt").exists()


def test_denied_tool_not_run(registry, tmp_path):
    (tmp_path / "a.txt").write_text("x")

    async def no(req):
        return False

    new = []
    events = collect(run_agent(delete_turns("a.txt"), "m", [{"role": "user", "content": "sil"}], registry, new, confirm=no))
    assert (tmp_path / "a.txt").exists()
    assert new[1]["content"] == "Denied by the user: ‘a.txt’ silinecek."
    assert events[1].type == "confirm_result" and events[1].approved is False
    assert events[2].type == "tool" and events[2].result == "Denied by the user: ‘a.txt’ silinecek."


def test_no_confirm_hook_denies(registry, tmp_path):
    (tmp_path / "a.txt").write_text("x")
    new = []
    collect(run_agent(delete_turns("a.txt"), "m", [{"role": "user", "content": "sil"}], registry, new))
    assert (tmp_path / "a.txt").exists()
    assert new[1]["content"] == "Denied by the user: ‘a.txt’ silinecek."


def test_raising_confirm_hook_denies(registry, tmp_path):
    (tmp_path / "a.txt").write_text("x")

    async def boom(req):
        raise RuntimeError("x")

    new = []
    events = collect(run_agent(delete_turns("a.txt"), "m", [{"role": "user", "content": "sil"}], registry, new, confirm=boom))
    assert (tmp_path / "a.txt").exists() and events[1].approved is False
    assert new[1]["content"] == "Denied by the user: ‘a.txt’ silinecek."


def test_two_confirmations_in_one_turn(registry, tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.txt").write_text("x")

    async def first_only(req):
        return req.arguments["filename"] == "a.txt"

    events = collect(run_agent(delete_turns("a.txt", "b.txt"), "m", [{"role": "user", "content": "sil"}], registry, [], confirm=first_only))
    assert not (tmp_path / "a.txt").exists() and (tmp_path / "b.txt").exists()
    assert [e.type for e in events if e.type.startswith("confirm")] == ["confirm", "confirm_result", "confirm", "confirm_result"]


def test_unconfirmed_tools_skip_hook(registry, tmp_path):
    async def boom(req):
        raise AssertionError("should not be called")

    call = ToolCall("c1", "create_file", {"filename": "x.txt"})
    p = FakeProvider(turns=[[ChatEvent("tool_calls", tool_calls=[call])], [ChatEvent("text", "ok")]])
    events = collect(run_agent(p, "m", [{"role": "user", "content": "x"}], registry, [], confirm=boom))
    assert [e.type for e in events] == ["tool", "text"] and (tmp_path / "x.txt").exists()
