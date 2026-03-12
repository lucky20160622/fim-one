"""Tests for the auto-routing classifier (ReAct vs DAG mode selection)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from fim_one.core.model import ChatMessage, LLMResult
from fim_one.core.planner.router import RouteDecision, classify_execution_mode

from .conftest import FakeLLM


# ======================================================================
# RouteDecision dataclass
# ======================================================================


class TestRouteDecision:
    """Verify RouteDecision dataclass fields."""

    def test_react_decision(self) -> None:
        decision = RouteDecision(mode="react", reasoning="simple query")
        assert decision.mode == "react"
        assert decision.reasoning == "simple query"

    def test_dag_decision(self) -> None:
        decision = RouteDecision(mode="dag", reasoning="complex multi-step task")
        assert decision.mode == "dag"
        assert decision.reasoning == "complex multi-step task"


# ======================================================================
# classify_execution_mode() -- happy paths
# ======================================================================


def _make_classification_llm(mode: str, reasoning: str) -> FakeLLM:
    """Create a FakeLLM that returns a classification JSON response."""
    response = LLMResult(
        message=ChatMessage(
            role="assistant",
            content=json.dumps({"mode": mode, "reasoning": reasoning}),
        ),
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    return FakeLLM(responses=[response])


class TestClassifyReact:
    """classify_execution_mode returns mode='react' when LLM says so."""

    @pytest.mark.asyncio
    async def test_react_classification(self) -> None:
        llm = _make_classification_llm("react", "simple greeting")
        result = await classify_execution_mode("Hello, how are you?", llm)
        assert result.mode == "react"
        assert result.reasoning == "simple greeting"


class TestClassifyDag:
    """classify_execution_mode returns mode='dag' when LLM says so."""

    @pytest.mark.asyncio
    async def test_dag_classification(self) -> None:
        llm = _make_classification_llm("dag", "multi-step analysis task")
        result = await classify_execution_mode(
            "Find all customers who churned, analyze reasons, draft email campaign",
            llm,
        )
        assert result.mode == "dag"
        assert result.reasoning == "multi-step analysis task"


# ======================================================================
# classify_execution_mode() -- error handling
# ======================================================================


class _RaisingLLM(FakeLLM):
    """A FakeLLM that always raises on chat()."""

    def __init__(self) -> None:
        super().__init__(responses=[])

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResult:
        raise RuntimeError("LLM is down")


class TestClassifyError:
    """classify_execution_mode defaults to 'react' on exception."""

    @pytest.mark.asyncio
    async def test_exception_defaults_to_react(self) -> None:
        llm = _RaisingLLM()
        result = await classify_execution_mode("any query", llm)
        assert result.mode == "react"
        # The reasoning should mention some error context
        assert "error" in result.reasoning.lower() or "fallback" in result.reasoning.lower()


# ======================================================================
# classify_execution_mode() -- invalid mode normalization
# ======================================================================


class TestClassifyInvalidMode:
    """Invalid mode values are normalized to 'react'."""

    @pytest.mark.asyncio
    async def test_invalid_mode_normalized_to_react(self) -> None:
        llm = _make_classification_llm("turbo_mode", "unknown mode")
        result = await classify_execution_mode("some query", llm)
        assert result.mode == "react"

    @pytest.mark.asyncio
    async def test_empty_mode_normalized_to_react(self) -> None:
        llm = _make_classification_llm("", "empty mode")
        result = await classify_execution_mode("some query", llm)
        assert result.mode == "react"


# ======================================================================
# classify_execution_mode() -- query truncation
# ======================================================================


class TestClassifyQueryTruncation:
    """classify_execution_mode truncates query to 2000 chars."""

    @pytest.mark.asyncio
    async def test_truncates_long_query(self) -> None:
        llm = _make_classification_llm("react", "ok")

        # Capture what was actually sent to the LLM
        captured_messages: list[list[ChatMessage]] = []
        original_chat = llm.chat

        async def _capture_chat(
            messages: list[ChatMessage],
            **kwargs: Any,
        ) -> LLMResult:
            captured_messages.append(messages)
            return await original_chat(messages, **kwargs)

        llm.chat = _capture_chat  # type: ignore[assignment]

        long_query = "x" * 5000
        await classify_execution_mode(long_query, llm)

        assert len(captured_messages) == 1
        user_content = captured_messages[0][0].content
        assert isinstance(user_content, str)
        # The prompt should contain the truncated version (2000 chars of 'x')
        # not the full 5000 chars
        assert "x" * 2000 in user_content
        assert "x" * 2001 not in user_content
