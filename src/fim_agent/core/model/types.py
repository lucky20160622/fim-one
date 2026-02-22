"""Type definitions for the Model layer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolCallRequest:
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCallRequest] | None = None
    name: str | None = None

    def to_openai_dict(self) -> dict[str, Any]:
        """Convert to OpenAI API format.

        Returns:
            A dictionary conforming to the OpenAI chat completion message schema.
        """
        d: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        return d


@dataclass
class StreamChunk:
    """A single chunk from a streaming LLM response."""

    delta_content: str | None = None
    finish_reason: str | None = None
    tool_calls: list[ToolCallRequest] | None = None


@dataclass
class LLMResult:
    """Result from a non-streaming LLM call."""

    message: ChatMessage
    usage: dict[str, int] = field(default_factory=dict)
