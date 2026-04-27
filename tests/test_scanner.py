import asyncio
import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from db.database import Database


@dataclass
class _FakeStat:
    st_mtime: float


class _FakeDirEntry:
    def __init__(self, name: str, *, is_dir: bool = False, is_file: bool = False, mtime: float = 0.0) -> None:
        self.name = name
        self._is_dir = is_dir
        self._is_file = is_file
        self._mtime = mtime

    def is_dir(self, follow_symlinks: bool = False) -> bool:
        return self._is_dir

    def is_file(self, follow_symlinks: bool = False) -> bool:
        return self._is_file

    def stat(self, follow_symlinks: bool = False) -> _FakeStat:
        return _FakeStat(self._mtime)


class _FakeScandirContext:
    def __init__(self, entries):
        self._entries = entries

    def __enter__(self):
        return iter(self._entries)

    def __exit__(self, exc_type, exc, tb):
        return False


class ScannerTests(unittest.TestCase):
    def test_scan_folder_detects_new_modified_and_deleted_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            folder_path = tmp_path / "library"
            folder_path.mkdir()

            existing_file = folder_path / "existing.jpg"
            modified_file = folder_path / "modified.png"
            tolerant_file = folder_path / "tolerant.jpg"
            new_file = folder_path / "nested" / "deeper" / "new.webp"
            unsupported_file = folder_path / "ignore.txt"
            hidden_file = folder_path / ".hidden" / "secret.jpg"
            macosx_file = folder_path / "__MACOSX" / "junk.jpg"
            eadir_file = folder_path / "@eaDir" / "junk.png"
            thumbsdb_file = folder_path / "Thumbs.db" / "junk.gif"
            deleted_file = folder_path / "deleted.gif"

            new_file.parent.mkdir(parents=True)
            hidden_file.parent.mkdir(parents=True)
            macosx_file.parent.mkdir(parents=True)
            eadir_file.parent.mkdir(parents=True)
            thumbsdb_file.parent.mkdir(parents=True)

            existing_file.write_bytes(b"existing")
            modified_file.write_bytes(b"modified")
            tolerant_file.write_bytes(b"tolerant")
            new_file.write_bytes(b"new")
            unsupported_file.write_bytes(b"ignore")
            hidden_file.write_bytes(b"hidden")
            macosx_file.write_bytes(b"junk")
            eadir_file.write_bytes(b"junk")
            thumbsdb_file.write_bytes(b"junk")

            os.utime(existing_file, (1_700_000_000, 1_700_000_000))
            os.utime(modified_file, (1_700_000_000, 1_700_000_100))
            os.utime(tolerant_file, (1_700_000_000, 1_700_000_200))
            os.utime(new_file, (1_700_000_000, 1_700_000_200))
            os.utime(hidden_file, (1_700_000_000, 1_700_000_300))

            db_path = tmp_path / "photofinder.db"
            database = Database(db_path=db_path)
            asyncio.run(database.initialize())

            def canonical(path: Path) -> str:
                return str(path.resolve(strict=False))

            async def seed_database() -> None:
                async with database.connect() as connection:
                    cursor = await connection.execute(
                        "INSERT INTO folders (path, added_at, last_scan, photo_count, is_active) VALUES (?, ?, ?, ?, ?)",
                        (
                            canonical(folder_path),
                            datetime.now(timezone.utc).isoformat(),
                            None,
                            0,
                            1,
                        ),
                    )
                    folder_id = cursor.lastrowid

                    await connection.executemany(
                        "INSERT INTO photos (path, filename, folder_id, indexed_at, file_mtime) VALUES (?, ?, ?, ?, ?)",
                        [
                            (
                                canonical(existing_file),
                                existing_file.name,
                                folder_id,
                                datetime.now(timezone.utc).isoformat(),
                                os.path.getmtime(existing_file),
                            ),
                            (
                                canonical(modified_file),
                                modified_file.name,
                                folder_id,
                                datetime.now(timezone.utc).isoformat(),
                                1_700_000_000.0,
                            ),
                            (
                                canonical(tolerant_file),
                                tolerant_file.name,
                                folder_id,
                                datetime.now(timezone.utc).isoformat(),
                                1_700_000_200.0 + 5e-7,
                            ),
                            (
                                canonical(deleted_file),
                                deleted_file.name,
                                folder_id,
                                datetime.now(timezone.utc).isoformat(),
                                1_700_000_000.0,
                            ),
                        ],
                    )
                    await connection.commit()

            asyncio.run(seed_database())

            from core.scanner import ScanResult, scan_folder

            scan_input = os.path.relpath(folder_path, Path.cwd())
            result = asyncio.run(scan_folder(scan_input, database=database))

            self.assertIsInstance(result, ScanResult)
            self.assertEqual(result.total_found, 4)
            self.assertEqual(result.new_files, [canonical(new_file)])
            self.assertEqual(result.modified_files, [canonical(modified_file)])
            self.assertEqual(result.deleted_files, [canonical(deleted_file)])
            self.assertNotIn(canonical(tolerant_file), result.modified_files)
            self.assertNotIn(canonical(hidden_file), result.new_files)
            self.assertNotIn(canonical(macosx_file), result.new_files)
            self.assertNotIn(canonical(eadir_file), result.new_files)
            self.assertNotIn(canonical(thumbsdb_file), result.new_files)

    def test_discover_files_skips_unreadable_entries(self) -> None:
        import core.scanner as scanner

        root_path = Path("/virtual/root")
        blocked_dir = root_path / "blocked"
        expected_file = root_path / "ok.jpg"

        def fake_scandir(path: str):
            if path == str(root_path):
                return _FakeScandirContext(
                    [
                        _FakeDirEntry("blocked", is_dir=True),
                        _FakeDirEntry("ok.jpg", is_file=True, mtime=123.0),
                    ]
                )
            if path == str(blocked_dir):
                raise PermissionError("blocked")
            raise AssertionError("unexpected scandir path")

        with mock.patch.object(scanner.os, "scandir", side_effect=fake_scandir):
            discovered = scanner._discover_files(root_path)

        self.assertEqual(discovered, {str(expected_file.resolve(strict=False)): 123.0})


if __name__ == "__main__":
    unittest.main()
