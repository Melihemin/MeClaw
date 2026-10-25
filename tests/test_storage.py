import pytest

from meclaw.storage import Storage


@pytest.fixture
def store(tmp_path):
    return Storage(tmp_path / "x" / "t.db")


def test_create_and_list(store):
    a = store.create_conversation()
    b = store.create_conversation()
    store.add_messages(a["id"], [{"role": "user", "content": "hi"}])
    assert [c["id"] for c in store.list_conversations()] == [a["id"], b["id"]]


def test_messages_roundtrip(store):
    c = store.create_conversation()
    msgs = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "list_items", "arguments": {}}]},
        {"role": "tool", "content": "ok", "tool_call_id": "c1", "name": "list_items"},
        {"role": "assistant", "content": "bitti"},
    ]
    store.add_messages(c["id"], msgs)
    assert store.get_conversation(c["id"])["messages"] == msgs


def test_turkish_roundtrip(store):
    c = store.create_conversation()
    store.update_conversation(c["id"], title="Çiğdem'in ödevi ğüşıöçİ", provider="ollama", model="qwen3:8b")
    store.add_messages(c["id"], [{"role": "user", "content": "ğüşıöçİ"}])
    got = store.get_conversation(c["id"])
    assert got["title"] == "Çiğdem'in ödevi ğüşıöçİ" and got["messages"][0]["content"] == "ğüşıöçİ"
    assert got["provider"] == "ollama" and got["model"] == "qwen3:8b"


def test_delete_cascades(store):
    c = store.create_conversation()
    store.add_messages(c["id"], [{"role": "user", "content": "x"}])
    assert store.delete_conversation(c["id"]) is True
    assert store.get_conversation(c["id"]) is None and store.delete_conversation(c["id"]) is False
