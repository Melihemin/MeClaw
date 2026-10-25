import asyncio
import queue
import threading

import pytest
from fastapi.testclient import TestClient

from meclaw.llm.base import ChatEvent, ToolCall
from meclaw.storage import Storage
from server import create_app
from tests.fakes import FakeProvider, make_registry
from tests.helpers import parse_sse

WAIT = 3  # seconds; every queue read is bounded so a bug fails instead of hanging
LOCAL = {"X-MeClaw": "1"}


class Tap:
    """ASGI wrapper that publishes /api/chat SSE events as they are sent.

    Starlette's TestClient buffers the whole response body, so a test cannot see the
    `confirm` event through the response while the stream is paused. The tap sees each
    chunk at send time instead. Setting `disconnect` makes the next receive() report
    http.disconnect, which is how a closed browser tab reaches the app.
    """

    def __init__(self, app):
        self.app = app
        self.events: queue.Queue = queue.Queue()
        self.disconnect = threading.Event()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/api/chat":
            return await self.app(scope, receive, send)
        buf = ""
        first = True

        async def tap_receive():
            nonlocal first
            if first:
                first = False
                return await receive()
            while not self.disconnect.is_set():
                await asyncio.sleep(0.01)
            return {"type": "http.disconnect"}

        async def tap_send(message):
            nonlocal buf
            if message["type"] == "http.response.body":
                buf += message.get("body", b"").decode("utf-8")
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    self.events.put(parse_sse(block + "\n\n")[0])
            await send(message)

        await self.app(scope, tap_receive, tap_send)


@pytest.fixture
def ws(tmp_path):
    path = tmp_path / "ws"
    path.mkdir()
    (path / "a.txt").write_text("x")
    return path


def delete_provider():
    call = ToolCall("c1", "delete_file", {"filename": "a.txt"})
    return FakeProvider(turns=[[ChatEvent("tool_calls", tool_calls=[call])], [ChatEvent("text", "bitti")]])


@pytest.fixture
def setup(tmp_path, ws):
    tap = Tap(create_app({"fake": delete_provider()}, make_registry(ws), Storage(tmp_path / "t.db")))
    with TestClient(tap, base_url="http://127.0.0.1") as client:
        yield client, tap


def start_chat(client):
    cid = client.post("/api/conversations").json()["id"]
    body = {"conversation_id": cid, "provider": "fake", "model": "fake-1", "message": "sil"}
    done: queue.Queue = queue.Queue()

    def reader():
        try:
            done.put(client.post("/api/chat", json=body))
        except BaseException as exc:  # surface reader failures in the main thread
            done.put(exc)

    threading.Thread(target=reader, daemon=True).start()
    return done


def next_event(tap, name):
    while True:
        event = tap.events.get(timeout=WAIT)
        if event[0] == name:
            return event[1]


def all_events(tap, done):
    result = done.get(timeout=WAIT)
    if isinstance(result, BaseException):
        raise result
    events = []
    while not tap.events.empty():
        events.append(tap.events.get_nowait())
    return events


def confirm(client, cid, approved):
    return client.post("/api/chat/confirm", json={"confirm_id": cid, "approved": approved}, headers=LOCAL)


def test_confirm_flow_approve(setup, ws):
    client, tap = setup
    done = start_chat(client)
    req = next_event(tap, "confirm")
    assert req["name"] == "delete_file" and req["description"] == "‘a.txt’ silinecek." and req["preview"] == ""
    assert confirm(client, req["id"], True).status_code == 204
    rest = all_events(tap, done)
    names = ["confirm"] + [n for n, _ in rest]
    assert names == ["confirm", "confirm_result", "tool", "text", "done"]
    assert rest[0][1] == {"id": req["id"], "approved": True}
    assert not (ws / "a.txt").exists()


def test_confirm_flow_deny(setup, ws):
    client, tap = setup
    done = start_chat(client)
    req = next_event(tap, "confirm")
    assert confirm(client, req["id"], False).status_code == 204
    rest = dict(all_events(tap, done))
    assert rest["confirm_result"] == {"id": req["id"], "approved": False}
    assert rest["tool"]["result"] == "Denied by the user: ‘a.txt’ silinecek."
    assert (ws / "a.txt").exists()


def test_confirm_timeout(setup, ws, monkeypatch):
    monkeypatch.setattr("server.CONFIRM_TIMEOUT", 0.2)
    client, tap = setup
    done = start_chat(client)
    req = next_event(tap, "confirm")
    rest = dict(all_events(tap, done))
    assert rest["confirm_result"] == {"id": req["id"], "approved": False}
    assert (ws / "a.txt").exists()
    assert confirm(client, req["id"], True).status_code == 404


def test_confirm_after_resolution_404(setup):
    client, tap = setup
    done = start_chat(client)
    req = next_event(tap, "confirm")
    assert confirm(client, req["id"], True).status_code == 204
    all_events(tap, done)
    assert confirm(client, req["id"], True).status_code == 404
    assert confirm(client, "nope", True).status_code == 404


def test_confirm_requires_local(setup):
    client, _ = setup
    assert client.post("/api/chat/confirm", json={"confirm_id": "x", "approved": True}).status_code == 403
    r = client.post(
        "/api/chat/confirm",
        json={"confirm_id": "x", "approved": True},
        headers={**LOCAL, "Origin": "http://evil.example"},
    )
    assert r.status_code == 403


def test_pending_cleared_on_disconnect(setup, ws):
    client, tap = setup
    done = start_chat(client)
    req = next_event(tap, "confirm")
    tap.disconnect.set()
    done.get(timeout=WAIT)
    assert confirm(client, req["id"], True).status_code == 404
    assert (ws / "a.txt").exists()
