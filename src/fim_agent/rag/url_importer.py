"""URL → Markdown importer using Jina Reader API."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_JINA_READER_BASE = "https://r.jina.ai/"
_MAX_CONCURRENT = 3


async def fetch_url_as_markdown(url: str, jina_api_key: str) -> dict:
    """Fetch a URL via Jina Reader and return title + markdown content.

    Returns a dict with keys: ``url``, ``title``, ``content``.
    Raises ``httpx.HTTPStatusError`` on non-2xx responses.
    """
    headers = {
        "Authorization": f"Bearer {jina_api_key}",
        "Accept": "application/json",
        "X-Return-Format": "markdown",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{_JINA_READER_BASE}{url}", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        payload = data.get("data", {})
        return {
            "url": url,
            "title": payload.get("title") or url,
            "content": payload.get("content", ""),
        }


def get_jina_api_key() -> str:
    key = os.environ.get("JINA_API_KEY", "")
    if not key:
        raise ValueError("JINA_API_KEY is not set")
    return key
