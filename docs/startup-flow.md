# PhotoFinder 启动流程

本文档描述当前代码实现下，PhotoFinder 从进程启动到前端可交互的完整启动链路。

## 1. 入口层

入口文件是 [main.py](main.py)。

启动命令有两种常见形式：

- 本地开发：`python3 main.py`
- 打包产物：`dist/PhotoFinder/PhotoFinder`

### 1.1 运行时 Python 选择

`main.py` 启动后先执行 `_ensure_runtime_python()`：

1. 检查项目内 `.venv` 是否存在
2. 如果当前进程不是这套虚拟环境里的 Python，就用 `os.execv(...)` 直接切换到 `.venv/bin/python`（Windows 为 `Scripts/python.exe`）
3. 这样后续依赖、`sqlite3` 能力、模型推理环境都尽量统一

### 1.2 目录初始化

随后执行：

```python
config.ensure_app_directories()
```

会确保这些目录存在：

- `APP_DATA_DIR`
- `MODELS_DIR`
- `CACHE_DIR`
- `TOKENIZER_DIR`

当前 `config.py` 的核心路径规则是：

- `BASE_DIR`
  - 普通运行时：项目根目录
  - PyInstaller 打包时：`sys._MEIPASS`
- `WEB_DIR = BASE_DIR / "web"`
- 数据目录：
  - macOS / Linux：`~/.photofinder`
  - Windows：`%LOCALAPPDATA%/PhotoFinder`

## 2. 数据库初始化

`main.py` 在真正创建 Web 应用之前，先执行：

```python
asyncio.run(database.initialize())
```

对应实现见 [db/database.py](db/database.py)。

### 2.1 `database.initialize()`

数据库初始化步骤是：

1. 再次确保应用目录存在
2. 创建数据库文件父目录
3. 打开一个 `aiosqlite` 连接
4. 执行 `_configure_connection(connection)`
5. 根据扩展是否可用，执行 `run_migrations(...)`

### 2.2 连接配置

`_configure_connection()` 会做两件事：

1. 执行 `PRAGMA foreign_keys = ON`
2. 尝试加载 `sqlite-vec`

### 2.3 `sqlite-vec` 加载逻辑

加载逻辑是保守降级模式：

1. 先 `import sqlite_vec`
2. 检查底层 `sqlite3` 连接是否支持：
   - `enable_load_extension`
   - `load_extension`
3. 如果支持，则加载 `sqlite_vec.loadable_path()`
4. 如果任何一步失败，则记录 warning，并退回普通 BLOB 存储表

也就是说：

- 最理想情况：`photo_vectors` 是 `vec0` 虚表
- 降级情况：`photo_vectors` 是普通表，但程序仍能启动

### 2.4 迁移执行

迁移定义见 [db/migrations.py](db/migrations.py)。

`run_migrations()` 会创建：

- `folders`
- `photos`
- `index_jobs`
- `app_config`
- `photo_vectors`

以及这些基础配置项：

- `clip_model`
- `text_model`
- `top_k`
- `thumbnail_size`
- `first_run`

## 3. 端口选择与浏览器打开

数据库初始化完成后，`main.py` 继续执行：

1. `_find_available_port(config.PORT)`
2. `create_app()`
3. `_schedule_browser_open(port)`
4. `uvicorn.run(...)`

### 3.1 端口选择

默认端口来自 [config.py](config.py)：

```python
PORT = 7700
```

`_find_available_port()` 会从 `7700` 开始探测：

- 如果 `127.0.0.1:7700` 没被占用，就使用 `7700`
- 否则递增到 `7701`、`7702`，直到找到空闲端口

### 3.2 自动打开浏览器

`_schedule_browser_open(port)` 会启动一个 `threading.Timer(1.5, ...)`，
在 1.5 秒后打开：

```text
http://127.0.0.1:{port}/
```

## 4. FastAPI 应用创建

应用工厂在 [api/app.py](api/app.py)。

### 4.1 `create_app()`

`create_app()` 会准备这几类运行时对象：

- `database`
- `embedder`
- `model_downloader`
- `indexing_state`

这些对象既会挂到 `app.state`，也会注入到 `lifespan` 生命周期里。

### 4.2 生命周期 `lifespan`

FastAPI 启动时还会再次调用：

```python
await app.state.database.initialize()
```

也就是说数据库初始化实际上发生两次：

1. `main.py` 里显式初始化一次
2. FastAPI lifespan 里再初始化一次

因为迁移是幂等的，所以不会出错，只是重复做一遍初始化检查。

### 4.3 中间件与挂载

应用启动时会配置：

- `CORSMiddleware`
  - `allow_origins=["*"]`
  - 方便局域网设备访问

静态文件挂载：

```python
app.mount("/web", StaticFiles(directory=config.WEB_DIR), name="web")
```

路由挂载：

- `library.router`
- `search.router`
- `image.router`
- `system.router`
- `system.index_router`
- `system.models_router`

根路径 `/` 会重定向到：

```text
/web/index.html
```

健康检查接口是：

```text
/api/health
```

## 5. 前端首屏启动

前端控制器在 [web/app.js](web/app.js)。

页面加载后会执行：

```javascript
document.addEventListener("DOMContentLoaded", () => {
  bootstrap();
});
```

### 5.1 `bootstrap()` 首屏请求

前端首屏并发请求四个接口：

1. `GET /api/system/info`
2. `GET /api/library/folders`
3. `GET /api/index/status`
4. `GET /api/models/download/status`

### 5.2 首屏状态决定

`bootstrap()` 根据返回值更新前端状态：

- `state.systemInfo`
- `state.folders`
- `state.indexStatus`
- `state.modelDownloadStatus`

然后决定主舞台状态：

- `total_photos > 0`：进入 `search` 态
- 否则：进入 `empty` 态

如果 bootstrap 任一关键请求失败：

- 设置 `state.bootstrapError`
- 主舞台显示 fatal 错误态

### 5.3 首屏渲染

`render()` 会同步更新三块区域：

1. 左侧抽屉
2. 中央舞台
3. 右侧详情面板

当前首屏 UI 重点包括：

- 文件夹列表
- 搜索框
- 空库提示 / 搜索结果 / 无结果提示
- 详情面板

## 6. 启动后的后台轮询

如果启动时发现有后台任务仍在进行，前端会启动轮询。

### 6.1 索引轮询

当 `state.indexStatus.is_running` 为真时：

- 每 2 秒轮询 `GET /api/index/status`

### 6.2 模型下载轮询

当 `state.modelDownloadStatus.downloading` 为真时：

- 每 1.5 秒轮询 `GET /api/models/download/status`

### 6.3 轮询保护

当前实现包含两层保护：

1. 不重复注册相同定时器
2. 单次轮询在飞行中时，不接受下一次 tick

如果轮询报错：

- 当前定时器会被清掉
- 错误信息会写入详情面板

## 7. 照片导入流程

当前系统导入照片的基本单位不是“单张图片”，而是“一个文件夹”。
系统会递归扫描该文件夹中的图片文件，写入数据库，然后启动后台索引。

### 7.1 前端导入路径

用户在主界面左侧抽屉里点击 `Add Folder` 后：

1. 前端调用 `GET /api/system/open-folder`
2. 后端通过 `tkinter.filedialog.askdirectory()` 弹出系统文件夹选择器
3. 用户选中一个照片目录
4. 前端拿到目录路径后，调用 `POST /api/library/add`

请求体格式是：

```json
{
  "path": "/Users/example/Pictures"
}
```

### 7.2 后端导入链路

`POST /api/library/add` 收到目录后会执行：

1. 校验路径是否存在、是否是目录
2. 对 `folders` 做插入或复用
3. 启动后台扫描与索引任务
4. 立即返回 `folder_id` 和 `scanning_started`

后台任务随后会继续：

1. 递归扫描目录中的图片文件
2. 提取基础元数据
   - 文件名
   - 宽高
   - 文件大小
   - 修改时间
   - EXIF 拍摄时间
3. 写入 `photos`
4. 生成缩略图
5. 调用图像向量模型写入 `photo_vectors`
6. 将对应图片标记为 `has_vector = 1`

### 7.3 导入完成后的前端状态变化

前端在提交导入后会刷新：

- `GET /api/library/folders`
- `GET /api/index/status`
- `GET /api/system/info`

如果索引正在跑，前端会自动开始索引轮询。

用户随后会看到这些变化：

- 左侧抽屉出现新导入的文件夹
- 中央区域从空库态切换到可搜索状态
- 索引进度条开始推进
- 索引完成后，图片可以被搜索并查看缩略图/原图

### 7.4 直接走 API 的导入方式

如果不经过前端，也可以直接调用接口导入：

```bash
curl -s -X POST http://127.0.0.1:7700/api/library/add \
  -H "Content-Type: application/json" \
  -d '{"path":"/Users/example/Pictures"}'
```

导入后可用这些接口查看状态：

- `GET /api/library/folders`
- `GET /api/index/status`
- `GET /api/system/info`
- `GET /api/search?q=...`

## 8. 搜索链路

用户搜索时：

1. `searchPhotos(query)` 更新当前查询状态
2. 调用 `GET /api/search?q=...`
3. 如果是中文查询，后端可能返回 `rewritten_query`
4. 前端更新：
   - 结果列表
   - 当前选中图片
   - 改写提示文案
   - 右侧详情面板

## 9. 打包后二进制的启动差异

打包后启动入口仍然是 `main.py`，但有两点不同：

### 9.1 静态文件路径

打包环境中：

```python
IS_FROZEN = getattr(sys, "frozen", False)
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WEB_DIR = BASE_DIR / "web"
```

也就是说：

- 本地开发时，静态文件来自项目目录下的 `web/`
- 打包运行时，静态文件来自 PyInstaller 展开的 `_MEIPASS/web`

### 9.2 用户数据目录不变

即使是打包产物，数据库、模型、缓存仍写在用户目录，而不是写进 `dist/`：

- macOS: `~/.photofinder`
- Linux: `~/.photofinder`
- Windows: `%LOCALAPPDATA%/PhotoFinder`

这保证了：

- 升级程序不会丢索引数据
- 模型文件不会被重复打包

## 10. 当前实现里的一个实际特征

当前启动链路里，数据库初始化会发生两次：

1. `main.py -> database.initialize()`
2. `FastAPI lifespan -> database.initialize()`

这是当前代码真实存在的行为。它不会导致功能错误，因为迁移是幂等的，但如果后续要优化启动时间，可以把其中一次去掉。

## 11. 简化时序图

```text
python3 main.py
  -> 切换到 .venv Python
  -> ensure_app_directories()
  -> database.initialize()
      -> 配置 SQLite
      -> 尝试加载 sqlite-vec
      -> 执行 migrations
  -> 找可用端口
  -> create_app()
      -> 创建 FastAPI
      -> 配置 lifespan / CORS / 静态文件 / 路由
  -> 1.5 秒后打开浏览器
  -> uvicorn.run()
      -> lifespan 再次 database.initialize()
      -> 提供 /、/web/*、/api/*

浏览器打开 /
  -> 307 到 /web/index.html
  -> 加载 web/app.js
  -> DOMContentLoaded -> bootstrap()
      -> GET /api/system/info
      -> GET /api/library/folders
      -> GET /api/index/status
      -> GET /api/models/download/status
  -> 渲染左抽屉 / 中央舞台 / 右侧详情
  -> 如有任务则启动轮询
```
