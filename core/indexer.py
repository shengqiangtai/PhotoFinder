from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import sqlite_vec

import config
from core.embedder import embedder as default_embedder
from core.scanner import scan_folder
from utils.image_utils import extract_exif_date, generate_thumbnail, read_image_safe


@dataclass
class IndexingState:
    is_running: bool = False
    current_job_id: Optional[int] = None
    total: int = 0
    processed: int = 0
    failed: int = 0
    current_file: str = ""
    phase: str = "idle"
    eta_seconds: int = 0
    speed_per_second: float = 0.0


indexing_state = IndexingState()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _vector_source(embedder) -> str:
    provider = getattr(embedder, "provider", None)
    if provider in {"jina", "voyage"}:
        return provider
    return "local"


def _extract_photo_metadata(photo_path: str) -> dict[str, Any]:
    image = read_image_safe(photo_path)
    try:
        width, height = image.size
    finally:
        image.close()

    stat_result = Path(photo_path).stat()
    return {
        "filename": Path(photo_path).name,
        "size_bytes": stat_result.st_size,
        "width": width,
        "height": height,
        "taken_at": extract_exif_date(photo_path),
        "indexed_at": _utc_now_iso(),
        "file_mtime": stat_result.st_mtime,
        "has_vector": 0,
        "thumbnail": None,
        "error_msg": None,
    }


def _build_error_photo_metadata(photo_path: str, error: Exception) -> dict[str, Any]:
    path = Path(photo_path)
    try:
        stat_result = path.stat()
    except OSError:
        stat_result = None

    return {
        "filename": path.name,
        "size_bytes": stat_result.st_size if stat_result is not None else None,
        "width": None,
        "height": None,
        "taken_at": None,
        "indexed_at": _utc_now_iso(),
        "file_mtime": stat_result.st_mtime if stat_result is not None else 0.0,
        "has_vector": 0,
        "thumbnail": None,
        "error_msg": str(error),
    }


async def _write_photo_row(connection: Any, folder_id: int, photo_path: str, metadata: dict[str, Any]) -> None:
    await connection.execute(
        """
        INSERT INTO photos (
            path, filename, folder_id, size_bytes, width, height, taken_at,
            indexed_at, file_mtime, has_vector, vector_source, thumbnail, error_msg
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            filename = excluded.filename,
            folder_id = excluded.folder_id,
            size_bytes = excluded.size_bytes,
            width = excluded.width,
            height = excluded.height,
            taken_at = excluded.taken_at,
            indexed_at = excluded.indexed_at,
            file_mtime = excluded.file_mtime,
            has_vector = excluded.has_vector,
            vector_source = NULL,
            thumbnail = excluded.thumbnail,
            error_msg = excluded.error_msg
        """,
        (
            photo_path,
            metadata["filename"],
            folder_id,
            metadata["size_bytes"],
            metadata["width"],
            metadata["height"],
            metadata["taken_at"],
            metadata["indexed_at"],
            metadata["file_mtime"],
            metadata["has_vector"],
            metadata["thumbnail"],
            metadata["error_msg"],
        ),
    )


async def _mark_photo_error(connection: Any, photo_id: int, message: str) -> None:
    await connection.execute(
        """
        UPDATE photos
        SET has_vector = 0, vector_source = NULL, error_msg = ?, indexed_at = ?
        WHERE id = ?
        """,
        (message[:500], _utc_now_iso(), photo_id),
    )


async def _store_vector(connection: Any, photo_id: int, vector: np.ndarray) -> None:
    serialized = sqlite_vec.serialize_float32(np.asarray(vector, dtype=np.float32).tolist())
    await connection.execute("DELETE FROM photo_vectors WHERE photo_id = ?", (photo_id,))
    await connection.execute(
        "INSERT INTO photo_vectors (photo_id, embedding) VALUES (?, ?)",
        (photo_id, serialized),
    )


async def _update_index_job(connection: Any, state: IndexingState, *, status: str, error_msg: Optional[str] = None) -> None:
    if state.current_job_id is None:
        return

    await connection.execute(
        """
        UPDATE index_jobs
        SET status = ?, total_files = ?, processed_files = ?, failed_files = ?,
            finished_at = CASE WHEN ? IN ('completed', 'failed') THEN ? ELSE finished_at END,
            error_msg = ?
        WHERE id = ?
        """,
        (
            status,
            state.total,
            state.processed,
            state.failed,
            status,
            _utc_now_iso(),
            error_msg,
            state.current_job_id,
        ),
    )


def _update_eta(state: IndexingState, start_time: float) -> None:
    elapsed = max(time.monotonic() - start_time, 1e-6)
    state.speed_per_second = round(state.processed / elapsed, 2) if state.processed else 0.0
    if state.speed_per_second > 0 and state.total >= state.processed:
        remaining = state.total - state.processed
        state.eta_seconds = int(remaining / state.speed_per_second) if remaining else 0
    else:
        state.eta_seconds = 0


async def start_indexing(
    folder_id: int,
    folder_path: str,
    *,
    database,
    embedder=default_embedder,
    state: Optional[IndexingState] = None,
) -> None:
    active_state = state or indexing_state
    if active_state.is_running:
        raise RuntimeError("An indexing job is already running")

    active_state.is_running = True
    active_state.phase = "scanning"
    active_state.total = 0
    active_state.processed = 0
    active_state.failed = 0
    active_state.current_file = ""
    active_state.eta_seconds = 0
    active_state.speed_per_second = 0.0
    start_time = time.monotonic()

    async with database.connect() as connection:
        cursor = await connection.execute(
            """
            INSERT INTO index_jobs (folder_id, status, total_files, processed_files, failed_files, started_at)
            VALUES (?, 'running', 0, 0, 0, ?)
            """,
            (folder_id, _utc_now_iso()),
        )
        active_state.current_job_id = cursor.lastrowid
        await connection.commit()

    try:
        scan_result = await scan_folder(folder_path, database=database)

        async with database.connect() as connection:
            for photo_path in scan_result.new_files:
                try:
                    metadata = _extract_photo_metadata(photo_path)
                except Exception as exc:
                    metadata = _build_error_photo_metadata(photo_path, exc)
                await _write_photo_row(connection, folder_id, photo_path, metadata)

            for photo_path in scan_result.modified_files:
                try:
                    metadata = _extract_photo_metadata(photo_path)
                except Exception as exc:
                    metadata = _build_error_photo_metadata(photo_path, exc)
                await _write_photo_row(connection, folder_id, photo_path, metadata)

            for photo_path in scan_result.deleted_files:
                photo_cursor = await connection.execute(
                    "SELECT id FROM photos WHERE path = ?",
                    (photo_path,),
                )
                row = await photo_cursor.fetchone()
                if row is not None:
                    await connection.execute("DELETE FROM photo_vectors WHERE photo_id = ?", (row["id"],))
                await connection.execute("DELETE FROM photos WHERE path = ?", (photo_path,))

            photo_count = await (
                await connection.execute(
                    "SELECT COUNT(*) FROM photos WHERE folder_id = ?",
                    (folder_id,),
                )
            ).fetchone()
            await connection.execute(
                "UPDATE folders SET last_scan = ?, photo_count = ? WHERE id = ?",
                (_utc_now_iso(), photo_count[0], folder_id),
            )
            await connection.commit()

        active_state.phase = "embedding"
        await embedder.load()

        async with database.connect() as connection:
            pending_rows = await (
                await connection.execute(
                    """
                    SELECT id, path, filename
                    FROM photos
                    WHERE has_vector = 0
                    ORDER BY id ASC
                    """
                )
            ).fetchall()

        active_state.total = len(pending_rows)
        await _update_job_status(database, active_state, status="running")

        for offset in range(0, len(pending_rows), config.BATCH_SIZE):
            batch_rows = pending_rows[offset : offset + config.BATCH_SIZE]
            batch_paths = [row["path"] for row in batch_rows]
            batch_size = 8 if _vector_source(embedder) != "local" else config.BATCH_SIZE
            batch_vectors = await _maybe_await(embedder.encode_images_batch(batch_paths, batch_size=batch_size))

            if len(batch_vectors) == len(batch_rows):
                pairs = zip(batch_rows, batch_vectors)
            else:
                pairs = []
                for row in batch_rows:
                    try:
                        vector = await _maybe_await(embedder.encode_image(row["path"]))
                    except Exception as exc:
                        active_state.failed += 1
                        async with database.connect() as connection:
                            await _mark_photo_error(connection, row["id"], str(exc))
                            await connection.commit()
                        _update_eta(active_state, start_time)
                        await _update_job_status(database, active_state, status="running")
                        continue
                    pairs.append((row, vector))

            for row, vector in pairs:
                active_state.current_file = row["filename"]
                if vector is None:
                    active_state.failed += 1
                    async with database.connect() as connection:
                        await _mark_photo_error(connection, row["id"], "Embedding failed")
                        await connection.commit()
                    _update_eta(active_state, start_time)
                    await _update_job_status(database, active_state, status="running")
                    continue
                try:
                    thumbnail = generate_thumbnail(row["path"], size=config.THUMBNAIL_SIZE)
                    async with database.connect() as connection:
                        await _store_vector(connection, row["id"], vector)
                        await connection.execute(
                            """
                            UPDATE photos
                            SET has_vector = 1, vector_source = ?, thumbnail = ?, indexed_at = ?, error_msg = NULL
                            WHERE id = ?
                            """,
                            (_vector_source(embedder), thumbnail, _utc_now_iso(), row["id"]),
                        )
                        await connection.commit()
                    active_state.processed += 1
                except Exception as exc:
                    active_state.failed += 1
                    async with database.connect() as connection:
                        await _mark_photo_error(connection, row["id"], str(exc))
                        await connection.commit()

                _update_eta(active_state, start_time)
                await _update_job_status(database, active_state, status="running")

        active_state.phase = "done"
        active_state.current_file = ""
        active_state.eta_seconds = 0
        await _update_job_status(database, active_state, status="completed")
    except Exception as exc:
        active_state.phase = "idle"
        active_state.current_file = ""
        await _update_job_status(database, active_state, status="failed", error_msg=str(exc))
        raise
    finally:
        active_state.is_running = False


async def _update_job_status(database, state: IndexingState, *, status: str, error_msg: Optional[str] = None) -> None:
    async with database.connect() as connection:
        await _update_index_job(connection, state, status=status, error_msg=error_msg)
        await connection.commit()
