"""Registry mapping Channel type strings to concrete classes."""

from __future__ import annotations

from typing import Any

from .base import BaseChannel
from .feishu import FeishuChannel

# Map of ``type`` column value → BaseChannel subclass.
CHANNEL_TYPES: dict[str, type[BaseChannel]] = {
    "feishu": FeishuChannel,
}


def get_channel_class(channel_type: str) -> type[BaseChannel] | None:
    """Return the class registered for ``channel_type`` or ``None``."""
    return CHANNEL_TYPES.get(channel_type)


def build_channel(
    channel_type: str, config: dict[str, Any]
) -> BaseChannel | None:
    """Instantiate a channel from its type + config.

    Returns ``None`` if the type is not registered.
    """
    cls = get_channel_class(channel_type)
    if cls is None:
        return None
    return cls(config)
