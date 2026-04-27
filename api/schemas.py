from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, model_validator


class AddFolderRequest(BaseModel):
    path: str


class AddFolderResponse(BaseModel):
    folder_id: int
    path: str
    status: str


class FolderResponse(BaseModel):
    id: int
    path: str
    photo_count: int
    indexed_count: int
    last_scan: Optional[str] = None


class FolderListResponse(BaseModel):
    folders: List[FolderResponse]


class ModelStatusResponse(BaseModel):
    visual: str
    textual: str
    multilingual: str


class DownloadProgressResponse(BaseModel):
    model: str
    percent: int


class ModelDownloadRequest(BaseModel):
    model: str


class ModelDownloadStartResponse(BaseModel):
    status: str


class ModelDownloadStatusResponse(BaseModel):
    downloading: bool
    model: Optional[str] = None
    percent: int
    error: Optional[str] = None


class IndexStatusResponse(BaseModel):
    is_running: bool
    phase: str
    total: int
    processed: int
    failed: int
    current_file: str
    progress_percent: int
    eta_seconds: int
    speed_per_second: float
    requires_reindex: bool = False


class SearchResultResponse(BaseModel):
    id: int
    filename: str
    taken_at: Optional[str] = None
    thumbnail_url: str
    full_image_url: str
    similarity: float
    match_score: int


class SearchResponse(BaseModel):
    results: List[SearchResultResponse]
    total: int
    query: str
    rewritten_query: Optional[str] = None
    search_time_ms: int


class SystemInfoResponse(BaseModel):
    version: str
    model_status: ModelStatusResponse
    download_progress: Optional[DownloadProgressResponse] = None
    total_photos: int
    indexed_photos: int
    db_size_mb: float
    lan_url: Optional[str] = None
    first_run: bool


class APIKeyRequest(BaseModel):
    provider: str
    api_key: str


class APIKeyResponse(BaseModel):
    status: str
    provider: str


class EmbeddingModeRequest(BaseModel):
    mode: str
    provider: Optional[str] = "jina"


class EmbeddingModeResponse(BaseModel):
    mode: str
    provider: str
    requires_reindex: bool
    message: str


class SettingsResponse(BaseModel):
    embedding_mode: str
    api_provider: str
    jina_key_configured: bool
    voyage_key_configured: bool
    local_model_status: ModelStatusResponse
    vector_dim: int
    index_mode_mismatch: bool


class OpenFolderResponse(BaseModel):
    selected_path: Optional[str] = None
    cancelled: Optional[bool] = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "OpenFolderResponse":
        selected = self.selected_path is not None
        cancelled = self.cancelled is not None

        if selected == cancelled:
            raise ValueError("OpenFolderResponse must have exactly one outcome")
        if cancelled and self.cancelled is not True:
            raise ValueError("cancelled outcome must be true")
        return self
