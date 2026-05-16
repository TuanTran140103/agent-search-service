from __future__ import annotations

from src.core.config import Settings
from src.queue.protocol import MessageQueue


def create_queue(settings: Settings) -> MessageQueue:
    if settings.queue_backend == "redis":
        from src.queue.redis import RedisStreamQueue

        return RedisStreamQueue(redis_url=settings.redis_uri)

    from src.queue.inprocess import InProcessQueue

    return InProcessQueue(maxsize=settings.queue_maxsize)


__all__ = ["MessageQueue", "create_queue"]
