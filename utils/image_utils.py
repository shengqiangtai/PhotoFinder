"""Image helpers for safe loading, thumbnails, and EXIF dates."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

from PIL import Image, ImageOps

try:  # pragma: no cover - optional dependency
    from pillow_heif import register_heif_opener
except ImportError:  # pragma: no cover - optional dependency
    register_heif_opener = None
else:  # pragma: no cover - optional dependency
    register_heif_opener()


PathLike = Union[str, Path]
EXIF_DATE_TAGS = (36867, 36868, 306)


def read_image_safe(path: PathLike) -> Image.Image:
    """Open an image, normalize orientation, and return an in-memory RGB copy."""

    with Image.open(path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        return normalized


def generate_thumbnail(path: PathLike, size: int = 256) -> bytes:
    """Return a JPEG thumbnail for the given image path."""

    thumbnail = read_image_safe(path)
    thumbnail.thumbnail((size, size), Image.LANCZOS)

    buffer = BytesIO()
    thumbnail.save(buffer, format="JPEG")
    return buffer.getvalue()


def extract_exif_date(path: PathLike) -> Optional[str]:
    """Return the first valid EXIF date as an ISO8601 string."""

    with Image.open(path) as image:
        exif = image.getexif()
        if not exif:
            return None

        for key in EXIF_DATE_TAGS:
            raw_value = exif.get(key)
            if not raw_value:
                continue
            try:
                parsed = datetime.strptime(str(raw_value), "%Y:%m:%d %H:%M:%S")
            except (TypeError, ValueError):
                continue
            return parsed.isoformat()

    return None
