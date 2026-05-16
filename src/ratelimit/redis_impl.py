from __future__ import annotations

import logging
import time

import redis.asyncio as aioredis

from src.ratelimit.protocol import RateLimitResult, RateLimiter

logger = logging.getLogger(__name__)


class RedisRateLimiter(RateLimiter):
    def __init__(
        self,
        redis_url: str,
        per_user: int = 10,
        global_limit: int = 1000,
        window: int = 60,
    ):
        self._redis_url = redis_url
        self._per_user = per_user
        self._global_limit = global_limit
        self._window = window
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True
            )
        return self._redis

    async def check(self, key: str, cost: int = 1) -> RateLimitResult:
        r = await self._get_redis()
        now = int(time.time())
        window_start = now - self._window

        user_key = f"ratelimit:user:{key}"
        global_key = "ratelimit:global"

        pipe = r.pipeline()
        pipe.zremrangebyscore(user_key, 0, window_start)
        pipe.zcard(user_key)
        pipe.zremrangebyscore(global_key, 0, window_start)
        pipe.zcard(global_key)
        results = await pipe.execute()

        user_count = results[1]
        global_count = results[3]

        if global_count >= self._global_limit:
            return RateLimitResult(allowed=False, retry_after=float(self._window))

        if user_count >= self._per_user:
            return RateLimitResult(
                allowed=False,
                remaining=max(0, self._per_user - user_count),
                retry_after=float(self._window),
            )

        score = float(now)
        member = str(now)

        pipe2 = r.pipeline()
        pipe2.zadd(user_key, {member: score})
        pipe2.expire(user_key, self._window * 2)
        pipe2.zadd(global_key, {member: score})
        pipe2.expire(global_key, self._window * 2)
        await pipe2.execute()

        return RateLimitResult(
            allowed=True,
            remaining=max(0, self._per_user - user_count - 1),
        )

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None
