# PhotoFinder — 本地 AI 相册语义搜索系统
## 完整项目架构规格文档 v1.0

> **本文档用途**：向 AI 描述整个项目的架构、技术选型、模块实现细节与开发顺序。
> AI 应按照「第九节：实现顺序」逐步生成代码，每个阶段完成后再进行下一阶段。
> 遇到任何模糊之处，以本文档的决策为准，不要自行发明替代方案。

---

## 目录

1. [项目定位与核心目标](#1-项目定位与核心目标)
2. [技术选型总览](#2-技术选型总览)
3. [目录结构](#3-目录结构)
4. [数据库设计](#4-数据库设计)
5. [后端模块详细规格](#5-后端模块详细规格)
6. [API 接口规格](#6-api-接口规格)
7. [前端 UI 规格](#7-前端-ui-规格)
8. [打包与发布规格](#8-打包与发布规格)
9. [实现顺序（分阶段）](#9-实现顺序分阶段)
10. [关键代码模式与约定](#10-关键代码模式与约定)
11. [配置管理](#11-配置管理)
12. [错误处理规范](#12-错误处理规范)

---

## 1. 项目定位与核心目标

### 1.1 一句话描述
PhotoFinder 是一个**零配置、单文件启动**的本地 AI 相册语义搜索工具。用户双击打开后，选择照片文件夹，即可用中文自然语言搜索数万张照片。完全离线，数据不出本机。

### 1.2 目标用户
- 没有任何技术背景的普通家庭用户
- 有几千到几十万张照片积累的人
- 重视隐私、不愿上传照片到云端的用户
- 需要在手机上也能搜索家庭照片的用户

### 1.3 核心体验（不可妥协）
```
双击程序 → 浏览器自动打开 → 选文件夹 → 等待建索引（后台，可继续用）
→ 搜索框输入"海边的狗" → 0.5秒内返回相关图片 → 手机扫二维码也能用
```

### 1.4 差异化定位
| 对比项 | Immich / PhotoPrism | PhotoFinder |
|--------|---------------------|-------------|
| 启动方式 | Docker Compose，需命令行 | 双击 exe/app |
| 依赖 | PostgreSQL、Redis 等多服务 | 无外部依赖，全内嵌 |
| 配置 | 需编辑 .env 文件 | 零配置 |
| 面向用户 | 技术用户 | 所有人 |
| 核心功能 | 完整相册管理 | 专注 AI 语义搜索 |

---

## 2. 技术选型总览

### 2.1 技术栈决策表

| 层 | 选择 | 备选方案 | 选择理由 |
|----|------|----------|----------|
| **后端框架** | FastAPI (Python 3.11+) | Flask, Django | 异步原生、自动文档、Pydantic 校验 |
| **AI 推理** | ONNX Runtime 1.18+ | PyTorch, TensorFlow | 打包体积小 (~150MB vs ~800MB)，无 CUDA 依赖也能跑 |
| **CLIP 模型** | `clip-ViT-B-32` (ONNX 格式) | SigLIP, UForm | 英文准确率高，模型仅 ~300MB，中文通过 tokenizer 可用 |
| **中文支持** | `multilingual-clip` 文本编码器 | UForm | 专为多语言优化，文本编码器单独替换 |
| **向量存储** | `sqlite-vec` (SQLite 扩展) | Qdrant, pgvector | 零独立进程，跟程序走，5万张图 <200ms |
| **元数据存储** | SQLite (via `aiosqlite`) | PostgreSQL | 零配置，单文件，够用 |
| **图像处理** | `Pillow` + `pillow-heif` | OpenCV | 轻量，HEIC 支持 |
| **前端** | 原生 HTML + CSS + JS (单文件) | React, Vue | 零构建步骤，内嵌方便，用户无感 |
| **二维码** | `qrcode` 库 | 无 | 轻量，生成局域网访问二维码 |
| **打包** | PyInstaller 6.x | Nuitka, cx_Freeze | 最成熟，社区最大 |
| **任务队列** | `asyncio` + `concurrent.futures` | Celery | 不引入 Redis/RabbitMQ 依赖 |

### 2.2 Python 依赖清单（requirements.txt）

```
fastapi==0.111.0
uvicorn[standard]==0.30.0
aiosqlite==0.20.0
sqlite-vec==0.1.6
onnxruntime==1.18.0
Pillow==10.3.0
pillow-heif==0.16.0
transformers==4.41.0        # 仅用 tokenizer，不加载 PyTorch 模型
tokenizers==0.19.0
numpy==1.26.4
qrcode[pil]==7.4.2
psutil==5.9.8
aiofiles==23.2.1
python-multipart==0.0.9
httpx==0.27.0               # 用于首次模型下载
tqdm==4.66.4                # 下载进度
```

> **注意**：`transformers` 仅用于加载 tokenizer（文本 token 化），不引入 PyTorch。
> 安装时需用 `pip install transformers --no-deps` 然后单独装 `tokenizers`。

---

## 3. 目录结构

```
photofinder/
│
├── main.py                     # 程序唯一入口
│
├── config.py                   # 全局配置（路径、常量、运行时状态）
│
├── core/
│   ├── __init__.py
│   ├── scanner.py              # 文件扫描与变更检测
│   ├── embedder.py             # CLIP ONNX 推理，生成图像向量
│   ├── indexer.py              # 调度建索引流程（扫描→推理→写库）
│   └── searcher.py             # 文本查询 → 向量检索 → 返回结果
│
├── db/
│   ├── __init__.py
│   ├── database.py             # SQLite 连接池、初始化、sqlite-vec 加载
│   └── migrations.py           # 建表语句（首次运行自动执行）
│
├── api/
│   ├── __init__.py
│   ├── app.py                  # FastAPI 实例、中间件、静态文件挂载
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── search.py           # GET /api/search
│   │   ├── library.py          # POST /api/library/add, GET /api/library/status
│   │   ├── image.py            # GET /api/image/{id}, GET /api/thumbnail/{id}
│   │   └── system.py           # GET /api/system/info, GET /api/system/qrcode
│   └── schemas.py              # Pydantic 请求/响应模型
│
├── web/                        # 前端静态文件（全部内嵌，单页应用）
│   ├── index.html              # 唯一 HTML 文件（包含全部 UI 逻辑）
│   ├── style.css               # 全局样式
│   └── app.js                  # 前端逻辑
│
├── models/                     # ONNX 模型文件（首次运行时下载到此）
│   ├── .gitkeep
│   ├── clip_visual.onnx        # 图像编码器（~280MB）
│   ├── clip_textual.onnx       # 英文文本编码器（~60MB）
│   └── multilingual_textual.onnx  # 多语言文本编码器（~470MB，可选下载）
│
├── utils/
│   ├── __init__.py
│   ├── image_utils.py          # 图像读取、缩略图生成、HEIC 转换
│   ├── network_utils.py        # 获取本机局域网 IP、生成二维码
│   └── model_downloader.py     # 从 Hugging Face 下载 ONNX 模型
│
├── requirements.txt
├── README.md
├── build/
│   ├── build_windows.spec      # PyInstaller Windows 配置
│   ├── build_mac.spec          # PyInstaller macOS 配置
│   └── build_linux.spec        # PyInstaller Linux 配置
│
└── .gitignore
```

---

## 4. 数据库设计

数据库文件路径：`{用户主目录}/.photofinder/photofinder.db`

### 4.1 表结构

#### `photos` 表 — 照片元数据

```sql
CREATE TABLE IF NOT EXISTS photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL UNIQUE,     -- 照片绝对路径
    filename    TEXT NOT NULL,            -- 文件名（含扩展名）
    folder_id   INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    size_bytes  INTEGER,                  -- 文件大小（字节）
    width       INTEGER,                  -- 图像宽度（px）
    height      INTEGER,                  -- 图像高度（px）
    taken_at    TEXT,                     -- EXIF 拍摄时间（ISO8601 格式）
    indexed_at  TEXT NOT NULL,            -- 建索引时间
    file_mtime  REAL NOT NULL,            -- 文件修改时间戳（用于增量检测）
    has_vector  INTEGER DEFAULT 0,        -- 0=未向量化, 1=已向量化
    thumbnail   BLOB,                     -- JPEG 缩略图（256px，存 BLOB）
    error_msg   TEXT                      -- 若处理失败，记录错误原因
);

CREATE INDEX IF NOT EXISTS idx_photos_path ON photos(path);
CREATE INDEX IF NOT EXISTS idx_photos_folder ON photos(folder_id);
CREATE INDEX IF NOT EXISTS idx_photos_taken_at ON photos(taken_at);
CREATE INDEX IF NOT EXISTS idx_photos_has_vector ON photos(has_vector);
```

#### `folders` 表 — 受监控的文件夹

```sql
CREATE TABLE IF NOT EXISTS folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL UNIQUE,     -- 文件夹绝对路径
    added_at    TEXT NOT NULL,            -- 添加时间
    last_scan   TEXT,                     -- 最近一次扫描时间
    photo_count INTEGER DEFAULT 0,        -- 照片总数（统计用）
    is_active   INTEGER DEFAULT 1         -- 1=监控中, 0=已停用
);
```

#### `photo_vectors` 虚拟表 — 图像向量（sqlite-vec）

```sql
-- 使用 sqlite-vec 创建向量虚拟表（512维，对应 CLIP ViT-B/32）
CREATE VIRTUAL TABLE IF NOT EXISTS photo_vectors USING vec0(
    photo_id    INTEGER PRIMARY KEY,
    embedding   FLOAT[512]
);
```

#### `index_jobs` 表 — 建索引任务状态

```sql
CREATE TABLE IF NOT EXISTS index_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id       INTEGER REFERENCES folders(id),
    status          TEXT NOT NULL,        -- 'pending','running','completed','failed'
    total_files     INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    failed_files    INTEGER DEFAULT 0,
    started_at      TEXT,
    finished_at     TEXT,
    error_msg       TEXT
);
```

#### `app_config` 表 — 运行时配置

```sql
CREATE TABLE IF NOT EXISTS app_config (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
-- 初始数据
INSERT OR IGNORE INTO app_config VALUES ('clip_model', 'clip-vit-b-32');
INSERT OR IGNORE INTO app_config VALUES ('text_model', 'multilingual');   -- 'english' 或 'multilingual'
INSERT OR IGNORE INTO app_config VALUES ('top_k', '20');
INSERT OR IGNORE INTO app_config VALUES ('thumbnail_size', '256');
INSERT OR IGNORE INTO app_config VALUES ('first_run', '1');
```

---

## 5. 后端模块详细规格

### 5.1 `main.py` — 程序入口

**职责**：初始化所有组件，启动 Web 服务器，自动打开浏览器。

```python
# 伪代码描述行为：

def main():
    # 1. 确保数据目录存在
    ensure_data_dir()  # 创建 ~/.photofinder/

    # 2. 初始化数据库（建表、加载 sqlite-vec 扩展）
    await database.init()

    # 3. 检查模型是否存在，不存在则标记需要下载
    model_status = check_models()

    # 4. 创建 FastAPI app
    app = create_app()

    # 5. 启动 uvicorn（监听 0.0.0.0:7700）
    # 使用 0.0.0.0 而不是 127.0.0.1，局域网手机才能访问

    # 6. 延迟 1.5 秒后自动打开浏览器 localhost:7700
    # 使用 threading.Timer 或 asyncio，不阻塞服务器启动

if __name__ == "__main__":
    main()
```

**端口**：固定使用 `7700`。若被占用，自动递增尝试 `7701`, `7702`...

### 5.2 `core/scanner.py` — 文件扫描

**职责**：扫描指定文件夹，找出所有支持的图片文件，与数据库对比后返回新增/修改/删除的文件列表。

```python
# 支持的文件扩展名
SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.gif',
    '.heic', '.heif',                          # Apple 格式
    '.tiff', '.tif', '.bmp',
    '.cr2', '.nef', '.arw', '.dng'             # RAW 格式（仅提取缩略图）
}

class ScanResult:
    new_files: list[str]         # 数据库中没有的文件
    modified_files: list[str]    # mtime 变化的文件（需重新索引）
    deleted_files: list[str]     # 文件已不存在但数据库有记录的
    total_found: int             # 扫描到的文件总数

async def scan_folder(folder_path: str) -> ScanResult:
    """
    1. 递归遍历 folder_path 下所有文件
    2. 过滤出 SUPPORTED_EXTENSIONS 中的文件
    3. 从数据库获取该文件夹所有已知文件的 {path: mtime} 映射
    4. 对比得出 new / modified / deleted 三类
    5. 返回 ScanResult
    """
```

**注意**：
- 扫描应该是非阻塞的，使用 `os.scandir` 而不是 `os.walk`（性能更好）
- 跳过隐藏文件（以 `.` 开头的文件和目录）
- 跳过系统目录：`__MACOSX`, `@eaDir`, `Thumbs.db`

### 5.3 `core/embedder.py` — CLIP 推理

**职责**：加载 ONNX 模型，为图像和文本生成向量。

#### 类结构

```python
class CLIPEmbedder:
    def __init__(self):
        self.visual_session = None      # ONNX InferenceSession（图像编码器）
        self.textual_session = None     # ONNX InferenceSession（文本编码器）
        self.tokenizer = None           # HuggingFace tokenizer
        self.is_loaded = False

    async def load(self):
        """
        异步加载模型（在线程池中执行，不阻塞事件循环）
        加载顺序: visual → textual → tokenizer
        加载完成后设置 self.is_loaded = True
        """

    def encode_image(self, image_path: str) -> np.ndarray:
        """
        1. 用 Pillow 读取图像
        2. 处理 HEIC 格式（需 pillow-heif）
        3. 调整大小到 224x224（BICUBIC 插值）
        4. 转 RGB（处理 RGBA、灰度等格式）
        5. 归一化（均值 [0.48145466, 0.4578275, 0.40821073]，
                   标准差 [0.26862954, 0.26130258, 0.27577711]）
        6. ONNX 推理 → 512维向量
        7. L2 归一化
        返回: np.ndarray shape=(512,) dtype=float32
        """

    def encode_text(self, text: str) -> np.ndarray:
        """
        1. tokenizer 对文本编码（max_length=77，截断）
        2. ONNX 推理 → 512维向量
        3. L2 归一化
        返回: np.ndarray shape=(512,) dtype=float32
        """

    def encode_images_batch(self, image_paths: list[str],
                             batch_size: int = 16) -> list[np.ndarray]:
        """
        批量编码图像，batch_size 默认 16
        遇到单张图片失败时记录错误并跳过，不中断整体批次
        """
```

#### ONNX Session 初始化参数

```python
import onnxruntime as ort

# 优先使用 GPU，降级到 CPU
providers = []
if ort.get_device() == 'GPU':
    providers.append('CUDAExecutionProvider')
providers.append('CPUExecutionProvider')

session = ort.InferenceSession(model_path, providers=providers)

# 线程数设置（不抢占用户 CPU）
session_options = ort.SessionOptions()
session_options.intra_op_num_threads = max(1, os.cpu_count() // 2)
session_options.inter_op_num_threads = 1
```

### 5.4 `core/indexer.py` — 建索引调度

**职责**：整体协调"扫描→推理→写库"的完整流程，管理进度状态。

```python
class IndexingState:
    """全局单例，记录当前索引状态（供前端轮询）"""
    is_running: bool = False
    current_job_id: int = None
    total: int = 0
    processed: int = 0
    failed: int = 0
    current_file: str = ""       # 当前正在处理的文件名（显示用）
    phase: str = ""              # 'scanning' | 'embedding' | 'done' | 'idle'
    eta_seconds: int = 0         # 预计剩余秒数

indexing_state = IndexingState()  # 模块级单例

async def start_indexing(folder_path: str):
    """
    完整流程（在后台 asyncio Task 中运行，不阻塞 API）：

    Phase 1 - scanning（约几秒）:
        1. 更新 state.phase = 'scanning'
        2. 调用 scanner.scan_folder()
        3. 将新文件批量插入 photos 表（has_vector=0）
        4. 删除 deleted_files 对应的记录

    Phase 2 - embedding（主要耗时）:
        1. 更新 state.phase = 'embedding'
        2. 从数据库查询所有 has_vector=0 的照片（包括历史遗留）
        3. 分批（每批 16 张）调用 embedder.encode_images_batch()
        4. 每批完成后：
           a. 将 512 维向量写入 photo_vectors 虚拟表
           b. 更新 photos.has_vector = 1
           c. 同时生成并存储缩略图 BLOB（256px JPEG，质量 80）
           d. 更新 indexing_state.processed += len(batch)
           e. 计算 ETA（基于已处理速度）
        5. 失败的文件：写入 photos.error_msg，has_vector 保持 0

    Phase 3 - done:
        1. 更新 index_jobs 表 status='completed'
        2. 更新 indexing_state.phase = 'done'
        3. 5秒后自动重置 indexing_state 为 idle
    """
```

**并发控制**：
- 同一时刻只允许一个索引任务运行（检查 `indexing_state.is_running`）
- ONNX 推理在 `ThreadPoolExecutor(max_workers=1)` 中运行，避免多线程 ONNX 问题

### 5.5 `core/searcher.py` — 向量检索

**职责**：将用户文本查询转为向量，在 sqlite-vec 中做相似度检索。

```python
async def search(query: str, top_k: int = 20,
                 folder_id: int = None,
                 date_from: str = None,
                 date_to: str = None) -> list[SearchResult]:
    """
    1. 调用 embedder.encode_text(query) → query_vector (512维)
    2. 执行 sqlite-vec ANN 查询：

       SELECT
           p.id, p.path, p.filename, p.taken_at,
           p.width, p.height,
           distance
       FROM photo_vectors v
       JOIN photos p ON p.id = v.photo_id
       WHERE v.embedding MATCH :query_vector
         AND K = :top_k
         [AND p.folder_id = :folder_id]
         [AND p.taken_at BETWEEN :date_from AND :date_to]
       ORDER BY distance ASC

    3. 返回 SearchResult 列表（含相似度分数转为 0-100 的百分比）
    """

class SearchResult:
    id: int
    filename: str
    taken_at: str
    thumbnail_url: str      # '/api/thumbnail/{id}'
    full_image_url: str     # '/api/image/{id}'
    similarity: float       # 0.0 ~ 1.0（越高越相关）
```

**相似度转换**：CLIP 余弦相似度范围约 0.1~0.4，做线性映射到 0~1 供前端显示。

---

## 6. API 接口规格

所有接口前缀 `/api`，返回 JSON。

### 6.1 搜索接口

```
GET /api/search

Query Parameters:
  q         string   必填   搜索词，如 "海边的狗"
  top_k     int      可选   返回数量，默认 20，最大 100
  folder_id int      可选   限定在某个文件夹内搜索
  date_from string   可选   日期过滤起始（YYYY-MM-DD）
  date_to   string   可选   日期过滤结束（YYYY-MM-DD）

Response 200:
{
  "results": [
    {
      "id": 1234,
      "filename": "IMG_5678.jpg",
      "taken_at": "2023-08-15T14:23:00",
      "thumbnail_url": "/api/thumbnail/1234",
      "full_image_url": "/api/image/1234",
      "similarity": 0.87
    }
  ],
  "total": 20,
  "query": "海边的狗",
  "search_time_ms": 145
}

Response 503（模型未加载完成）:
{
  "error": "model_loading",
  "message": "AI 模型正在加载，请稍后再试"
}
```

### 6.2 图片接口

```
GET /api/image/{id}
  返回原图二进制（Content-Type 按实际格式，支持 Range 请求）

GET /api/thumbnail/{id}
  返回 JPEG 缩略图二进制（256px，从 photos.thumbnail BLOB 读取）
  Cache-Control: max-age=86400
```

### 6.3 图库管理接口

```
POST /api/library/add
Body: { "path": "/Users/name/Pictures" }
Response:
{
  "folder_id": 1,
  "path": "/Users/name/Pictures",
  "status": "scanning_started"
}
副作用：触发后台 indexing task（异步，立即返回）

GET /api/library/folders
Response:
{
  "folders": [
    {
      "id": 1,
      "path": "/Users/name/Pictures",
      "photo_count": 52341,
      "indexed_count": 48200,
      "last_scan": "2024-01-15T10:30:00"
    }
  ]
}

DELETE /api/library/folder/{id}
  从数据库删除文件夹及其所有照片记录和向量（不删除磁盘文件）

POST /api/library/rescan/{id}
  触发对指定文件夹的增量扫描（异步，立即返回）
```

### 6.4 索引进度接口（前端轮询用）

```
GET /api/index/status
Response:
{
  "is_running": true,
  "phase": "embedding",       // "idle" | "scanning" | "embedding" | "done"
  "total": 52341,
  "processed": 12500,
  "failed": 3,
  "current_file": "IMG_1234.jpg",
  "progress_percent": 24,
  "eta_seconds": 3420,
  "speed_per_second": 3.5     // 张/秒
}
```

### 6.5 系统信息接口

```
GET /api/system/info
Response:
{
  "version": "1.0.0",
  "model_status": {
    "visual": "loaded",         // "not_downloaded" | "downloading" | "loading" | "loaded"
    "textual": "loaded",
    "multilingual": "loaded"
  },
  "download_progress": null,    // 或 { "model": "clip_visual", "percent": 45 }
  "total_photos": 52341,
  "indexed_photos": 48200,
  "db_size_mb": 312,
  "lan_url": "http://192.168.1.5:7700",
  "first_run": false
}

GET /api/system/qrcode
  返回局域网访问地址的 QR 码 PNG 图片
  若无局域网 IP，返回 404

GET /api/system/open-folder
  Query: path (string)
  打开系统文件夹选择对话框（使用 tkinter.filedialog 或系统命令）
  Response: { "selected_path": "/Users/name/Pictures" } 或 { "cancelled": true }
```

### 6.6 模型下载接口

```
POST /api/models/download
Body: { "model": "multilingual" }  // "clip_visual" | "clip_textual" | "multilingual"
  触发后台下载（异步，立即返回）
  Response: { "status": "download_started" }

GET /api/models/download/status
  Response:
  {
    "downloading": true,
    "model": "clip_visual",
    "percent": 45,
    "downloaded_mb": 135,
    "total_mb": 280
  }
```

---

## 7. 前端 UI 规格

### 7.1 整体设计原则
- **单页应用**，无路由切换，通过显示/隐藏不同面板实现
- **响应式**：桌面（>768px）和手机（<768px）都要好用
- **无障碍**：搜索框自动聚焦，支持回车搜索
- **暗色主题**：深色背景，减少眼疲劳

### 7.2 页面状态机

```
[首次运行页] → 选择文件夹 → [建索引进度页] → 完成 → [搜索主页]
                                                          ↑
                                              [搜索结果页] ←→ [搜索主页]
```

### 7.3 各页面 UI 规格

#### 状态 A：首次运行 / 无图库
```
┌────────────────────────────────────┐
│  🔍 PhotoFinder                    │
│                                    │
│  让你用中文找到任何一张照片           │
│  完全本地 · 隐私安全 · 无需联网      │
│                                    │
│  ┌──────────────────────────────┐  │
│  │     选择照片文件夹            │  │
│  │  [ 📁 浏览并选择文件夹 ]      │  │
│  │   或将文件夹拖拽到此处        │  │
│  └──────────────────────────────┘  │
│                                    │
│  注意：首次使用需下载 AI 模型        │
│  （约 350MB，仅需一次）              │
└────────────────────────────────────┘
```

#### 状态 B：建索引中
```
┌────────────────────────────────────┐
│  🔍 PhotoFinder                    │
│                                    │
│  正在分析你的照片...                 │
│                                    │
│  ████████████░░░░░░░  58%          │
│  已完成 30,234 / 52,341 张          │
│                                    │
│  正在处理：IMG_8934.HEIC            │
│  处理速度：3.5 张/秒                 │
│  预计剩余：约 1 小时 22 分           │
│                                    │
│  [ 你可以先开始搜索已完成的照片 ]    │
│  [ 继续使用 → ]                    │
└────────────────────────────────────┘
```

#### 状态 C：搜索主页（建索引完成后默认页）
```
┌────────────────────────────────────┐
│  🔍 PhotoFinder    [⚙️] [📱二维码]  │
├────────────────────────────────────┤
│                                    │
│  ┌──────────────────────────────┐  │
│  │ 🔍 试试搜索"海边日落"...     │  │  ← 自动聚焦
│  └──────────────────────────────┘  │
│                                    │
│  52,341 张照片已就绪                 │
│                                    │
│  试试这些搜索:                      │
│  [生日蛋糕] [海边] [下雪] [宠物]    │
│                                    │
│         📱 手机也能用              │
│         [二维码图片]               │
│      192.168.1.5:7700             │
└────────────────────────────────────┘
```

#### 状态 D：搜索结果页
```
┌────────────────────────────────────┐
│  🔍 [  海边的狗          ] [×]      │
│     找到 20 张  · 用时 0.2秒        │
├────────────────────────────────────┤
│                                    │
│  [图][图][图][图]   ← 瀑布流/网格   │
│  [图][图][图][图]      自适应列数   │
│  [图][图][图][图]                   │
│                                    │
│  鼠标悬浮显示:                      │
│    文件名、拍摄时间、相关度          │
│                                    │
│  [加载更多...] ← 每次追加20张       │
└────────────────────────────────────┘
```

#### 图片查看 Modal（点击图片后弹出）
```
┌──────────────────────────────────────────┐
│  [×]                          [← →导航]  │
│                                          │
│            [ 图片全尺寸显示 ]              │
│                                          │
│  IMG_5678.jpg                            │
│  📅 2023年8月15日 14:23                  │
│  📐 4032 × 3024  |  📦 8.2MB            │
│  [📁 在文件夹中显示]                      │
└──────────────────────────────────────────┘
```

### 7.4 前端技术细节

**搜索防抖**：用户停止输入 300ms 后触发搜索（不是每键一搜）

**进度轮询**：建索引期间，前端每 2 秒 GET `/api/index/status` 更新进度

**图片懒加载**：使用 `IntersectionObserver` 实现，不在视口内的图片不加载

**手机适配**：
- 搜索框占满屏幕宽度
- 图片网格：手机 2列，平板 3列，桌面 4-5列（CSS Grid auto-fill）
- 点击图片全屏查看，支持左右滑动切换

**离线/错误状态**：
- 模型未加载：搜索框下方显示加载状态条，允许用户等待
- 搜索无结果：显示"没有找到相关照片，试试换个描述"

---

## 8. 打包与发布规格

### 8.1 打包策略

**方案**：PyInstaller `--onedir` 模式（不用 `--onefile`，启动更快）

```
dist/
└── PhotoFinder/
    ├── PhotoFinder.exe      (或 PhotoFinder / PhotoFinder.app)
    ├── _internal/           (依赖、运行时)
    │   ├── models/          (ONNX 模型，首次运行时下载到这里)
    │   └── web/             (前端静态文件)
    └── ...
```

**发布包**：
- 将 `PhotoFinder/` 目录压缩为 zip
- GitHub Releases 上传三个平台的 zip

### 8.2 模型下载策略（重要）

```
程序不预打包模型（避免安装包 >300MB）
首次启动时：
  1. 检查 {app_data_dir}/models/ 是否有模型文件
  2. 若缺少：在欢迎页显示"需要下载 AI 模型"提示
  3. 用户点击"下载"后，后台从 Hugging Face Hub 下载
  4. 下载地址（使用镜像加速，国内用户友好）:
     主地址: https://huggingface.co/{model_repo}/resolve/main/{file}
     备用镜像: https://hf-mirror.com/{model_repo}/resolve/main/{file}
  5. 下载进度实时通过 /api/models/download/status 暴露给前端

模型文件存储位置:
  Windows: C:\Users\{name}\AppData\Local\PhotoFinder\models\
  macOS:   /Users/{name}/.photofinder/models/
  Linux:   /home/{name}/.photofinder/models/

使用 config.APP_DATA_DIR 统一管理路径
```

### 8.3 PyInstaller 关键配置

```python
# build_windows.spec 关键配置（其他平台类似）
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('web/', 'web/'),              # 前端静态文件
        ('models/.gitkeep', 'models/') # 创建 models 目录占位
    ],
    hiddenimports=[
        'sqlite_vec',
        'onnxruntime',
        'PIL._tkinter_finder',
        'aiosqlite',
    ],
    ...
)
```

---

## 9. 实现顺序（分阶段）

> **重要：每个阶段必须完全实现并测试通过后，再开始下一阶段。**
> **每个阶段结束后，整个程序必须是可运行的状态。**

### Phase 1：基础框架（目标：程序能启动，浏览器能打开）

1. **`config.py`**
   - 定义 APP_DATA_DIR（跨平台路径）
   - 定义 PORT=7700
   - 定义模型路径常量
   - 定义支持的图片格式列表

2. **`db/database.py`** 和 **`db/migrations.py`**
   - SQLite 连接（aiosqlite）
   - 加载 sqlite-vec 扩展
   - 执行建表语句

3. **`api/app.py`**
   - 创建 FastAPI 实例
   - 挂载 `/web` 静态文件
   - 根路径 `/` 重定向到 `/web/index.html`

4. **`web/index.html`（骨架版）**
   - 简单的 Hello World 页面
   - 确认前端能被访问

5. **`main.py`**
   - 初始化 DB
   - 启动 uvicorn
   - 1.5 秒后打开浏览器

**Phase 1 验收标准**：双击 `python main.py`，浏览器自动打开，看到页面。

---

### Phase 2：扫描与元数据（目标：能导入文件夹，照片元数据存入 DB）

1. **`utils/image_utils.py`**
   - `read_image_safe(path)` → PIL Image（处理 HEIC、RAW、损坏文件）
   - `generate_thumbnail(path, size=256)` → bytes（JPEG）
   - `extract_exif_date(path)` → str | None

2. **`core/scanner.py`**
   - 实现 `scan_folder()` 完整逻辑

3. **`api/routes/library.py`**
   - `POST /api/library/add`（触发后台 scan task）
   - `GET /api/library/folders`

4. **`api/schemas.py`**
   - 定义 AddFolderRequest, FolderResponse

5. **`utils/network_utils.py`**
   - `get_lan_ip()` → str（获取局域网 IP）

6. **`api/routes/system.py`**
   - `GET /api/system/info`
   - `GET /api/system/open-folder`（调用文件夹选择对话框）

**Phase 2 验收标准**：通过 API 添加文件夹后，数据库的 photos 表有记录，has_vector=0。

---

### Phase 3：AI 推理与建索引（目标：能生成向量）

1. **`utils/model_downloader.py`**
   - 实现从 HuggingFace 下载 ONNX 模型
   - 支持断点续传
   - 暴露下载进度

2. **`core/embedder.py`**
   - 实现完整 CLIPEmbedder 类
   - 先用测试图片验证向量输出维度和数值合理性

3. **`core/indexer.py`**
   - 实现 `start_indexing()` 完整流程
   - IndexingState 单例

4. **`api/routes/library.py`** 更新
   - `POST /api/library/add` 扫描完成后自动触发 indexing

5. **`api/routes/system.py`** 更新
   - `GET /api/index/status`
   - `POST /api/models/download`
   - `GET /api/models/download/status`

**Phase 3 验收标准**：添加文件夹后，photo_vectors 表有数据，photos.has_vector=1。

---

### Phase 4：搜索功能（目标：核心功能可用）

1. **`core/searcher.py`**
   - 实现 `search()` 完整逻辑
   - 测试不同查询词的搜索结果质量

2. **`api/routes/search.py`**
   - `GET /api/search`

3. **`api/routes/image.py`**
   - `GET /api/image/{id}`（返回原图）
   - `GET /api/thumbnail/{id}`（返回缩略图 BLOB）

**Phase 4 验收标准**：`curl "http://localhost:7700/api/search?q=dog"` 返回有意义的结果。

---

### Phase 5：完整前端（目标：完整用户体验）

1. **`web/index.html`** 完整实现
   - 5 种状态的 UI（见 7.3 节）
   - 搜索防抖、瀑布流、懒加载
   - 图片查看 Modal

2. **`web/style.css`**
   - 响应式布局
   - 暗色主题

3. **`web/app.js`**
   - 状态机逻辑
   - API 调用封装
   - 进度轮询
   - 二维码展示

4. **`api/routes/system.py`** 更新
   - `GET /api/system/qrcode`（返回 PNG 二维码）

**Phase 5 验收标准**：完整的用户流程可以走通（选文件夹 → 建索引 → 搜索 → 看图）。

---

### Phase 6：打包发布（目标：普通用户能用）

1. **`build/build_windows.spec`** 等三个平台配置文件

2. 测试打包后是否能正常运行

3. **`README.md`**
   - 配截图/GIF
   - 下载链接
   - 常见问题

4. GitHub Actions CI/CD（可选）

---

## 10. 关键代码模式与约定

### 10.1 异步约定
- 所有数据库操作必须是 `async/await`（使用 aiosqlite）
- ONNX 推理是 CPU 密集型，必须放在 `ThreadPoolExecutor` 里：
  ```python
  loop = asyncio.get_event_loop()
  result = await loop.run_in_executor(thread_pool, embedder.encode_image, path)
  ```

### 10.2 错误处理约定
- 单张图片处理失败：记录 error_msg，继续处理下一张，不抛异常
- API 级错误：使用 FastAPI HTTPException，返回标准格式
- 模型未加载：返回 503 + `{"error": "model_loading"}`

### 10.3 sqlite-vec 使用约定
```python
# 向量必须序列化为 bytes 后存入
import struct
vector_bytes = struct.pack(f'{len(vector)}f', *vector)

# 查询时使用 vec_f32() 辅助函数
query = """
    SELECT photo_id, distance
    FROM photo_vectors
    WHERE embedding MATCH vec_f32(:query_vec)
      AND K = :k
    ORDER BY distance
"""
```

### 10.4 路径处理约定
- 所有路径存储为绝对路径字符串
- 跨平台路径使用 `pathlib.Path`，转字符串时用 `str(path)`
- Windows 路径分隔符用 `os.path.normpath()` 统一处理

### 10.5 CORS 配置
```python
# 允许局域网手机访问
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 局域网内全放通
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 10.6 静态文件服务
```python
from fastapi.staticfiles import StaticFiles
# web/ 目录下的文件通过 /web/ 路径访问
app.mount("/web", StaticFiles(directory="web"), name="web")

# 根路径重定向到主页
@app.get("/")
async def root():
    return RedirectResponse(url="/web/index.html")
```

---

## 11. 配置管理

**`config.py`** — 所有配置集中在此文件

```python
import os
import sys
from pathlib import Path

# 判断是否在 PyInstaller 打包环境中
IS_FROZEN = getattr(sys, 'frozen', False)
BASE_DIR = Path(sys._MEIPASS) if IS_FROZEN else Path(__file__).parent

# 用户数据目录（跨平台）
if sys.platform == 'win32':
    APP_DATA_DIR = Path(os.environ['LOCALAPPDATA']) / 'PhotoFinder'
elif sys.platform == 'darwin':
    APP_DATA_DIR = Path.home() / '.photofinder'
else:  # Linux
    APP_DATA_DIR = Path.home() / '.photofinder'

DB_PATH = APP_DATA_DIR / 'photofinder.db'
MODELS_DIR = APP_DATA_DIR / 'models'
CACHE_DIR = APP_DATA_DIR / 'cache'

# 服务器配置
HOST = '0.0.0.0'
PORT = 7700

# 模型配置
CLIP_VISUAL_MODEL = MODELS_DIR / 'clip_visual.onnx'
CLIP_TEXTUAL_MODEL = MODELS_DIR / 'clip_textual.onnx'
MULTILINGUAL_MODEL = MODELS_DIR / 'multilingual_textual.onnx'
VECTOR_DIM = 512

# 索引配置
THUMBNAIL_SIZE = 256
THUMBNAIL_QUALITY = 80
BATCH_SIZE = 16                    # ONNX 推理批次大小
INDEXING_THREADS = 1               # ONNX 推理线程数（不要改，多线程会冲突）

# 搜索配置
DEFAULT_TOP_K = 20
MAX_TOP_K = 100

# 支持的图片格式
SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.gif',
    '.heic', '.heif', '.tiff', '.tif', '.bmp',
    '.cr2', '.nef', '.arw', '.dng',
}

# HuggingFace 模型地址（可替换为镜像）
HF_BASE_URL = 'https://hf-mirror.com'
MODEL_URLS = {
    'clip_visual': f'{HF_BASE_URL}/openai/clip-vit-base-patch32/resolve/main/onnx/visual.onnx',
    'clip_textual': f'{HF_BASE_URL}/openai/clip-vit-base-patch32/resolve/main/onnx/textual.onnx',
    'multilingual': f'{HF_BASE_URL}/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/onnx/model.onnx',
}
```

---

## 12. 错误处理规范

### 12.1 图片读取失败
```python
# 在 embedder.py 和 indexer.py 中：
try:
    vector = embedder.encode_image(path)
except Exception as e:
    # 更新数据库：记录错误，不更新 has_vector
    await db.execute(
        "UPDATE photos SET error_msg=? WHERE path=?",
        [str(e)[:500], path]
    )
    indexing_state.failed += 1
    continue  # 继续处理下一张
```

### 12.2 模型文件损坏
```python
# 加载模型时：
try:
    session = ort.InferenceSession(model_path)
except Exception as e:
    # 删除损坏的模型文件，提示用户重新下载
    os.remove(model_path)
    raise ModelCorruptedError(f"模型文件损坏，请重新下载：{e}")
```

### 12.3 磁盘空间不足
```python
# 开始建索引前检查：
import shutil
free_space = shutil.disk_usage(APP_DATA_DIR).free
if free_space < 500 * 1024 * 1024:  # 少于 500MB 警告
    # 通过 system/info 接口返回警告
```

### 12.4 前端统一错误处理
```javascript
// app.js 中：
async function apiCall(url, options = {}) {
    try {
        const resp = await fetch(url, options);
        if (!resp.ok) {
            const err = await resp.json();
            showError(err.message || '请求失败');
            return null;
        }
        return await resp.json();
    } catch (e) {
        showError('无法连接到本地服务，请确认程序正在运行');
        return null;
    }
}
```

---

## 附录 A：模型选型说明

| 场景 | 推荐模型 | 原因 |
|------|----------|------|
| 纯英文搜索 | `clip-vit-base-patch32`（原版） | 准确率最高，文件最小 |
| 中文/多语言搜索 | `clip-ViT-B-32-multilingual-v1` | 专为多语言优化的文本编码器 |
| 低配机器 | 同上，仅替换文本编码器，图像编码器共用 | 节省内存 |

**关键**：图像编码器（visual）可以在英文和多语言模型间共用，因为图像向量空间是对齐的。只需替换文本编码器（textual）即可实现中文搜索。

## 附录 B：性能预期（i5-10代，16GB RAM，NVMe SSD）

| 操作 | 预期性能 |
|------|----------|
| 首次建索引（5万张） | 3~5 小时（3~5张/秒，CPU） |
| 首次建索引（5万张，RTX 3060） | 15~30 分钟 |
| 文字搜索（5万张已建索引） | < 200ms |
| 增量扫描（新增100张） | < 2 分钟 |
| 程序启动到可搜索 | < 5 秒 |

## 附录 C：GitHub 仓库规范

```
仓库名: photofinder
描述: 🔍 本地 AI 相册搜索 · 用中文找到任何一张照片 · 零配置 · 完全离线
Topics: photo-search, clip, local-ai, privacy, self-hosted, semantic-search
License: MIT（鼓励社区贡献，商业友好）
README 语言: 中文 + 英文双语
```

**README 必须包含**：
1. 一行描述 + Badge（Stars、License、平台支持）
2. GIF 演示（搜索过程）
3. 下载链接（直接下载，不需要任何技术知识）
4. 三步上手（下载 → 打开 → 选文件夹）
5. 常见问题（Mac 安全警告怎么处理、第一次为什么要下载模型等）
6. 系统要求

---

*文档版本：v1.0 | 最后更新：2026-04*
