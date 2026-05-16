from __future__ import annotations

import abc


class RateLimitResult:
    def __init__(
        self, allowed: bool, remaining: int = 0, retry_after: float = 0.0
    ):
        self.allowed = allowed
        self.remaining = remaining
        self.retry_after = retry_after


class RateLimiter(abc.ABC):
    @abc.abstractmethod
    async def check(self, key: str, cost: int = 1) -> RateLimitResult:
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        ...
