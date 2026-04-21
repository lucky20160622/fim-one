"""Per-agent task-completion notifications over the :mod:`fim_one.core.channels`
abstraction.

When an agent (ReAct or DAG) finishes a conversation turn with a
``final_answer``, if the agent has a completion-notification channel
configured in ``model_config_json.notifications.on_complete``, post a
summary card to that channel.

This module is **distinct from** the Hook System
(:mod:`fim_one.web.hooks_bootstrap`):

- Hooks are per-tool-call enforcement points (PreToolUse / PostToolUse)
  that can block a run.
- Completion notifications are per-run, one-shot, fire-and-forget side
  effects that MUST NEVER delay or fail the user-facing chat response.

The config shape on the agent is::

    {
      "notifications": {
        "on_complete": {
          "enabled": true,
          "channel_id": "<channel-uuid>"
        }
      }
    }

Usage at the trigger site::

    asyncio.create_task(
        notify_agent_completion(
            agent=agent_shim,
            conversation_id=conversation_id,
            user_message=q,
            final_answer=answer,
            tools_used=list(tools_used_in_run),
            duration_seconds=time.time() - t0,
            session_factory=create_session,
        )
    )

Every failure path logs a warning and returns — ``notify_agent_completion``
NEVER raises.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import select as sa_select

from fim_one.core.channels import build_channel
from fim_one.core.channels.feishu import FeishuChannel


__all__ = [
    "SessionFactory",
    "build_completion_card",
    "format_duration",
    "notify_agent_completion",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@runtime_checkable
class _AgentLike(Protocol):
    """Structural subset of :class:`fim_one.web.models.agent.Agent`.

    The real ORM row works; so does a
    :class:`types.SimpleNamespace` wrapper used in the web layer when the
    code already holds a lightweight dict.  Minimum fields we read:

    - ``org_id`` — used to prevent cross-org channel targeting
    - ``id`` — logging / correlation only (may be ``None``)
    - ``name`` — shown in the notification card header
    - ``model_config_json`` — dict (or falsy) holding
      ``notifications.on_complete``
    """

    org_id: Any  # pragma: no cover - protocol attribute
    id: Any  # pragma: no cover - protocol attribute
    name: Any  # pragma: no cover - protocol attribute
    model_config_json: Any  # pragma: no cover - protocol attribute


SessionFactory = Callable[[], Any]
"""Zero-arg callable returning a fresh ``AsyncSession`` we own.

The function opens its own short-lived session via this factory so it
doesn't piggy-back on the web request's session (which will already be
closed by the time the background notification fires).
"""


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def _parse_on_complete_config(
    model_config_json: Any,
) -> dict[str, Any] | None:
    """Return the ``on_complete`` block if notifications are enabled.

    Returns ``None`` for any no-op condition (config missing, disabled,
    malformed).  Never raises.
    """
    if not model_config_json or not isinstance(model_config_json, dict):
        return None

    notifications = model_config_json.get("notifications")
    if not isinstance(notifications, dict):
        return None

    on_complete = notifications.get("on_complete")
    if not isinstance(on_complete, dict):
        return None

    if not on_complete.get("enabled"):
        return None

    return on_complete


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_duration(seconds: float) -> str:
    """Human-friendly duration string.

    Examples:
        ``0.4`` → ``"0.4s"``
        ``2.345`` → ``"2.3s"``
        ``47.0`` → ``"47.0s"``
        ``107`` → ``"1m 47s"``
        ``3725`` → ``"1h 2m 5s"``
    """
    if seconds < 0:
        seconds = 0.0
    if seconds < 60:
        return f"{seconds:.1f}s"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    return f"{minutes}m {secs}s"


def _truncate(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` chars, appending ``…`` on overflow."""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    # Chop on a line boundary if one is nearby — keeps the preview readable
    # for answers that begin with a header / first paragraph.
    head = text[:limit]
    last_nl = head.rfind("\n")
    if last_nl >= limit - 80:  # only honor if it's near the end of the cut
        head = head[:last_nl]
    return head.rstrip() + "\n\n…"


def _format_tools(tools: list[str]) -> str:
    """Join ``tools`` with commas, truncating to 6 with an ellipsis."""
    if not tools:
        return "—"
    # Deduplicate while preserving first-seen order.
    seen: set[str] = set()
    unique: list[str] = []
    for t in tools:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    if len(unique) <= 6:
        return ", ".join(unique)
    return ", ".join(unique[:6]) + ", …"


def _portal_conversation_url(conversation_id: str) -> str | None:
    """Build a clickable link back to the portal, if a base URL is set."""
    base = os.environ.get("FRONTEND_URL") or os.environ.get("BACKEND_URL")
    if not base:
        return None
    base = base.rstrip("/")
    return f"{base}/conversations/{conversation_id}"


# ---------------------------------------------------------------------------
# Card builder (Feishu v2.0)
# ---------------------------------------------------------------------------


def build_completion_card(
    *,
    agent_name: str,
    duration_seconds: float,
    tools_used: list[str],
    user_message: str,
    final_answer: str,
    conversation_id: str | None,
) -> dict[str, Any]:
    """Build a Feishu interactive card summarizing a finished agent run.

    Green ``template`` header (positive completion), duration + tools
    metadata row, and body sections for the user message and final
    answer.  Truncation: user message 200 chars, final answer 600 chars.
    """
    header_title = f"{agent_name or 'Agent'} — Task complete"[:100]

    # Metadata row — duration, tools, conversation.
    duration_str = format_duration(duration_seconds)
    tools_str = _format_tools(tools_used)
    columns: list[dict[str, Any]] = [
        {
            "tag": "column",
            "width": "weighted",
            "weight": 1,
            "elements": [
                {"tag": "markdown", "content": f"**Duration**\n{duration_str}"},
            ],
        },
        {
            "tag": "column",
            "width": "weighted",
            "weight": 2,
            "elements": [
                {"tag": "markdown", "content": f"**Tools**\n{tools_str}"},
            ],
        },
    ]
    if conversation_id:
        url = _portal_conversation_url(conversation_id)
        conv_md = (
            f"**Conversation**\n[{conversation_id[:8]}…]({url})"
            if url
            else f"**Conversation**\n`{conversation_id[:8]}…`"
        )
        columns.append(
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [{"tag": "markdown", "content": conv_md}],
            }
        )

    user_preview = _truncate(user_message or "", 200)
    answer_preview = _truncate(final_answer or "", 600)

    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": header_title},
            "template": "green",
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 12px 12px",
            "elements": [
                {
                    "tag": "column_set",
                    "horizontal_spacing": "8px",
                    "columns": columns,
                },
                {"tag": "hr"},
                {
                    "tag": "markdown",
                    "content": f"**User message**\n{user_preview}",
                },
                {"tag": "hr"},
                {
                    "tag": "markdown",
                    "content": f"**Final answer**\n{answer_preview}",
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def notify_agent_completion(
    *,
    agent: _AgentLike,
    conversation_id: str | None,
    user_message: str,
    final_answer: str,
    tools_used: list[str],
    duration_seconds: float,
    session_factory: SessionFactory,
) -> None:
    """Fire-and-forget completion notification.

    If the agent is configured for completion notifications, load the
    target :class:`fim_one.web.models.channel.Channel`, build a Feishu
    interactive card, and post it.  This function NEVER raises — every
    failure path logs a warning and returns, because a notification
    failure must not break the user-facing chat response.

    Args:
        agent: Object exposing ``org_id``, ``id``, ``name``,
            ``model_config_json``.  The ORM row or a ``SimpleNamespace``
            shim both work.
        conversation_id: ID of the conversation being notified about
            (used in the card link back to the portal).  May be ``None``.
        user_message: The triggering user message, will be truncated to
            200 chars for display.
        final_answer: The agent's final answer, truncated to 600 chars.
        tools_used: Names of tools called during the run.  Max 6 are
            shown; more are summarized as ``"…"``.  Order is preserved
            and duplicates are collapsed.
        duration_seconds: Wall-clock duration of the agent run.
        session_factory: Zero-arg callable returning a fresh
            ``AsyncSession``.  The function uses it in an ``async with``
            block — DO NOT pass the request-scoped session.
    """
    try:
        on_complete = _parse_on_complete_config(
            getattr(agent, "model_config_json", None)
        )
        if on_complete is None:
            return

        channel_id = on_complete.get("channel_id")
        if not isinstance(channel_id, str) or not channel_id:
            logger.warning(
                "Agent %r has on_complete.enabled=true but no channel_id; "
                "skipping completion notification",
                getattr(agent, "id", None),
            )
            return

        agent_org_id = getattr(agent, "org_id", None)

        # Fetch the channel in its own short-lived session.
        from fim_one.web.models.channel import Channel

        async with session_factory() as db:
            stmt = sa_select(Channel).where(Channel.id == channel_id)
            result = await db.execute(stmt)
            channel_row = result.scalar_one_or_none()

        if channel_row is None:
            logger.warning(
                "Completion notification channel %r not found (agent=%r); "
                "skipping",
                channel_id,
                getattr(agent, "id", None),
            )
            return

        if not channel_row.is_active:
            logger.warning(
                "Completion notification channel %r is inactive (agent=%r); "
                "skipping",
                channel_id,
                getattr(agent, "id", None),
            )
            return

        if agent_org_id and channel_row.org_id != agent_org_id:
            logger.warning(
                "Channel %r org_id=%r does not match agent org_id=%r; "
                "skipping completion notification",
                channel_id,
                channel_row.org_id,
                agent_org_id,
            )
            return

        config = channel_row.config if isinstance(channel_row.config, dict) else {}
        channel = build_channel(channel_row.type, config)
        if channel is None:
            logger.warning(
                "No channel adapter registered for type=%r (channel=%r); "
                "skipping completion notification",
                channel_row.type,
                channel_id,
            )
            return

        chat_id = config.get("chat_id")
        if not isinstance(chat_id, str) or not chat_id:
            logger.warning(
                "Channel %r has no chat_id configured; skipping "
                "completion notification",
                channel_id,
            )
            return

        # Build the card.  Right now we only support Feishu's v2.0 card
        # schema; future channel types should grow their own card
        # builders (``build_completion_card`` is Feishu-specific).
        if not isinstance(channel, FeishuChannel):
            logger.warning(
                "Completion notification for channel type %r is not "
                "supported yet; skipping (channel=%r)",
                channel_row.type,
                channel_id,
            )
            return

        card = build_completion_card(
            agent_name=getattr(agent, "name", None) or "Agent",
            duration_seconds=duration_seconds,
            tools_used=tools_used,
            user_message=user_message,
            final_answer=final_answer,
            conversation_id=conversation_id,
        )

        send_result = await channel.send_interactive_card(chat_id, card)
        if not send_result.ok:
            logger.warning(
                "Completion notification send failed for channel=%r: %s",
                channel_id,
                send_result.error,
            )
            return

        logger.info(
            "Posted completion notification to channel=%r (agent=%r, "
            "conversation=%r)",
            channel_id,
            getattr(agent, "id", None),
            conversation_id,
        )
    except Exception:  # pragma: no cover - defensive outer shield
        logger.exception(
            "notify_agent_completion crashed; swallowing to protect chat "
            "response (agent=%r, conversation=%r)",
            getattr(agent, "id", None),
            conversation_id,
        )
        return
