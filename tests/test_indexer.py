import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

import config
from db.database import Database


class _FakeEmbedder:
    def __init__(self) -> None:
        self.is_loaded = False
        self.loaded = 0

    async def load(self) -> None:
        self.is_loaded = True
        self.loaded += 1

    def encode_images_batch(self, image_paths, batch_size=config.BATCH_SIZE):
        vectors = []
        for index, _path in enumerate(image_paths, start=1):
            vector = np.zeros(config.VECTOR_DIM, dtype=np.float32)
            vector[index - 1] = 1.0
            vectors.append(vector)
        return vectors


class IndexerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.database = Database(db_path=self.temp_path / "photofinder.db")
        asyncio.run(self.database.initialize())

    def test_start_indexing_writes_vectors_and_thumbnails(self) -> None:
        from core.indexer import IndexingState, start_indexing

        folder_path = self.temp_path / "library"
        folder_path.mkdir()
        photo_path = folder_path / "sample.jpg"
        Image.new("RGB", (18, 10), color="red").save(photo_path)

        async def seed_folder() -> int:
            async with self.database.connect() as connection:
                cursor = await connection.execute(
                    """
                    INSERT INTO folders (path, added_at, last_scan, photo_count, is_active)
                    VALUES (?, ?, NULL, 0, 1)
                    """,
                    (
                        str(folder_path.resolve(strict=False)),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                await connection.commit()
                return cursor.lastrowid

        folder_id = asyncio.run(seed_folder())
        state = IndexingState()
        embedder = _FakeEmbedder()

        asyncio.run(
            start_indexing(
                folder_id,
                str(folder_path.resolve(strict=False)),
                database=self.database,
                embedder=embedder,
                state=state,
            )
        )

        async def fetch_rows():
            async with self.database.connect() as connection:
                photo_row = await (
                    await connection.execute(
                        """
                        SELECT path, has_vector, thumbnail, error_msg
                        FROM photos
                        """
                    )
                ).fetchone()
                vector_count = await (
                    await connection.execute("SELECT COUNT(*) FROM photo_vectors")
                ).fetchone()
                return photo_row, vector_count[0]

        photo_row, vector_count = asyncio.run(fetch_rows())

        self.assertTrue(embedder.is_loaded)
        self.assertEqual(embedder.loaded, 1)
        self.assertIsNotNone(photo_row)
        self.assertEqual(photo_row["path"], str(photo_path.resolve(strict=False)))
        self.assertEqual(photo_row["has_vector"], 1)
        self.assertIsNone(photo_row["error_msg"])
        self.assertIsInstance(photo_row["thumbnail"], bytes)
        self.assertGreater(len(photo_row["thumbnail"]), 0)
        self.assertEqual(vector_count, 1)
        self.assertFalse(state.is_running)
        self.assertEqual(state.phase, "done")
        self.assertEqual(state.total, 1)
        self.assertEqual(state.processed, 1)
        self.assertEqual(state.failed, 0)

    def test_start_indexing_rejects_concurrent_runs(self) -> None:
        from core.indexer import IndexingState, start_indexing

        state = IndexingState(is_running=True)

        with self.assertRaises(RuntimeError):
            asyncio.run(
                start_indexing(
                    1,
                    str(self.temp_path.resolve(strict=False)),
                    database=self.database,
                    embedder=_FakeEmbedder(),
                    state=state,
                )
            )


if __name__ == "__main__":
    unittest.main()
