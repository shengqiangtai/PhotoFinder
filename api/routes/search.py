from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import config
from api.schemas import SearchResponse
from core.searcher import debug_search, search
from utils.query_rewriter import rewrite_query_for_clip


router = APIRouter(tags=["search"])


def _resolve_query_for_search(q: str, *, text_model: str | None) -> tuple[str, str | None]:
    rewritten = rewrite_query_for_clip(q)
    use_rewritten_query = rewritten.was_rewritten and text_model not in {"multilingual", "api"}
    query_for_search = rewritten.rewritten_query if use_rewritten_query else q
    rewritten_query = rewritten.rewritten_query if use_rewritten_query else None
    return query_for_search, rewritten_query


@router.get("/api/search/debug")
async def debug_search_photos(
    q: str,
    request: Request,
    top_k: int = config.DEFAULT_TOP_K,
    folder_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty")

    top_k = max(1, min(top_k, config.MAX_TOP_K))
    embedder = request.app.state.embedder

    try:
        await embedder.load()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"error": "model_loading", "message": "AI 模型正在加载，请稍后再试"},
        )

    text_model = "api" if getattr(embedder, "provider", None) in {"jina", "voyage"} else getattr(embedder, "loaded_text_model", None)
    query_for_search, rewritten_query = _resolve_query_for_search(q, text_model=text_model)

    try:
        debug_payload = await debug_search(
            query=query_for_search,
            top_k=top_k,
            folder_id=folder_id,
            date_from=date_from,
            date_to=date_to,
            database=request.app.state.database,
            embedder=embedder,
        )
    except RuntimeError:
        return JSONResponse(
            status_code=503,
            content={"error": "model_loading", "message": "AI 模型正在加载，请稍后再试"},
        )

    return {
        "query": q,
        "query_for_search": query_for_search,
        "text_model": debug_payload["text_model"],
        "rewritten_query": rewritten_query,
        "variants": debug_payload["variants"],
    }


@router.get("/api/search", response_model=SearchResponse)
async def search_photos(
    q: str,
    request: Request,
    top_k: int = config.DEFAULT_TOP_K,
    folder_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty")

    top_k = max(1, min(top_k, config.MAX_TOP_K))
    embedder = request.app.state.embedder

    try:
        await embedder.load()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"error": "model_loading", "message": "AI 模型正在加载，请稍后再试"},
        )

    query_for_search, rewritten_query = _resolve_query_for_search(
        q,
        text_model="api" if getattr(embedder, "provider", None) in {"jina", "voyage"} else getattr(embedder, "loaded_text_model", None),
    )

    started = time.perf_counter()
    try:
        results = await search(
            query=query_for_search,
            top_k=top_k,
            folder_id=folder_id,
            date_from=date_from,
            date_to=date_to,
            database=request.app.state.database,
            embedder=embedder,
        )
    except RuntimeError:
        return JSONResponse(
            status_code=503,
            content={"error": "model_loading", "message": "AI 模型正在加载，请稍后再试"},
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return SearchResponse(
        results=results,
        total=len(results),
        query=q,
        rewritten_query=rewritten_query,
        search_time_ms=elapsed_ms,
    )
