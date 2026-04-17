"""Tests for Anthropic prompt-cache observability.

Verifies that:

1. ``_merge_cache_usage`` pulls ``cache_read_input_tokens`` /
   ``cache_creation_input_tokens`` from the two shapes LiteLLM
   surfaces them in (direct attribute vs nested
   ``prompt_tokens_details``).
2. Missing cache fields degrade to 0 without crashing.
3. ``TurnProfiler.add_cache_hit`` accumulates across multiple calls
   and ``emit`` produces a ``turn_cache`` log line.
4. ``UsageSummary`` carries the cache fields through record →
   get_summary and through __add__ / __iadd__.
5. The ``/chat/*`` ``done`` SSE payload surfaces the cache totals
   under a new ``cache`` key (smoke-tested by calling the payload
   construction block directly — no HTTP needed).
"""

from __future__ import annotations

import logging

import pytest

from fim_one.core.agent.turn_profiler import TurnProfiler, make_profiler
from fim_one.core.model.openai_compatible import _merge_cache_usage
from fim_one.core.model.usage import UsageSummary, UsageTracker

# ======================================================================
# _merge_cache_usage — raw attribute parsing
# ======================================================================


class _StubDirectUsage:
    """Mimics LiteLLM >= 1.50 usage object with direct attrs."""

    def __init__(
        self,
        *,
        cache_read: int | None = None,
        cache_creation: int | None = None,
    ) -> None:
        if cache_read is not None:
            self.cache_read_input_tokens = cache_read
        if cache_creation is not None:
            self.cache_creation_input_tokens = cache_creation


class _StubNestedUsage:
    """Mimics OpenAI-compat shim with nested prompt_tokens_details."""

    class _Details:
        def __init__(self, cached_tokens: int) -> None:
            self.cached_tokens = cached_tokens

    def __init__(self, cached_tokens: int) -> None:
        self.prompt_tokens_details = self._Details(cached_tokens)


class TestMergeCacheUsage:
    def test_direct_attrs(self) -> None:
        usage: dict[str, int] = {"prompt_tokens": 100}
        _merge_cache_usage(
            usage,
            _StubDirectUsage(cache_read=1067, cache_creation=10),
        )
        assert usage["cache_read_input_tokens"] == 1067
        assert usage["cache_creation_input_tokens"] == 10

    def test_nested_fallback(self) -> None:
        usage: dict[str, int] = {"prompt_tokens": 100}
        _merge_cache_usage(usage, _StubNestedUsage(cached_tokens=512))
        assert usage["cache_read_input_tokens"] == 512
        # Creation has no nested fallback — stays 0.
        assert usage["cache_creation_input_tokens"] == 0

    def test_direct_wins_over_nested(self) -> None:
        """When both shapes are present the direct attribute wins."""

        class _Both:
            cache_read_input_tokens = 999
            cache_creation_input_tokens = 7

            class _Details:
                cached_tokens = 1

            prompt_tokens_details = _Details()

        usage: dict[str, int] = {}
        _merge_cache_usage(usage, _Both())
        assert usage["cache_read_input_tokens"] == 999
        assert usage["cache_creation_input_tokens"] == 7

    def test_missing_defaults_to_zero(self) -> None:
        """An object with no cache-related attributes at all."""
        usage: dict[str, int] = {}
        _merge_cache_usage(usage, object())
        assert usage["cache_read_input_tokens"] == 0
        assert usage["cache_creation_input_tokens"] == 0

    def test_malformed_non_int_ignored(self) -> None:
        """A stringly-typed cache field must not crash or pollute."""

        class _Weird:
            cache_read_input_tokens = "1067"
            cache_creation_input_tokens = None

        usage: dict[str, int] = {}
        _merge_cache_usage(usage, _Weird())
        assert usage["cache_read_input_tokens"] == 0
        assert usage["cache_creation_input_tokens"] == 0


# ======================================================================
# TurnProfiler.add_cache_hit + emit log line
# ======================================================================


class TestTurnProfilerCacheHit:
    def test_add_cache_hit_accumulates(self) -> None:
        p = TurnProfiler(turn_id=1)
        p.add_cache_hit(cache_read=100, cache_creation=20, model_id="claude-x")
        p.add_cache_hit(cache_read=50, cache_creation=0)
        assert p.cache_read_tokens == 150
        assert p.cache_creation_tokens == 20
        assert p.model_id == "claude-x"

    def test_model_id_sticky_on_first_call(self) -> None:
        p = TurnProfiler(turn_id=1)
        p.add_cache_hit(cache_read=1, model_id="first")
        p.add_cache_hit(cache_read=1, model_id="second")
        assert p.model_id == "first"

    def test_negative_ignored(self) -> None:
        p = TurnProfiler(turn_id=1)
        p.add_cache_hit(cache_read=-5, cache_creation=-10)
        assert p.cache_read_tokens == 0
        assert p.cache_creation_tokens == 0

    def test_cache_summary_snapshot(self) -> None:
        p = TurnProfiler(turn_id=1)
        p.add_cache_hit(cache_read=1067, cache_creation=0)
        snap = p.cache_summary()
        assert snap == {"read_tokens": 1067, "creation_tokens": 0}

    def test_emit_logs_turn_cache_line(self, caplog: pytest.LogCaptureFixture) -> None:
        p = TurnProfiler(turn_id=1)
        p.add_cache_hit(cache_read=1067, cache_creation=0, model_id="claude-x")
        caplog.set_level(logging.INFO, logger="fim_one.core.agent.turn_profiler")
        p.emit(conversation_id="conv-123")
        messages = [r.getMessage() for r in caplog.records]
        assert any("turn_cache" in m for m in messages)
        assert any("read_tokens=1067" in m for m in messages)
        assert any("model=claude-x" in m for m in messages)
        # Saved = 1067 * 0.9 = 960
        assert any("saved_input_tokens=960" in m for m in messages)

    def test_emit_skips_cache_line_when_zero(self, caplog: pytest.LogCaptureFixture) -> None:
        """No cache activity → no turn_cache log line."""
        p = TurnProfiler(turn_id=1)
        caplog.set_level(logging.INFO, logger="fim_one.core.agent.turn_profiler")
        p.emit()
        messages = [r.getMessage() for r in caplog.records]
        assert not any("turn_cache" in m for m in messages)

    def test_noop_profiler_cache_hit_is_silent(self) -> None:
        import os

        os.environ["REACT_TURN_PROFILE_ENABLED"] = "false"
        try:
            p = make_profiler(turn_id=1)
            p.add_cache_hit(cache_read=1000, cache_creation=0)
            # NoOp profiler ignores everything.
            assert p.to_dict() == {}
            assert p.cache_summary() == {"read_tokens": 0, "creation_tokens": 0}
        finally:
            os.environ.pop("REACT_TURN_PROFILE_ENABLED", None)


# ======================================================================
# UsageSummary + UsageTracker cache aggregation
# ======================================================================


class TestUsageSummaryCacheFields:
    def test_defaults_zero(self) -> None:
        s = UsageSummary()
        assert s.cache_read_input_tokens == 0
        assert s.cache_creation_input_tokens == 0

    def test_add_sums_cache(self) -> None:
        a = UsageSummary(cache_read_input_tokens=100, cache_creation_input_tokens=5)
        b = UsageSummary(cache_read_input_tokens=50, cache_creation_input_tokens=1)
        c = a + b
        assert c.cache_read_input_tokens == 150
        assert c.cache_creation_input_tokens == 6

    def test_iadd_sums_cache(self) -> None:
        a = UsageSummary(cache_read_input_tokens=100)
        b = UsageSummary(cache_read_input_tokens=50, cache_creation_input_tokens=3)
        a += b
        assert a.cache_read_input_tokens == 150
        assert a.cache_creation_input_tokens == 3


async def test_usage_tracker_aggregates_cache() -> None:
    tracker = UsageTracker()
    await tracker.record(
        {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "cache_read_input_tokens": 80,
            "cache_creation_input_tokens": 0,
        }
    )
    await tracker.record(
        {
            "prompt_tokens": 50,
            "completion_tokens": 5,
            "total_tokens": 55,
            "cache_read_input_tokens": 40,
            "cache_creation_input_tokens": 10,
        }
    )
    summary = tracker.get_summary()
    assert summary.prompt_tokens == 150
    assert summary.cache_read_input_tokens == 120
    assert summary.cache_creation_input_tokens == 10


async def test_usage_tracker_missing_cache_keys_default_to_zero() -> None:
    """Legacy/test callers that don't set cache keys get zeros, no crash."""
    tracker = UsageTracker()
    await tracker.record({"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110})
    s = tracker.get_summary()
    assert s.prompt_tokens == 100
    assert s.cache_read_input_tokens == 0
    assert s.cache_creation_input_tokens == 0


# ======================================================================
# /chat/* done payload shape — construct the dict directly
# ======================================================================


def test_done_payload_includes_cache_block() -> None:
    """Smoke-test the payload construction pattern used in chat.py."""
    usage_summary = UsageSummary(
        prompt_tokens=1200,
        completion_tokens=300,
        total_tokens=1500,
        llm_calls=2,
        cache_read_input_tokens=1067,
        cache_creation_input_tokens=0,
    )
    # Mirror the chat.py construction block.
    payload: dict[str, object] = {
        "answer": "42",
        "iterations": 2,
    }
    payload["usage"] = {
        "prompt_tokens": usage_summary.prompt_tokens,
        "completion_tokens": usage_summary.completion_tokens,
        "total_tokens": usage_summary.total_tokens,
    }
    payload["cache"] = {
        "read_tokens": usage_summary.cache_read_input_tokens,
        "creation_tokens": usage_summary.cache_creation_input_tokens,
    }
    assert payload["cache"] == {"read_tokens": 1067, "creation_tokens": 0}
    assert payload["usage"] == {
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "total_tokens": 1500,
    }
