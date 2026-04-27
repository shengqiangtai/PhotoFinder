from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.embedder import APIEmbedder, BaseEmbedder, LocalEmbedder
from db.migrations import API_VECTOR_DIM, LOCAL_VECTOR_DIM, reset_vectors_for_mode

_current_embedder: BaseEmbedder | Any | None = None


class EmbedderSwitchError(RuntimeError):
    error_code = "switch_failed"
    status_code = 400


class IndexingRunningError(EmbedderSwitchError):
    error_code = "indexing_running"
    status_code = 409


class MissingAPIKeyError(EmbedderSwitchError):
    error_code = "no_api_key"
    status_code = 400


@dataclass(frozen=True)
class EmbedderSwitchResult:
    embedder: BaseEmbedder | Any
    mode: str
    provider: str
    requires_reindex: bool


async def read_app_config(database) -> dict[str, str]:
    async with database.connect() as connection:
        rows = await (await connection.execute("SELECT key, value FROM app_config")).fetchall()
    return {row["key"]: row["value"] for row in rows}


async def write_app_config(database, values: dict[str, str]) -> None:
    async with database.connect() as connection:
        await connection.executemany(
            """
            INSERT INTO app_config (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            list(values.items()),
        )
        await connection.commit()


async def init_embedder(database=None, *, embedder: BaseEmbedder | Any | None = None) -> BaseEmbedder | Any:
    global _current_embedder
    if embedder is not None:
        _current_embedder = embedder
        return embedder
    if database is None:
        from db.database import database as default_database

        database = default_database

    config_rows = await read_app_config(database)
    mode = config_rows.get("embedding_mode", "local")
    provider = config_rows.get("api_provider", "jina")
    if mode == "api":
        _current_embedder = APIEmbedder(provider=provider, api_key=config_rows.get(f"{provider}_api_key", ""))
    else:
        _current_embedder = LocalEmbedder()
    return _current_embedder


def get_embedder() -> BaseEmbedder | Any:
    if _current_embedder is None:
        raise RuntimeError("Embedder not initialized")
    return _current_embedder


def set_embedder(embedder: BaseEmbedder | Any) -> None:
    global _current_embedder
    _current_embedder = embedder


async def switch_embedder(
    mode: str,
    provider: str = "jina",
    *,
    database,
    indexing_state=None,
) -> EmbedderSwitchResult:
    if mode not in {"local", "api"}:
        raise ValueError("mode must be 'local' or 'api'")
    if provider not in {"jina", "voyage"}:
        raise ValueError("provider must be 'jina' or 'voyage'")
    if indexing_state is not None and getattr(indexing_state, "is_running", False):
        raise IndexingRunningError("请等待当前索引任务完成后再切换")

    config_rows = await read_app_config(database)
    if mode == "api":
        api_key = config_rows.get(f"{provider}_api_key", "")
        if not api_key:
            raise MissingAPIKeyError(f"请先配置 {provider.title()} API Key")
        new_embedder = APIEmbedder(provider=provider, api_key=api_key)
        target_dim = API_VECTOR_DIM
    else:
        new_embedder = LocalEmbedder()
        target_dim = LOCAL_VECTOR_DIM

    async with database.connect() as connection:
        await reset_vectors_for_mode(
            connection,
            dim=target_dim,
            vector_extension_enabled=database.sqlite_vec_available,
        )
        await connection.executemany(
            """
            INSERT INTO app_config (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            [
                ("embedding_mode", mode),
                ("api_provider", provider),
                ("vector_dim", str(target_dim)),
            ],
        )
        await connection.commit()

    set_embedder(new_embedder)
    return EmbedderSwitchResult(
        embedder=new_embedder,
        mode=mode,
        provider=provider,
        requires_reindex=True,
    )
