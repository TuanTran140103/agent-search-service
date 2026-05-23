from __future__ import annotations

from dependency_injector import containers, providers

import os
import uuid
from typing import AsyncIterator

from ag_ui.core import BaseEvent, EventType, RunAgentInput, RunFinishedEvent
from langgraph.checkpoint.memory import MemorySaver

from src.agent.tools.search_tool import SEARCH_TOOLS
from src.core.config import Settings
from src.graph_builder import (
    build_deep_agent,
    create_agent_inst,
    create_db_pool,
)
from src.queue import MessageQueue, RedisStreamQueue
from src.ratelimit import RedisRateLimiter
from src.services.llm_service import llm_factory


def _build_interrupt_on(settings: Settings) -> dict | None:
    raw = settings.deepagent_interrupt_on.strip()
    if not raw:
        return None
    return {name.strip(): True for name in raw.split(",")}


def _resolve_checkpointer(settings: Settings, db_pool):
    """Return AsyncPostgresSaver when a real DB URI is configured,
    otherwise fall back to MemorySaver (useful for tests / development
    without infrastructure)."""
    if os.environ.get("LM_AGENT_TESTING") or not settings.database_uri:
        return MemorySaver()
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    return AsyncPostgresSaver(conn=db_pool)


def _resolve_db_pool(settings: Settings):
    if os.environ.get("LM_AGENT_TESTING") or not settings.database_uri:
        return None
    return create_db_pool(database_uri=settings.database_uri)


class _MockQueue(MessageQueue):
    """In-memory queue for tests — no Redis needed."""

    async def publish(self, agent_name: str, input: RunAgentInput) -> str:
        return input.run_id or str(uuid.uuid4())

    async def subscribe(self, run_id: str) -> AsyncIterator[BaseEvent]:
        yield RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id="",
            run_id=run_id,
        )

    async def shutdown(self) -> None:
        pass


def _resolve_queue(settings: Settings) -> MessageQueue:
    if os.environ.get("LM_AGENT_TESTING") or not settings.redis_uri:
        return _MockQueue()
    return RedisStreamQueue(redis_url=settings.redis_uri)


class ApplicationContainer(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            "src.api.server",
            "src.worker.agent_worker",
            "src.worker_main",
        ]
    )

    settings = providers.Singleton(Settings)

    # ── Database / Checkpointer ──────────────────────────────────────
    db_pool = providers.Singleton(
        _resolve_db_pool,
        settings=settings,
    )
    checkpointer = providers.Singleton(
        _resolve_checkpointer,
        settings=settings,
        db_pool=db_pool,
    )

    # ── LLM ──────────────────────────────────────────────────────────
    llm_model = providers.Singleton(
        llm_factory.create_deepagent_model,
        provider=settings.provided.llm_provider,
        model=settings.provided.llm_model,
    )

    # ── DeepAgent Graph ──────────────────────────────────────────────
    interrupt_on = providers.Singleton(
        _build_interrupt_on,
        settings=settings,
    )

    graph = providers.Singleton(
        build_deep_agent,
        model=llm_model,
        tools=SEARCH_TOOLS,
        system_prompt=None,  # uses default from graph_builder
        subagent_configs=None,
        checkpointer=checkpointer,
        store=None,  # will use InMemoryStore default
        interrupt_on=interrupt_on,
        response_format=None,
        name=settings.provided.agent_name,
    )

    agent = providers.Singleton(
        create_agent_inst,
        name=settings.provided.agent_name,
        description=settings.provided.agent_description,
        graph=graph,
    )

    # ── Queue & Rate Limiter ─────────────────────────────────────────
    queue = providers.Singleton(
        _resolve_queue,
        settings=settings,
    )
    rate_limiter = providers.Singleton(
        RedisRateLimiter,
        redis_url=settings.provided.redis_uri,
        per_user=settings.provided.rate_limit_per_user,
        global_limit=settings.provided.rate_limit_global,
        window=settings.provided.rate_limit_window,
    )


_container: ApplicationContainer | None = None


def init_container(settings: Settings | None = None) -> ApplicationContainer:
    global _container
    if _container is not None:
        return _container
    if settings is not None:
        _container = ApplicationContainer(settings=settings)
    else:
        _container = ApplicationContainer()
    _container.wire(modules=[
        "src.api.server",
        "src.worker.agent_worker",
        "src.worker_main",
    ])
    return _container


def get_container() -> ApplicationContainer:
    assert _container is not None, "Container not initialized"
    return _container


def get_settings() -> Settings:
    return get_container().settings()


def get_queue() -> RedisStreamQueue:
    return get_container().queue()


def get_graph():
    return get_container().graph()


def get_rate_limiter() -> RedisRateLimiter:
    return get_container().rate_limiter()


def reset_container() -> None:
    global _container
    if _container is not None:
        _container = None


__all__ = [
    "ApplicationContainer",
    "init_container",
    "get_container",
    "get_settings",
    "get_queue",
    "get_graph",
    "get_rate_limiter",
    "reset_container",
]
