"""Shared utility helpers for fim-agent core modules."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from *text*.

    Handles common LLM output patterns:

    1. Pure JSON string.
    2. JSON wrapped in ``\\`\\`\\`json ... \\`\\`\\``` code fences.
    3. JSON embedded in prose (first balanced ``{`` to ``}``).

    Returns:
        A parsed ``dict`` if a valid JSON object was found, otherwise ``None``.
    """
    text = text.strip()

    # 1. Direct parse.
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Strip markdown code fences.
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        try:
            data = json.loads(fence_match.group(1).strip())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. Extract first balanced { ... } block.
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start : i + 1])
                        if isinstance(data, dict):
                            return data
                    except (json.JSONDecodeError, TypeError):
                        pass
                    break

    return None
