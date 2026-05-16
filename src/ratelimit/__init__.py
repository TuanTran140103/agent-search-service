from __future__ import annotations

from src.core.config import Settings
from src.ratelimit.protocol import RateLimiter


def create_rate_limiter(settings: Settings) -> RateLimiter:
    if settings.rate_limit_backend == "redis":
        from src.ratelimit.redis_impl import RedisRateLimiter

        return RedisRateLimiter(
            redis_url=settings.redis_uri,
            per_user=settings.rate_limit_per_user,
            global_limit=settings.rate_limit_global,
            window=settings.rate_limit_window,
        )

    from src.ratelimit.memory import InMemoryRateLimiter

    return InMemoryRateLimiter(
        per_user=settings.rate_limit_per_user,
        global_limit=settings.rate_limit_global,
        window=settings.rate_limit_window,
    )


__all__ = ["RateLimiter", "create_rate_limiter"]
