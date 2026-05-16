from __future__ import annotations

from dependency_injector import containers, providers

from src.core.config import Settings
from src.queue import MessageQueue, create_queue
from src.ratelimit import RateLimiter, create_rate_limiter


class ApplicationContainer(containers.DeclarativeContainer):
    settings = providers.Singleton(Settings)
    queue = providers.Singleton(create_queue, settings=settings)
    rate_limiter = providers.Singleton(create_rate_limiter, settings=settings)


_container: ApplicationContainer | None = None


def init_container(settings: Settings | None = None) -> None:
    global _container
    if _container is not None:
        return
    if settings is not None:
        _container = ApplicationContainer(settings=settings)
    else:
        _container = ApplicationContainer()


def get_settings() -> Settings:
    assert _container is not None, "Container not initialized"
    return _container.settings()


def get_queue() -> MessageQueue:
    assert _container is not None, "Container not initialized"
    return _container.queue()


def get_rate_limiter() -> RateLimiter:
    assert _container is not None, "Container not initialized"
    return _container.rate_limiter()


def reset_container() -> None:
    global _container
    _container = None


__all__ = [
    "ApplicationContainer",
    "init_container",
    "get_settings",
    "get_queue",
    "get_rate_limiter",
    "reset_container",
]
