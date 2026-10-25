import asyncio

from meclaw.memory import MEMORY_RULES, build_system_prompt
from meclaw.storage import Storage
from tests.fakes import make_registry


def run(reg, name, **args):
    return asyncio.run(reg.run(name, args))


def test_memory_crud(tmp_path):
    s = Storage(tmp_path / "m.db")
    a = s.add_memory("Adım Melih")
    b = s.add_memory("Python seviyorum")
    assert [m["content"] for m in s.list_memories()] == ["Adım Melih", "Python seviyorum"]
    assert s.update_memory(a["id"], "Adım Melih Emin") and not s.update_memory(999, "x")
    assert s.delete_memory(b["id"]) and not s.delete_memory(b["id"])
    assert s.clear_memories() == 1 and s.list_memories() == []


def test_build_system_prompt():
    mems = [{"id": 1, "content": "Adım Melih"}, {"id": 2, "content": "Kahve sever"}]
    out = build_system_prompt("BASE", mems, True)
    assert out.startswith("BASE\n\n") and MEMORY_RULES in out
    assert out.endswith("Known facts about the user:\n[1] Adım Melih\n[2] Kahve sever")
    assert build_system_prompt("BASE", mems, False) == "BASE"
    assert build_system_prompt("BASE", [], True).endswith("Known facts about the user:\n(none yet)")


def test_prompt_keeps_newest_100():
    mems = [{"id": i, "content": f"n{i}"} for i in range(1, 151)]
    out = build_system_prompt("B", mems, True)
    assert "[51] n51" in out and "[50] n50" not in out


def test_rules_are_short():
    assert len(MEMORY_RULES) < 600


def test_remember_forget_tools(tmp_path):
    storage = Storage(tmp_path / "m.db")
    reg = make_registry(tmp_path / "ws", storage=storage)
    assert run(reg, "remember", content="Adı Melih") == "Saved memory #1."
    assert run(reg, "remember", content="x" * 501) == "Memory is too long (max 500 characters)."
    assert run(reg, "remember", content="  ") == "Memory is empty."
    assert run(reg, "forget", memory_id=1) == "Forgot memory #1."
    assert run(reg, "forget", memory_id=1) == "No memory #1."
    assert not {"remember", "forget"} & make_registry(tmp_path / "ws", storage=storage, memory=False).names()
    assert not {"remember", "forget"} & make_registry(tmp_path / "ws").names()
