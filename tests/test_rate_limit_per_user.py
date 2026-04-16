"""Tests for per-user token-bucket rate limiting (I.17).

These tests verify that the rate limiter partitions its state per user id
so that one noisy user cannot starve the shared budget of other users on
the same worker.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from fim_one.core.model.rate_limit import (
    RateLimitConfig,
    TokenBucketRateLimiter,
    current_user_id,
    reset_current_user_id,
    set_current_user_id,
)


# ======================================================================
# Helpers
# ======================================================================


async def _drain_request_bucket(
    limiter: TokenBucketRateLimiter, key: str
) -> None:
    """Force the bucket for ``key`` into an empty state (no request tokens)."""
    bucket, lock = await limiter._get_bucket(key)
    async with lock:
        bucket.request_tokens = 0.0


# ======================================================================
# Per-user isolation
# ======================================================================


class TestPerUserIsolation:
    """Distinct user ids must own independent buckets."""

    async def test_separate_users_have_independent_buckets(self) -> None:
        """User A saturating their bucket must not block user B."""
        # 60 RPM means refill = 1 req/sec.  Drain user A entirely, then
        # verify user B can acquire immediately (fast path, no sleep).
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(requests_per_minute=60, tokens_per_minute=100_000)
        )

        # Prime user A by acquiring once (creates the bucket), then drain it.
        await limiter.acquire(user_id="alice")
        await _drain_request_bucket(limiter, "alice")

        # User B must be able to acquire in well under a second -- if the
        # buckets were shared, bob would block on alice's empty bucket
        # waiting for refill.
        start = time.monotonic()
        await limiter.acquire(user_id="bob")
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"user bob was starved by user alice (waited {elapsed:.3f}s)"

        # The limiter should now track two distinct bucket keys.
        assert set(limiter._tracked_keys()) == {"alice", "bob"}

    async def test_same_user_shares_bucket(self) -> None:
        """Two calls with the same user id must hit the same bucket."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(requests_per_minute=60, tokens_per_minute=100_000)
        )

        await limiter.acquire(user_id="alice")
        await limiter.acquire(user_id="alice")

        # Only one bucket should exist for alice.
        assert limiter._tracked_keys() == ["alice"]
        bucket, _ = await limiter._get_bucket("alice")
        # Started at 60, two acquires spend 2 -- allow a small refill tolerance.
        assert 57.5 <= bucket.request_tokens <= 60.0


# ======================================================================
# Backward compatibility
# ======================================================================


class TestBackwardCompatibility:
    """Callers without a user id must still get a working limiter."""

    async def test_none_user_id_falls_back_to_shared(self) -> None:
        """Passing no user_id and no contextvar should use the shared key."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(requests_per_minute=60, tokens_per_minute=100_000)
        )

        # Make sure no stray contextvar leaks in from another test.
        token = set_current_user_id(None)
        try:
            await limiter.acquire()
            await limiter.acquire(estimated_tokens=0)
        finally:
            reset_current_user_id(token)

        assert limiter._tracked_keys() == ["__shared__"]

    async def test_contextvar_is_used_when_user_id_omitted(self) -> None:
        """The ``current_user_id`` contextvar must be picked up automatically."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(requests_per_minute=60, tokens_per_minute=100_000)
        )

        token = set_current_user_id("carol")
        try:
            await limiter.acquire()  # no explicit user_id
        finally:
            reset_current_user_id(token)

        assert limiter._tracked_keys() == ["carol"]

    async def test_explicit_user_id_overrides_contextvar(self) -> None:
        """An explicit ``user_id=`` must beat whatever is in the contextvar."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(requests_per_minute=60, tokens_per_minute=100_000)
        )

        token = set_current_user_id("carol")
        try:
            await limiter.acquire(user_id="dave")
        finally:
            reset_current_user_id(token)

        assert limiter._tracked_keys() == ["dave"]


# ======================================================================
# Global fallback (env var escape hatch)
# ======================================================================


class TestDisabledPerUserMode:
    """Setting ``per_user=False`` must restore the legacy single-bucket path."""

    async def test_disabled_per_user_mode_uses_global(self) -> None:
        """All users collide into a single ``__global__`` bucket."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(
                requests_per_minute=60,
                tokens_per_minute=100_000,
                per_user=False,
            )
        )

        await limiter.acquire(user_id="alice")
        await limiter.acquire(user_id="bob")
        await limiter.acquire()  # no user_id at all

        # Only one sentinel bucket should exist.
        assert limiter._tracked_keys() == ["__global__"]
        bucket, _ = await limiter._get_bucket("__global__")
        # All three acquires should have hit the same bucket.
        assert 56.5 <= bucket.request_tokens <= 60.0

    async def test_env_var_controls_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``LLM_RATE_LIMIT_PER_USER=false`` should flip the default off."""
        monkeypatch.setenv("LLM_RATE_LIMIT_PER_USER", "false")
        cfg = RateLimitConfig()
        assert cfg.per_user is False

        monkeypatch.setenv("LLM_RATE_LIMIT_PER_USER", "true")
        cfg = RateLimitConfig()
        assert cfg.per_user is True

        monkeypatch.setenv("LLM_RATE_LIMIT_PER_USER", "0")
        cfg = RateLimitConfig()
        assert cfg.per_user is False


# ======================================================================
# Idle cleanup
# ======================================================================


class TestBucketCleanup:
    """Idle per-user buckets must be evicted to prevent memory growth."""

    async def test_bucket_cleanup_removes_idle_users(self) -> None:
        """A bucket that has not been touched recently is evicted on sweep."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(
                requests_per_minute=60,
                tokens_per_minute=100_000,
                cleanup_idle_seconds=0.05,  # very short TTL for the test
            )
        )

        # Create several user buckets.
        await limiter.acquire(user_id="alice")
        await limiter.acquire(user_id="bob")
        await limiter.acquire(user_id="carol")
        assert set(limiter._tracked_keys()) == {"alice", "bob", "carol"}

        # Let them all go idle past the TTL.
        await asyncio.sleep(0.1)

        # Cleanup is lazy: each acquire samples one bucket at random.
        # We patch the random.choice used inside rate_limit so the sweep
        # is deterministic.
        targets = ["alice", "bob", "carol"]
        with patch(
            "fim_one.core.model.rate_limit.random.choice",
            side_effect=targets,
        ):
            # One fresh acquire per round; each should evict one stale bucket
            # before creating its own (fresh) bucket.
            await limiter.acquire(user_id="dave")
            await limiter.acquire(user_id="dave")
            await limiter.acquire(user_id="dave")

        # alice/bob/carol should all be gone; dave should remain.
        assert limiter._tracked_keys() == ["dave"]

    async def test_fresh_buckets_are_not_evicted(self) -> None:
        """Buckets touched within the TTL must survive a sweep attempt."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(
                requests_per_minute=60,
                tokens_per_minute=100_000,
                cleanup_idle_seconds=60.0,  # plenty of slack
            )
        )
        await limiter.acquire(user_id="alice")
        await limiter.acquire(user_id="bob")

        with patch(
            "fim_one.core.model.rate_limit.random.choice",
            return_value="alice",
        ):
            await limiter.acquire(user_id="carol")

        assert set(limiter._tracked_keys()) == {"alice", "bob", "carol"}

    async def test_sentinel_keys_are_never_evicted(self) -> None:
        """The ``__shared__``/``__global__`` sentinels must not be reclaimed."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(
                requests_per_minute=60,
                tokens_per_minute=100_000,
                cleanup_idle_seconds=0.01,
            )
        )
        await limiter.acquire()  # populates __shared__
        await limiter.acquire(user_id="alice")
        await asyncio.sleep(0.05)

        # Force the sweep to *try* to evict the sentinel.
        with patch(
            "fim_one.core.model.rate_limit.random.choice",
            return_value="__shared__",
        ):
            await limiter.acquire(user_id="alice")

        assert "__shared__" in limiter._tracked_keys()


# ======================================================================
# Concurrency correctness
# ======================================================================


class TestConcurrencyCorrectness:
    """Verify per-bucket locking serialises concurrent writes."""

    async def test_concurrent_same_user_requests_are_serialized(self) -> None:
        """Ten concurrent acquires for the same user must all succeed once."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(requests_per_minute=100, tokens_per_minute=100_000)
        )
        completed = 0

        async def _acquire() -> None:
            nonlocal completed
            await limiter.acquire(user_id="alice")
            completed += 1

        tasks = [asyncio.create_task(_acquire()) for _ in range(10)]
        await asyncio.wait(tasks, timeout=5.0)

        assert completed == 10
        # The single bucket for alice should reflect all 10 acquires.
        bucket, _ = await limiter._get_bucket("alice")
        # 100 initial - 10 spent, small refill tolerance.
        assert 89.0 <= bucket.request_tokens <= 100.0

    async def test_concurrent_different_users_do_not_interfere(self) -> None:
        """Parallel acquires for different users share no bucket state."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(requests_per_minute=100, tokens_per_minute=100_000)
        )

        async def _acquire(uid: str) -> None:
            for _ in range(5):
                await limiter.acquire(user_id=uid)

        await asyncio.gather(
            _acquire("alice"),
            _acquire("bob"),
            _acquire("carol"),
        )

        for uid in ("alice", "bob", "carol"):
            bucket, _ = await limiter._get_bucket(uid)
            # Each user spent exactly 5 out of 100.
            assert 93.0 <= bucket.request_tokens <= 100.0


# ======================================================================
# report_usage threading
# ======================================================================


class TestReportUsagePerUser:
    """``report_usage`` must charge the same bucket that ``acquire`` used."""

    async def test_report_usage_targets_per_user_bucket(self) -> None:
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(requests_per_minute=1000, tokens_per_minute=1000)
        )

        await limiter.acquire(estimated_tokens=0, user_id="alice")
        await limiter.report_usage(
            actual_tokens=400, estimated_tokens=0, user_id="alice"
        )

        alice_bucket, _ = await limiter._get_bucket("alice")
        # alice should have ~600 tokens left (1000 - 400), not bob.
        assert 595.0 <= alice_bucket.token_tokens <= 605.0

        # bob's bucket is untouched and still full.
        bob_bucket, _ = await limiter._get_bucket("bob")
        assert bob_bucket.token_tokens == pytest.approx(1000.0, abs=1.0)

    async def test_report_usage_uses_contextvar(self) -> None:
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(requests_per_minute=1000, tokens_per_minute=1000)
        )

        token = set_current_user_id("alice")
        try:
            await limiter.acquire(estimated_tokens=0)
            await limiter.report_usage(actual_tokens=300, estimated_tokens=0)
        finally:
            reset_current_user_id(token)

        alice_bucket, _ = await limiter._get_bucket("alice")
        assert 695.0 <= alice_bucket.token_tokens <= 705.0


# ======================================================================
# ContextVar lifecycle
# ======================================================================


class TestContextVarLifecycle:
    """The ContextVar helpers should behave like the stdlib primitive."""

    async def test_set_and_reset_roundtrip(self) -> None:
        assert current_user_id.get() is None
        token = set_current_user_id("alice")
        try:
            assert current_user_id.get() == "alice"
        finally:
            reset_current_user_id(token)
        assert current_user_id.get() is None

    async def test_asyncio_tasks_inherit_context(self) -> None:
        """Tasks spawned inside an outer scope must see the bound user id."""
        seen: list[str | None] = []

        async def _observe() -> None:
            seen.append(current_user_id.get())

        token = set_current_user_id("alice")
        try:
            task = asyncio.create_task(_observe())
            await task
        finally:
            reset_current_user_id(token)

        assert seen == ["alice"]
