# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


project_root = Path(SPECPATH).resolve().parent
main_script = project_root / "main.py"
web_dir = project_root / "web"
models_placeholder = project_root / "models" / ".gitkeep"

datas = [
    (str(web_dir), "web"),
]
if models_placeholder.exists():
    datas.append((str(models_placeholder), "models"))

hiddenimports = [
    "sqlite_vec",
    "onnxruntime",
    "aiosqlite",
    "PIL._tkinter_finder",
]
hiddenimports += collect_submodules(
    "numpy",
    filter=lambda name: ".tests" not in name and not name.endswith(".conftest"),
)

datas += collect_data_files("numpy")

binaries = []
binaries += collect_dynamic_libs("numpy")
binaries += collect_dynamic_libs("onnxruntime")
binaries += collect_dynamic_libs("sqlite_vec")

a = Analysis(
    [str(main_script)],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoFinder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PhotoFinder",
)
