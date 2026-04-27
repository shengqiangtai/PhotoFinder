import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from api.app import create_app
from db.database import Database


class ImageRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.database = Database(db_path=self.temp_path / "photofinder.db")
        asyncio.run(self.database.initialize())

        self.image_path = self.temp_path / "sample.jpg"
        Image.new("RGB", (32, 32), color="red").save(self.image_path)

        async def seed() -> None:
            async with self.database.connect() as connection:
                await connection.execute(
                    """
                    INSERT INTO photos (
                        id, path, filename, indexed_at, file_mtime, has_vector, thumbnail
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        str(self.image_path.resolve(strict=False)),
                        self.image_path.name,
                        "2024-01-01T00:00:00+00:00",
                        self.image_path.stat().st_mtime,
                        1,
                        b"jpeg-thumb",
                    ),
                )
                await connection.commit()

        asyncio.run(seed())

    def test_get_image_returns_original_file(self) -> None:
        client = TestClient(create_app(database=self.database))
        response = client.get("/api/image/1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertGreater(len(response.content), 0)

    def test_get_thumbnail_returns_cached_blob(self) -> None:
        client = TestClient(create_app(database=self.database))
        response = client.get("/api/thumbnail/1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(response.headers["cache-control"], "max-age=86400")
        self.assertEqual(response.content, b"jpeg-thumb")


if __name__ == "__main__":
    unittest.main()
