"""OpenAI-compatible LLM implementation."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from .base import BaseLLM
from .types import ChatMessage, LLMResult, StreamChunk, ToolCallRequest

logger = logging.getLogger(__name__)


class OpenAICompatibleLLM(BaseLLM):
    """LLM implementation for any OpenAI-compatible API endpoint.

    Works with OpenAI, Azure OpenAI, vLLM, Ollama, and other providers that
    expose the ``/v1/chat/completions`` interface.

    Args:
        api_key: API key for authentication.
        base_url: Base URL of the API (e.g. ``https://api.openai.com/v1``).
        model: Model identifier (e.g. ``gpt-4o``).
        default_temperature: Fallback temperature when none is specified per-call.
        default_max_tokens: Fallback max_tokens when none is specified per-call.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        default_temperature: float = 0.7,
        default_max_tokens: int = 4096,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResult:
        """Send a non-streaming chat completion request.

        Args:
            messages: The conversation history.
            tools: Optional tool definitions.
            temperature: Sampling temperature override.
            max_tokens: Maximum tokens to generate.
            response_format: Optional response format constraint.

        Returns:
            An ``LLMResult`` with the parsed assistant message and usage stats.

        Raises:
            openai.APIError: On upstream API failures.
        """
        kwargs = self._build_request_kwargs(
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            stream=False,
        )
        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        assistant_msg = self._parse_choice_message(choice)

        usage: dict[str, int] = {}
        if response.usage is not None:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResult(message=assistant_msg, usage=usage)

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Send a streaming chat completion request.

        Yields ``StreamChunk`` instances as they arrive.  Tool-call deltas are
        accumulated and emitted as complete ``ToolCallRequest`` objects once the
        stream signals ``finish_reason`` of ``"tool_calls"`` or ``"stop"``.

        Args:
            messages: The conversation history.
            tools: Optional tool definitions.
            temperature: Sampling temperature override.
            max_tokens: Maximum tokens to generate.

        Yields:
            ``StreamChunk`` for each fragment received from the API.

        Raises:
            openai.APIError: On upstream API failures.
        """
        kwargs = self._build_request_kwargs(
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        stream = await self._client.chat.completions.create(**kwargs)

        # Accumulate partial tool calls keyed by their index in the array.
        pending_tool_calls: dict[int, _PartialToolCall] = {}

        async for chunk in stream:  # type: ignore[union-attr]
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            # --- content fragment ---
            delta_content = getattr(delta, "content", None)

            # --- tool-call fragments ---
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in pending_tool_calls:
                        pending_tool_calls[idx] = _PartialToolCall()
                    partial = pending_tool_calls[idx]
                    if tc_delta.id:
                        partial.id = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            partial.name += tc_delta.function.name
                        if tc_delta.function.arguments:
                            partial.arguments += tc_delta.function.arguments

            # Emit a chunk for every delta that carries content.
            if delta_content:
                yield StreamChunk(delta_content=delta_content, finish_reason=finish_reason)

            # When the stream finishes, flush any accumulated tool calls.
            if finish_reason in ("tool_calls", "stop") and pending_tool_calls:
                completed = self._flush_tool_calls(pending_tool_calls)
                yield StreamChunk(
                    finish_reason=finish_reason,
                    tool_calls=completed,
                )
                pending_tool_calls.clear()
            elif finish_reason and not pending_tool_calls:
                # Final chunk with no tool calls (normal stop).
                yield StreamChunk(finish_reason=finish_reason)

    @property
    def abilities(self) -> dict[str, bool]:
        """All standard capabilities are supported."""
        return {
            "tool_call": True,
            "json_mode": True,
            "vision": True,
            "streaming": True,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_request_kwargs(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        response_format: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Build the keyword arguments dict for the OpenAI client call."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [m.to_openai_dict() for m in messages],
            "temperature": temperature if temperature is not None else self._default_temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._default_max_tokens,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
        if response_format is not None:
            kwargs["response_format"] = response_format
        return kwargs

    @staticmethod
    def _parse_tool_calls(
        raw_tool_calls: list[Any],
    ) -> list[ToolCallRequest]:
        """Parse tool calls from an OpenAI response choice."""
        result: list[ToolCallRequest] = []
        for tc in raw_tool_calls:
            try:
                arguments = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Failed to parse tool-call arguments for %s, using raw string",
                    tc.function.name,
                )
                arguments = {"_raw": tc.function.arguments}
            result.append(
                ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments,
                )
            )
        return result

    @staticmethod
    def _parse_choice_message(choice: Any) -> ChatMessage:
        """Convert an OpenAI choice object into a ``ChatMessage``."""
        msg = choice.message
        tool_calls: list[ToolCallRequest] | None = None
        if msg.tool_calls:
            tool_calls = OpenAICompatibleLLM._parse_tool_calls(msg.tool_calls)
        return ChatMessage(
            role=msg.role,
            content=msg.content,
            tool_calls=tool_calls,
        )

    @staticmethod
    def _flush_tool_calls(
        pending: dict[int, _PartialToolCall],
    ) -> list[ToolCallRequest]:
        """Convert accumulated partial tool calls into complete requests."""
        completed: list[ToolCallRequest] = []
        for idx in sorted(pending):
            partial = pending[idx]
            try:
                arguments = json.loads(partial.arguments)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Failed to parse streamed tool-call arguments for %s, using raw string",
                    partial.name,
                )
                arguments = {"_raw": partial.arguments}
            completed.append(
                ToolCallRequest(
                    id=partial.id,
                    name=partial.name,
                    arguments=arguments,
                )
            )
        return completed


class _PartialToolCall:
    """Mutable accumulator for streamed tool-call fragments."""

    __slots__ = ("arguments", "id", "name")

    def __init__(self) -> None:
        self.id: str = ""
        self.name: str = ""
        self.arguments: str = ""
