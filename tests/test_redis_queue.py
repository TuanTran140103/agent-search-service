from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _valid_payload(run_id: str = "r1") -> str:
    return json.dumps({
        "thread_id": "t1",
        "run_id": run_id,
        "state": {},
        "messages": [{"id": "m1", "role": "user", "content": "hi"}],
        "tools": [],
        "context": [],
        "forwarded_props": {},
    })


class AsyncGen:
    """Callable that returns an async iterable."""

    def __init__(self, items):
        self._items = items

    def __call__(self):
        return self._iter()

    async def _iter(self):
        for item in self._items:
            yield item


@pytest.fixture
def mock_pubsub():
    p = MagicMock()
    p.subscribe = AsyncMock()
    p.unsubscribe = AsyncMock()
    p.close = AsyncMock()
    return p


@pytest.fixture
def mock_redis(mock_pubsub):
    m = MagicMock()
    m.xadd = AsyncMock(return_value=b"12345-0")
    m.xgroup_create = AsyncMock()
    m.xreadgroup = AsyncMock()
    m.xack = AsyncMock()
    m.publish = AsyncMock()
    m.close = AsyncMock()
    m.pubsub = MagicMock(return_value=mock_pubsub)
    return m


@pytest.mark.asyncio
async def test_publish_calls_xadd(mock_redis):
    with patch("redis.asyncio.from_url", return_value=mock_redis):
        from src.queue.redis import RedisStreamQueue
        from tests.conftest import make_agent_input

        queue = RedisStreamQueue("redis://fake:6379/0")
        input_data = make_agent_input(thread_id="t1", run_id="r1")
        run_id = await queue.publish("test-agent", input_data)

        assert run_id == "r1"
        mock_redis.xadd.assert_awaited_once()
        args = mock_redis.xadd.call_args[0]
        assert args[0] == "agent:requests"
        assert args[1]["run_id"] == "r1"
        assert args[1]["agent_name"] == "test-agent"


@pytest.mark.asyncio
async def test_subscribe_receives_events_then_stops(mock_redis, mock_pubsub):
    mock_pubsub.listen = AsyncGen([
        {"type": "message", "data": '{"type":"RUN_STARTED"}'},
        {"type": "message", "data": '{"type":"RUN_FINISHED"}'},
    ])

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        from src.queue.redis import RedisStreamQueue

        queue = RedisStreamQueue("redis://fake:6379/0")
        events = []
        async for event in queue.subscribe("run-1"):
            events.append(event)

        assert len(events) == 2
        assert events[0].type == "RUN_STARTED"
        assert events[1].type == "RUN_FINISHED"
        mock_pubsub.subscribe.assert_awaited_once()
        mock_pubsub.unsubscribe.assert_awaited_once()
        mock_pubsub.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_entry_events_are_published(mock_redis):
    from src.queue.redis import RedisStreamQueue, RedisStreamWorker
    from tests.conftest import FakeEvent, MockAgent

    agent = MockAgent(events=[FakeEvent("RUN_STARTED"), FakeEvent("RUN_FINISHED")])
    queue = RedisStreamQueue("redis://fake:6379/0")
    worker = RedisStreamWorker(queue)

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        await worker.start({"test-agent": agent})
        # call _process_entry directly with decoded dict
        await worker._process_entry(
            mock_redis, "12345-0",
            {"run_id": "r1", "agent_name": "test-agent", "payload": _valid_payload()},
        )
        await worker.shutdown()

    assert mock_redis.publish.await_count >= 1


@pytest.mark.asyncio
async def test_process_entry_unknown_agent_acks(mock_redis):
    from src.queue.redis import RedisStreamQueue, RedisStreamWorker

    queue = RedisStreamQueue("redis://fake:6379/0")
    worker = RedisStreamWorker(queue)

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        await worker.start({})
        await worker._process_entry(
            mock_redis, "67890-0",
            {"run_id": "bad-run", "agent_name": "nonexistent", "payload": _valid_payload()},
        )
        await worker.shutdown()

    mock_redis.xack.assert_awaited_once()
    mock_redis.publish.assert_not_awaited()
