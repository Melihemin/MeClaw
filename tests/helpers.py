import json

from fastapi.testclient import TestClient


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        name, data = "", ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = line[len("data: "):]
        events.append((name, json.loads(data)))
    return events


def make_client(app):
    return TestClient(app, base_url="http://127.0.0.1")
