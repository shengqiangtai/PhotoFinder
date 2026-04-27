from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import httpx

import config

Asset = Tuple[str, Path]


@dataclass
class DownloadProgress:
    downloading: bool = False
    model: Optional[str] = None
    percent: int = 0
    error: Optional[str] = None


def default_model_assets() -> Dict[str, List[Asset]]:
    tokenizer_assets = [
        (url, config.TOKENIZER_DIR / filename)
        for filename, url in config.TOKENIZER_ASSET_URLS.items()
    ]
    multilingual_tokenizer_assets = [
        (url, config.MULTILINGUAL_TOKENIZER_DIR / filename)
        for filename, url in config.MULTILINGUAL_TOKENIZER_ASSET_URLS.items()
    ]
    return {
        "clip_visual": [(config.MODEL_URLS["clip_visual"], config.CLIP_VISUAL_MODEL)],
        "clip_textual": [(config.MODEL_URLS["clip_textual"], config.CLIP_TEXTUAL_MODEL)] + tokenizer_assets,
        "multilingual": [
            (config.MODEL_URLS["multilingual"], config.MULTILINGUAL_MODEL),
            (config.MODEL_URLS["multilingual_dense"], config.MULTILINGUAL_DENSE_MODEL),
        ]
        + multilingual_tokenizer_assets,
    }


class ModelDownloader:
    def __init__(
        self,
        *,
        model_assets: Optional[Dict[str, List[Asset]]] = None,
        client_factory: Optional[Callable[[], httpx.AsyncClient]] = None,
    ) -> None:
        self.model_assets = model_assets or default_model_assets()
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(follow_redirects=True))
        self.progress = DownloadProgress()
        self._lock = asyncio.Lock()

    def has_model(self, model_name: str) -> bool:
        if model_name not in self.model_assets:
            return False
        return all(path.exists() for _, path in self.model_assets[model_name])

    def get_progress_payload(self) -> Dict[str, object]:
        return {
            "downloading": self.progress.downloading,
            "model": self.progress.model,
            "percent": self.progress.percent,
            "error": self.progress.error,
        }

    async def download_model(self, model_name: str) -> None:
        if model_name not in self.model_assets:
            raise ValueError(f"Unsupported model: {model_name}")

        async with self._lock:
            self.progress.downloading = True
            self.progress.model = model_name
            self.progress.percent = 0
            self.progress.error = None

            assets = self.model_assets[model_name]
            downloaded_assets = 0
            total_assets = len(assets)

            try:
                async with self.client_factory() as client:
                    for url, target_path in assets:
                        await self._download_asset(client, url, target_path)
                        downloaded_assets += 1
                        self.progress.percent = int(downloaded_assets * 100 / total_assets)
            except Exception as exc:
                self.progress.error = str(exc)
                raise
            finally:
                self.progress.downloading = False
                if self.progress.error is None and downloaded_assets == total_assets:
                    self.progress.percent = 100

    async def _download_asset(
        self,
        client: httpx.AsyncClient,
        url: str,
        target_path: Path,
    ) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = target_path.with_suffix(target_path.suffix + ".part")

        start_byte = partial_path.stat().st_size if partial_path.exists() else 0
        headers = {"Range": f"bytes={start_byte}-"} if start_byte else None

        async with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()

            if start_byte and getattr(response, "status_code", None) != 206:
                start_byte = 0
                partial_path.unlink(missing_ok=True)

            content_length = response.headers.get("Content-Length")
            total_size = start_byte + int(content_length) if content_length else None

            mode = "ab" if start_byte else "wb"
            written = start_byte
            with partial_path.open(mode) as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
                    written += len(chunk)
                    if total_size:
                        self.progress.percent = min(99, int(written * 100 / total_size))

        partial_path.replace(target_path)


model_downloader = ModelDownloader()
