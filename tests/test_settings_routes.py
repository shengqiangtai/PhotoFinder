import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import sqlite_vec
from fastapi.testclient import TestClient

from api.app import create_app
from core.indexer import IndexingState
from db.database import Database


class _FakeEmbedder:
    is_loaded = False
    visual_session = None
    loaded_text_model = None

    async def load(self) -> None:
        self.is_loaded = True

    @property
    def vector_dim(self) -> int:
        return 512


class _FakeAPIEmbedder:
    def __init__(self, provider: str = "jina", api_key: str | None = None) -> None:
        self.provider = provider
        self.api_key = api_key

    async def validate_api_key(self, api_key: str) -> bool:
        return api_key == "valid-key"

    @property
    def vector_dim(self) -> int:
        return 1024

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key)


class SettingsRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.database = Database(db_path=self.temp_path / "photofinder.db")
        asyncio.run(self.database.initialize())
        self.indexing_state = IndexingState()

    def _create_app(self):
        return create_app(
            database=self.database,
            embedder=_FakeEmbedder(),
            indexing_state=self.indexing_state,
        )

    def test_get_settings_hides_keys_and_reports_default_local_mode(self) -> None:
        app = self._create_app()
        response = TestClient(app).get("/api/settings")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["embedding_mode"], "local")
        self.assertEqual(payload["api_provider"], "jina")
        self.assertFalse(payload["jina_key_configured"])
        self.assertFalse(payload["voyage_key_configured"])
        self.assertEqual(payload["vector_dim"], 512)
        self.assertFalse(payload["index_mode_mismatch"])
        self.assertNotIn("valid-key", str(payload))

    def test_post_api_key_validates_and_stores_key_without_returning_secret(self) -> None:
        app = self._create_app()

        with mock.patch("api.routes.settings.APIEmbedder", _FakeAPIEmbedder):
            response = TestClient(app).post(
                "/api/settings/api-key",
                json={"provider": "jina", "api_key": "valid-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "provider": "jina"})

        async def fetch_key() -> str:
            async with self.database.connect() as connection:
                row = await (
                    await connection.execute("SELECT value FROM app_config WHERE key = 'jina_api_key'")
                ).fetchone()
                return row["value"]

        self.assertEqual(asyncio.run(fetch_key()), "valid-key")

    def test_post_api_key_rejects_invalid_key(self) -> None:
        app = self._create_app()

        with mock.patch("api.routes.settings.APIEmbedder", _FakeAPIEmbedder):
            response = TestClient(app).post(
                "/api/settings/api-key",
                json={"provider": "jina", "api_key": "bad-key"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_key")

    def test_post_embedding_mode_rejects_missing_api_key(self) -> None:
        app = self._create_app()

        response = TestClient(app).post(
            "/api/settings/embedding-mode",
            json={"mode": "api", "provider": "jina"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "no_api_key")

    def test_post_embedding_mode_returns_409_when_indexing_is_running(self) -> None:
        app = self._create_app()
        app.state.indexing_state.is_running = True

        response = TestClient(app).post(
            "/api/settings/embedding-mode",
            json={"mode": "local"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "indexing_running")

    def test_post_embedding_mode_switches_to_api_and_resets_existing_vectors(self) -> None:
        app = self._create_app()

        async def seed() -> None:
            async with self.database.connect() as connection:
                await connection.execute(
                    "UPDATE app_config SET value = 'valid-key' WHERE key = 'jina_api_key'"
                )
                await connection.execute(
                    """
                    INSERT INTO folders (id, path, added_at, photo_count, is_active)
                    VALUES (1, ?, '2024-01-01T00:00:00+00:00', 1, 1)
                    """,
                    (str(self.temp_path),),
                )
                await connection.execute(
                    """
                    INSERT INTO photos (
                        id, path, filename, folder_id, indexed_at, file_mtime,
                        has_vector, vector_source
                    )
                    VALUES (1, 'photo.jpg', 'photo.jpg', 1, '2024-01-01T00:00:00+00:00', 1.0, 1, 'local')
                    """
                )
                vector = sqlite_vec.serialize_float32(np.ones(512, dtype=np.float32).tolist())
                await connection.execute(
                    "INSERT INTO photo_vectors (photo_id, embedding) VALUES (1, ?)",
                    (vector,),
                )
                await connection.commit()

        asyncio.run(seed())

        with mock.patch("api.routes.settings.APIEmbedder", _FakeAPIEmbedder):
            response = TestClient(app).post(
                "/api/settings/embedding-mode",
                json={"mode": "api", "provider": "jina"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "api")
        self.assertTrue(response.json()["requires_reindex"])

        async def fetch_state() -> tuple[dict[str, str], int, tuple[int, str | None]]:
            async with self.database.connect() as connection:
                rows = await (
                    await connection.execute(
                        "SELECT key, value FROM app_config WHERE key IN ('embedding_mode', 'api_provider', 'vector_dim')"
                    )
                ).fetchall()
                vector_count = await (await connection.execute("SELECT COUNT(*) FROM photo_vectors")).fetchone()
                photo = await (
                    await connection.execute("SELECT has_vector, vector_source FROM photos WHERE id = 1")
                ).fetchone()
            return {row["key"]: row["value"] for row in rows}, vector_count[0], (photo["has_vector"], photo["vector_source"])

        config_rows, vector_count, photo_state = asyncio.run(fetch_state())

        self.assertEqual(config_rows, {"embedding_mode": "api", "api_provider": "jina", "vector_dim": "1024"})
        self.assertEqual(vector_count, 0)
        self.assertEqual(photo_state, (0, None))

        status = TestClient(app).get("/api/index/status")
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["requires_reindex"])


if __name__ == "__main__":
    unittest.main()
