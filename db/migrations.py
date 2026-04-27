from __future__ import annotations

from typing import Sequence

LOCAL_VECTOR_DIM = 512
API_VECTOR_DIM = 1024


BASE_MIGRATIONS: Sequence[str] = (
    """
    CREATE TABLE IF NOT EXISTS folders (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        path        TEXT NOT NULL UNIQUE,
        added_at    TEXT NOT NULL,
        last_scan   TEXT,
        photo_count INTEGER DEFAULT 0,
        is_active   INTEGER DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS photos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        path        TEXT NOT NULL UNIQUE,
        filename    TEXT NOT NULL,
        folder_id   INTEGER REFERENCES folders(id) ON DELETE CASCADE,
        size_bytes  INTEGER,
        width       INTEGER,
        height      INTEGER,
        taken_at    TEXT,
        indexed_at  TEXT NOT NULL,
        file_mtime  REAL NOT NULL,
        has_vector  INTEGER DEFAULT 0,
        vector_source TEXT DEFAULT 'local',
        thumbnail   BLOB,
        error_msg   TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_photos_path ON photos(path)",
    "CREATE INDEX IF NOT EXISTS idx_photos_folder ON photos(folder_id)",
    "CREATE INDEX IF NOT EXISTS idx_photos_taken_at ON photos(taken_at)",
    "CREATE INDEX IF NOT EXISTS idx_photos_has_vector ON photos(has_vector)",
    """
    CREATE TABLE IF NOT EXISTS index_jobs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_id       INTEGER REFERENCES folders(id),
        status          TEXT NOT NULL,
        total_files     INTEGER DEFAULT 0,
        processed_files INTEGER DEFAULT 0,
        failed_files    INTEGER DEFAULT 0,
        started_at      TEXT,
        finished_at     TEXT,
        error_msg       TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_config (
        key     TEXT PRIMARY KEY,
        value   TEXT NOT NULL
    )
    """,
)

APP_CONFIG_SEEDS: Sequence[tuple[str, str]] = (
    ("clip_model", "clip-vit-b-32"),
    ("text_model", "multilingual"),
    ("top_k", "20"),
    ("thumbnail_size", "256"),
    ("first_run", "1"),
    ("embedding_mode", "local"),
    ("api_provider", "jina"),
    ("jina_api_key", ""),
    ("voyage_api_key", ""),
    ("vector_dim", str(LOCAL_VECTOR_DIM)),
)


def create_vectors_table(dim: int, *, vector_extension_enabled: bool) -> str:
    if vector_extension_enabled:
        return f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS photo_vectors USING vec0(
            photo_id    INTEGER PRIMARY KEY,
            embedding   FLOAT[{dim}]
        )
        """
    return """
    CREATE TABLE IF NOT EXISTS photo_vectors (
        photo_id    INTEGER PRIMARY KEY,
        embedding   BLOB
    )
    """


async def _ensure_column(connection, table_name: str, column_name: str, definition: str) -> None:
    rows = await (await connection.execute(f"PRAGMA table_info({table_name})")).fetchall()
    if column_name in {row["name"] for row in rows}:
        return
    await connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


async def _read_vector_dim(connection) -> int:
    row = await (
        await connection.execute("SELECT value FROM app_config WHERE key = 'vector_dim'")
    ).fetchone()
    if row is None:
        return LOCAL_VECTOR_DIM
    try:
        return int(row["value"])
    except (TypeError, ValueError):
        return LOCAL_VECTOR_DIM


async def recreate_vectors_table(connection, *, dim: int, vector_extension_enabled: bool) -> None:
    await connection.execute("DROP TABLE IF EXISTS photo_vectors")
    await connection.execute(create_vectors_table(dim, vector_extension_enabled=vector_extension_enabled))


async def reset_vectors_for_mode(connection, *, dim: int, vector_extension_enabled: bool) -> None:
    await recreate_vectors_table(connection, dim=dim, vector_extension_enabled=vector_extension_enabled)
    await connection.execute("UPDATE photos SET has_vector = 0, vector_source = NULL")
    await connection.execute(
        """
        INSERT INTO app_config (key, value)
        VALUES ('vector_dim', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(dim),),
    )


async def run_migrations(connection, *, vector_extension_enabled: bool) -> None:
    for statement in BASE_MIGRATIONS:
        await connection.execute(statement)

    await _ensure_column(connection, "photos", "vector_source", "TEXT DEFAULT 'local'")

    await connection.executemany(
        "INSERT OR IGNORE INTO app_config (key, value) VALUES (?, ?)",
        APP_CONFIG_SEEDS,
    )

    vector_dim = await _read_vector_dim(connection)
    await connection.execute(create_vectors_table(vector_dim, vector_extension_enabled=vector_extension_enabled))
    await connection.commit()
