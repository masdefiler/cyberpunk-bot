"""publish.py — Instagram iki adımlı akış (requests mock'lu)."""
import pytest

from src import publish


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    vals = {"IG_USER_ID": "1789", "IG_ACCESS_TOKEN": "TOK", "GRAPH_BASE": ""}
    monkeypatch.setattr(publish.config, "env", lambda k, d="": vals.get(k, d))
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)   # bekleme yok


def test_publish_happy_path(monkeypatch):
    posts = iter([
        FakeResp({"id": "CREATION_1"}),     # /media
        FakeResp({"id": "MEDIA_99"}),       # /media_publish
    ])
    monkeypatch.setattr(publish.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(publish.requests, "get",
                        lambda *a, **k: FakeResp({"status_code": "FINISHED"}))

    media_id = publish.publish("https://img/x.png", "başlık #neon")
    assert media_id == "MEDIA_99"


def test_publish_container_error_raises(monkeypatch):
    monkeypatch.setattr(publish.requests, "post",
                        lambda *a, **k: FakeResp({"error": {"message": "kötü url"}}, status=400))
    with pytest.raises(publish.PublishError):
        publish.publish("https://img/x.png", "cap")


def test_publish_waits_then_finishes(monkeypatch):
    posts = iter([FakeResp({"id": "C1"}), FakeResp({"id": "M1"})])
    statuses = iter([
        FakeResp({"status_code": "IN_PROGRESS"}),
        FakeResp({"status_code": "IN_PROGRESS"}),
        FakeResp({"status_code": "FINISHED"}),
    ])
    monkeypatch.setattr(publish.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(publish.requests, "get", lambda *a, **k: next(statuses))
    assert publish.publish("u", "c") == "M1"


def test_publish_container_status_error(monkeypatch):
    posts = iter([FakeResp({"id": "C1"})])
    monkeypatch.setattr(publish.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(publish.requests, "get",
                        lambda *a, **k: FakeResp({"status_code": "ERROR", "status": "bozuk"}))
    with pytest.raises(publish.PublishError):
        publish.publish("u", "c")
