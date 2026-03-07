"""Artifact listing and download endpoints for conversation tool outputs."""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from fim_agent.web.auth import get_current_user
from fim_agent.web.exceptions import AppError
from fim_agent.web.models import User
from fim_agent.web.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["artifacts"])

UPLOAD_ROOT = Path(os.environ.get("UPLOADS_DIR", "uploads"))


def _artifacts_dir(conversation_id: str) -> Path:
    return UPLOAD_ROOT / "conversations" / conversation_id / "artifacts"


async def _validate_conversation_ownership(
    conversation_id: str, user_id: str,
) -> None:
    """Ensure the conversation belongs to *user_id*."""
    from sqlalchemy import select as sa_select

    from fim_agent.db import create_session
    from fim_agent.web.models import Conversation

    async with create_session() as session:
        result = await session.execute(
            sa_select(Conversation.id).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise AppError("conversation_not_found", status_code=404)


@router.get("/{conversation_id}/artifacts", response_model=ApiResponse)
async def list_artifacts(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> ApiResponse:
    """List all artifacts for a conversation."""
    await _validate_conversation_ownership(conversation_id, current_user.id)
    d = _artifacts_dir(conversation_id)
    if not d.exists():
        return ApiResponse(data=[])

    artifacts = []
    for f in sorted(d.iterdir()):
        if not f.is_file():
            continue
        # stored_name format: {artifact_id}_{original_name}
        parts = f.name.split("_", 1)
        artifact_id = parts[0]
        original_name = parts[1] if len(parts) > 1 else f.name
        mime, _ = mimetypes.guess_type(str(f))
        artifacts.append({
            "id": artifact_id,
            "name": original_name,
            "mime_type": mime or "application/octet-stream",
            "size": f.stat().st_size,
            "url": f"/api/conversations/{conversation_id}/artifacts/{artifact_id}",
        })
    return ApiResponse(data=artifacts)


@router.get("/{conversation_id}/artifacts/{artifact_id}")
async def download_artifact(
    conversation_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download a specific artifact."""
    await _validate_conversation_ownership(conversation_id, current_user.id)
    d = _artifacts_dir(conversation_id)
    if not d.exists():
        raise AppError("artifact_not_found", status_code=404)

    # Find file matching the artifact_id prefix.
    for f in d.iterdir():
        if f.name.startswith(f"{artifact_id}_"):
            parts = f.name.split("_", 1)
            original_name = parts[1] if len(parts) > 1 else f.name
            mime, _ = mimetypes.guess_type(str(f))
            return FileResponse(
                path=str(f),
                filename=original_name,
                media_type=mime or "application/octet-stream",
            )

    raise AppError("artifact_not_found", status_code=404)
