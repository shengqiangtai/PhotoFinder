import asyncio
import tempfile
import unittest
from pathlib import Path


class _FakeStreamResponse:
    def __init__(self, body: bytes, *, content_length: int | None = None) -> None:
        self._body = body
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self):
        midpoint = len(self._body) // 2 or len(self._body)
        yield self._body[:midpoint]
        if midpoint < len(self._body):
            yield self._body[midpoint:]


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, url, headers=None):
        return self._responses.pop(0)


class ModelDownloaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)

    def test_download_model_writes_file_and_updates_progress(self) -> None:
        from utils.model_downloader import ModelDownloader

        target_path = self.temp_path / "clip_visual.onnx"
        downloader = ModelDownloader(
            model_assets={"clip_visual": [("https://example.test/visual.onnx", target_path)]},
            client_factory=lambda: _FakeClient(
                [_FakeStreamResponse(b"12345678", content_length=8)]
            ),
        )

        asyncio.run(downloader.download_model("clip_visual"))

        self.assertEqual(target_path.read_bytes(), b"12345678")
        self.assertFalse(downloader.progress.downloading)
        self.assertEqual(downloader.progress.model, "clip_visual")
        self.assertEqual(downloader.progress.percent, 100)
        self.assertIsNone(downloader.progress.error)

    def test_default_multilingual_assets_include_tokenizer_and_projection(self) -> None:
        import config
        from utils.model_downloader import default_model_assets

        assets = default_model_assets()["multilingual"]
        target_paths = {target_path for _, target_path in assets}

        self.assertIn(config.MULTILINGUAL_MODEL, target_paths)
        self.assertIn(config.MULTILINGUAL_DENSE_MODEL, target_paths)
        self.assertIn(config.MULTILINGUAL_TOKENIZER_DIR / "tokenizer.json", target_paths)
        self.assertIn(config.MULTILINGUAL_TOKENIZER_DIR / "vocab.txt", target_paths)

    def test_download_model_rejects_unknown_model(self) -> None:
        from utils.model_downloader import ModelDownloader

        downloader = ModelDownloader(model_assets={})

        with self.assertRaises(ValueError):
            asyncio.run(downloader.download_model("unknown"))


if __name__ == "__main__":
    unittest.main()
