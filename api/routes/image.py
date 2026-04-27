from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response


router = APIRouter(tags=["image"])


@router.get("/api/image/{photo_id}")
async def get_image(photo_id: int, request: Request):
    async with request.app.state.database.connect() as connection:
        row = await (
            await connection.execute("SELECT path FROM photos WHERE id = ?", (photo_id,))
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")

    media_type = mimetypes.guess_type(row["path"])[0] or "application/octet-stream"
    return FileResponse(row["path"], media_type=media_type)


@router.get("/api/thumbnail/{photo_id}")
async def get_thumbnail(photo_id: int, request: Request):
    async with request.app.state.database.connect() as connection:
        row = await (
            await connection.execute(
                "SELECT thumbnail FROM photos WHERE id = ?",
                (photo_id,),
            )
        ).fetchone()

    if row is None or row["thumbnail"] is None:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return Response(
        content=row["thumbnail"],
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )
