import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from utils.image_utils import extract_exif_date, generate_thumbnail, read_image_safe


def _write_generated_image(path: Path, mode: str, size: tuple, color: tuple, fmt: str) -> None:
    image = Image.new(mode, size, color)
    image.save(path, format=fmt)


class ImageUtilsTests(unittest.TestCase):
    def test_read_image_safe_returns_rgb_for_generated_rgba_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "rgba.png"
            _write_generated_image(path, "RGBA", (2, 2), (10, 20, 30, 40), "PNG")

            image = read_image_safe(path)

            self.assertIsInstance(image, Image.Image)
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (2, 2))

    def test_generate_thumbnail_returns_jpeg_bytes_for_local_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "source.png"
            _write_generated_image(path, "RGB", (512, 256), (1, 2, 3), "PNG")

            thumbnail_bytes = generate_thumbnail(path)

            self.assertIsInstance(thumbnail_bytes, bytes)

            with Image.open(BytesIO(thumbnail_bytes)) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertLessEqual(image.width, 256)
                self.assertLessEqual(image.height, 256)
                self.assertEqual(image.size, (256, 128))

    def test_extract_exif_date_returns_none_when_exif_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "plain.png"
            _write_generated_image(path, "RGB", (4, 4), (255, 0, 0), "PNG")

            self.assertIsNone(extract_exif_date(path))


if __name__ == "__main__":
    unittest.main()
