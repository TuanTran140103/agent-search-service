from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.container import reset_container, init_container

    reset_container()
    init_container()

    from src.api.server import app

    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "service" in data


def test_agent_health(client):
    resp = client.get("/agent/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["agent"]["name"] == "lm-assistant"


def test_list_agents(client):
    resp = client.get("/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["agents"]) == 1
    assert data["agents"][0]["name"] == "lm-assistant"
    assert data["agents"][0]["endpoint"] == "/agent"


def test_create_and_list_threads(client):
    resp = client.post("/threads", json={})
    assert resp.status_code == 200
    thread = resp.json()
    assert "thread_id" in thread
    assert thread["metadata"] == {}

    resp = client.get("/threads")
    assert resp.status_code == 200
    threads = resp.json()["threads"]
    assert len(threads) == 1


def test_get_thread(client):
    client.post("/threads", json={"thread_id": "my-thread"})
    resp = client.get("/threads/my-thread")
    assert resp.status_code == 200
    assert resp.json()["thread_id"] == "my-thread"


def test_get_thread_not_found(client):
    resp = client.get("/threads/nonexistent")
    assert resp.status_code == 404


def test_delete_thread(client):
    client.post("/threads", json={"thread_id": "del-me"})
    resp = client.delete("/threads/del-me")
    assert resp.status_code == 200
    resp = client.get("/threads/del-me")
    assert resp.status_code == 404


def test_get_thread_state_empty_for_new_thread(client):
    resp = client.post("/threads", json={})
    tid = resp.json()["thread_id"]
    resp = client.get(f"/threads/{tid}/state")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


def test_put_and_get_thread_state(client):
    resp = client.post("/threads", json={"thread_id": "state-test"})
    assert resp.status_code == 200

    resp = client.put(
        "/threads/state-test/state",
        json={
            "messages": [
                {"role": "user", "content": "hello", "id": "u1"},
                {"role": "assistant", "content": "hi there", "id": "a1"},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 2

    resp = client.get("/threads/state-test/state")
    assert resp.status_code == 200
    msgs = resp.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["content"] == "hello"
    assert msgs[1]["content"] == "hi there"


def test_put_thread_state_preserves_existing(client):
    resp = client.post("/threads", json={"thread_id": "append-test"})
    assert resp.status_code == 200

    resp = client.put(
        "/threads/append-test/state",
        json={"messages": [{"role": "user", "content": "first", "id": "u1"}]},
    )
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 1

    resp = client.put(
        "/threads/append-test/state",
        json={"messages": [{"role": "assistant", "content": "second", "id": "a1"}]},
    )
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 2

    resp = client.get("/threads/append-test/state")
    assert len(resp.json()["messages"]) == 2


def test_thread_state_history(client):
    resp = client.post("/threads", json={"thread_id": "history-test"})
    assert resp.status_code == 200

    resp = client.get("/threads/history-test/state/history")
    assert resp.status_code == 200
    assert len(resp.json()["checkpoints"]) >= 1

    resp = client.put(
        "/threads/history-test/state",
        json={"messages": [{"role": "user", "content": "msg", "id": "m1"}]},
    )
    assert resp.status_code == 200

    resp = client.get("/threads/history-test/state/history")
    assert len(resp.json()["checkpoints"]) >= 2

    # Verify first checkpoint has empty messages, second has the msg
    cps = resp.json()["checkpoints"]
    assert cps[0]["message_count"] == 1
    assert cps[1]["message_count"] == 0


def test_delete_thread_clears_checkpointer(client):
    resp = client.post("/threads", json={"thread_id": "clear-test"})
    assert resp.status_code == 200

    client.put(
        "/threads/clear-test/state",
        json={"messages": [{"role": "user", "content": "x", "id": "x1"}]},
    )

    resp = client.get("/threads/clear-test/state")
    assert len(resp.json()["messages"]) == 1

    resp = client.delete("/threads/clear-test")
    assert resp.status_code == 200

    resp = client.get("/threads/clear-test/state")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"thread_id": "t1"},
        {
            "thread_id": "t1",
            "run_id": "r1",
            "state": {},
            "messages": [{"role": "user"}],
            "tools": [],
            "context": [],
            "forwarded_props": {},
        },
    ],
)
def test_agent_post_validation(client, body):
    resp = client.post("/agent", json=body)
    assert resp.status_code == 422


def test_rate_limiter_rejects_after_limit():
    from src.ratelimit.memory import InMemoryRateLimiter

    limiter = InMemoryRateLimiter(per_user=1, global_limit=100, window=60)

    import asyncio
    r1 = asyncio.run(limiter.check("test-user"))
    assert r1.allowed is True

    r2 = asyncio.run(limiter.check("test-user"))
    assert r2.allowed is False
