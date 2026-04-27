# Phase 1 Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 bootstrap so `python main.py` initializes the app data directory and database, starts an HTTP server, serves a skeleton page, and opens the browser automatically.

**Architecture:** Keep Phase 1 intentionally small: one configuration module for all paths/constants, one database wrapper for aiosqlite lifecycle and migrations, one FastAPI app factory that serves static assets, and one executable `main.py` that picks an available port and runs uvicorn. Make `sqlite-vec` best-effort during bootstrap so missing native support does not block the Phase 1 acceptance path.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, aiosqlite, sqlite-vec, unittest.

---

### Task 1: Establish smoke tests for bootstrap behavior

**Files:**
- Create: `tests/test_phase1.py`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class Phase1SmokeTests(unittest.TestCase):
    def test_config_can_create_runtime_directories(self):
        import config

        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.object(config, "APP_DATA_DIR", Path(tmp_dir)):
                with mock.patch.object(config, "MODELS_DIR", Path(tmp_dir) / "models"):
                    with mock.patch.object(config, "CACHE_DIR", Path(tmp_dir) / "cache"):
                        config.ensure_app_directories()
                        self.assertTrue(Path(tmp_dir).exists())

    def test_database_initialization_creates_core_tables(self):
        import config
        from db.database import Database

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "photofinder.db"
            database = Database(db_path)
            asyncio.run(database.initialize())
            self.assertTrue(db_path.exists())

    def test_root_redirects_to_web_index(self):
        from fastapi.testclient import TestClient
        from api.app import create_app

        client = TestClient(create_app())
        response = client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/web/index.html")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_phase1 -v`
Expected: FAIL with import errors because `config.py`, `db/database.py`, and `api/app.py` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create the Phase 1 modules with only the behavior required by the tests and the architecture spec.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_phase1 -v`
Expected: PASS

- [ ] **Step 5: Verify runtime startup**

Run: `python3 main.py`
Expected: Uvicorn starts on `0.0.0.0:7700` or the next free port, browser open is scheduled, and `/web/index.html` is reachable.
