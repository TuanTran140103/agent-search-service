from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ag_ui.core import RunAgentInput


def make_agent_input(
    thread_id: str = "test-thread",
    run_id: str = "test-run",
) -> RunAgentInput:
    return RunAgentInput(
        thread_id=thread_id,
        run_id=run_id,
        state={},
        messages=[{"id": "m1", "role": "user", "content": "hi"}],
        tools=[],
        context=[],
        forwarded_props={},
    )


class FakeEvent:
    def __init__(self, event_type: str, **kwargs):
        self.type = event_type
        self.__dict__.update(kwargs)

    def model_dump_json(self, **kw):
        import json
        return json.dumps({"type": self.type, **{k: v for k, v in self.__dict__.items() if k != "type"}})

    @classmethod
    def model_validate(cls, data: dict):
        return cls(data.get("type", "UNKNOWN"), **{k: v for k, v in data.items() if k != "type"})


class MockAgent:
    def __init__(self, events=None):
        self._events = events or []

    def clone(self):
        return self

    async def run(self, _input) -> AsyncGenerator:
        for ev in self._events:
            yield ev
