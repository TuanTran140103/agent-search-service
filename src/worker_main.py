from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

os.environ["LANGGRAPH_FAST_API"] = "true"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.core.config import settings
from src.core.log import configure_logging, get_logger
from src.queue.redis import RedisStreamWorker

configure_logging(
    level=settings.log_level,
    json_format=settings.log_json,
    service=settings.log_service,
)

logger = get_logger("worker")


async def main():
    from src.worker.agent_worker import build_agent_registry

    from src.container import ApplicationContainer, init_container

    c = init_container()
    queue = c.queue()

    pool = c.db_pool()
    if pool.closed:
        if sys.platform == "win32":
            loop = asyncio.get_running_loop()
            if isinstance(loop, asyncio.ProactorEventLoop):
                raise RuntimeError(
                    "psycopg requires SelectorEventLoop on Windows. "
                    "Run via 'python main.py' instead of uvicorn/gunicorn directly."
                )
        await pool.open()
        checkpointer = c.checkpointer()
        await checkpointer.setup()

    logger.info("worker_starting", agent=c.settings().agent_name)

    agents = await build_agent_registry()
    worker = RedisStreamWorker(queue)
    await worker.start(agents)

    logger.info("worker_ready")

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass

    await worker.shutdown()
    await queue.shutdown()
    logger.info("worker_shutdown")


if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("worker_stopped")
