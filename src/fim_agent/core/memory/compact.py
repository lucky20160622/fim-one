"""Smart truncation utilities for conversation history compaction.

Provides token estimation and message truncation so that long conversation
histories fit within a configurable token budget.  Supports both a fast
heuristic mode (``smart_truncate``) and an LLM-powered mode
(``llm_compact``) that summarises old turns to preserve semantic context.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fim_agent.core.model.types import ChatMessage

if TYPE_CHECKING:
    from fim_agent.core.model import BaseLLM

logger = logging.getLogger(__name__)

_COMPACT_PROMPT = """\
Summarise the following conversation history into a concise paragraph.
Preserve key facts, decisions, tool results, and any data the user or
assistant referenced.  Drop greetings, filler, and redundant back-and-forth.
Reply with ONLY the summary text — no JSON, no markdown headers.
Write in the same language as the conversation."""


class CompactUtils:
    """Stateless helpers for estimating and truncating conversation history."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for mixed-language text.

        Uses different heuristics depending on character type:
        - ASCII characters (English, code, punctuation): ~4 chars per token
        - CJK / non-ASCII characters (Chinese, Japanese, Korean, etc.):
          ~1.5 chars per token (each CJK char is typically 1-2 tokens)

        Args:
            text: The string to estimate.

        Returns:
            Approximate number of tokens.
        """
        if not text:
            return 0

        ascii_chars = 0
        non_ascii_chars = 0
        for ch in text:
            if ord(ch) < 128:
                ascii_chars += 1
            else:
                non_ascii_chars += 1

        # ASCII: ~4 chars per token; CJK/non-ASCII: ~1.5 chars per token
        tokens = ascii_chars / 4.0 + non_ascii_chars / 1.5
        return max(1, int(tokens))

    @classmethod
    def estimate_messages_tokens(cls, messages: list[ChatMessage]) -> int:
        """Estimate total token count across multiple messages.

        Each message adds ~4 tokens of overhead (role, delimiters).

        Args:
            messages: The list of messages.

        Returns:
            Approximate total token count.
        """
        total = 0
        for msg in messages:
            total += 4  # per-message overhead
            total += cls.estimate_tokens(msg.content or "")
        return total

    @classmethod
    def smart_truncate(
        cls,
        messages: list[ChatMessage],
        max_tokens: int = 8000,
    ) -> list[ChatMessage]:
        """Truncate messages to fit within a token budget.

        Keeps the most recent messages by scanning backwards from the end.
        Ensures the returned list does not start with an ``assistant`` message
        (which would confuse the LLM).

        Args:
            messages: Full conversation history (oldest first).
            max_tokens: Maximum token budget.

        Returns:
            A suffix of *messages* that fits within *max_tokens*.
        """
        if not messages:
            return []

        if cls.estimate_messages_tokens(messages) <= max_tokens:
            return list(messages)

        # Walk backwards, accumulating messages until we exceed the budget.
        result: list[ChatMessage] = []
        budget = max_tokens
        for msg in reversed(messages):
            cost = 4 + cls.estimate_tokens(msg.content or "")
            if budget - cost < 0:
                break
            result.append(msg)
            budget -= cost

        result.reverse()

        # Drop leading assistant messages — the history must start with a
        # user message so the LLM doesn't see a context-free assistant turn.
        while result and result[0].role == "assistant":
            result.pop(0)

        return result

    @classmethod
    async def llm_compact(
        cls,
        messages: list[ChatMessage],
        llm: BaseLLM,
        max_tokens: int = 8000,
        keep_recent: int = 4,
    ) -> list[ChatMessage]:
        """Compress conversation history using an LLM summary.

        If the history already fits within *max_tokens*, it is returned
        unchanged.  Otherwise the earliest turns are summarised into a
        single system message while the most recent *keep_recent*
        user/assistant pairs are kept verbatim.

        Args:
            messages: Full conversation history (oldest first).
            llm: A fast LLM to use for summarisation.
            max_tokens: Maximum token budget for the returned history.
            keep_recent: Number of recent messages to preserve verbatim.

        Returns:
            A compacted message list that fits within *max_tokens*.
        """
        if not messages:
            return []

        total = cls.estimate_messages_tokens(messages)
        if total <= max_tokens:
            return list(messages)

        # Split: keep the most recent messages, summarise the rest.
        if len(messages) <= keep_recent:
            # Not enough to split — fall back to heuristic truncation.
            return cls.smart_truncate(messages, max_tokens)

        old_messages = messages[:-keep_recent]
        recent_messages = list(messages[-keep_recent:])

        # Build the text block to summarise.
        lines: list[str] = []
        for msg in old_messages:
            prefix = "User" if msg.role == "user" else "Assistant"
            lines.append(f"{prefix}: {msg.content}")
        history_text = "\n".join(lines)

        try:
            result = await llm.chat([
                ChatMessage(role="system", content=_COMPACT_PROMPT),
                ChatMessage(role="user", content=history_text),
            ])
            summary = (result.message.content or "").strip()
        except Exception:
            logger.warning("LLM compact failed, falling back to truncation", exc_info=True)
            return cls.smart_truncate(messages, max_tokens)

        if not summary:
            return cls.smart_truncate(messages, max_tokens)

        compacted = [
            ChatMessage(role="system", content=f"[Conversation summary]: {summary}"),
            *recent_messages,
        ]

        # If the compacted result is still too long, truncate the recent part.
        if cls.estimate_messages_tokens(compacted) > max_tokens:
            return cls.smart_truncate(compacted, max_tokens)

        return compacted
