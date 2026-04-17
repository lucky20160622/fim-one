"""Abstract base class for outbound messaging channels."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChannelSendResult:
    """Standard outcome shape for a channel send/callback call."""

    ok: bool
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class BaseChannel(abc.ABC):
    """Platform-agnostic outbound messaging channel.

    Implementations wrap platform-specific SDKs / HTTP APIs.  The ``config``
    dict is whatever was stored in the ``channels.config`` row (decrypted
    by ``EncryptedJSON`` on read).  For Feishu this typically contains
    ``app_id``, ``app_secret``, ``chat_id``, plus optional
    ``verification_token`` / ``encrypt_key``.
    """

    type: str = "base"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    # -- Outbound --

    @abc.abstractmethod
    async def send_message(self, payload: dict[str, Any]) -> ChannelSendResult:
        """Send a message payload.

        ``payload`` is platform-specific.  For Feishu::

            {"chat_id": "oc_xxx", "msg_type": "text", "content": "hello"}
            {"chat_id": "oc_xxx", "msg_type": "interactive", "card": {...}}
        """

    # -- Inbound (callbacks) --

    async def verify_signature(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Return True if the callback's signature headers are valid.

        Default: no verification.  Platforms that support signed callbacks
        (Feishu encrypt key, Slack HMAC) MUST override this.
        """
        return True

    @abc.abstractmethod
    async def handle_callback(
        self,
        body: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Process an incoming callback event.

        Returns the payload that should be sent back to the platform (for
        challenge/verification handshakes) merged with a normalized
        ``event`` dict describing what happened::

            {
                "response": {"challenge": "..."},  # what to echo back
                "event": {
                    "kind": "url_verification" | "card_action" | "unknown",
                    "action": "approve" | "reject" | None,
                    "confirmation_id": str | None,
                    "open_id": str | None,
                },
            }
        """
