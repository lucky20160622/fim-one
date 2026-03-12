"""Tests for the step verifier (per-step verification for DAG execution)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from fim_one.core.model import ChatMessage, LLMResult
from fim_one.core.planner.step_verifier import VerificationResult, verify_step

from .conftest import FakeLLM


# ======================================================================
# VerificationResult dataclass
# ======================================================================


class TestVerificationResult:
    """Verify VerificationResult dataclass fields."""

    def test_passed_result(self) -> None:
        result = VerificationResult(passed=True, reason="looks good")
        assert result.passed is True
        assert result.reason == "looks good"

    def test_failed_result(self) -> None:
        result = VerificationResult(passed=False, reason="incomplete")
        assert result.passed is False
        assert result.reason == "incomplete"


# ======================================================================
# verify_step() — happy paths
# ======================================================================


def _make_verification_llm(passed: bool, reason: str) -> FakeLLM:
    """Create a FakeLLM that returns a verification JSON response."""
    response = LLMResult(
        message=ChatMessage(
            role="assistant",
            content=json.dumps({"passed": passed, "reason": reason}),
        ),
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    return FakeLLM(responses=[response])


class TestVerifyStepPassed:
    """verify_step returns passed=True when LLM says so."""

    @pytest.mark.asyncio
    async def test_passed(self) -> None:
        llm = _make_verification_llm(True, "looks good")
        result = await verify_step(
            task="Summarise the document",
            result_summary="The document is about AI.",
            llm=llm,
        )
        assert result.passed is True
        assert result.reason == "looks good"


class TestVerifyStepFailed:
    """verify_step returns passed=False when LLM says so."""

    @pytest.mark.asyncio
    async def test_failed(self) -> None:
        llm = _make_verification_llm(False, "incomplete")
        result = await verify_step(
            task="Summarise the document",
            result_summary="The document is about AI.",
            llm=llm,
        )
        assert result.passed is False
        assert result.reason == "incomplete"


# ======================================================================
# verify_step() — error handling
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


class TestVerifyStepError:
    """verify_step defaults to passed=True on exception.

    When the LLM raises, ``structured_llm_call`` catches the error internally
    and returns the ``default_value``.  The outer ``verify_step`` then converts
    that dict to a ``VerificationResult``.  Either path (structured default or
    outer except) must yield ``passed=True``.
    """

    @pytest.mark.asyncio
    async def test_exception_defaults_to_passed(self) -> None:
        llm = _RaisingLLM()
        result = await verify_step(
            task="Do something",
            result_summary="Did it",
            llm=llm,
        )
        assert result.passed is True
        # The reason may come from the structured_llm_call default_value
        # fallback or from the outer except block -- both are valid.
        assert "fallback" in result.reason.lower() or "error" in result.reason.lower()


# ======================================================================
# verify_step() — truncation
# ======================================================================


class TestVerifyStepTruncation:
    """verify_step truncates result_summary to 2000 chars."""

    @pytest.mark.asyncio
    async def test_truncates_long_result(self) -> None:
        llm = _make_verification_llm(True, "ok")

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

        long_result = "x" * 5000
        await verify_step(task="task", result_summary=long_result, llm=llm)

        assert len(captured_messages) == 1
        user_content = captured_messages[0][0].content
        assert isinstance(user_content, str)
        # The prompt should contain the truncated version (2000 chars of 'x')
        # not the full 5000 chars
        assert "x" * 2000 in user_content
        assert "x" * 2001 not in user_content
