"""Runtime embedding mode and API key settings."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config
from api.schemas import APIKeyRequest, APIKeyResponse, EmbeddingModeRequest, EmbeddingModeResponse, SettingsResponse
from core.embedder import APIEmbedder
from core.embedder_manager import (
    EmbedderSwitchError,
    read_app_config,
    switch_embedder,
    write_app_config,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _model_status(path, *, loaded: bool, downloading: bool) -> str:
    if loaded:
        return "loaded"
    if downloading:
        return "downloading"
    if path.exists():
        return "loading"
    return "not_downloaded"


def _active_vector_source(mode: str, provider: str) -> str:
    return provider if mode == "api" else "local"


async def _has_reindex_gap(database) -> bool:
    async with database.connect() as connection:
        total_row = await (await connection.execute("SELECT COUNT(*) FROM photos")).fetchone()
        indexed_row = await (await connection.execute("SELECT COUNT(*) FROM photos WHERE has_vector = 1")).fetchone()
    return total_row[0] > indexed_row[0]


async def _index_mode_mismatch(database, *, mode: str, provider: str, vector_dim: int) -> bool:
    source = _active_vector_source(mode, provider)
    async with database.connect() as connection:
        mismatch_row = await (
            await connection.execute(
                """
                SELECT COUNT(*)
                FROM photos
                WHERE has_vector = 1
                  AND COALESCE(vector_source, '') != ?
                """,
                (source,),
            )
        ).fetchone()
        stored_dim_row = await (
            await connection.execute("SELECT value FROM app_config WHERE key = 'vector_dim'")
        ).fetchone()
    try:
        stored_dim = int(stored_dim_row["value"]) if stored_dim_row is not None else vector_dim
    except (TypeError, ValueError):
        stored_dim = vector_dim
    return mismatch_row[0] > 0 or stored_dim != vector_dim


@router.get("", response_model=SettingsResponse)
async def get_settings(request: Request) -> SettingsResponse:
    database = request.app.state.database
    downloader = request.app.state.model_downloader
    embedder = request.app.state.embedder
    config_rows = await read_app_config(database)

    mode = config_rows.get("embedding_mode", "local")
    provider = config_rows.get("api_provider", "jina")
    vector_dim = int(config_rows.get("vector_dim") or getattr(embedder, "vector_dim", config.VECTOR_DIM))
    return SettingsResponse(
        embedding_mode=mode,
        api_provider=provider,
        jina_key_configured=bool(config_rows.get("jina_api_key")),
        voyage_key_configured=bool(config_rows.get("voyage_api_key")),
        local_model_status={
            "visual": _model_status(
                config.CLIP_VISUAL_MODEL,
                loaded=bool(getattr(embedder, "is_loaded", False) and getattr(embedder, "visual_session", None) is not None),
                downloading=bool(downloader.progress.downloading and downloader.progress.model == "clip_visual"),
            ),
            "textual": _model_status(
                config.CLIP_TEXTUAL_MODEL,
                loaded=bool(getattr(embedder, "is_loaded", False) and getattr(embedder, "loaded_text_model", None) == "textual"),
                downloading=bool(downloader.progress.downloading and downloader.progress.model == "clip_textual"),
            ),
            "multilingual": _model_status(
                config.MULTILINGUAL_MODEL,
                loaded=bool(getattr(embedder, "is_loaded", False) and getattr(embedder, "loaded_text_model", None) == "multilingual"),
                downloading=bool(downloader.progress.downloading and downloader.progress.model == "multilingual"),
            ),
        },
        vector_dim=vector_dim,
        index_mode_mismatch=await _index_mode_mismatch(
            database,
            mode=mode,
            provider=provider,
            vector_dim=vector_dim,
        ),
    )


@router.post("/api-key", response_model=APIKeyResponse)
async def configure_api_key(payload: APIKeyRequest, request: Request) -> APIKeyResponse | JSONResponse:
    provider = payload.provider.lower()
    if provider not in {"jina", "voyage"}:
        return JSONResponse(status_code=400, content={"error": "invalid_provider", "message": "API 服务商不支持"})

    probe = APIEmbedder(provider=provider)
    if not await probe.validate_api_key(payload.api_key):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_key", "message": "API Key 无效，请检查"},
        )

    await write_app_config(request.app.state.database, {f"{provider}_api_key": payload.api_key})
    return APIKeyResponse(status="ok", provider=provider)


@router.post("/embedding-mode", response_model=EmbeddingModeResponse)
async def change_embedding_mode(payload: EmbeddingModeRequest, request: Request) -> EmbeddingModeResponse | JSONResponse:
    mode = payload.mode.lower()
    provider = (payload.provider or "jina").lower()
    try:
        result = await switch_embedder(
            mode,
            provider,
            database=request.app.state.database,
            indexing_state=request.app.state.indexing_state,
        )
    except EmbedderSwitchError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_code, "message": str(exc)},
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": "invalid_mode", "message": str(exc)})

    request.app.state.embedder = result.embedder
    return EmbeddingModeResponse(
        mode=result.mode,
        provider=result.provider,
        requires_reindex=result.requires_reindex,
        message="切换成功，需要重新建索引才能使用新模式搜索",
    )


async def requires_reindex(database) -> bool:
    return await _has_reindex_gap(database)
