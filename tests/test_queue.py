import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.queue.inprocess import InProcessQueue
from src.queue.redis import RedisStreamQueue


@pytest.mark.asyncio
async def test_inprocess_queue_publish_subscribe():
    queue = InProcessQueue(maxsize=10)

    class MockAgent:
        def clone(self):
            return self

        async def run(self, input_data):
            yield _make_event("RUN_STARTED")
            yield _make_event("RUN_FINISHED")

    from ag_ui.core import RunAgentInput

    input_data = RunAgentInput(
        thread_id="test-thread",
        run_id="test-run",
        state={},
        messages=[{"id": "m1", "role": "user", "content": "hi"}],
        tools=[],
        context=[],
        forwarded_props={},
    )

    await queue.start_worker({"test-agent": MockAgent()})

    run_id = await queue.publish("test-agent", input_data)
    assert run_id == "test-run"

    events = []
    async for event in queue.subscribe(run_id):
        events.append(event)

    assert len(events) == 2
    assert events[0].type == "RUN_STARTED"
    assert events[1].type == "RUN_FINISHED"

    await queue.shutdown()


@pytest.mark.asyncio
async def test_inprocess_queue_worker_error():
    queue = InProcessQueue(maxsize=10)

    class FailingAgent:
        def clone(self):
            return self

        async def run(self, _):
            yield _make_event("RUN_STARTED")
            raise RuntimeError("agent crashed")

    from ag_ui.core import RunAgentInput

    input_data = RunAgentInput(
        thread_id="test",
        run_id="test-error",
        state={},
        messages=[{"id": "m1", "role": "user", "content": "hi"}],
        tools=[],
        context=[],
        forwarded_props={},
    )

    await queue.start_worker({"test-agent": FailingAgent()})
    await queue.publish("test-agent", input_data)

    events = []
    async for event in queue.subscribe("test-error"):
        events.append(event)
        if event.type == "RUN_ERROR":
            break

    assert len(events) == 2
    assert events[0].type == "RUN_STARTED"
    assert events[1].type == "RUN_ERROR"
    assert "agent crashed" in events[1].message

    await queue.shutdown()


def _make_event(event_type: str):
    from pydantic import BaseModel, Field

    class FakeEvent(BaseModel):
        type: str = event_type

    return FakeEvent()
