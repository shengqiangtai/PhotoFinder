from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

import aiosqlite

import config
from db.migrations import run_migrations

LOGGER = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or config.DB_PATH)
        self.sqlite_vec_available = False

    async def initialize(self) -> None:
        config.ensure_app_directories()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with self.connect() as connection:
            self.sqlite_vec_available = await self._configure_connection(connection)
            await run_migrations(
                connection,
                vector_extension_enabled=self.sqlite_vec_available,
            )

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(self.db_path)
        try:
            connection.row_factory = sqlite3.Row
            await self._configure_connection(connection)
            yield connection
        finally:
            await connection.close()

    async def _configure_connection(self, connection: aiosqlite.Connection) -> bool:
        await connection.execute("PRAGMA foreign_keys = ON")
        return await self._try_load_sqlite_vec(connection)

    async def _try_load_sqlite_vec(self, connection: aiosqlite.Connection) -> bool:
        try:
            import sqlite_vec
        except ImportError:
            LOGGER.warning("sqlite-vec is not installed; falling back to plain table storage.")
            return False

        raw_connection = connection._conn
        if not hasattr(raw_connection, "enable_load_extension") or not hasattr(raw_connection, "load_extension"):
            LOGGER.warning("sqlite3 extension loading is unavailable in this Python build; using fallback table.")
            return False

        try:
            await connection.enable_load_extension(True)
            await connection.load_extension(str(sqlite_vec.loadable_path()))
            await connection.enable_load_extension(False)
            return True
        except Exception as exc:
            LOGGER.warning("Failed to load sqlite-vec extension: %s", exc)
            return False


database = Database()
