# PhotoFinder

PhotoFinder 是本地照片语义检索工具。导入照片文件夹后，应用会在本机建立向量索引，支持英文搜索和中文查询改写，点击结果即可查看原图与缩略图。

## 功能概览

- 文件夹导入与增量扫描
- 图片向量索引：`sqlite-vec` + ONNX Runtime
- 搜索接口：`/api/search`
- 图片接口：`/api/image/{id}`、`/api/thumbnail/{id}`
- 系统信息与二维码：`/api/system/info`、`/api/system/qrcode`
- 前端单页流程：导入 -> 建索引 -> 搜索 -> 查看详情

## 运行要求

- Python 3.10+（推荐 3.12/3.13）
- 支持 `sqlite3` 扩展加载（用于 `sqlite-vec`）
- macOS / Windows / Linux

## 本地启动

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python main.py
```

启动后会自动打开浏览器，默认访问 `http://127.0.0.1:7700/`。端口被占用时会自动递增。

## 测试

```bash
./.venv/bin/python -m unittest discover -v
```

前端控制器测试会调用 `tests/web_app_controller_harness.js`，需要本机安装 Node.js。

## 隐私与本地数据

PhotoFinder 默认把数据库、模型、缩略图缓存和可选 API key 保存在用户本机应用数据目录：

- macOS / Linux: `~/.photofinder/`
- Windows: `%LOCALAPPDATA%\PhotoFinder\`

仓库不会提交照片、缩略图、SQLite 数据库、模型文件、API key、`.env` 文件或构建产物。提交代码前建议运行：

```bash
rg -n --hidden -S "(api[_-]?key|secret|token|password|credential|Authorization|Bearer|/Users/your-name)" .
```

如果你需要在 issue 中提供日志或示例，请先移除个人路径、照片文件名、数据库文件和密钥。

## 打包发布（Phase 6）

安装依赖后执行对应平台的 PyInstaller spec：

```bash
./.venv/bin/pyinstaller build/build_windows.spec
./.venv/bin/pyinstaller build/build_mac.spec
./.venv/bin/pyinstaller build/build_linux.spec
```

构建产物位于 `dist/`，压缩包和安装包应上传到 GitHub Releases，不应提交到 Git 仓库。建议发布说明包含平台、版本号和 SHA256 校验值。

模型文件不预打包进仓库，首次启动由应用下载到用户本机目录。

## 下载链接

正式二进制包请通过 GitHub Releases 发布和下载。当前仓库只跟踪源码、测试、文档和打包脚本。

## 使用流程

1. 左侧抽屉点击 `Add Folder` 选择照片目录。
2. 等待后台建索引，进度会显示在侧栏和详情区域。
3. 在搜索框输入英文或中文描述。
4. 点击结果卡片，在右侧查看详情并打开原图。

## 项目结构

```text
api/        FastAPI 路由
core/       索引、向量、搜索核心逻辑
db/         SQLite 初始化与迁移
utils/      图像处理、下载、网络工具
web/        前端页面、样式、控制器
build/      PyInstaller 三平台 spec
tests/      单元测试与控制器 harness
docs/       设计与启动流程文档
models/     模型占位目录；真实模型不提交
```

## 常见问题

### Q1: 启动时报 `sqlite3 extension loading is unavailable`

当前 Python 运行时未编译扩展加载能力。请更换支持 `enable_load_extension` / `load_extension` 的 Python 环境。

### Q2: 首次搜索较慢

首次会加载 ONNX 模型并构建缓存，后续搜索会明显更快。

### Q3: 中文搜索效果一般

当前实现是中文查询改写到英文视觉词后再检索。可通过扩充词表提升命中效果。

### Q4: 端口 7700 被占用

程序会自动递增端口，例如 7701、7702，以日志中的实际端口为准。
