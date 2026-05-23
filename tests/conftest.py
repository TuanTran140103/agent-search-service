from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest

# ── Test environment overrides ──────────────────────────────────────
# These must be set **before** any application module is imported so
# that Settings() and the DI container initialise in test mode.
os.environ.setdefault("LM_AGENT_TESTING", "1")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("LLM_API_KEY", "test-key")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ag_ui.core import RunAgentInput

# Force SelectorEventLoop on Windows (required by psycopg async)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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
        return json.dumps(
            {"type": self.type, **{k: v for k, v in self.__dict__.items() if k != "type"}}
        )

    @classmethod
    def model_validate(cls, data: dict):
        return cls(
            data.get("type", "UNKNOWN"),
            **{k: v for k, v in data.items() if k != "type"},
        )


class MockAgent:
    def __init__(self, events=None):
        self._events = events or []

    def clone(self):
        return self

    async def run(self, _input) -> AsyncGenerator:
        for ev in self._events:
            yield ev


@pytest.fixture
def client():
    from src.api.server import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
