from __future__ import annotations

import asyncio
import base64
import os
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from PIL import Image

import config
from utils.image_utils import read_image_safe

_USE_DEFAULT = object()


class EmbedderAPIError(RuntimeError):
    pass


class InvalidAPIKeyError(EmbedderAPIError):
    pass


class InsufficientCreditsError(EmbedderAPIError):
    pass


class BaseEmbedder(ABC):
    @abstractmethod
    async def encode_image(self, image_path: str) -> np.ndarray:
        """Return an L2-normalized image vector."""

    @abstractmethod
    async def encode_text(self, text: str) -> np.ndarray:
        """Return an L2-normalized text vector."""

    @abstractmethod
    async def encode_images_batch(self, image_paths: list[str], batch_size: int = 16) -> list[np.ndarray | None]:
        """Return one vector or None per input image path."""

    @property
    @abstractmethod
    def vector_dim(self) -> int:
        """Active vector dimensionality."""

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """Whether this embedder can accept requests."""


class LocalEmbedder(BaseEmbedder):
    def __init__(
        self,
        *,
        visual_model_path: Optional[Path] = None,
        textual_model_path: Optional[Path] = None,
        multilingual_model_path: Optional[Path] | object = _USE_DEFAULT,
        tokenizer_dir: Optional[Path] = None,
        multilingual_tokenizer_dir: Optional[Path] = None,
        multilingual_dense_model_path: Optional[Path] = None,
        session_factory: Optional[Callable[..., object]] = None,
        tokenizer_loader: Optional[Callable[[Path], object]] = None,
        dense_loader: Optional[Callable[[Path], object]] = None,
    ) -> None:
        self.visual_model_path = Path(visual_model_path or config.CLIP_VISUAL_MODEL)
        self.textual_model_path = Path(textual_model_path or config.CLIP_TEXTUAL_MODEL)
        if multilingual_model_path is _USE_DEFAULT:
            self.multilingual_model_path = config.MULTILINGUAL_MODEL
        elif multilingual_model_path is None:
            self.multilingual_model_path = None
        else:
            self.multilingual_model_path = Path(multilingual_model_path)
        self.tokenizer_dir = Path(tokenizer_dir or config.TOKENIZER_DIR)
        self.multilingual_tokenizer_dir = Path(multilingual_tokenizer_dir or config.MULTILINGUAL_TOKENIZER_DIR)
        self.multilingual_dense_model_path = Path(multilingual_dense_model_path or config.MULTILINGUAL_DENSE_MODEL)
        self.session_factory = session_factory or self._default_session_factory
        self.tokenizer_loader = tokenizer_loader or self._default_tokenizer_loader
        self.dense_loader = dense_loader or self._default_dense_loader

        self.visual_session = None
        self.textual_session = None
        self.tokenizer = None
        self.multilingual_projection: Optional[np.ndarray] = None
        self.multilingual_bias: Optional[np.ndarray] = None
        self.is_loaded = False
        self.loaded_text_model: Optional[str] = None
        self._load_lock = asyncio.Lock()

    @property
    def vector_dim(self) -> int:
        return config.VECTOR_DIM

    @property
    def is_ready(self) -> bool:
        return self.is_loaded

    def reset(self) -> None:
        self.visual_session = None
        self.textual_session = None
        self.tokenizer = None
        self.multilingual_projection = None
        self.multilingual_bias = None
        self.is_loaded = False
        self.loaded_text_model = None

    async def load(self) -> None:
        if self.is_loaded:
            return

        async with self._load_lock:
            if self.is_loaded:
                return
            await asyncio.to_thread(self._load_sync)
            self.is_loaded = True

    def encode_image(self, image_path: str) -> np.ndarray:
        self._ensure_loaded()

        image = read_image_safe(image_path)
        try:
            prepared = self._prepare_image(image)
        finally:
            image.close()

        input_name = self.visual_session.get_inputs()[0].name
        outputs = self.visual_session.run(None, {input_name: prepared})
        return self._normalize_vector(outputs[0][0])

    def encode_text(self, text: str) -> np.ndarray:
        self._ensure_loaded()

        tokens = self.tokenizer(
            text,
            padding="max_length",
            truncation=True,
            max_length=128 if self.loaded_text_model == "multilingual" else 77,
            return_tensors="np",
        )

        inputs = {}
        for input_meta in self.textual_session.get_inputs():
            if input_meta.name in tokens:
                inputs[input_meta.name] = tokens[input_meta.name].astype(np.int64)

        outputs = self.textual_session.run(None, inputs)
        if self.loaded_text_model == "multilingual" and self.multilingual_projection is not None:
            pooled = self._mean_pool(outputs[0], tokens["attention_mask"])
            projected = self._apply_dense_projection(pooled[0])
            return self._normalize_vector(projected)
        return self._normalize_vector(outputs[0][0])

    def encode_images_batch(self, image_paths: list[str], batch_size: int = 16) -> list[np.ndarray | None]:
        self._ensure_loaded()

        vectors: list[np.ndarray | None] = []
        for image_path in image_paths:
            try:
                vectors.append(self.encode_image(image_path))
            except Exception:
                vectors.append(None)
        return vectors

    def _load_sync(self) -> None:
        self._assert_exists(self.visual_model_path, "visual model")
        text_model_path, model_name = self._resolve_text_model_path()
        self._assert_exists(self.tokenizer_dir, "tokenizer directory")

        self.visual_session = self.session_factory(
            str(self.visual_model_path),
            providers=self._providers(),
            sess_options=self._session_options(),
        )
        self.textual_session = self._load_textual_session(text_model_path, model_name)
        if model_name == "multilingual" and not self._textual_session_outputs_vector(self.textual_session):
            if self._can_use_multilingual_projection():
                self.multilingual_projection, self.multilingual_bias = self._load_multilingual_projection()
            elif self.textual_model_path.exists():
                text_model_path = self.textual_model_path
                model_name = "textual"
                self.textual_session = self._load_textual_session(text_model_path, model_name)
            else:
                raise RuntimeError(
                    f"Multilingual text encoder output is not compatible with {config.VECTOR_DIM}-dimensional image vectors"
                )
        tokenizer_dir = self.multilingual_tokenizer_dir if model_name == "multilingual" else self.tokenizer_dir
        self.tokenizer = self.tokenizer_loader(tokenizer_dir)
        self.loaded_text_model = model_name

    def _load_textual_session(self, text_model_path: Path, model_name: str):
        return self.session_factory(
            str(text_model_path),
            providers=self._providers(),
            sess_options=self._session_options(),
        )

    def _textual_session_outputs_vector(self, session: object) -> bool:
        get_outputs = getattr(session, "get_outputs", None)
        if get_outputs is None:
            return True
        outputs = get_outputs()
        if not outputs:
            return False
        shape = getattr(outputs[0], "shape", None)
        if not shape:
            return True
        return len(shape) <= 2 and shape[-1] == config.VECTOR_DIM

    def _can_use_multilingual_projection(self) -> bool:
        return self.multilingual_dense_model_path.exists() and self.multilingual_tokenizer_dir.exists()

    def _load_multilingual_projection(self) -> tuple[np.ndarray, Optional[np.ndarray]]:
        loaded = self.dense_loader(self.multilingual_dense_model_path)
        if isinstance(loaded, tuple):
            weight = np.asarray(loaded[0], dtype=np.float32)
            bias = None if loaded[1] is None else np.asarray(loaded[1], dtype=np.float32)
        else:
            weight = np.asarray(loaded, dtype=np.float32)
            bias = None
        if weight.shape == (config.VECTOR_DIM, 768):
            projection = weight
        elif weight.shape == (768, config.VECTOR_DIM):
            projection = weight.T
        else:
            raise RuntimeError(f"Unsupported multilingual dense weight shape: {weight.shape}")
        if bias is not None and bias.shape != (config.VECTOR_DIM,):
            raise RuntimeError(f"Unsupported multilingual dense bias shape: {bias.shape}")
        return projection, bias

    def _mean_pool(self, hidden_states: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
        hidden_states = np.asarray(hidden_states, dtype=np.float32)
        attention_mask = np.asarray(attention_mask, dtype=np.float32)
        expanded_mask = attention_mask[..., np.newaxis]
        summed = np.sum(hidden_states * expanded_mask, axis=1)
        counts = np.clip(np.sum(expanded_mask, axis=1), 1e-9, None)
        return summed / counts

    def _apply_dense_projection(self, vector: np.ndarray) -> np.ndarray:
        if self.multilingual_projection is None:
            raise RuntimeError("Missing multilingual dense projection")
        projected = np.asarray(vector, dtype=np.float32) @ self.multilingual_projection.T
        if self.multilingual_bias is not None:
            projected = projected + self.multilingual_bias
        return projected

    def _resolve_text_model_path(self) -> tuple[Path, str]:
        if self.multilingual_model_path and Path(self.multilingual_model_path).exists():
            return Path(self.multilingual_model_path), "multilingual"
        if self.textual_model_path.exists():
            return self.textual_model_path, "textual"
        self._assert_exists(self.textual_model_path, "textual model")
        return self.textual_model_path, "textual"

    def _providers(self) -> list[str]:
        try:
            import onnxruntime as ort
        except ImportError:
            return ["CPUExecutionProvider"]

        providers = []
        if ort.get_device() == "GPU":
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")
        return providers

    def _session_options(self):
        import onnxruntime as ort

        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = max(1, (os.cpu_count() or 1) // 2)
        session_options.inter_op_num_threads = 1
        return session_options

    def _default_session_factory(self, model_path: str, **kwargs):
        import onnxruntime as ort

        return ort.InferenceSession(model_path, **kwargs)

    def _default_tokenizer_loader(self, tokenizer_dir: Path):
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(str(tokenizer_dir), local_files_only=True, use_fast=True)

    def _default_dense_loader(self, model_path: Path):
        from safetensors.numpy import load_file

        tensors = load_file(str(model_path))
        weight = None
        bias = None
        for key, value in tensors.items():
            array = np.asarray(value, dtype=np.float32)
            if array.ndim == 2 and weight is None:
                weight = array
            elif array.ndim == 1 and bias is None:
                bias = array
        if weight is None:
            raise RuntimeError(f"Missing dense weight tensor: {model_path}")
        return weight, bias

    def _prepare_image(self, image: Image.Image) -> np.ndarray:
        resized = image.resize((224, 224), Image.BICUBIC)
        array = np.asarray(resized, dtype=np.float32) / 255.0
        array = np.transpose(array, (2, 0, 1))
        mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32).reshape(3, 1, 1)
        std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32).reshape(3, 1, 1)
        normalized = (array - mean) / std
        return normalized[np.newaxis, ...]

    def _normalize_vector(self, vector: np.ndarray) -> np.ndarray:
        vector = np.asarray(vector, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm

    def _ensure_loaded(self) -> None:
        if not self.is_loaded or self.visual_session is None or self.textual_session is None or self.tokenizer is None:
            raise RuntimeError("CLIP embedder is not loaded")

    def _assert_exists(self, path: Path, description: str) -> None:
        if not Path(path).exists():
            raise FileNotFoundError(f"Missing {description}: {path}")


class APIEmbedder(BaseEmbedder):
    JINA_ENDPOINT = "https://api.jina.ai/v1/embeddings"
    VOYAGE_ENDPOINT = "https://api.voyageai.com/v1/multimodalembeddings"

    def __init__(
        self,
        provider: str = "jina",
        *,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        if provider not in {"jina", "voyage"}:
            raise ValueError("provider must be 'jina' or 'voyage'")
        self.provider = provider
        self.api_key = api_key
        if client is None:
            import httpx

            client = httpx.AsyncClient(timeout=30.0)
        self._client = client

    async def load(self) -> None:
        return None

    def reset(self) -> None:
        return None

    @property
    def vector_dim(self) -> int:
        return 1024

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key)

    async def validate_api_key(self, api_key: str) -> bool:
        previous_key = self.api_key
        self.api_key = api_key
        try:
            embedding = await self.encode_text("test")
            return embedding.shape == (self.vector_dim,)
        except Exception:
            return False
        finally:
            self.api_key = previous_key

    async def encode_image(self, image_path: str) -> np.ndarray:
        encoded = self._image_to_base64_jpeg(image_path)
        if self.provider == "voyage":
            payload = self._voyage_payload([{"type": "image_base64", "image_base64": encoded}], input_type="document")
        else:
            payload = self._jina_payload([{"image": encoded}])
        response = await self._call_with_retry(payload)
        return self._normalize_vector(self._extract_embedding(response, 0))

    async def encode_text(self, text: str) -> np.ndarray:
        if self.provider == "voyage":
            payload = self._voyage_payload([{"type": "text", "text": text}], input_type="query")
        else:
            payload = self._jina_payload([{"text": text}])
        response = await self._call_with_retry(payload)
        return self._normalize_vector(self._extract_embedding(response, 0))

    async def encode_images_batch(self, image_paths: list[str], batch_size: int = 8) -> list[np.ndarray | None]:
        results: list[np.ndarray | None] = [None] * len(image_paths)
        for offset in range(0, len(image_paths), batch_size):
            paths = image_paths[offset : offset + batch_size]
            encoded_items: list[tuple[int, str]] = []
            for batch_index, image_path in enumerate(paths):
                try:
                    encoded_items.append((offset + batch_index, self._image_to_base64_jpeg(image_path)))
                except Exception:
                    results[offset + batch_index] = None
            if not encoded_items:
                continue

            try:
                response = await self._call_with_retry(self._batch_image_payload([item[1] for item in encoded_items]))
                for local_index, vector in self._extract_embeddings(response).items():
                    if local_index < len(encoded_items):
                        original_index = encoded_items[local_index][0]
                        results[original_index] = self._normalize_vector(vector)
            except Exception:
                for original_index, encoded in encoded_items:
                    try:
                        response = await self._call_with_retry(self._batch_image_payload([encoded]))
                        results[original_index] = self._normalize_vector(self._extract_embedding(response, 0))
                    except Exception:
                        results[original_index] = None
            await asyncio.sleep(0.1)
        return results

    def _jina_payload(self, inputs: list[dict[str, str]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": "jina-clip-v2",
            "normalized": True,
            "input": inputs,
        }
        if inputs and "image" in inputs[0]:
            payload["embedding_type"] = "float"
        return payload

    def _voyage_payload(self, content: list[dict[str, str]], *, input_type: str) -> dict[str, Any]:
        return {
            "model": "voyage-multimodal-3",
            "inputs": [{"content": [item]} for item in content],
            "input_type": input_type,
        }

    def _batch_image_payload(self, images: list[str]) -> dict[str, Any]:
        if self.provider == "voyage":
            return self._voyage_payload(
                [{"type": "image_base64", "image_base64": image} for image in images],
                input_type="document",
            )
        return self._jina_payload([{"image": image} for image in images])

    async def _call_with_retry(self, payload: dict[str, Any], max_retries: int = 3) -> dict[str, Any]:
        if not self.api_key:
            raise InvalidAPIKeyError("API key is not configured")

        endpoint = self.VOYAGE_ENDPOINT if self.provider == "voyage" else self.JINA_ENDPOINT
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        import httpx

        for attempt in range(max_retries):
            try:
                response = await self._client.post(endpoint, headers=headers, json=payload)
                if response.status_code == 429 and attempt < max_retries - 1:
                    wait_seconds = int(response.headers.get("Retry-After", "5"))
                    await asyncio.sleep(wait_seconds)
                    continue
                if response.status_code == 401:
                    raise InvalidAPIKeyError("API key is invalid or expired")
                if response.status_code == 402:
                    raise InsufficientCreditsError("API credits are insufficient")
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
        raise EmbedderAPIError("API request failed")

    def _extract_embedding(self, response: dict[str, Any], index: int) -> np.ndarray:
        embeddings = self._extract_embeddings(response)
        if index not in embeddings:
            raise EmbedderAPIError("API response did not include expected embedding")
        return embeddings[index]

    def _extract_embeddings(self, response: dict[str, Any]) -> dict[int, np.ndarray]:
        data = response.get("data")
        if not isinstance(data, list):
            raise EmbedderAPIError("API response missing data")
        embeddings: dict[int, np.ndarray] = {}
        for default_index, item in enumerate(data):
            if not isinstance(item, dict) or "embedding" not in item:
                continue
            index = int(item.get("index", default_index))
            embeddings[index] = np.asarray(item["embedding"], dtype=np.float32).reshape(-1)
        return embeddings

    def _image_to_base64_jpeg(self, image_path: str) -> str:
        image = read_image_safe(image_path)
        try:
            image = image.convert("RGB")
            image.thumbnail((512, 512), Image.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=90, optimize=True)
            return base64.b64encode(buffer.getvalue()).decode("ascii")
        finally:
            image.close()

    def _normalize_vector(self, vector: np.ndarray) -> np.ndarray:
        vector = np.asarray(vector, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm


CLIPEmbedder = LocalEmbedder
embedder = LocalEmbedder()
