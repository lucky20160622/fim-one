"""File upload, download, and listing endpoints."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from fim_agent.web.auth import get_current_user
from fim_agent.web.models import User
from fim_agent.web.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

UPLOAD_ROOT = Path(os.environ.get("UPLOADS_DIR", "uploads"))
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _user_dir(user_id: str) -> Path:
    return UPLOAD_ROOT / f"user_{user_id}"


def _index_path(user_id: str) -> Path:
    return _user_dir(user_id) / "index.json"


def _load_index(user_id: str) -> dict[str, dict]:
    path = _index_path(user_id)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_index(user_id: str, index: dict[str, dict]) -> None:
    path = _index_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2))


@router.post("/upload", response_model=ApiResponse)
async def upload_file(
    file: UploadFile,
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ApiResponse:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No filename provided",
        )

    user_dir = _user_dir(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    stored_name = f"{file_id}_{safe_name}"
    dest = user_dir / stored_name

    # Read in chunks and enforce size limit
    total_size = 0
    with dest.open("wb") as f:
        while True:
            chunk = await file.read(8192)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB",
                )
            f.write(chunk)

    # Update index
    index = _load_index(current_user.id)
    file_url = f"/uploads/user_{current_user.id}/{stored_name}"
    index[file_id] = {
        "filename": file.filename,
        "stored_name": stored_name,
        "file_url": file_url,
        "size": total_size,
    }
    _save_index(current_user.id, index)

    return ApiResponse(
        data={
            "file_id": file_id,
            "filename": file.filename,
            "file_url": file_url,
            "size": total_size,
        }
    )


@router.get("", response_model=ApiResponse)
async def list_files(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ApiResponse:
    index = _load_index(current_user.id)
    files = [
        {
            "file_id": fid,
            "filename": meta["filename"],
            "file_url": meta["file_url"],
            "size": meta["size"],
        }
        for fid, meta in index.items()
    ]
    return ApiResponse(data=files)


@router.get("/{file_id}")
async def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> FileResponse:
    index = _load_index(current_user.id)
    meta = index.get(file_id)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    file_path = _user_dir(current_user.id) / meta["stored_name"]
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )

    return FileResponse(
        path=str(file_path),
        filename=meta["filename"],
        media_type="application/octet-stream",
    )


@router.delete("/{file_id}", response_model=ApiResponse)
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ApiResponse:
    index = _load_index(current_user.id)
    meta = index.get(file_id)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Remove from disk
    file_path = _user_dir(current_user.id) / meta["stored_name"]
    file_path.unlink(missing_ok=True)

    # Remove from index
    del index[file_id]
    _save_index(current_user.id, index)

    return ApiResponse(data={"deleted": file_id})
