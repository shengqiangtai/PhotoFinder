from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import config
from api.routes import image, library, search, settings, system
from core.embedder import CLIPEmbedder, embedder as default_embedder
from core.embedder_manager import init_embedder, set_embedder
from core.indexer import IndexingState, indexing_state as default_indexing_state
from db.database import Database, database as default_database
from utils.model_downloader import ModelDownloader, model_downloader as default_model_downloader


def create_app(
    database: Optional[Database] = None,
    *,
    embedder: Optional[CLIPEmbedder] = None,
    model_downloader: Optional[ModelDownloader] = None,
    indexing_state: Optional[IndexingState] = None,
) -> FastAPI:
    active_database = database or default_database
    active_embedder = embedder or default_embedder
    active_model_downloader = model_downloader or default_model_downloader
    active_indexing_state = indexing_state or default_indexing_state

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = active_database
        app.state.embedder = active_embedder
        app.state.model_downloader = active_model_downloader
        app.state.indexing_state = active_indexing_state
        await app.state.database.initialize()
        if embedder is None and isinstance(app.state.database, Database):
            app.state.embedder = await init_embedder(app.state.database)
        else:
            await init_embedder(app.state.database, embedder=active_embedder)
        yield

    app = FastAPI(title="PhotoFinder", version="1.0.0", lifespan=lifespan)
    app.state.database = active_database
    app.state.embedder = active_embedder
    app.state.model_downloader = active_model_downloader
    app.state.indexing_state = active_indexing_state
    set_embedder(active_embedder)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/web", StaticFiles(directory=config.WEB_DIR), name="web")
    app.include_router(library.router)
    app.include_router(search.router)
    app.include_router(image.router)
    app.include_router(settings.router)
    app.include_router(system.router)
    app.include_router(system.index_router)
    app.include_router(system.models_router)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/web/index.html")

    @app.get("/api/health", tags=["system"])
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
