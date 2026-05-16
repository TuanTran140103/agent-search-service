import asyncio

import pytest

from src.ratelimit.memory import InMemoryRateLimiter


@pytest.mark.asyncio
async def test_user_rate_limit():
    rl = InMemoryRateLimiter(per_user=2, global_limit=100, window=60)

    r1 = await rl.check("user1")
    assert r1.allowed is True
    assert r1.remaining == 1

    r2 = await rl.check("user1")
    assert r2.allowed is True
    assert r2.remaining == 0

    r3 = await rl.check("user1")
    assert r3.allowed is False
    assert r3.retry_after > 0


@pytest.mark.asyncio
async def test_global_rate_limit():
    rl = InMemoryRateLimiter(per_user=100, global_limit=3, window=60)

    for i in range(3):
        r = await rl.check(f"user-{i}")
        assert r.allowed is True, f"Request {i} should be allowed"

    r4 = await rl.check("user-4")
    assert r4.allowed is False, "4th request should be blocked"


@pytest.mark.asyncio
async def test_different_users_independent():
    rl = InMemoryRateLimiter(per_user=1, global_limit=100, window=60)

    r1 = await rl.check("alice")
    assert r1.allowed is True

    r2 = await rl.check("bob")
    assert r2.allowed is True

    r3 = await rl.check("alice")
    assert r3.allowed is False


@pytest.mark.asyncio
async def test_window_expiry():
    rl = InMemoryRateLimiter(per_user=1, global_limit=100, window=1)

    r1 = await rl.check("user1")
    assert r1.allowed is True

    r2 = await rl.check("user1")
    assert r2.allowed is False

    await asyncio.sleep(1.2)

    r3 = await rl.check("user1")
    assert r3.allowed is True, "Should reset after window"


@pytest.mark.asyncio
async def test_concurrent_users_global():
    rl = InMemoryRateLimiter(per_user=2, global_limit=5, window=60)

    results = await asyncio.gather(*[rl.check(f"user-{i}") for i in range(10)])

    allowed = sum(1 for r in results if r.allowed)
    blocked = sum(1 for r in results if not r.allowed)

    assert allowed == 5, "Only 5 global requests allowed"
    assert blocked == 5, "5 should be blocked"
