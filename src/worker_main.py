from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

os.environ["LANGGRAPH_FAST_API"] = "true"

from src.core.config import settings
from src.core.log import configure_logging, get_logger

configure_logging(
    level=settings.log_level,
    json_format=settings.log_json,
    service=settings.log_service,
)

logger = get_logger("worker")


async def main():
    from src.container import get_queue, get_settings, init_container
    from src.worker.agent_worker import build_agent_registry

    init_container()

    settings_ = get_settings()
    queue = get_queue()

    logger.info(
        "worker_starting",
        backend=settings_.queue_backend,
        agent=settings_.agent_name,
    )

    if settings_.queue_backend != "redis":
        logger.warning("queue_backend_is_not_redis", backend=settings_.queue_backend)

    agents = build_agent_registry()
    await queue.start_worker(agents)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("worker_shutdown")
