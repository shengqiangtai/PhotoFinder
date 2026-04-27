import os
import sys
from pathlib import Path


IS_FROZEN = getattr(sys, "frozen", False)
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

if sys.platform == "win32":
    APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "PhotoFinder"
elif sys.platform == "darwin":
    APP_DATA_DIR = Path.home() / ".photofinder"
else:
    APP_DATA_DIR = Path.home() / ".photofinder"

DB_PATH = APP_DATA_DIR / "photofinder.db"
MODELS_DIR = APP_DATA_DIR / "models"
CACHE_DIR = APP_DATA_DIR / "cache"
WEB_DIR = BASE_DIR / "web"

HOST = "0.0.0.0"
PORT = 7700

CLIP_VISUAL_MODEL = MODELS_DIR / "clip_visual.onnx"
CLIP_TEXTUAL_MODEL = MODELS_DIR / "clip_textual.onnx"
MULTILINGUAL_MODEL = MODELS_DIR / "multilingual_textual.onnx"
TOKENIZER_DIR = MODELS_DIR / "clip_tokenizer"
MULTILINGUAL_TOKENIZER_DIR = MODELS_DIR / "multilingual_tokenizer"
MULTILINGUAL_DENSE_MODEL = MODELS_DIR / "multilingual_dense.safetensors"
VECTOR_DIM = 512

THUMBNAIL_SIZE = 256
THUMBNAIL_QUALITY = 80
BATCH_SIZE = 16
INDEXING_THREADS = 1

DEFAULT_TOP_K = 20
MAX_TOP_K = 100

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".heic",
    ".heif",
    ".tiff",
    ".tif",
    ".bmp",
    ".cr2",
    ".nef",
    ".arw",
    ".dng",
}

HF_BASE_URL = "https://huggingface.co"
MODEL_URLS = {
    "clip_visual": f"{HF_BASE_URL}/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model.onnx",
    "clip_textual": f"{HF_BASE_URL}/Xenova/clip-vit-base-patch32/resolve/main/onnx/text_model.onnx",
    "multilingual": f"{HF_BASE_URL}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/onnx/model.onnx",
    "multilingual_dense": f"{HF_BASE_URL}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/2_Dense/model.safetensors",
}

TOKENIZER_ASSET_URLS = {
    "tokenizer.json": f"{HF_BASE_URL}/Xenova/clip-vit-base-patch32/resolve/main/tokenizer.json",
    "tokenizer_config.json": f"{HF_BASE_URL}/Xenova/clip-vit-base-patch32/resolve/main/tokenizer_config.json",
    "special_tokens_map.json": f"{HF_BASE_URL}/Xenova/clip-vit-base-patch32/resolve/main/special_tokens_map.json",
    "vocab.json": f"{HF_BASE_URL}/Xenova/clip-vit-base-patch32/resolve/main/vocab.json",
    "merges.txt": f"{HF_BASE_URL}/Xenova/clip-vit-base-patch32/resolve/main/merges.txt",
}

MULTILINGUAL_TOKENIZER_ASSET_URLS = {
    "tokenizer.json": f"{HF_BASE_URL}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/tokenizer.json",
    "tokenizer_config.json": f"{HF_BASE_URL}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/tokenizer_config.json",
    "special_tokens_map.json": f"{HF_BASE_URL}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/special_tokens_map.json",
    "vocab.txt": f"{HF_BASE_URL}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/vocab.txt",
}


def ensure_app_directories() -> None:
    for path in (APP_DATA_DIR, MODELS_DIR, CACHE_DIR, TOKENIZER_DIR, MULTILINGUAL_TOKENIZER_DIR):
        path.mkdir(parents=True, exist_ok=True)
