import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from db.database import Database


class LibraryRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.database = Database(db_path=self.temp_path / "photofinder.db")
        asyncio.run(self.database.initialize())

    def test_add_folder_starts_background_indexing_and_persists_folder(self) -> None:
        from api.app import create_app

        folder_path = self.temp_path / "library"
        folder_path.mkdir()

        app = create_app(database=self.database)
        client = TestClient(app)

        with mock.patch("api.routes.library.start_indexing", new_callable=AsyncMock) as start_indexing_mock:
            response = client.post("/api/library/add", json={"path": str(folder_path)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "folder_id": 1,
                "path": str(folder_path.resolve(strict=False)),
                "status": "scanning_started",
            },
        )
        start_indexing_mock.assert_awaited_once_with(
            1,
            str(folder_path.resolve(strict=False)),
            database=self.database,
            embedder=app.state.embedder,
            state=app.state.indexing_state,
        )

        async def fetch_folder():
            async with self.database.connect() as connection:
                return await (
                    await connection.execute(
                        "SELECT id, path, photo_count, last_scan FROM folders"
                    )
                ).fetchone()

        folder_row = asyncio.run(fetch_folder())

        self.assertIsNotNone(folder_row)
        self.assertEqual(folder_row["path"], str(folder_path.resolve(strict=False)))
        self.assertEqual(folder_row["photo_count"], 0)
        self.assertIsNone(folder_row["last_scan"])

    def test_get_folders_returns_folder_statistics(self) -> None:
        from api.app import create_app

        folder_one = str((self.temp_path / "one").resolve(strict=False))
        folder_two = str((self.temp_path / "two").resolve(strict=False))
        inactive_folder = str((self.temp_path / "inactive").resolve(strict=False))

        async def seed() -> None:
            async with self.database.connect() as connection:
                await connection.execute(
                    """
                    INSERT INTO folders (id, path, added_at, last_scan, photo_count, is_active)
                    VALUES (1, ?, '2024-01-01T00:00:00+00:00', '2024-01-02T00:00:00+00:00', 2, 1)
                    """,
                    (folder_one,),
                )
                await connection.execute(
                    """
                    INSERT INTO folders (id, path, added_at, last_scan, photo_count, is_active)
                    VALUES (2, ?, '2024-01-03T00:00:00+00:00', NULL, 1, 1)
                    """,
                    (folder_two,),
                )
                await connection.execute(
                    """
                    INSERT INTO folders (id, path, added_at, last_scan, photo_count, is_active)
                    VALUES (3, ?, '2024-01-04T00:00:00+00:00', '2024-01-05T00:00:00+00:00', 5, 0)
                    """,
                    (inactive_folder,),
                )
                await connection.executemany(
                    """
                    INSERT INTO photos (path, filename, folder_id, indexed_at, file_mtime, has_vector)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (folder_one + "/a.jpg", "a.jpg", 1, "2024-01-02T00:00:00+00:00", 1.0, 1),
                        (folder_one + "/b.jpg", "b.jpg", 1, "2024-01-02T00:00:00+00:00", 2.0, 0),
                        (folder_two + "/c.jpg", "c.jpg", 2, "2024-01-03T00:00:00+00:00", 3.0, 1),
                    ],
                )
                await connection.commit()

        asyncio.run(seed())

        client = TestClient(create_app(database=self.database))
        response = client.get("/api/library/folders")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "folders": [
                    {
                        "id": 2,
                        "path": folder_two,
                        "photo_count": 1,
                        "indexed_count": 1,
                        "last_scan": None,
                    },
                    {
                        "id": 1,
                        "path": folder_one,
                        "photo_count": 2,
                        "indexed_count": 1,
                        "last_scan": "2024-01-02T00:00:00+00:00",
                    },
                ]
            },
        )

    def test_create_app_lifespan_initializes_injected_database(self) -> None:
        from api.app import create_app

        database = mock.Mock()
        database.initialize = AsyncMock()

        with TestClient(create_app(database=database)):
            pass

        database.initialize.assert_awaited_once_with()

    def test_add_folder_rejects_missing_directory(self) -> None:
        from api.app import create_app

        client = TestClient(create_app(database=self.database))
        response = client.post("/api/library/add", json={"path": str(self.temp_path / "missing")})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Folder does not exist"})


if __name__ == "__main__":
    unittest.main()
