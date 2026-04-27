import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Set
from unittest import mock


class Phase1SmokeTests(unittest.TestCase):
    def test_config_can_create_runtime_directories(self) -> None:
        import config

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch.object(config, "APP_DATA_DIR", tmp_path):
                with mock.patch.object(config, "MODELS_DIR", tmp_path / "models"):
                    with mock.patch.object(config, "CACHE_DIR", tmp_path / "cache"):
                        config.ensure_app_directories()
                        self.assertTrue(tmp_path.exists())
                        self.assertTrue((tmp_path / "models").exists())
                        self.assertTrue((tmp_path / "cache").exists())

    def test_database_initialization_creates_core_tables(self) -> None:
        from db.database import Database

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "photofinder.db"
            database = Database(db_path=db_path)

            asyncio.run(database.initialize())

            self.assertTrue(db_path.exists())

            async def fetch_table_names() -> Set[str]:
                names: Set[str] = set()
                async with database.connect() as connection:
                    cursor = await connection.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                    )
                    rows = await cursor.fetchall()
                    names.update(row[0] for row in rows)
                return names

            table_names = asyncio.run(fetch_table_names())
            self.assertIn("photos", table_names)
            self.assertIn("folders", table_names)
            self.assertIn("index_jobs", table_names)
            self.assertIn("app_config", table_names)

    def test_database_initialization_seeds_api_mode_config_and_vector_source(self) -> None:
        from db.database import Database

        with tempfile.TemporaryDirectory() as tmp_dir:
            database = Database(db_path=Path(tmp_dir) / "photofinder.db")

            asyncio.run(database.initialize())

            async def fetch_config_and_columns() -> tuple[dict[str, str], set[str]]:
                async with database.connect() as connection:
                    config_rows = await (
                        await connection.execute(
                            """
                            SELECT key, value
                            FROM app_config
                            WHERE key IN (
                                'embedding_mode', 'api_provider', 'jina_api_key',
                                'voyage_api_key', 'vector_dim'
                            )
                            """
                        )
                    ).fetchall()
                    columns = await (await connection.execute("PRAGMA table_info(photos)")).fetchall()
                return {row["key"]: row["value"] for row in config_rows}, {row["name"] for row in columns}

            config_rows, column_names = asyncio.run(fetch_config_and_columns())

            self.assertEqual(config_rows["embedding_mode"], "local")
            self.assertEqual(config_rows["api_provider"], "jina")
            self.assertEqual(config_rows["jina_api_key"], "")
            self.assertEqual(config_rows["voyage_api_key"], "")
            self.assertEqual(config_rows["vector_dim"], "512")
            self.assertIn("vector_source", column_names)

if __name__ == "__main__":
    unittest.main()
