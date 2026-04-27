import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

import config


class _FakeVisualSession:
    def get_inputs(self):
        return [SimpleNamespace(name="pixel_values")]

    def run(self, _output_names, inputs):
        vector = np.arange(1, config.VECTOR_DIM + 1, dtype=np.float32)
        return [vector.reshape(1, -1)]


class _FakeTextualSession:
    def get_inputs(self):
        return [
            SimpleNamespace(name="input_ids"),
            SimpleNamespace(name="attention_mask"),
        ]

    def run(self, _output_names, inputs):
        vector = np.arange(config.VECTOR_DIM, 0, -1, dtype=np.float32)
        return [vector.reshape(1, -1)]


class _FakeIncompatibleTextualSession:
    def get_inputs(self):
        return [
            SimpleNamespace(name="input_ids"),
            SimpleNamespace(name="attention_mask"),
        ]

    def get_outputs(self):
        return [
            SimpleNamespace(name="last_hidden_state", shape=["batch_size", "sequence_length", 768]),
        ]

    def run(self, _output_names, inputs):
        vector = np.ones((1, 77, 768), dtype=np.float32)
        return [vector]


class _FakeMultilingualHiddenSession:
    def get_inputs(self):
        return [
            SimpleNamespace(name="input_ids"),
            SimpleNamespace(name="attention_mask"),
        ]

    def get_outputs(self):
        return [
            SimpleNamespace(name="last_hidden_state", shape=["batch_size", "sequence_length", 768]),
        ]

    def run(self, _output_names, inputs):
        hidden_states = np.zeros((1, 3, 768), dtype=np.float32)
        hidden_states[0, 0, :] = 1.0
        hidden_states[0, 1, :] = 3.0
        hidden_states[0, 2, :] = 100.0
        return [hidden_states]


class _FakeTokenizer:
    def __call__(self, text, *, padding, truncation, max_length, return_tensors):
        assert text
        assert padding == "max_length"
        assert truncation is True
        assert max_length == 77
        assert return_tensors == "np"
        return {
            "input_ids": np.ones((1, 77), dtype=np.int64),
            "attention_mask": np.ones((1, 77), dtype=np.int64),
        }


class _FakeMultilingualTokenizer:
    def __call__(self, text, *, padding, truncation, max_length, return_tensors):
        assert text
        assert padding == "max_length"
        assert truncation is True
        assert max_length == 128
        assert return_tensors == "np"
        return {
            "input_ids": np.ones((1, 3), dtype=np.int64),
            "attention_mask": np.array([[1, 1, 0]], dtype=np.int64),
        }


class CLIPEmbedderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.visual_model = self.temp_path / "visual.onnx"
        self.textual_model = self.temp_path / "textual.onnx"
        self.tokenizer_dir = self.temp_path / "tokenizer"
        self.visual_model.write_bytes(b"visual")
        self.textual_model.write_bytes(b"textual")
        self.tokenizer_dir.mkdir()

    def test_load_initializes_sessions_and_tokenizer(self) -> None:
        from core.embedder import CLIPEmbedder

        created_paths = []

        def session_factory(model_path, providers=None, sess_options=None):
            created_paths.append(Path(model_path).name)
            if "visual" in str(model_path):
                return _FakeVisualSession()
            return _FakeTextualSession()

        embedder = CLIPEmbedder(
            visual_model_path=self.visual_model,
            textual_model_path=self.textual_model,
            multilingual_model_path=None,
            tokenizer_dir=self.tokenizer_dir,
            session_factory=session_factory,
            tokenizer_loader=lambda _: _FakeTokenizer(),
        )

        asyncio.run(embedder.load())

        self.assertTrue(embedder.is_loaded)
        self.assertEqual(created_paths, ["visual.onnx", "textual.onnx"])
        self.assertIsNotNone(embedder.visual_session)
        self.assertIsNotNone(embedder.textual_session)
        self.assertIsNotNone(embedder.tokenizer)

    def test_load_prefers_multilingual_text_model_when_available(self) -> None:
        from core.embedder import CLIPEmbedder

        multilingual_model = self.temp_path / "multilingual.onnx"
        multilingual_model.write_bytes(b"multilingual")
        created_paths = []

        def session_factory(model_path, providers=None, sess_options=None):
            created_paths.append(Path(model_path).name)
            if "visual" in str(model_path):
                return _FakeVisualSession()
            return _FakeTextualSession()

        embedder = CLIPEmbedder(
            visual_model_path=self.visual_model,
            textual_model_path=self.textual_model,
            multilingual_model_path=multilingual_model,
            multilingual_dense_model_path=self.temp_path / "missing_dense.safetensors",
            tokenizer_dir=self.tokenizer_dir,
            session_factory=session_factory,
            tokenizer_loader=lambda _: _FakeTokenizer(),
        )

        asyncio.run(embedder.load())

        self.assertEqual(created_paths, ["visual.onnx", "multilingual.onnx"])
        self.assertEqual(embedder.loaded_text_model, "multilingual")

    def test_load_falls_back_when_multilingual_text_model_is_not_512_dimensional(self) -> None:
        from core.embedder import CLIPEmbedder

        multilingual_model = self.temp_path / "multilingual.onnx"
        multilingual_model.write_bytes(b"multilingual")
        created_paths = []

        def session_factory(model_path, providers=None, sess_options=None):
            created_paths.append(Path(model_path).name)
            if "visual" in str(model_path):
                return _FakeVisualSession()
            if "multilingual" in str(model_path):
                return _FakeIncompatibleTextualSession()
            return _FakeTextualSession()

        embedder = CLIPEmbedder(
            visual_model_path=self.visual_model,
            textual_model_path=self.textual_model,
            multilingual_model_path=multilingual_model,
            multilingual_dense_model_path=self.temp_path / "missing_dense.safetensors",
            tokenizer_dir=self.tokenizer_dir,
            session_factory=session_factory,
            tokenizer_loader=lambda _: _FakeTokenizer(),
        )

        asyncio.run(embedder.load())

        self.assertEqual(created_paths, ["visual.onnx", "multilingual.onnx", "textual.onnx"])
        self.assertEqual(embedder.loaded_text_model, "textual")

    def test_encode_text_uses_multilingual_pooling_and_dense_projection(self) -> None:
        from core.embedder import CLIPEmbedder

        multilingual_model = self.temp_path / "multilingual.onnx"
        multilingual_tokenizer_dir = self.temp_path / "multilingual_tokenizer"
        multilingual_dense_model = self.temp_path / "multilingual_dense.safetensors"
        multilingual_model.write_bytes(b"multilingual")
        multilingual_tokenizer_dir.mkdir()
        multilingual_dense_model.write_bytes(b"dense")
        tokenizer_paths = []

        projection = np.zeros((config.VECTOR_DIM, 768), dtype=np.float32)
        projection[:, : config.VECTOR_DIM] = np.eye(config.VECTOR_DIM, dtype=np.float32)

        def session_factory(model_path, providers=None, sess_options=None):
            if "visual" in str(model_path):
                return _FakeVisualSession()
            if "multilingual" in str(model_path):
                return _FakeMultilingualHiddenSession()
            return _FakeTextualSession()

        def tokenizer_loader(tokenizer_dir):
            tokenizer_paths.append(Path(tokenizer_dir).name)
            if Path(tokenizer_dir) == multilingual_tokenizer_dir:
                return _FakeMultilingualTokenizer()
            return _FakeTokenizer()

        embedder = CLIPEmbedder(
            visual_model_path=self.visual_model,
            textual_model_path=self.textual_model,
            multilingual_model_path=multilingual_model,
            multilingual_tokenizer_dir=multilingual_tokenizer_dir,
            multilingual_dense_model_path=multilingual_dense_model,
            tokenizer_dir=self.tokenizer_dir,
            session_factory=session_factory,
            tokenizer_loader=tokenizer_loader,
            dense_loader=lambda _: projection,
        )

        asyncio.run(embedder.load())
        vector = embedder.encode_text("数学公式")

        self.assertEqual(embedder.loaded_text_model, "multilingual")
        self.assertEqual(tokenizer_paths, ["multilingual_tokenizer"])
        self.assertEqual(vector.shape, (config.VECTOR_DIM,))
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=5)

    def test_encode_image_returns_normalized_vector(self) -> None:
        from core.embedder import CLIPEmbedder

        photo_path = self.temp_path / "sample.jpg"
        Image.new("RGB", (32, 24), color="orange").save(photo_path)

        embedder = CLIPEmbedder(
            visual_model_path=self.visual_model,
            textual_model_path=self.textual_model,
            multilingual_model_path=None,
            tokenizer_dir=self.tokenizer_dir,
            session_factory=lambda model_path, **_: _FakeVisualSession()
            if "visual" in str(model_path)
            else _FakeTextualSession(),
            tokenizer_loader=lambda _: _FakeTokenizer(),
        )
        asyncio.run(embedder.load())

        vector = embedder.encode_image(str(photo_path))

        self.assertEqual(vector.shape, (config.VECTOR_DIM,))
        self.assertEqual(vector.dtype, np.float32)
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=5)

    def test_encode_text_returns_normalized_vector(self) -> None:
        from core.embedder import CLIPEmbedder

        embedder = CLIPEmbedder(
            visual_model_path=self.visual_model,
            textual_model_path=self.textual_model,
            multilingual_model_path=None,
            tokenizer_dir=self.tokenizer_dir,
            session_factory=lambda model_path, **_: _FakeVisualSession()
            if "visual" in str(model_path)
            else _FakeTextualSession(),
            tokenizer_loader=lambda _: _FakeTokenizer(),
        )
        asyncio.run(embedder.load())

        vector = embedder.encode_text("orange cat on the beach")

        self.assertEqual(vector.shape, (config.VECTOR_DIM,))
        self.assertEqual(vector.dtype, np.float32)
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=5)

    def test_encode_images_batch_preserves_failed_image_positions(self) -> None:
        from core.embedder import CLIPEmbedder

        good_photo = self.temp_path / "good.jpg"
        bad_photo = self.temp_path / "broken.jpg"
        Image.new("RGB", (20, 20), color="purple").save(good_photo)
        bad_photo.write_bytes(b"not-an-image")

        embedder = CLIPEmbedder(
            visual_model_path=self.visual_model,
            textual_model_path=self.textual_model,
            multilingual_model_path=None,
            tokenizer_dir=self.tokenizer_dir,
            session_factory=lambda model_path, **_: _FakeVisualSession()
            if "visual" in str(model_path)
            else _FakeTextualSession(),
            tokenizer_loader=lambda _: _FakeTokenizer(),
        )
        asyncio.run(embedder.load())

        vectors = embedder.encode_images_batch([str(good_photo), str(bad_photo)])

        self.assertEqual(len(vectors), 2)
        self.assertEqual(vectors[0].shape, (config.VECTOR_DIM,))
        self.assertIsNone(vectors[1])


if __name__ == "__main__":
    unittest.main()
