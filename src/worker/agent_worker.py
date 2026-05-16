from __future__ import annotations

import logging

from ag_ui_langgraph import LangGraphAgent

from src.container import get_queue, get_settings
from src.graph_builder import create_agent

logger = logging.getLogger(__name__)


def build_agent_registry() -> dict[str, LangGraphAgent]:
    settings = get_settings()
    agent = create_agent(name=settings.agent_name, description=settings.agent_description)
    return {settings.agent_name: agent}


async def run_worker() -> None:
    settings = get_settings()
    queue = get_queue()
    agents = build_agent_registry()

    logger.info(
        "Starting worker: backend=%s agents=%s",
        settings.queue_backend,
        list(agents.keys()),
    )

    await queue.start_worker(agents)
