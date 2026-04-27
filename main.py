from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import config


def _preferred_python() -> Optional[Path]:
    if sys.platform == "win32":
        candidate = Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else None


def _ensure_runtime_python() -> None:
    preferred_python = _preferred_python()
    if preferred_python is None:
        return

    venv_root = preferred_python.parent.parent
    current_prefix = Path(sys.prefix).resolve()
    if current_prefix == venv_root.resolve():
        return

    os.execv(str(preferred_python), [str(preferred_python), str(Path(__file__).resolve())])


def _find_available_port(start_port: int) -> int:
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1


def _schedule_browser_open(port: int) -> None:
    def open_browser() -> None:
        webbrowser.open(f"http://127.0.0.1:{port}/")

    timer = threading.Timer(1.5, open_browser)
    timer.daemon = True
    timer.start()


def main() -> None:
    _ensure_runtime_python()

    import uvicorn

    from api.app import create_app
    from db.database import database

    config.ensure_app_directories()
    asyncio.run(database.initialize())

    port = _find_available_port(config.PORT)
    app = create_app()
    _schedule_browser_open(port)

    uvicorn.run(app, host=config.HOST, port=port, log_level="info")


if __name__ == "__main__":
    main()
