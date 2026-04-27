import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from api.app import create_app
from db.database import Database


class _FakeRouteEmbedder:
    def __init__(self, *, loaded_text_model: str = "textual", provider: str | None = None) -> None:
        self.is_loaded = True
        self.loaded_text_model = loaded_text_model
        self.provider = provider

    async def load(self) -> None:
        self.is_loaded = True


class SearchRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.database = Database(db_path=self.temp_path / "photofinder.db")
        asyncio.run(self.database.initialize())

    def test_search_route_returns_results(self) -> None:
        app = create_app(database=self.database, embedder=_FakeRouteEmbedder())
        client = TestClient(app)

        fake_results = [
            {
                "id": 1,
                "filename": "sunset.jpg",
                "taken_at": "2024-04-10T10:00:00",
                "thumbnail_url": "/api/thumbnail/1",
                "full_image_url": "/api/image/1",
                "similarity": 0.91,
                "match_score": 93,
            }
        ]

        with mock.patch("api.routes.search.search", autospec=True) as search_mock:
            search_mock.return_value = fake_results
            response = client.get("/api/search", params={"q": "sunset", "top_k": 5})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["query"], "sunset")
        self.assertEqual(payload["results"], fake_results)

    def test_search_route_rewrites_chinese_query_before_searching(self) -> None:
        app = create_app(database=self.database, embedder=_FakeRouteEmbedder())
        client = TestClient(app)

        with mock.patch("api.routes.search.search", autospec=True) as search_mock:
            search_mock.return_value = []
            response = client.get("/api/search", params={"q": "日落"})

        self.assertEqual(response.status_code, 200)
        _, kwargs = search_mock.call_args
        self.assertEqual(kwargs["query"], "sunset")
        self.assertEqual(response.json()["query"], "日落")
        self.assertEqual(response.json()["rewritten_query"], "sunset")

    def test_search_route_keeps_chinese_query_when_multilingual_text_model_is_loaded(self) -> None:
        app = create_app(database=self.database, embedder=_FakeRouteEmbedder(loaded_text_model="multilingual"))
        client = TestClient(app)

        with mock.patch("api.routes.search.search", autospec=True) as search_mock:
            search_mock.return_value = []
            response = client.get("/api/search", params={"q": "日落"})

        self.assertEqual(response.status_code, 200)
        _, kwargs = search_mock.call_args
        self.assertEqual(kwargs["query"], "日落")
        self.assertEqual(response.json()["query"], "日落")
        self.assertIsNone(response.json()["rewritten_query"])

    def test_search_route_keeps_chinese_query_when_api_embedder_is_active(self) -> None:
        app = create_app(database=self.database, embedder=_FakeRouteEmbedder(provider="jina"))
        client = TestClient(app)

        with mock.patch("api.routes.search.search", autospec=True) as search_mock:
            search_mock.return_value = []
            response = client.get("/api/search", params={"q": "森林"})

        self.assertEqual(response.status_code, 200)
        _, kwargs = search_mock.call_args
        self.assertEqual(kwargs["query"], "森林")
        self.assertIsNone(response.json()["rewritten_query"])

    def test_search_debug_route_returns_variants_and_text_model(self) -> None:
        app = create_app(database=self.database, embedder=_FakeRouteEmbedder(loaded_text_model="multilingual"))
        client = TestClient(app)

        fake_debug_payload = {
            "query": "数学公式",
            "query_for_search": "数学公式",
            "text_model": "multilingual",
            "rewritten_query": None,
            "variants": [
                {
                    "query": "数学公式",
                    "results": [
                        {
                            "id": 1,
                            "filename": "formula.jpg",
                            "taken_at": None,
                            "thumbnail_url": "/api/thumbnail/1",
                            "full_image_url": "/api/image/1",
                            "distance": 0.4,
                            "similarity": 0.8,
                            "match_score": 88,
                        }
                    ],
                }
            ],
        }

        with mock.patch("api.routes.search.debug_search", autospec=True) as debug_search_mock:
            debug_search_mock.return_value = fake_debug_payload
            response = client.get("/api/search/debug", params={"q": "数学公式", "top_k": 3})

        self.assertEqual(response.status_code, 200)
        _, kwargs = debug_search_mock.call_args
        self.assertEqual(kwargs["query"], "数学公式")
        self.assertEqual(kwargs["top_k"], 3)
        self.assertEqual(response.json(), fake_debug_payload)

    def test_search_route_returns_503_when_embedder_load_fails(self) -> None:
        class _BrokenEmbedder:
            async def load(self) -> None:
                raise FileNotFoundError("missing model")

        app = create_app(database=self.database, embedder=_BrokenEmbedder())
        client = TestClient(app)

        response = client.get("/api/search", params={"q": "sunset"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"error": "model_loading", "message": "AI 模型正在加载，请稍后再试"},
        )


if __name__ == "__main__":
    unittest.main()
