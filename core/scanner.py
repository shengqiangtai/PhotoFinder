"""Filesystem scanning and database diff detection."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from math import isclose
from pathlib import Path
from typing import Dict, List, Optional

import config
from db.database import Database, database as default_database

_SKIP_NAMES = {"__MACOSX", "@eaDir", "Thumbs.db"}
_MTIME_TOLERANCE = 1e-6


@dataclass
class ScanResult:
    new_files: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    deleted_files: List[str] = field(default_factory=list)
    total_found: int = 0


def _should_skip(name: str) -> bool:
    return (
        name.startswith(".")
        or name in _SKIP_NAMES
        or name.lower() == "thumbs.db"
    )


def _canonicalize_path(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _mtimes_differ(stored_mtime: float, current_mtime: float) -> bool:
    return not isclose(stored_mtime, current_mtime, rel_tol=0.0, abs_tol=_MTIME_TOLERANCE)


def _discover_files(folder_path: Path) -> Dict[str, float]:
    discovered: Dict[str, float] = {}

    def walk(current_path: Path) -> None:
        try:
            with os.scandir(str(current_path)) as entries:
                for entry in entries:
                    name = entry.name
                    if _should_skip(name):
                        continue

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            walk(_canonicalize_path(current_path / name))
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            continue

                        suffix = Path(name).suffix.lower()
                        if suffix not in config.SUPPORTED_EXTENSIONS:
                            continue

                        stat_result = entry.stat(follow_symlinks=False)
                        discovered[str(_canonicalize_path(current_path / name))] = stat_result.st_mtime
                    except OSError:
                        continue
        except OSError:
            return

    walk(folder_path)
    return discovered


async def scan_folder(folder_path: str, database: Optional[Database] = None) -> ScanResult:
    folder_root = _canonicalize_path(Path(folder_path))
    loop = asyncio.get_running_loop()
    discovered = await loop.run_in_executor(None, _discover_files, folder_root)

    known_files: Dict[str, float] = {}
    active_database = database or default_database
    async with active_database.connect() as connection:
        cursor = await connection.execute(
            "SELECT id FROM folders WHERE path = ?",
            (str(folder_root),),
        )
        folder_row = await cursor.fetchone()
        if folder_row is not None:
            cursor = await connection.execute(
                "SELECT path, file_mtime FROM photos WHERE folder_id = ?",
                (folder_row["id"],),
            )
            rows = await cursor.fetchall()
            known_files = {
                str(_canonicalize_path(Path(row["path"]))): float(row["file_mtime"])
                for row in rows
            }

    discovered_paths = set(discovered)
    known_paths = set(known_files)

    return ScanResult(
        new_files=sorted(path for path in discovered_paths - known_paths),
        modified_files=sorted(
            path
            for path in discovered_paths & known_paths
            if _mtimes_differ(known_files[path], discovered[path])
        ),
        deleted_files=sorted(path for path in known_paths - discovered_paths),
        total_found=len(discovered),
    )
