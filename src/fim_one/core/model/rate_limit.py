"""Token-bucket rate limiter for LLM API calls.

Per-user keyed buckets (I.17):
    The limiter keeps one token-bucket pair (request bucket + token bucket)
    per user id so that one noisy user cannot starve the shared process-wide
    budget of other users on the same worker.  The effective key is resolved
    in this priority order:

        1.  Explicit ``user_id=...`` argument to :meth:`acquire`.
        2.  The module-level ``current_user_id`` :class:`contextvars.ContextVar`
            (typically set by the web request handler before agent execution).
        3.  A constant shared key (``"__shared__"``) -- backward compatible
            with callers that have no notion of a user.

    When the ``LLM_RATE_LIMIT_PER_USER`` environment variable is set to
    ``false``/``0``/``no`` the limiter falls back to a single
    ``"__global__"`` bucket, reproducing the legacy behaviour exactly.  This
    is a safety valve, not a user-facing feature flag.

    Idle buckets are evicted on-the-fly: each :meth:`acquire` call lazily
    samples one random tracked key and drops it if it has not been touched
    in ``cleanup_idle_seconds`` (default 600 s).  No background task is
    required, keeping the limiter fully self-contained.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request-scoped user id -- set by the web layer so that rate limiting can
# partition buckets per user without threading ``user_id`` through the
# ``BaseLLM`` signature and every intermediate wrapper.
# ---------------------------------------------------------------------------

current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "fim_one_rate_limit_user_id",
    default=None,
)


def set_current_user_id(user_id: str | None) -> contextvars.Token[str | None]:
    """Bind the current user id for the remainder of this asyncio task.

    Returns the :class:`contextvars.Token` the caller can pass to
    :meth:`contextvars.ContextVar.reset` on exit, mirroring the standard
    ContextVar ``set()`` API.
    """
    return current_user_id.set(user_id)


def reset_current_user_id(token: contextvars.Token[str | None]) -> None:
    """Reset the current user id contextvar to its previous value."""
    current_user_id.reset(token)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


# Sentinel keys used when no real user id is available.  They are plain
# strings so the bucket dictionary type stays simple (``dict[str, ...]``).
_SHARED_KEY = "__shared__"
_GLOBAL_KEY = "__global__"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for the token-bucket rate limiter.

    Args:
        requests_per_minute: Maximum number of requests allowed per minute.
        tokens_per_minute: Maximum number of tokens allowed per minute.
        per_user: If True, each distinct user id gets its own pair of
            buckets.  If False, a single process-global bucket is used
            regardless of caller.  The default is read from the
            ``LLM_RATE_LIMIT_PER_USER`` environment variable (default:
            True).  Explicit construction arguments still win over the
            environment.
        cleanup_idle_seconds: How long a per-user bucket may sit untouched
            before it becomes eligible for lazy eviction.  Reclaims memory
            for bursty workloads where the active user set churns.
    """

    requests_per_minute: int = 60
    tokens_per_minute: int = 100_000
    per_user: bool = field(
        default_factory=lambda: _env_bool("LLM_RATE_LIMIT_PER_USER", True),
    )
    cleanup_idle_seconds: float = 600.0


# ---------------------------------------------------------------------------
# Per-key bucket state
# ---------------------------------------------------------------------------


@dataclass
class _Bucket:
    """Mutable per-user token-bucket state."""

    request_tokens: float
    token_tokens: float
    last_refill: float
    last_touched: float


class TokenBucketRateLimiter:
    """A dual token-bucket rate limiter for request count and token count.

    Both buckets refill continuously at a steady rate.  When a bucket is
    empty, callers are made to wait (never rejected).

    The limiter is partitioned per user id: each distinct user gets an
    independent bucket pair, preventing cross-user starvation.  See the
    module docstring for the full key resolution rules.

    This class is safe for concurrent use via a per-key :class:`asyncio.Lock`.

    Args:
        config: Rate limit configuration.
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._config = config or RateLimitConfig()
        self._request_rate: float = self._config.requests_per_minute / 60.0
        self._token_rate: float = self._config.tokens_per_minute / 60.0

        # Per-user bucket state.  Buckets are created on first touch via
        # ``_get_bucket``; the dict itself is guarded by ``_state_lock``
        # when mutated to avoid concurrent insert races.
        self._buckets: dict[str, _Bucket] = {}
        self._state_lock = asyncio.Lock()
        # ``defaultdict(asyncio.Lock)`` is safe here because access only
        # happens while ``_state_lock`` is held.
        self._bucket_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------
    # Key resolution
    # ------------------------------------------------------------------

    def _resolve_key(self, user_id: str | None) -> str:
        """Decide which bucket key this call should target."""
        if not self._config.per_user:
            return _GLOBAL_KEY
        if user_id:
            return user_id
        ctx_val = current_user_id.get()
        if ctx_val:
            return ctx_val
        return _SHARED_KEY

    # ------------------------------------------------------------------
    # Bucket management
    # ------------------------------------------------------------------

    async def _get_bucket(self, key: str) -> tuple[_Bucket, asyncio.Lock]:
        """Return (or lazily create) the bucket + lock for ``key``."""
        async with self._state_lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                now = time.monotonic()
                bucket = _Bucket(
                    request_tokens=float(self._config.requests_per_minute),
                    token_tokens=float(self._config.tokens_per_minute),
                    last_refill=now,
                    last_touched=now,
                )
                self._buckets[key] = bucket
            lock = self._bucket_locks[key]
            return bucket, lock

    def _refill(self, bucket: _Bucket) -> None:
        """Refill both buckets based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        bucket.last_refill = now
        bucket.last_touched = now

        bucket.request_tokens = min(
            float(self._config.requests_per_minute),
            bucket.request_tokens + elapsed * self._request_rate,
        )
        bucket.token_tokens = min(
            float(self._config.tokens_per_minute),
            bucket.token_tokens + elapsed * self._token_rate,
        )

    def _wait_time(self, bucket: _Bucket, estimated_tokens: int) -> float:
        """Seconds the caller must sleep before this bucket can serve them."""
        wait = 0.0

        if bucket.request_tokens < 1.0:
            wait = max(wait, (1.0 - bucket.request_tokens) / self._request_rate)

        needed = float(estimated_tokens)
        if bucket.token_tokens < needed:
            wait = max(wait, (needed - bucket.token_tokens) / self._token_rate)

        return wait

    async def _maybe_evict_idle(self) -> None:
        """Lazy cleanup: sample one random bucket and evict if stale."""
        # Only sweep occasionally -- cheap, bounded, no background task.
        async with self._state_lock:
            if len(self._buckets) <= 1:
                return
            # Random sample: O(1) amortised instead of iterating every key.
            candidate_key = random.choice(list(self._buckets.keys()))
            # Never evict the legacy sentinel keys -- they are always
            # process-lifetime and evicting would reset state unexpectedly.
            if candidate_key in (_SHARED_KEY, _GLOBAL_KEY):
                return
            bucket = self._buckets[candidate_key]
            idle_for = time.monotonic() - bucket.last_touched
            if idle_for < self._config.cleanup_idle_seconds:
                return
            del self._buckets[candidate_key]
            self._bucket_locks.pop(candidate_key, None)
            logger.debug(
                "Evicted idle rate-limit bucket %s (idle %.0fs)",
                candidate_key,
                idle_for,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(
        self,
        estimated_tokens: int = 0,
        *,
        user_id: str | None = None,
    ) -> None:
        """Wait until the rate limiter permits the request, then consume tokens.

        Args:
            estimated_tokens: Estimated token count for the upcoming request.
                When unknown, pass 0 to only throttle on request count.
            user_id: Optional explicit bucket key.  When ``None`` (the
                default) the limiter reads the ``current_user_id`` context
                variable; if that is also unset the shared sentinel key is
                used so backward-compatible callers keep working.
        """
        key = self._resolve_key(user_id)
        await self._maybe_evict_idle()

        while True:
            bucket, lock = await self._get_bucket(key)
            async with lock:
                self._refill(bucket)
                wait = self._wait_time(bucket, estimated_tokens)

                if wait <= 0:
                    bucket.request_tokens -= 1.0
                    bucket.token_tokens -= float(estimated_tokens)
                    bucket.last_touched = time.monotonic()
                    return

            logger.debug(
                "Rate limiter waiting %.2fs key=%s "
                "(request_tokens=%.1f, token_tokens=%.1f)",
                wait,
                key,
                bucket.request_tokens,
                bucket.token_tokens,
            )
            await asyncio.sleep(wait)

    async def report_usage(
        self,
        actual_tokens: int,
        estimated_tokens: int = 0,
        *,
        user_id: str | None = None,
    ) -> None:
        """Adjust the token bucket after learning the actual token count.

        If the actual usage exceeds the initial estimate, the difference is
        subtracted from the token bucket.  If usage was lower than estimated,
        tokens are returned to the bucket.

        Args:
            actual_tokens: The real number of tokens consumed.
            estimated_tokens: The estimate passed to ``acquire()`` earlier.
            user_id: Same semantics as :meth:`acquire` -- must match the
                key that was used when reserving the tokens.
        """
        diff = actual_tokens - estimated_tokens
        if diff == 0:
            return
        key = self._resolve_key(user_id)
        bucket, lock = await self._get_bucket(key)
        async with lock:
            self._refill(bucket)
            bucket.token_tokens -= float(diff)

    # ------------------------------------------------------------------
    # Introspection helpers (used by tests)
    # ------------------------------------------------------------------

    def _tracked_keys(self) -> list[str]:
        """Return the list of currently tracked bucket keys (for tests)."""
        return list(self._buckets.keys())
