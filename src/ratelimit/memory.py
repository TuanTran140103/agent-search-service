from __future__ import annotations

import asyncio
import logging
import time

from src.ratelimit.protocol import RateLimitResult, RateLimiter

logger = logging.getLogger(__name__)


class InMemoryRateLimiter(RateLimiter):
    def __init__(
        self, per_user: int = 10, global_limit: int = 1000, window: int = 60
    ):
        self._user_limit = per_user
        self._global_limit = global_limit
        self._window = window
        self._user_windows: dict[str, list[float]] = {}
        self._global_window: list[float] = []
        self._lock = asyncio.Lock()

    async def check(self, key: str, cost: int = 1) -> RateLimitResult:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self._window

            self._global_window = [
                t for t in self._global_window if t > cutoff
            ]
            if len(self._global_window) >= self._global_limit:
                retry_after = self._global_window[0] + self._window - now
                return RateLimitResult(
                    allowed=False,
                    retry_after=max(retry_after, 0.0),
                )

            if key not in self._user_windows:
                self._user_windows[key] = []
            user_ts = self._user_windows[key]
            user_ts[:] = [t for t in user_ts if t > cutoff]

            if len(user_ts) >= self._user_limit:
                retry_after = user_ts[0] + self._window - now
                remaining = max(0, self._user_limit - len(user_ts))
                return RateLimitResult(
                    allowed=False,
                    remaining=remaining,
                    retry_after=max(retry_after, 0.0),
                )

            self._global_window.append(now)
            user_ts.append(now)

            user_remaining = max(0, self._user_limit - len(user_ts))
            return RateLimitResult(
                allowed=True,
                remaining=user_remaining,
            )

    async def close(self) -> None:
        pass
