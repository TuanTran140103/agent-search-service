from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


def _tid(prefix: str = "t") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

_HDRS = {"X-User-Id": "test-user"}


@pytest.fixture
def client():
    from src.api.server import app
    from src.container import reset_container

    reset_container()
    with TestClient(app) as c:
        yield c
    reset_container()


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


def test_get_thread_state_empty_for_new_thread(client):
    tid = _tid("state")
    resp = client.get(f"/threads/{tid}/state")
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


def _setup_thread_state(tid: str, messages: list[tuple[str, str, str]]):
    """Helper: use graph.astream to seed checkpoints through the middleware.

    Each tuple is (id, role, content).
    """
    import asyncio

    from src.container import get_container
    from ag_ui_langgraph.utils import agui_messages_to_langchain

    graph = get_container().graph()
    config = {"configurable": {"thread_id": tid}}

    async def _seed():
        accumulated = []
        for msg_id, role, content in messages:
            accumulated.append({"id": msg_id, "role": role, "content": content})
            agui_objs = [_dict_to_agui(m) for m in accumulated]
            lc = agui_messages_to_langchain(agui_objs)
            async for _ in graph.astream(
                {"messages": lc},
                stream_mode="updates",
                config=config,
                interrupt_before=["model"],
            ):
                pass

    asyncio.run(_seed())


def _dict_to_agui(data: dict):
    """Replica of server's _to_agui_message for test access."""
    role = data.get("role", "")
    if role == "user":
        from ag_ui.core.types import UserMessage
        return UserMessage(**data)
    elif role == "assistant":
        from ag_ui.core.types import AssistantMessage
        return AssistantMessage(**data)
    raise ValueError(f"Unsupported role: {role}")


def test_patch_thread_state_requires_messages(client):
    tid = _tid("patch")
    resp = client.patch(f"/threads/{tid}/state", json={})
    assert resp.status_code == 400
    assert "messages" in resp.text.lower()


def test_patch_thread_state_message_not_found(client):
    tid = _tid("patch")
    resp = client.patch(
        f"/threads/{tid}/state",
        json={"messages": [{"id": "nonexistent", "role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 404


def test_patch_thread_state_edits_message(client):
    tid = _tid("patch")
    msg_id = "edit-me"

    _setup_thread_state(tid, [("a", "user", "hello"), (msg_id, "user", "original"), ("c", "user", "third")])

    new_content = "edited content"
    resp = client.patch(
        f"/threads/{tid}/state",
        json={
            "messages": [{"id": msg_id, "role": "user", "content": new_content}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    msgs = data["messages"]

    # Verify message was updated
    edited = [m for m in msgs if m.get("id") == msg_id]
    assert len(edited) == 1
    assert edited[0]["content"] == new_content

    # Messages after the edit point are dropped.
    ids = {m["id"] for m in msgs}
    assert "a" in ids
    assert "c" not in ids


def test_fork_thread_creates_new_thread(client):
    tid = _tid("fork")
    msg_id = "fork-msg"

    _setup_thread_state(tid, [(msg_id, "user", "source message")])

    new_tid = _tid("fork-target")
    resp = client.post(
        f"/threads/{tid}/fork",
        json={"new_thread_id": new_tid},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == new_tid
    assert len(data["messages"]) > 0
    assert data["messages"][0]["id"] == msg_id
