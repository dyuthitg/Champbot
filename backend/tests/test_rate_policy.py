"""
Tests for the global per-account rate limiter (src/infrastructure/rate_policy.py).

Proves the property the legacy in-memory limiter lacked: the cap is enforced
GLOBALLY per LinkedIn account across multiple agent instances sharing Redis,
and hourly cap / daily cap / cooldown all block correctly.
"""

import pytest
import fakeredis.aioredis

from src.infrastructure.rate_policy import AccountRateLimiter

pytestmark = pytest.mark.asyncio


class Clock:
    """Manually-advanceable clock for deterministic window tests."""
    def __init__(self, start: float = 1_000_000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def redis_client():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def test_daily_cap_blocks_after_limit(redis_client):
    clock = Clock()
    rl = AccountRateLimiter(redis_client, clock=clock)

    allowed = 0
    for _ in range(5):
        d = await rl.check_and_consume("acct-1", "connect", per_hour=100, per_day=3)
        if d.allowed:
            allowed += 1
        clock.advance(1)  # avoid cooldown interference

    assert allowed == 3, "only per_day slots should be granted"
    last = await rl.check_and_consume("acct-1", "connect", per_hour=100, per_day=3)
    assert not last
    assert last.reason == "daily_cap"


async def test_cap_is_global_across_instances(redis_client):
    """Two limiter instances (simulating two pooled agents) share one counter."""
    clock = Clock()
    agent_a = AccountRateLimiter(redis_client, clock=clock)
    agent_b = AccountRateLimiter(redis_client, clock=clock)

    granted = 0
    for i in range(4):
        inst = agent_a if i % 2 == 0 else agent_b
        d = await inst.check_and_consume("acct-1", "connect", per_hour=100, per_day=2)
        granted += 1 if d.allowed else 0
        clock.advance(1)

    # Despite two separate instances, the account-wide daily cap of 2 holds.
    assert granted == 2


async def test_cooldown_blocks_then_allows(redis_client):
    clock = Clock()
    rl = AccountRateLimiter(redis_client, clock=clock)

    first = await rl.check_and_consume("a", "like", per_hour=100, per_day=100, cooldown_seconds=10)
    assert first

    blocked = await rl.check_and_consume("a", "like", per_hour=100, per_day=100, cooldown_seconds=10)
    assert not blocked
    assert blocked.reason == "cooldown"
    assert 0 < blocked.retry_after_seconds <= 10

    clock.advance(10)
    ok = await rl.check_and_consume("a", "like", per_hour=100, per_day=100, cooldown_seconds=10)
    assert ok


async def test_hourly_window_rolls_off(redis_client):
    clock = Clock()
    rl = AccountRateLimiter(redis_client, clock=clock)

    for _ in range(3):
        assert await rl.check_and_consume("a", "comment", per_hour=3, per_day=100)
        clock.advance(1)

    assert not await rl.check_and_consume("a", "comment", per_hour=3, per_day=100)

    # After the hour window passes, the old entries roll off and it's allowed again.
    clock.advance(3601)
    assert await rl.check_and_consume("a", "comment", per_hour=3, per_day=100)


async def test_rejection_does_not_consume_a_slot(redis_client):
    """A blocked check must not inflate the window (the legacy limiter's bug)."""
    clock = Clock()
    rl = AccountRateLimiter(redis_client, clock=clock)

    assert await rl.check_and_consume("a", "connect", per_hour=100, per_day=1)
    clock.advance(1)
    # Several rejected attempts...
    for _ in range(5):
        assert not await rl.check_and_consume("a", "connect", per_hour=100, per_day=1)
        clock.advance(1)

    usage = await rl.usage("a", "connect")
    assert usage["day_used"] == 1, "rejected attempts must not consume slots"
