import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sqlite_vec

from db.database import Database


class _FakeSearchEmbedder:
    def __init__(self, *, loaded_text_model: str = "textual", provider: str | None = None) -> None:
        self.queries: list[str] = []
        self.loaded_text_model = loaded_text_model
        self.provider = provider

    async def load(self) -> None:
        return None

    def encode_text(self, query: str) -> np.ndarray:
        self.queries.append(query)
        if "forest" in query:
            return np.array([0.0, 1.0] + [0.0] * 510, dtype=np.float32)
        if "test_data" in query:
            return np.array([0.95, 0.05] + [0.0] * 510, dtype=np.float32)
        return np.array([1.0, 0.0] + [0.0] * 510, dtype=np.float32)


class SearcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.database = Database(db_path=self.temp_path / "photofinder.db")
        asyncio.run(self.database.initialize())
        asyncio.run(self._seed())

    def test_search_orders_results_and_maps_similarity(self) -> None:
        from core.searcher import search

        results = asyncio.run(
            search(
                "sunset beach",
                database=self.database,
                embedder=_FakeSearchEmbedder(),
            )
        )

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["filename"], "sunset.jpg")
        self.assertGreaterEqual(results[0]["similarity"], results[1]["similarity"])
        self.assertEqual(results[0]["thumbnail_url"], f"/api/thumbnail/{results[0]['id']}")
        self.assertEqual(results[0]["full_image_url"], f"/api/image/{results[0]['id']}")
        self.assertGreaterEqual(results[0]["similarity"], 0.0)
        self.assertLessEqual(results[0]["similarity"], 1.0)

    def test_search_supports_folder_and_date_filters(self) -> None:
        from core.searcher import search

        filtered = asyncio.run(
            search(
                "forest",
                folder_id=2,
                date_from="2024-05-01",
                date_to="2024-05-31",
                database=self.database,
                embedder=_FakeSearchEmbedder(),
            )
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["filename"], "forest.jpg")

    def test_search_expands_visual_query_templates(self) -> None:
        from core.searcher import search

        embedder = _FakeSearchEmbedder()

        asyncio.run(
            search(
                "sunset beach",
                top_k=1,
                database=self.database,
                embedder=embedder,
            )
        )

        self.assertEqual(
            embedder.queries,
            [
                "sunset beach",
                "a photo of sunset beach",
                "an image of sunset beach",
            ],
        )

    def test_search_adds_english_visual_terms_for_chinese_query(self) -> None:
        from core.searcher import search

        embedder = _FakeSearchEmbedder()

        asyncio.run(
            search(
                "海边的狗",
                top_k=1,
                database=self.database,
                embedder=embedder,
            )
        )

        self.assertEqual(
            embedder.queries,
            [
                "海边的狗",
                "beach dog",
                "a photo of beach dog",
                "an image of beach dog",
            ],
        )

    def test_search_keeps_chinese_query_unexpanded_for_multilingual_text_model(self) -> None:
        from core.searcher import search

        embedder = _FakeSearchEmbedder(loaded_text_model="multilingual")

        asyncio.run(
            search(
                "海边的狗",
                top_k=1,
                database=self.database,
                embedder=embedder,
            )
        )

        self.assertEqual(embedder.queries, ["海边的狗"])

    def test_search_keeps_chinese_query_unexpanded_for_api_embedder(self) -> None:
        from core.searcher import search

        embedder = _FakeSearchEmbedder(provider="jina")

        asyncio.run(
            search(
                "海边的狗",
                top_k=1,
                database=self.database,
                embedder=embedder,
            )
        )

        self.assertEqual(embedder.queries, ["海边的狗"])

    def test_debug_search_returns_results_grouped_by_query_variant(self) -> None:
        from core.searcher import debug_search

        embedder = _FakeSearchEmbedder()

        payload = asyncio.run(
            debug_search(
                "sunset beach",
                top_k=1,
                database=self.database,
                embedder=embedder,
            )
        )

        self.assertEqual(payload["text_model"], "textual")
        self.assertEqual(
            [variant["query"] for variant in payload["variants"]],
            [
                "sunset beach",
                "a photo of sunset beach",
                "an image of sunset beach",
            ],
        )
        self.assertEqual(payload["variants"][0]["results"][0]["filename"], "sunset.jpg")
        self.assertIn("distance", payload["variants"][0]["results"][0])
        self.assertIn("similarity", payload["variants"][0]["results"][0])

    def test_search_reranks_with_filename_and_path_matches(self) -> None:
        from core.searcher import search

        results = asyncio.run(
            search(
                "test_data",
                top_k=3,
                database=self.database,
                embedder=_FakeSearchEmbedder(),
            )
        )

        self.assertEqual(results[0]["filename"], "formula.jpg")
        self.assertGreater(results[0]["match_score"], results[1]["match_score"])

    def test_match_scores_are_gap_aware_when_vector_scores_are_crowded(self) -> None:
        from core.searcher import compute_match_scores

        scored = compute_match_scores(
            [
                {"id": 1, "similarity": 0.501, "keyword_score": 0.0},
                {"id": 2, "similarity": 0.500, "keyword_score": 0.0},
                {"id": 3, "similarity": 0.499, "keyword_score": 0.0},
            ]
        )

        self.assertLessEqual(scored[0]["match_score"], 65)
        self.assertGreater(scored[0]["match_score"], scored[-1]["match_score"])

    async def _seed(self) -> None:
        async with self.database.connect() as connection:
            await connection.executemany(
                """
                INSERT INTO folders (id, path, added_at, last_scan, photo_count, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                [
                    (1, str((self.temp_path / "one").resolve(strict=False)), datetime.now(timezone.utc).isoformat(), None, 1),
                    (2, str((self.temp_path / "two").resolve(strict=False)), datetime.now(timezone.utc).isoformat(), None, 1),
                ],
            )
            await connection.executemany(
                """
                INSERT INTO photos (
                    id, path, filename, folder_id, taken_at, indexed_at, file_mtime, has_vector, thumbnail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                [
                    (
                        1,
                        str((self.temp_path / "sunset.jpg").resolve(strict=False)),
                        "sunset.jpg",
                        1,
                        "2024-04-10T10:00:00",
                        datetime.now(timezone.utc).isoformat(),
                        1.0,
                        b"thumb-1",
                    ),
                    (
                        2,
                        str((self.temp_path / "forest.jpg").resolve(strict=False)),
                        "forest.jpg",
                        2,
                        "2024-05-15T08:00:00",
                        datetime.now(timezone.utc).isoformat(),
                        2.0,
                        b"thumb-2",
                    ),
                    (
                        3,
                        str((self.temp_path / "test_data" / "formula.jpg").resolve(strict=False)),
                        "formula.jpg",
                        1,
                        "2024-06-01T09:00:00",
                        datetime.now(timezone.utc).isoformat(),
                        3.0,
                        b"thumb-3",
                    ),
                ],
            )
            await connection.executemany(
                "INSERT INTO photo_vectors (photo_id, embedding) VALUES (?, ?)",
                [
                    (1, sqlite_vec.serialize_float32([1.0, 0.0] + [0.0] * 510)),
                    (2, sqlite_vec.serialize_float32([0.0, 1.0] + [0.0] * 510)),
                    (3, sqlite_vec.serialize_float32([0.9, 0.1] + [0.0] * 510)),
                ],
            )
            await connection.commit()


if __name__ == "__main__":
    unittest.main()
