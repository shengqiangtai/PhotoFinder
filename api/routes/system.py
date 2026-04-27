"""System, models, and indexing routes."""

from __future__ import annotations

import logging
import os
from io import BytesIO
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import Response
import qrcode

import config
from api.schemas import (
    IndexStatusResponse,
    ModelDownloadRequest,
    ModelDownloadStartResponse,
    ModelDownloadStatusResponse,
    ModelStatusResponse,
    OpenFolderResponse,
    SystemInfoResponse,
)
from api.routes.settings import requires_reindex
from utils.network_utils import get_lan_ip


router = APIRouter(prefix="/api/system", tags=["system"])
index_router = APIRouter(prefix="/api/index", tags=["index"])
models_router = APIRouter(prefix="/api/models", tags=["models"])
LOGGER = logging.getLogger(__name__)


def _model_status(path, *, loaded: bool, downloading: bool) -> str:
    if loaded:
        return "loaded"
    if downloading:
        return "downloading"
    if path.exists():
        return "loading"
    return "not_downloaded"


def _download_progress_payload(downloader) -> Dict[str, object] | None:
    if downloader.progress.model is None:
        return None
    return {
        "model": downloader.progress.model,
        "percent": downloader.progress.percent,
    }


def _get_lan_url() -> str | None:
    lan_ip = get_lan_ip()
    return "http://{}:{}".format(lan_ip, config.PORT) if lan_ip else None


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_info(request: Request) -> SystemInfoResponse:
    database = request.app.state.database
    embedder = request.app.state.embedder
    downloader = request.app.state.model_downloader

    async with database.connect() as connection:
        total_cursor = await connection.execute("SELECT COUNT(*) FROM photos")
        indexed_cursor = await connection.execute("SELECT COUNT(*) FROM photos WHERE has_vector = 1")
        first_run_cursor = await connection.execute(
            "SELECT value FROM app_config WHERE key = 'first_run'"
        )

        total_photos = (await total_cursor.fetchone())[0]
        indexed_photos = (await indexed_cursor.fetchone())[0]
        first_run_row = await first_run_cursor.fetchone()

    lan_url = _get_lan_url()
    db_size_bytes = os.path.getsize(database.db_path) if database.db_path.exists() else 0
    embedder_loaded = bool(getattr(embedder, "is_loaded", False))

    return SystemInfoResponse(
        version=request.app.version,
        model_status=ModelStatusResponse(
            visual=_model_status(
                config.CLIP_VISUAL_MODEL,
                loaded=bool(embedder_loaded and getattr(embedder, "visual_session", None) is not None),
                downloading=bool(downloader.progress.downloading and downloader.progress.model == "clip_visual"),
            ),
            textual=_model_status(
                config.CLIP_TEXTUAL_MODEL,
                loaded=bool(embedder_loaded and getattr(embedder, "loaded_text_model", None) == "textual"),
                downloading=bool(downloader.progress.downloading and downloader.progress.model == "clip_textual"),
            ),
            multilingual=_model_status(
                config.MULTILINGUAL_MODEL,
                loaded=bool(embedder_loaded and getattr(embedder, "loaded_text_model", None) == "multilingual"),
                downloading=bool(downloader.progress.downloading and downloader.progress.model == "multilingual"),
            ),
        ),
        download_progress=_download_progress_payload(downloader),
        total_photos=total_photos,
        indexed_photos=indexed_photos,
        db_size_mb=round(db_size_bytes / (1024 * 1024), 2),
        lan_url=lan_url,
        first_run=bool(first_run_row and first_run_row["value"] == "1"),
    )


@router.get("/qrcode")
async def get_system_qrcode() -> Response:
    lan_url = _get_lan_url()
    if lan_url is None:
        raise HTTPException(
            status_code=503,
            detail="LAN URL is unavailable for QR code generation",
        )
    buffer = BytesIO()
    qrcode.make(lan_url).save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")


@router.get("/open-folder", response_model=OpenFolderResponse)
async def open_folder() -> OpenFolderResponse:
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        selected_path = filedialog.askdirectory()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to open folder picker") from exc
    finally:
        if root is not None:
            root.destroy()

    if selected_path:
        return OpenFolderResponse(selected_path=selected_path)
    return OpenFolderResponse(cancelled=True)


@index_router.get("/status", response_model=IndexStatusResponse)
async def get_index_status(request: Request) -> IndexStatusResponse:
    state = request.app.state.indexing_state
    progress_percent = int((state.processed / state.total) * 100) if state.total else 0
    return IndexStatusResponse(
        is_running=state.is_running,
        phase=state.phase,
        total=state.total,
        processed=state.processed,
        failed=state.failed,
        current_file=state.current_file,
        progress_percent=progress_percent,
        eta_seconds=state.eta_seconds,
        speed_per_second=state.speed_per_second,
        requires_reindex=await requires_reindex(request.app.state.database),
    )


async def _download_and_reset(model_name: str, downloader, embedder) -> None:
    try:
        await downloader.download_model(model_name)
        embedder.reset()
    except Exception:
        LOGGER.exception("Failed to download model %s", model_name)


@models_router.post("/download", response_model=ModelDownloadStartResponse)
async def start_model_download(
    payload: ModelDownloadRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ModelDownloadStartResponse:
    downloader = request.app.state.model_downloader
    if payload.model not in downloader.model_assets:
        raise HTTPException(status_code=400, detail="Unsupported model")

    background_tasks.add_task(
        _download_and_reset,
        payload.model,
        downloader,
        request.app.state.embedder,
    )
    return ModelDownloadStartResponse(status="download_started")


@models_router.get("/download/status", response_model=ModelDownloadStatusResponse)
async def get_model_download_status(request: Request) -> ModelDownloadStatusResponse:
    progress = request.app.state.model_downloader.progress
    return ModelDownloadStatusResponse(
        downloading=progress.downloading,
        model=progress.model,
        percent=progress.percent,
        error=progress.error,
    )
