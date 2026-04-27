import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from api.app import create_app
from api.routes import system as system_routes
from db.database import Database


class SystemRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.database = Database(db_path=self.temp_path / "photofinder.db")
        asyncio.run(self.database.initialize())

    def test_get_system_info_returns_counts_and_config(self) -> None:
        class _FakeEmbedder:
            is_loaded = False
            visual_session = None
            loaded_text_model = None

        class _FakeDownloader:
            def __init__(self) -> None:
                self.progress = mock.Mock(
                    downloading=False,
                    model=None,
                    percent=0,
                    error=None,
                )

        async def seed() -> None:
            async with self.database.connect() as connection:
                await connection.execute(
                    """
                    INSERT INTO folders (id, path, added_at, last_scan, photo_count, is_active)
                    VALUES (1, ?, '2024-01-01T00:00:00+00:00', '2024-01-02T00:00:00+00:00', 2, 1)
                    """,
                    (str((self.temp_path / "library").resolve(strict=False)),),
                )
                await connection.executemany(
                    """
                    INSERT INTO photos (path, filename, folder_id, indexed_at, file_mtime, has_vector)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("photo-1.jpg", "photo-1.jpg", 1, "2024-01-02T00:00:00+00:00", 1.0, 1),
                        ("photo-2.jpg", "photo-2.jpg", 1, "2024-01-02T00:00:00+00:00", 2.0, 0),
                    ],
                )
                await connection.execute(
                    "UPDATE app_config SET value = '0' WHERE key = 'first_run'"
                )
                await connection.commit()

        asyncio.run(seed())

        with mock.patch("api.routes.system.get_lan_ip", return_value="192.168.1.8"):
            with mock.patch("api.routes.system.config.CLIP_VISUAL_MODEL", self.temp_path / "missing-visual.onnx"):
                with mock.patch("api.routes.system.config.CLIP_TEXTUAL_MODEL", self.temp_path / "missing-textual.onnx"):
                    with mock.patch("api.routes.system.config.MULTILINGUAL_MODEL", self.temp_path / "missing-multilingual.onnx"):
                        response = TestClient(
                            create_app(
                                database=self.database,
                                embedder=_FakeEmbedder(),
                                model_downloader=_FakeDownloader(),
                            )
                        ).get("/api/system/info")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], "1.0.0")
        self.assertEqual(
            payload["model_status"],
            {
                "visual": "not_downloaded",
                "textual": "not_downloaded",
                "multilingual": "not_downloaded",
            },
        )
        self.assertIsNone(payload["download_progress"])
        self.assertEqual(payload["total_photos"], 2)
        self.assertEqual(payload["indexed_photos"], 1)
        self.assertAlmostEqual(
            payload["db_size_mb"],
            round(self.database.db_path.stat().st_size / (1024 * 1024), 2),
            places=2,
        )
        self.assertEqual(payload["lan_url"], "http://192.168.1.8:7700")
        self.assertFalse(payload["first_run"])

    def test_get_system_info_handles_api_embedder_without_local_model_attributes(self) -> None:
        class _FakeAPIEmbedder:
            provider = "jina"

        class _FakeDownloader:
            def __init__(self) -> None:
                self.progress = mock.Mock(
                    downloading=False,
                    model=None,
                    percent=0,
                    error=None,
                )

        response = TestClient(
            create_app(
                database=self.database,
                embedder=_FakeAPIEmbedder(),
                model_downloader=_FakeDownloader(),
            )
        ).get("/api/system/info")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["model_status"],
            {
                "visual": "loading",
                "textual": "loading",
                "multilingual": "loading",
            },
        )

    def test_get_system_qrcode_returns_png_for_lan_url(self) -> None:
        app = create_app(database=self.database)

        with mock.patch("api.routes.system.get_lan_ip", return_value="192.168.1.8"):
            with mock.patch("api.routes.system.qrcode.make", wraps=system_routes.qrcode.make) as make_spy:
                response = TestClient(app).get("/api/system/qrcode")

        make_spy.assert_called_once_with("http://192.168.1.8:7700")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(response.content)) as image:
            image.load()
            self.assertEqual(image.size[0], image.size[1])
            self.assertGreater(image.size[0], 0)

    def test_get_system_qrcode_returns_503_when_lan_url_unavailable(self) -> None:
        app = create_app(database=self.database)

        with mock.patch("api.routes.system.get_lan_ip", return_value=None):
            response = TestClient(app).get("/api/system/qrcode")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "LAN URL is unavailable for QR code generation"},
        )

    def test_get_index_status_returns_runtime_progress(self) -> None:
        app = create_app(database=self.database)
        app.state.indexing_state.is_running = True
        app.state.indexing_state.phase = "embedding"
        app.state.indexing_state.total = 10
        app.state.indexing_state.processed = 4
        app.state.indexing_state.failed = 1
        app.state.indexing_state.current_file = "sample.jpg"
        app.state.indexing_state.eta_seconds = 12
        app.state.indexing_state.speed_per_second = 2.0

        response = TestClient(app).get("/api/index/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "is_running": True,
                "phase": "embedding",
                "total": 10,
                "processed": 4,
                "failed": 1,
                "current_file": "sample.jpg",
                "progress_percent": 40,
                "eta_seconds": 12,
                "speed_per_second": 2.0,
                "requires_reindex": False,
            },
        )

    def test_models_download_status_returns_progress(self) -> None:
        app = create_app(database=self.database)
        app.state.model_downloader.progress.downloading = True
        app.state.model_downloader.progress.model = "clip_visual"
        app.state.model_downloader.progress.percent = 45
        app.state.model_downloader.progress.error = None

        response = TestClient(app).get("/api/models/download/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "downloading": True,
                "model": "clip_visual",
                "percent": 45,
                "error": None,
            },
        )

    def test_post_models_download_starts_background_download(self) -> None:
        app = create_app(database=self.database)
        app.state.model_downloader.download_model = mock.AsyncMock()

        response = TestClient(app).post("/api/models/download", json={"model": "clip_visual"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "download_started"})
        app.state.model_downloader.download_model.assert_awaited_once_with("clip_visual")

    def test_open_folder_returns_selected_path_when_picker_succeeds(self) -> None:
        selected_path = str((self.temp_path / "chosen").resolve(strict=False))
        client = TestClient(create_app(database=self.database))
        root = mock.Mock()

        with mock.patch("tkinter.Tk", return_value=root) as tk_mock:
            with mock.patch(
                "tkinter.filedialog.askdirectory",
                return_value=selected_path,
            ) as picker_mock:
                response = client.get("/api/system/open-folder")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"selected_path": selected_path, "cancelled": None})
        tk_mock.assert_called_once_with()
        root.withdraw.assert_called_once_with()
        root.destroy.assert_called_once_with()
        picker_mock.assert_called_once_with()

    def test_open_folder_returns_cancelled_when_picker_returns_empty_string(self) -> None:
        client = TestClient(create_app(database=self.database))
        root = mock.Mock()

        with mock.patch("tkinter.Tk", return_value=root):
            with mock.patch("tkinter.filedialog.askdirectory", return_value=""):
                response = client.get("/api/system/open-folder")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"selected_path": None, "cancelled": True})
        root.withdraw.assert_called_once_with()
        root.destroy.assert_called_once_with()

    def test_open_folder_returns_http_500_when_picker_init_fails(self) -> None:
        client = TestClient(create_app(database=self.database))

        with mock.patch(
            "tkinter.Tk",
            side_effect=RuntimeError("no display available"),
        ):
            response = client.get("/api/system/open-folder")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Failed to open folder picker"})


if __name__ == "__main__":
    unittest.main()
