"""Per-turn phase profiler for the ReAct agent.

This module provides a light-weight :class:`TurnProfiler` that records
wall-clock timings for the distinct phases of a single ReAct "turn"
(one round of LLM call + tool execution).  The profiler is purely
observational: enabling or disabling it does not change agent behaviour.

Recorded phases
---------------

Each phase is stored as an elapsed ``float`` number of seconds.  A phase
that is not exercised in a given turn records ``0.0``.

- ``memory_load`` — loading messages from ``BaseMemory`` at turn start
- ``compact`` — time spent in ``ContextGuard.check_and_compact``
- ``tool_schema_build`` — building the tool schema / selection
- ``llm_first_token`` — time to the first streaming content token
- ``llm_total`` — total LLM call wall time
- ``tool_exec`` — sum of per-tool-call latencies in this turn

Environment
-----------

Profiling is gated by the ``REACT_TURN_PROFILE_ENABLED`` environment
variable (default: ``true``).  When disabled, :func:`make_profiler`
returns a :class:`NoOpTurnProfiler` whose methods are no-ops — the
context manager still yields, so wrapped code continues to run
normally, but nothing is recorded or logged.
"""

from __future__ import annotations

__fim_license__ = "FIM-SAL-1.1"
__fim_origin__ = "https://github.com/fim-ai/fim-one"

import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    """Parse a truthy/falsey environment variable.

    Accepts ``1``, ``true``, ``yes``, ``on`` (case-insensitive) as true
    and ``0``, ``false``, ``no``, ``off`` as false.  Unset or unknown
    values fall back to *default*.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def is_profiling_enabled() -> bool:
    """Return whether turn profiling is enabled via env var.

    Evaluated lazily on every call so tests may toggle the env var
    between runs with :func:`monkeypatch.setenv`.
    """
    return _env_bool("REACT_TURN_PROFILE_ENABLED", True)


@dataclass
class TurnProfiler:
    """Records phase-level timings for a single ReAct turn.

    Attributes:
        turn_id: The 1-indexed iteration number this profiler belongs to.
        phases: Mapping of phase name to cumulative elapsed seconds.
        cache_read_tokens: Cumulative input tokens served from the
            provider-side prompt cache across every LLM call in this
            turn.  Non-zero only when the model reports Anthropic-style
            cache usage (Claude / Bedrock / Vertex).  Surfaced in the
            ``turn_cache`` log line and the ``/chat/*`` ``done`` SSE
            payload so callers can detect cache honesty and quantify
            cost savings.
        cache_creation_tokens: Cumulative input tokens written to the
            provider-side cache during this turn.
        model_id: The resolved model identifier for the LLM used in
            this turn.  Captured once per turn (set by the first cache
            update) purely for log readability.
    """

    turn_id: int = 0
    phases: dict[str, float] = field(default_factory=dict)
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    model_id: str | None = None

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Measure elapsed wall time of a code block under *name*.

        Multiple invocations with the same *name* accumulate — useful
        for phases that fire in several places within a turn (e.g.
        ``micro_compact`` + ``check_and_compact`` both counted as
        ``compact``).
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.phases[name] = self.phases.get(name, 0.0) + elapsed

    def add(self, name: str, seconds: float) -> None:
        """Add *seconds* to the cumulative total for phase *name*.

        Useful when the caller measured elapsed time manually (e.g. the
        first-token latency inside a streaming loop) instead of using
        the ``phase()`` context manager.
        """
        if seconds < 0:
            seconds = 0.0
        self.phases[name] = self.phases.get(name, 0.0) + seconds

    def add_cache_hit(
        self,
        *,
        cache_read: int = 0,
        cache_creation: int = 0,
        model_id: str | None = None,
    ) -> None:
        """Accumulate prompt-cache token counters from one LLM call.

        Call sites feed the values pulled from the provider response
        (``LLMResult.usage["cache_read_input_tokens"]`` /
        ``cache_creation_input_tokens``).  The profiler aggregates
        across every LLM call in a single turn and ultimately surfaces
        the totals in the ``turn_cache`` log line and the ``/chat/*``
        ``done`` SSE payload.

        Negative values are clamped to zero — the method is a pure
        counter, never a reset.  ``model_id`` is stored once per turn
        on first call purely for log readability.
        """
        if cache_read > 0:
            self.cache_read_tokens += cache_read
        if cache_creation > 0:
            self.cache_creation_tokens += cache_creation
        if model_id and self.model_id is None:
            self.model_id = model_id

    def emit(self, conversation_id: str | None = None) -> None:
        """Emit a structured log line summarising this turn's phases.

        The log format is a single-line key=value series sorted by
        phase name, suitable for ``grep``/``awk`` pipelines and log
        aggregators.  Durations are rendered in milliseconds.

        When the turn recorded any prompt-cache token activity (non-zero
        ``cache_read_tokens`` / ``cache_creation_tokens``), a second
        ``turn_cache`` log line is emitted with the cache totals and a
        coarse savings estimate (cache reads are billed at ~10% of the
        normal input-token rate by Anthropic, so ``read * 0.9`` tokens
        worth of input was effectively discounted).
        """
        parts = " ".join(f"{k}={v * 1000:.0f}ms" for k, v in sorted(self.phases.items()))
        logger.info(
            "turn_profile conv=%s turn=%d %s",
            conversation_id or "-",
            self.turn_id,
            parts,
        )
        if self.cache_read_tokens > 0 or self.cache_creation_tokens > 0:
            saved = int(self.cache_read_tokens * 0.9)
            logger.info(
                "turn_cache conv=%s turn=%d model=%s read_tokens=%d "
                "create_tokens=%d saved_input_tokens=%d (~90%%)",
                conversation_id or "-",
                self.turn_id,
                self.model_id or "-",
                self.cache_read_tokens,
                self.cache_creation_tokens,
                saved,
            )

    def to_dict(self) -> dict[str, float]:
        """Return a shallow copy of the phases dict (mutation-safe)."""
        return dict(self.phases)

    def cache_summary(self) -> dict[str, int]:
        """Return a snapshot of the turn's cache token counters.

        Returns a dict with ``read_tokens`` and ``creation_tokens``
        keys suitable for inclusion in the ``/chat/*`` ``done`` SSE
        payload under the ``cache`` field.  Consumers that need to
        aggregate across turns can add the dicts key-wise.
        """
        return {
            "read_tokens": self.cache_read_tokens,
            "creation_tokens": self.cache_creation_tokens,
        }


class NoOpTurnProfiler(TurnProfiler):
    """A profiler that records nothing.

    Returned by :func:`make_profiler` when profiling is disabled.
    Retains the same interface so wiring sites remain unchanged.
    """

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        yield

    def add(self, name: str, seconds: float) -> None:
        return None

    def add_cache_hit(
        self,
        *,
        cache_read: int = 0,
        cache_creation: int = 0,
        model_id: str | None = None,
    ) -> None:
        return None

    def emit(self, conversation_id: str | None = None) -> None:
        return None

    def to_dict(self) -> dict[str, float]:
        return {}

    def cache_summary(self) -> dict[str, int]:
        return {"read_tokens": 0, "creation_tokens": 0}


def make_profiler(turn_id: int) -> TurnProfiler:
    """Return an enabled or no-op profiler depending on the env gate."""
    if is_profiling_enabled():
        return TurnProfiler(turn_id=turn_id)
    return NoOpTurnProfiler(turn_id=turn_id)
