"""Library management routes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from api.schemas import AddFolderRequest, AddFolderResponse, FolderListResponse
from core.indexer import start_indexing


router = APIRouter()


def _canonicalize_folder_path(path: str) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/api/library/add", response_model=AddFolderResponse, tags=["library"])
async def add_library_folder(
    payload: AddFolderRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> AddFolderResponse:
    folder_path = Path(payload.path).expanduser()
    if not folder_path.exists():
        raise HTTPException(status_code=400, detail="Folder does not exist")
    if not folder_path.is_dir():
        raise HTTPException(status_code=400, detail="Path must be a directory")

    canonical_path = _canonicalize_folder_path(payload.path)
    database = request.app.state.database

    async with database.connect() as connection:
        await connection.execute(
            """
            INSERT INTO folders (path, added_at, is_active)
            VALUES (?, ?, 1)
            ON CONFLICT(path) DO UPDATE SET is_active = 1
            """,
            (canonical_path, _utc_now_iso()),
        )
        cursor = await connection.execute(
            "SELECT id FROM folders WHERE path = ?",
            (canonical_path,),
        )
        folder_row = await cursor.fetchone()
        await connection.commit()

    background_tasks.add_task(
        start_indexing,
        folder_row["id"],
        canonical_path,
        database=database,
        embedder=request.app.state.embedder,
        state=request.app.state.indexing_state,
    )
    return AddFolderResponse(
        folder_id=folder_row["id"],
        path=canonical_path,
        status="scanning_started",
    )


@router.get("/api/library/folders", response_model=FolderListResponse, tags=["library"])
async def list_library_folders(request: Request) -> Dict[str, Any]:
    database = request.app.state.database
    async with database.connect() as connection:
        cursor = await connection.execute(
            """
            SELECT
                folders.id,
                folders.path,
                folders.photo_count,
                folders.last_scan,
                COALESCE(SUM(CASE WHEN photos.has_vector = 1 THEN 1 ELSE 0 END), 0) AS indexed_count
            FROM folders
            LEFT JOIN photos ON photos.folder_id = folders.id
            WHERE folders.is_active = 1
            GROUP BY folders.id
            ORDER BY folders.added_at DESC, folders.id DESC
            """
        )
        rows = await cursor.fetchall()

    return {
        "folders": [
            {
                "id": row["id"],
                "path": row["path"],
                "photo_count": row["photo_count"],
                "indexed_count": row["indexed_count"],
                "last_scan": row["last_scan"],
            }
            for row in rows
        ]
    }
